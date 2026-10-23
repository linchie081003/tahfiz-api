"""Sesi 3: penguatan sampel ayat dari hafalan baru.

Dua jenis aktivitas dipisah: penguatan latihan (boleh sambil menunggu penilaian, tanpa evaluasi baru) dan
penilaian formal (satu setoran, satu penilaian aktif). Hasil Sesi 3 tidak pernah meluluskan hafalan.
"""

import random
import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services import tanda, teaching
from app.services.surah_translit import surah_name

SAMPLE_SIZE = 3  # jumlah ayat penguatan per sesi
RECENT_DAYS = 7
OFFER_MIN_MARK_DAYS = 2
OFFER_MIN_FORGOT = 2
CHILD_REQUEST_DAILY_CAP = 1


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def responsible(db: AsyncSession, member_id: uuid.UUID) -> tuple[str, uuid.UUID | None]:
    """Satu aturan penanggung jawab: guru dengan tautan aktif, selain itu orang tua."""
    link = await teaching.active_link(db, member_id)
    if link:
        return "teacher", link.teacher_id
    member = await db.get(models.Member, member_id)
    from app.services import corrections

    if member and not await corrections.parent_may_evaluate(db, member.family_id):
        return "none", None  # tanpa guru dan kewenangan orang tua dimatikan: setoran tetap Pending Evaluation
    return "parent", None


