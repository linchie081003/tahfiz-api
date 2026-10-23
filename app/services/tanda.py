"""Tanda sulit (ayat/kata), hasil latihan per ayat, dan sambung ayat.

Tiga data terpisah: tanda, kelulusan, dan jadwal murajaah. Tanda hanya memengaruhi prioritas latihan.
"""

import random
import uuid
from datetime import date, datetime, time, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services import gamification, hafalan_ranges

RESULTS = ("lancar", "ragu", "lupa")
CLEAR_STREAK = 3  # tiga lancar berturut-turut menghilangkan tanda buatan anak
SAMBUNG_DAILY_REWARD_CAP = 3


async def active_marks(db: AsyncSession, member_id: uuid.UUID, surah_id: int | None = None) -> list[models.DifficultMark]:
    q = select(models.DifficultMark).where(models.DifficultMark.member_id == member_id, models.DifficultMark.status == "active")
    if surah_id is not None:
        q = q.where(models.DifficultMark.surah_id == surah_id)
    return list((await db.execute(q.order_by(models.DifficultMark.surah_id, models.DifficultMark.ayah_number))).scalars().all())


async def create_mark(
    db: AsyncSession, member_id: uuid.UUID, surah_id: int, ayah_number: int, *,
    word_start: int | None = None, word_end: int | None = None, reason: str | None = None,
    source: str = "manual", role: str = "child",
) -> models.DifficultMark:
    surah = await db.get(models.Surah, surah_id)
    if not surah or not 1 <= ayah_number <= surah.ayah_count:
        raise HTTPException(422, "Ayat tidak valid")
    word_text = None
    if word_start is not None:
        if word_end is None:
            word_end = word_start
        ayah = (await db.execute(select(models.Ayah).where(models.Ayah.surah_id == surah_id, models.Ayah.ayah_number == ayah_number))).scalar_one_or_none()
        words = (ayah.text_uthmani if ayah else "").split()
        if not words or word_start < 0 or word_end < word_start or word_end >= len(words):
            raise HTTPException(422, "Posisi kata tidak valid")
        word_text = " ".join(words[word_start : word_end + 1])
    existing = (
        await db.execute(
            select(models.DifficultMark).where(
                models.DifficultMark.member_id == member_id, models.DifficultMark.surah_id == surah_id,
                models.DifficultMark.ayah_number == ayah_number, models.DifficultMark.status == "active",
                models.DifficultMark.word_start.is_(None) if word_start is None else models.DifficultMark.word_start == word_start,
                models.DifficultMark.word_end.is_(None) if word_start is None else models.DifficultMark.word_end == word_end,
            )
        )
    ).scalars().first()
    if existing:
        return existing
    mark = models.DifficultMark(
        member_id=member_id, surah_id=surah_id, ayah_number=ayah_number, word_start=word_start, word_end=word_end,
        word_text=word_text, source=source, created_by_role=role, reason=reason,
    )
    db.add(mark)
    await db.flush()
    return mark


async def deactivate_mark(db: AsyncSession, member_id: uuid.UUID, mark_id: uuid.UUID) -> models.DifficultMark:
    mark = await db.get(models.DifficultMark, mark_id)
    if not mark or mark.member_id != member_id:
        raise HTTPException(404, "Tanda tidak ditemukan")
    if mark.created_by_role != "child":
        raise HTTPException(403, "Tanda dari penilai tidak bisa dihapus anak")
    mark.status, mark.inactive_reason = "inactive", "dihapus_anak"
    await db.flush()
    return mark


async def record_results(
    db: AsyncSession, member_id: uuid.UUID, kind: str, results: list[tuple[int, int, str]]
) -> dict:
    """Catat hasil per ayat. Satu hasil per ayat per panggilan, supaya 'tiga lancar' berasal dari percobaan berbeda."""
    latest: dict[tuple[int, int], str] = {}
    for sid, no, res in results:
        if res not in RESULTS:
            raise HTTPException(422, "Hasil harus lancar, ragu, atau lupa")
        latest[(sid, no)] = res
    created = cleared = 0
    for (sid, no), res in latest.items():
        surah = await db.get(models.Surah, sid)
        if not surah or not 1 <= no <= surah.ayah_count:
            raise HTTPException(422, "Ayat tidak valid")
        db.add(models.PracticeAttempt(member_id=member_id, kind=kind, surah_id=sid, ayah_number=no, result=res))
        c, k = await _apply(db, member_id, sid, no, res)
        created += c
        cleared += k
    await db.flush()
    return {"recorded": len(latest), "marks_created": created, "marks_cleared": cleared}


