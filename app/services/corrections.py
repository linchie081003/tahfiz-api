"""Koreksi penilaian dan kewenangan menilai.

Penilaian tidak pernah ditimpa: koreksi menambah baris baru (corrects_id) lengkap dengan penilai, waktu, dan alasan.
Status rentang dan jadwal murajaah dihitung ulang dari penilaian aktif. XP yang sudah diberikan tidak ditarik.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.models import SubmissionContext, SubmissionStatus, SurahProgressStatus, TahsinStatus
from app.services import gamification, hafalan_ranges, murojaah, sesi3

JUDGED = (SubmissionStatus.passed, SubmissionStatus.needs_retry, SubmissionStatus.not_fluent)


async def parent_may_evaluate(db: AsyncSession, family_id: uuid.UUID) -> bool:
    row = (await db.execute(select(models.FamilySettings).where(models.FamilySettings.family_id == family_id))).scalar_one_or_none()
    return True if row is None else bool(row.parent_can_evaluate)


async def history(db: AsyncSession, submission_id: uuid.UUID) -> list[models.Evaluation]:
    """Riwayat berurutan menurut rantai koreksi (asli dulu), bukan menurut jam, supaya stabil walau waktu sama."""
    rows = list((await db.execute(select(models.Evaluation).where(models.Evaluation.submission_id == submission_id))).scalars().all())
    by_id = {e.id: e for e in rows}

    def depth(e: models.Evaluation) -> int:
        d, cur = 0, e
        while cur.corrects_id and cur.corrects_id in by_id and d < 100:
            cur, d = by_id[cur.corrects_id], d + 1
        return d

    return sorted(rows, key=lambda e: (depth(e), e.created_at or datetime.min.replace(tzinfo=timezone.utc)))


def active_of(evals: list[models.Evaluation]) -> models.Evaluation | None:
    """Penilaian aktif: yang terbaru dan belum dikoreksi oleh baris lain."""
    corrected = {e.corrects_id for e in evals if e.corrects_id}
    live = [e for e in evals if e.id not in corrected]
    return live[-1] if live else None


async def correct(
    db: AsyncSession, sub: models.Submission, member: models.Member, *, evaluator_id: uuid.UUID, evaluator_role: str,
    status: SubmissionStatus, notes: str | None, rubric_scores: dict | None, reason: str,
) -> models.Evaluation:
    if sub.status not in JUDGED:
        raise HTTPException(409, "Setoran belum dinilai; gunakan penilaian biasa")
    if status not in JUDGED:
        raise HTTPException(422, "Hasil koreksi harus lulus, perlu diulang, atau belum lancar")
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(422, "Alasan koreksi wajib diisi")
    evals = await history(db, sub.id)
    current = active_of(evals)
    was_passed = sub.status == SubmissionStatus.passed
    ever_passed = any(e.result == "passed" for e in evals)
    ev = models.Evaluation(
        submission_id=sub.id, member_id=sub.member_id, evaluator_id=evaluator_id, evaluator_role=evaluator_role, result=status.value,
        notes=notes, rubric_scores=rubric_scores, corrects_id=current.id if current else None, correction_reason=reason,
        created_at=datetime.now(timezone.utc),
    )
    db.add(ev)
    sub.status, sub.rubric_scores, sub.evaluator_notes = status, rubric_scores, notes
    sub.evaluated_at = datetime.now(timezone.utc)
    await db.flush()
    now_passed = status == SubmissionStatus.passed

    if sub.context == SubmissionContext.tahsin:
        member.tahsin_status = TahsinStatus.passed if now_passed else TahsinStatus.failed
    if sub.context == SubmissionContext.ziyadah and sub.surah_id:
        rng = (await db.execute(select(models.MemorizedRange).where(models.MemorizedRange.submission_id == sub.id))).scalars().first()
        if now_passed:
            if rng:
                rng.status = "passed"
            else:
                rng = await hafalan_ranges.record_passed_range(db, sub)
            if rng:
                await murojaah.schedule_for_range(db, rng)
        elif rng and rng.status == "passed":
            rng.status = "superseded"
            for it in (await db.execute(select(models.MurojaahItem).where(models.MurojaahItem.range_id == rng.id, models.MurojaahItem.completed.is_(False)))).scalars().all():
                it.completed = True  # jadwal rentang yang tidak lagi lulus dihentikan
        if not now_passed:
            await sesi3.create_request(db, member, sub.id, "correction")
        await _recompute_progress(db, member.id, sub.surah_id, now_passed)
    if now_passed and not ever_passed:
        await gamification.add_xp(db, member.id, "setoran_lulus")  # sekali; XP yang sudah ada tidak ditarik
    await db.flush()
    return ev


async def _recompute_progress(db: AsyncSession, member_id: uuid.UUID, surah_id: int, last_passed: bool) -> None:
    prog = (await db.execute(select(models.MemberSurahProgress).where(models.MemberSurahProgress.member_id == member_id, models.MemberSurahProgress.surah_id == surah_id))).scalar_one_or_none()
    surah = await db.get(models.Surah, surah_id)
    if not prog or not surah:
        return
    covered = await hafalan_ranges.covered_ayahs(db, member_id, surah_id)
    prog.current_ayah = min(max(covered) + 1, surah.ayah_count) if covered else 1
    if len(covered) >= surah.ayah_count:
        prog.status = SurahProgressStatus.passed
    elif prog.status == SurahProgressStatus.passed or last_passed:
        prog.status = SurahProgressStatus.in_progress
    else:
        prog.status = SurahProgressStatus.needs_retry
