"""Rentang hafalan dan penilaian append-only (tahap 1: ditulis berdampingan dengan data lama).

Aturan: data rentang, riwayat penilaian, dan jadwal tidak digabung. Penggabungan hanya untuk tampilan.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services import murojaah


async def record_evaluation(
    db: AsyncSession,
    sub: models.Submission,
    *,
    evaluator_id: uuid.UUID | None,
    evaluator_role: str,
    result: str,
    notes: str | None,
    rubric_scores: dict | None,
    source: str = "live",
    ayah_start: int | None = None,
    ayah_end: int | None = None,
) -> models.Evaluation:
    ev = models.Evaluation(
        submission_id=sub.id,
        member_id=sub.member_id,
        evaluator_id=evaluator_id,
        evaluator_role=evaluator_role,
        result=result,
        notes=notes,
        rubric_scores=rubric_scores,
        source=source,
        ayah_start=ayah_start,
        ayah_end=ayah_end,
    )
    db.add(ev)
    await db.flush()
    return ev


async def record_passed_range(
    db: AsyncSession, sub: models.Submission, *, source: str = "evaluation",
    ayah_start: int | None = None, ayah_end: int | None = None, status: str = "passed", note: str | None = None,
) -> models.MemorizedRange | None:
    """Catat rentang lulus dari setoran ziyadah. Idempoten per setoran dan rentang.

    Tanpa ayah_start/ayah_end dipakai seluruh rentang setoran; dengan keduanya hanya bagian yang lulus.
    """
    if sub.surah_id is None or sub.ayah_start is None:
        return None
    a = ayah_start if ayah_start is not None else sub.ayah_start
    b = ayah_end if ayah_end is not None else (sub.ayah_end if sub.ayah_end is not None else sub.ayah_start)
    existing = (
        await db.execute(
            select(models.MemorizedRange).where(
                models.MemorizedRange.submission_id == sub.id,
                models.MemorizedRange.ayah_start == a,
                models.MemorizedRange.ayah_end == b,
            )
        )
    ).scalars().first()
    if existing:
        return existing
    rng = models.MemorizedRange(
        member_id=sub.member_id,
        surah_id=sub.surah_id,
        ayah_start=a,
        ayah_end=b,
        submission_id=sub.id,
        source=source,
        status=status,
        note=note,
    )
    db.add(rng)
    await db.flush()
    return rng


def sub_bounds(sub: models.Submission) -> tuple[int, int] | None:
    if sub.ayah_start is None:
        return None
    return sub.ayah_start, (sub.ayah_end if sub.ayah_end is not None else sub.ayah_start)


def active_parts(evals: list[models.Evaluation]) -> list[models.Evaluation]:
    """Penilaian aktif per rentang: yang belum dikoreksi baris lain. Hanya baris berentang yang dihitung."""
    corrected = {e.corrects_id for e in evals if e.corrects_id}
    return [e for e in evals if e.id not in corrected and e.ayah_start is not None]


def evaluated_ayahs(evals: list[models.Evaluation]) -> set[int]:
    out: set[int] = set()
    for e in active_parts(evals):
        out.update(range(e.ayah_start, (e.ayah_end or e.ayah_start) + 1))
    return out


def overall_status(sub: models.Submission, evals: list[models.Evaluation]) -> models.SubmissionStatus | None:
    """Status setoran dari penilaian aktif: None bila masih ada ayat yang belum dinilai."""
    b = sub_bounds(sub)
    parts = active_parts(evals)
    if b is None or not parts:
        return None
    if evaluated_ayahs(evals) < set(range(b[0], b[1] + 1)):
        return None
    results = {e.result for e in parts}
    if results == {"passed"}:
        return models.SubmissionStatus.passed
    return models.SubmissionStatus.needs_retry if "needs_retry" in results else models.SubmissionStatus.not_fluent


def range_status(sub: models.Submission, evals: list[models.Evaluation]) -> list[dict]:
    """Status per rentang setoran: bagian yang sudah dinilai (hasil aktif) dan sisa yang masih menunggu."""
    b = sub_bounds(sub)
    if b is None:
        return []
    parts = sorted(active_parts(evals), key=lambda e: e.ayah_start)
    if not parts:  # penilaian lama tanpa rentang: berlaku untuk seluruh setoran
        return [{"ayah_start": b[0], "ayah_end": b[1], "status": sub.status.value if sub.status.value != "pending_ai" else "pending_eval", "evaluation_id": None}]
    out: list[dict] = []
    cur = b[0]
    for e in parts:
        if e.ayah_start > cur:
            out.append({"ayah_start": cur, "ayah_end": e.ayah_start - 1, "status": "pending_eval", "evaluation_id": None})
        out.append({"ayah_start": e.ayah_start, "ayah_end": e.ayah_end, "status": e.result, "evaluation_id": e.id})
        cur = e.ayah_end + 1
    if cur <= b[1]:
        out.append({"ayah_start": cur, "ayah_end": b[1], "status": "pending_eval", "evaluation_id": None})
    return out


async def current_assignment(db: AsyncSession, member_id: uuid.UUID) -> models.EvaluatorAssignment | None:
    return (
        await db.execute(
            select(models.EvaluatorAssignment).where(
                models.EvaluatorAssignment.member_id == member_id, models.EvaluatorAssignment.ended_at.is_(None)
            )
        )
    ).scalar_one_or_none()


async def covered_ayahs(db: AsyncSession, member_id: uuid.UUID, surah_id: int) -> set[int]:
    """Ayat yang tertutup rentang lulus (untuk tampilan dan status surat). Rentang tidak diubah."""
    rows = (
        await db.execute(
            select(models.MemorizedRange).where(
                models.MemorizedRange.member_id == member_id,
                models.MemorizedRange.surah_id == surah_id,
                models.MemorizedRange.status == "passed",
            )
        )
    ).scalars().all()
    out: set[int] = set()
    for r in rows:
        out.update(range(r.ayah_start, r.ayah_end + 1))
    return out


def merged_view(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Gabungan hanya untuk tampilan: 1-20 dan 21-40 tampil 1-40. Data aslinya tidak disentuh."""
    out: list[list[int]] = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _has_evaluation_proof(s: models.Submission) -> bool:
    """Bukti sah: setoran bertanda lulus DAN tercatat waktu penilaiannya."""
    return s.status == models.SubmissionStatus.passed and s.evaluated_at is not None