async def sources(db: AsyncSession, member_id: uuid.UUID) -> list[tuple[models.Submission, str]]:
    """Setoran ziyadah yang menunggu penilaian, lulus, atau perlu perbaikan dalam 7 hari terakhir."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
    rows = (
        await db.execute(
            select(models.Submission)
            .where(
                models.Submission.member_id == member_id,
                models.Submission.context == models.SubmissionContext.ziyadah,
                models.Submission.surah_id.is_not(None),
                models.Submission.ayah_start.is_not(None),
            )
            .order_by(models.Submission.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    out: list[tuple[models.Submission, str]] = []
    for s in rows:
        when = _aware(s.evaluated_at) or _aware(s.created_at)
        if s.status == models.SubmissionStatus.pending_eval:
            out.append((s, "pending"))
        elif s.status == models.SubmissionStatus.passed and when and when >= cutoff:
            out.append((s, "passed"))
        elif s.status in (models.SubmissionStatus.needs_retry, models.SubmissionStatus.not_fluent) and when and when >= cutoff:
            out.append((s, "remedial"))
    return out


def _ayahs(s: models.Submission) -> list[int]:
    end = s.ayah_end if s.ayah_end is not None else s.ayah_start
    return list(range(s.ayah_start, end + 1))


async def build(db: AsyncSession, member_id: uuid.UUID, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    srcs = await sources(db, member_id)
    marked = {(m.surah_id, m.ayah_number) for m in await tanda.active_marks(db, member_id)}
    order = {"remedial": 0, "pending": 1, "passed": 2}
    cands = []
    for s, state in srcs:
        for n in _ayahs(s):
            cands.append({"submission_id": s.id, "surah_id": s.surah_id, "ayah_number": n, "state": state, "marked": (s.surah_id, n) in marked})
    rng.shuffle(cands)
    cands.sort(key=lambda c: (not c["marked"], order[c["state"]]))  # bertanda, lalu remediasi, lalu menunggu, lalu lulus
    seen: set[tuple[int, int]] = set()
    sample = []
    for c in cands:
        key = (c["surah_id"], c["ayah_number"])
        if key in seen:
            continue
        seen.add(key)
        sample.append({**c, "surah_name": surah_name(c["surah_id"], "")})
        if len(sample) >= SAMPLE_SIZE:
            break
    sample.sort(key=lambda c: (c["surah_id"], c["ayah_number"]))
    return {"active": bool(srcs), "sample": sample, "offer": await offer(db, member_id, srcs)}


async def _open_request(db: AsyncSession, submission_id: uuid.UUID) -> models.EvaluationRequest | None:
    return (
        await db.execute(
            select(models.EvaluationRequest).where(models.EvaluationRequest.submission_id == submission_id, models.EvaluationRequest.status == "open")
        )
    ).scalars().first()


async def _child_requests_today(db: AsyncSession, member_id: uuid.UUID) -> int:
    start = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)
    return (
        await db.execute(
            select(func.count()).select_from(models.EvaluationRequest).where(
                models.EvaluationRequest.member_id == member_id, models.EvaluationRequest.reason == "child_mark",
                models.EvaluationRequest.created_at >= start,
            )
        )
    ).scalar_one()


async def offer(db: AsyncSession, member_id: uuid.UUID, srcs: list[tuple[models.Submission, str]] | None = None) -> dict | None:
    """Tawaran cek dari tanda: maksimal satu per hari, hanya untuk tanda aktif lebih dari dua hari atau dua kali lupa."""
    if await _child_requests_today(db, member_id) >= CHILD_REQUEST_DAILY_CAP:
        return None
    srcs = srcs if srcs is not None else await sources(db, member_id)
    now = datetime.now(timezone.utc)
    for m in await tanda.active_marks(db, member_id):
        if m.created_by_role != "child":
            continue
        sub = next((s for s, _ in srcs if s.surah_id == m.surah_id and m.ayah_number in _ayahs(s)), None)
        if not sub or await _open_request(db, sub.id):
            continue
        old = (now - _aware(m.created_at)).days >= OFFER_MIN_MARK_DAYS if m.created_at else False
        forgot = (
            await db.execute(
                select(func.count()).select_from(models.PracticeAttempt).where(
                    models.PracticeAttempt.member_id == member_id, models.PracticeAttempt.surah_id == m.surah_id,
                    models.PracticeAttempt.ayah_number == m.ayah_number, models.PracticeAttempt.result == "lupa",
                )
            )
        ).scalar_one()
        if old or forgot >= OFFER_MIN_FORGOT:
            return {"submission_id": sub.id, "surah_id": m.surah_id, "ayah_number": m.ayah_number, "reason": "tanda_lama" if old else "lupa_berulang"}
    return None


async def create_request(
    db: AsyncSession, member: models.Member, submission_id: uuid.UUID, reason: str, *,
    ayah_number: int | None = None, created_by: uuid.UUID | None = None,
) -> models.EvaluationRequest:
    sub = await db.get(models.Submission, submission_id)
    if not sub or sub.member_id != member.id or sub.surah_id is None:
        raise HTTPException(404, "Setoran tidak ditemukan")
    existing = await _open_request(db, sub.id)
    if existing:
        return existing  # satu permintaan terbuka per setoran, tidak ada penilaian aktif ganda
    if reason == "child_mark":
        if ayah_number is None or ayah_number not in _ayahs(sub):
            raise HTTPException(422, "Ayat tidak ada dalam setoran ini")
        marks = await tanda.active_marks(db, member.id, sub.surah_id)
        if not any(m.ayah_number == ayah_number for m in marks):
            raise HTTPException(422, "Tandai ayat sulit dulu sebelum meminta dicek")
        if await _child_requests_today(db, member.id) >= CHILD_REQUEST_DAILY_CAP:
            raise HTTPException(409, "Permintaan cek hari ini sudah dipakai")
    role, rid = await responsible(db, member.id)
    req = models.EvaluationRequest(
        member_id=member.id, submission_id=sub.id, surah_id=sub.surah_id, ayah_number=ayah_number, reason=reason,
        assignee_role=role, assignee_id=rid, created_by=created_by,
    )
    db.add(req)
    await db.flush()
    return req


async def resolve(db: AsyncSession, req: models.EvaluationRequest, by_id: uuid.UUID, by_role: str, note: str | None) -> None:
    if req.status != "open":
        return
    req.status, req.note = "done", note
    req.resolved_at, req.resolved_by, req.resolved_by_role = datetime.now(timezone.utc), by_id, by_role
    await db.flush()