async def _apply(db: AsyncSession, member_id: uuid.UUID, sid: int, no: int, res: str) -> tuple[int, int]:
    marks = (
        await db.execute(
            select(models.DifficultMark).where(
                models.DifficultMark.member_id == member_id, models.DifficultMark.surah_id == sid,
                models.DifficultMark.ayah_number == no, models.DifficultMark.status == "active",
                models.DifficultMark.word_start.is_(None),  # tanda kata hanya berubah lewat pengujian spesifik
            )
        )
    ).scalars().all()
    created = cleared = 0
    for m in marks:
        if res == "lancar":
            m.streak += 1
            if m.streak >= CLEAR_STREAK and m.created_by_role == "child":
                m.status, m.inactive_reason = "inactive", "lancar_3x"
                cleared += 1
        else:
            m.streak = 0
    if res == "lupa" and not marks:
        await create_mark(db, member_id, sid, no, source="auto", reason="Lupa saat latihan")
        created += 1
    return created, cleared


# ---- sambung ayat ----------------------------------------------------------------------------

async def build_questions(db: AsyncSession, member: models.Member, rng: random.Random | None = None) -> list[dict]:
    """Soal dari hafalan lulus. Tidak ada soal untuk ayat terakhir dalam rentang. PAUD: 2 soal pilihan ganda, lainnya 3 soal."""
    rng = rng or random.Random()
    paud = member.age_mode == models.AgeMode.paud
    want = 2 if paud else 3
    surah_ids = (
        await db.execute(select(models.MemorizedRange.surah_id).where(models.MemorizedRange.member_id == member.id, models.MemorizedRange.status == "passed").distinct())
    ).scalars().all()
    covered: dict[int, set[int]] = {}
    for sid in surah_ids:
        covered[sid] = await hafalan_ranges.covered_ayahs(db, member.id, sid)
    pairs = [(sid, k) for sid, cov in covered.items() for k in sorted(cov) if k + 1 in cov]
    if not pairs:
        return []
    marked = {(m.surah_id, m.ayah_number - 1) for m in await active_marks(db, member.id)}
    first = [p for p in pairs if p in marked]  # ayat bertanda didahulukan
    rest = [p for p in pairs if p not in marked]
    rng.shuffle(first)
    rng.shuffle(rest)
    picked = (first + rest)[:want]
    out = []
    for sid, k in picked:
        surah = await db.get(models.Surah, sid)
        q = {"surah_id": sid, "surah_name": surah.name_id if surah else "", "ayah_from": k, "mode": "ingat", "options": None}
        if paud:
            pool = [(sid, n) for n in covered[sid] if n not in (k + 1, k) and n != k + 1]
            others = [(s2, n) for s2, cov in covered.items() if s2 != sid for n in cov]
            rng.shuffle(pool)
            rng.shuffle(others)
            distract = (pool + others)[:2]
            if len(distract) == 2:
                opts = [{"surah_id": sid, "ayah_number": k + 1}] + [{"surah_id": s, "ayah_number": n} for s, n in distract]
                rng.shuffle(opts)
                q["mode"], q["options"] = "pilihan", opts
        out.append(q)
    return out


async def answer_sambung(
    db: AsyncSession, member_id: uuid.UUID, surah_id: int, ayah_from: int, mode: str,
    result: str | None, chosen_surah_id: int | None, chosen_ayah: int | None,
) -> dict:
    surah = await db.get(models.Surah, surah_id)
    if not surah or not 1 <= ayah_from < surah.ayah_count:
        raise HTTPException(422, "Soal tidak valid")
    correct: bool | None = None
    if mode == "pilihan":
        if chosen_surah_id is None or chosen_ayah is None:
            raise HTTPException(422, "Pilihan jawaban diperlukan")
        correct = chosen_surah_id == surah_id and chosen_ayah == ayah_from + 1
        result = "lancar" if correct else "lupa"
    elif mode == "ingat":
        if result not in RESULTS:
            raise HTTPException(422, "Hasil harus lancar, ragu, atau lupa")
    else:
        raise HTTPException(422, "Mode tidak dikenal")
    start = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)
    rewarded_today = (
        await db.execute(
            select(func.count()).select_from(models.ConnectAttempt).where(
                models.ConnectAttempt.member_id == member_id, models.ConnectAttempt.rewarded.is_(True), models.ConnectAttempt.created_at >= start
            )
        )
    ).scalar_one()
    # XP 'benar' hanya untuk pilihan ganda; mode ingat dinilai anak sendiri, jadi XP penyelesaian dengan batas harian.
    eligible = (mode == "pilihan" and correct) or mode == "ingat"
    reward = eligible and rewarded_today < SAMBUNG_DAILY_REWARD_CAP
    db.add(models.ConnectAttempt(member_id=member_id, surah_id=surah_id, ayah_from=ayah_from, mode=mode, result=result, correct=correct, rewarded=reward))
    if reward:
        await gamification.add_xp(db, member_id, "sambung_benar" if mode == "pilihan" else "sambung_selesai")
    db.add(models.PracticeAttempt(member_id=member_id, kind="sambung", surah_id=surah_id, ayah_number=ayah_from + 1, result=result))
    await _apply(db, member_id, surah_id, ayah_from + 1, result)
    await db.flush()
    return {"correct": correct, "result": result, "rewarded": reward}