async def _represented_ayahs(db: AsyncSession, member_id: uuid.UUID, surah_id: int) -> set[int]:
    """Ayat yang sudah punya rentang dalam status apa pun (kecuali superseded/rejected tetap dianggap sudah diputuskan)."""
    rows = (
        await db.execute(
            select(models.MemorizedRange).where(models.MemorizedRange.member_id == member_id, models.MemorizedRange.surah_id == surah_id)
        )
    ).scalars().all()
    out: set[int] = set()
    for r in rows:
        out.update(range(r.ayah_start, r.ayah_end + 1))
    return out


async def _unverified_gaps(
    db: AsyncSession, member_id: uuid.UUID, surah_id: int, upto: int, note: str,
) -> int:
    covered = await _represented_ayahs(db, member_id, surah_id)
    missing = [a for a in range(1, upto + 1) if a not in covered]
    n = 0
    for a, b in merged_view([(x, x) for x in missing]):
        db.add(models.MemorizedRange(member_id=member_id, surah_id=surah_id, ayah_start=a, ayah_end=b, source="migration", status="unverified", note=note))
        n += 1
    return n


async def reclassify_unverified(db: AsyncSession, member_id: uuid.UUID) -> int:
    """Rentang hasil migrasi yang berstatus passed tetapi tanpa bukti penilaian lulus diturunkan ke unverified.

    Jadwal murajaah terbuka untuk rentang itu dihentikan sampai terverifikasi. Rentang dari evaluasi nyata tidak disentuh.
    """
    rows = (
        await db.execute(
            select(models.MemorizedRange).where(
                models.MemorizedRange.member_id == member_id,
                models.MemorizedRange.source == "migration",
                models.MemorizedRange.status == "passed",
            )
        )
    ).scalars().all()
    n = 0
    for r in rows:
        sub = await db.get(models.Submission, r.submission_id) if r.submission_id else None
        if sub is not None and _has_evaluation_proof(sub):
            continue
        r.status = "unverified"
        r.note = r.note or "Hasil migrasi tanpa bukti penilaian lulus; perlu verifikasi manual"
        for it in (
            await db.execute(select(models.MurojaahItem).where(models.MurojaahItem.range_id == r.id, models.MurojaahItem.completed.is_(False)))
        ).scalars().all():
            it.completed = True
        n += 1
    await db.flush()
    return n


async def backfill_member(db: AsyncSession, member_id: uuid.UUID) -> dict:
    """Isi tabel baru dari data lama untuk satu anak. Aman dijalankan berulang.

    Hanya data dengan bukti penilaian lulus yang menjadi `passed`. Posisi ayat (current_ayah) dan status surat tanpa
    riwayat setoran tidak membuktikan kelulusan, jadi menjadi rentang `unverified` untuk diverifikasi manual.
    """
    made = {"ranges": 0, "evaluations": 0, "assignments": 0}

    def bump(key: str, n: int = 1):
        if n:
            made[key] = made.get(key, 0) + n

    bump("reclassified", await reclassify_unverified(db, member_id))
    subs = (
        await db.execute(select(models.Submission).where(models.Submission.member_id == member_id))
    ).scalars().all()
    for s in subs:
        if s.evaluated_at is not None and s.status in (
            models.SubmissionStatus.passed,
            models.SubmissionStatus.needs_retry,
            models.SubmissionStatus.not_fluent,
        ):
            has = (
                await db.execute(select(models.Evaluation.id).where(models.Evaluation.submission_id == s.id))
            ).first()
            if not has:
                await record_evaluation(
                    db, s, evaluator_id=None, evaluator_role="unknown", result=s.status.value,
                    notes=s.evaluator_notes, rubric_scores=s.rubric_scores, source="migration",
                )
                made["evaluations"] += 1
        if (
            s.context == models.SubmissionContext.ziyadah
            and s.status == models.SubmissionStatus.passed
            and s.surah_id is not None
        ):
            before = (
                await db.execute(select(models.MemorizedRange.id).where(models.MemorizedRange.submission_id == s.id))
            ).first()
            if not before:
                if _has_evaluation_proof(s):
                    await record_passed_range(db, s, source="migration")
                else:
                    await record_passed_range(
                        db, s, source="migration", status="unverified",
                        note="Setoran bertanda lulus tetapi tanpa catatan waktu penilaian; perlu verifikasi manual",
                    )
                made["ranges"] += 1

    # Surat lulus / posisi ayat tanpa bukti penilaian: bukan bukti kelulusan -> unverified.
    progs = (
        await db.execute(select(models.MemberSurahProgress).where(models.MemberSurahProgress.member_id == member_id))
    ).scalars().all()
    for p in progs:
        surah = await db.get(models.Surah, p.surah_id)
        if not surah:
            continue
        if p.status == models.SurahProgressStatus.passed:
            bump("unverified", await _unverified_gaps(db, member_id, p.surah_id, surah.ayah_count, "Surat berstatus lulus di data lama tanpa riwayat penilaian; perlu verifikasi manual"))
        elif p.current_ayah and p.current_ayah > 1:
            bump(
                "unverified",
                await _unverified_gaps(
                    db, member_id, p.surah_id, min(p.current_ayah - 1, surah.ayah_count),
                    f"Posisi ayat {p.current_ayah} di data lama tanpa riwayat penilaian lulus untuk ayat sebelumnya; perlu verifikasi manual",
                ),
            )
    await db.flush()

    # Progres surat tidak boleh lebih maju dari bukti: surat/posisi yang bertumpu pada rentang unverified diturunkan.
    for p in progs:
        unv = (
            await db.execute(
                select(models.MemorizedRange.ayah_start).where(
                    models.MemorizedRange.member_id == member_id,
                    models.MemorizedRange.surah_id == p.surah_id,
                    models.MemorizedRange.status == "unverified",
                )
            )
        ).scalars().all()
        if not unv:
            continue
        changed = False
        if p.current_ayah > min(unv):
            p.current_ayah, changed = min(unv), True
        if p.status == models.SurahProgressStatus.passed:
            p.status, changed = models.SurahProgressStatus.in_progress, True
        if changed:
            bump("progress_reset")
    await db.flush()

    # Penugasan penilai pertama dari tautan guru aktif, selain itu orang tua.
    if not await current_assignment(db, member_id):
        link = (
            await db.execute(
                select(models.TeacherLink).where(
                    models.TeacherLink.member_id == member_id, models.TeacherLink.status == "active"
                )
            )
        ).scalars().first()
        db.add(
            models.EvaluatorAssignment(
                member_id=member_id,
                evaluator_id=link.teacher_id if link else None,
                evaluator_role="teacher" if link else "parent",
                reason="migrasi",
            )
        )
        made["assignments"] += 1
    # Jadwal murajaah: item lama dinormalkan jadi rentang, hanya rentang lulus yang diberi jadwal.
    await murojaah.normalize_legacy_items(db, member_id)
    for r in (
        await db.execute(
            select(models.MemorizedRange).where(models.MemorizedRange.member_id == member_id, models.MemorizedRange.status == "passed")
        )
    ).scalars().all():
        if await murojaah.schedule_for_range(db, r):
            bump("schedules")
    await db.flush()
    return made


async def backfill_all(db: AsyncSession) -> dict:
    total = {"ranges": 0, "evaluations": 0, "assignments": 0}
    ids = (await db.execute(select(models.Member.id))).scalars().all()
    for mid in ids:
        r = await backfill_member(db, mid)
        for k, v in r.items():
            total[k] = total.get(k, 0) + v
    return total
