"""Setoran: validasi urutan ziyadah + evaluasi idempoten."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.models import SubmissionContext, SubmissionStatus, SurahProgressStatus, TahsinStatus
from app.services import gamification, hafalan_ranges, murojaah, progress


async def assert_ziyadah_setor_allowed(
    db: AsyncSession,
    member: models.Member,
    surah_id: int | None,
    ayah_start: int | None,
    ayah_end: int | None,
) -> models.MemberSurahProgress:
    if surah_id is None or ayah_start is None:
        raise HTTPException(409, "Setoran ziyadah wajib surah_id dan ayah_start")
    if not await progress.hafalan_unlocked(db, member):
        raise HTTPException(409, "Selesaikan Tahsin dulu")

    active = await progress.get_active_surah(db, member.id)
    if not active:
        # Belum ada surat aktif (mis. jalur baru atau data lama): susun ulang dari jalur hafalan anak.
        await progress.set_track(db, member.id, await progress.effective_track(db, member.id))
        active = await progress.get_active_surah(db, member.id)
    prog = (
        await db.execute(
            select(models.MemberSurahProgress).where(
                models.MemberSurahProgress.member_id == member.id,
                models.MemberSurahProgress.surah_id == surah_id,
            )
        )
    ).scalar_one_or_none()
    # Surat yang disetor harus sedang dipelajari (aktif di peta); tidak harus yang pertama jika ada lebih dari satu.
    if not prog or prog.status not in (SurahProgressStatus.in_progress, SurahProgressStatus.needs_retry):
        raise HTTPException(409, "Hanya surat aktif di peta yang boleh disetor")

    end = ayah_end if ayah_end is not None else ayah_start
    if end < ayah_start:
        raise HTTPException(409, "Rentang ayat tidak valid")

    surah = await db.get(models.Surah, surah_id)
    if not surah or ayah_start < 1 or end > surah.ayah_count:
        raise HTTPException(409, "Ayat di luar batas surat")

    allowed_starts = {prog.current_ayah, prog.current_ayah + 1}
    if ayah_start not in allowed_starts:
        raise HTTPException(
            409,
            "Ayat setoran harus sama dengan ayat aktif atau ayat berikutnya",
        )
    return prog


async def load_submission_for_evaluate(
    db: AsyncSession, submission_id: uuid.UUID, family_id: uuid.UUID
) -> models.Submission | None:
    result = await db.execute(
        select(models.Submission).where(models.Submission.id == submission_id).with_for_update()
    )
    sub = result.scalar_one_or_none()
    if not sub or sub.family_id != family_id:
        return None
    return sub


async def apply_submission_evaluation(
    db: AsyncSession,
    sub: models.Submission,
    member: models.Member,
    payload: schemas.EvaluateSubmissionIn,
    *,
    evaluator_id: uuid.UUID | None = None,
    evaluator_role: str = "parent",
) -> None:
    """Side effects for first-time evaluation (caller must ensure status is pending_eval)."""
    sub.status = payload.status
    sub.rubric_scores = payload.rubric_scores
    sub.evaluator_notes = payload.evaluator_notes
    sub.evaluated_at = datetime.now(timezone.utc)
    await hafalan_ranges.record_evaluation(
        db, sub, evaluator_id=evaluator_id, evaluator_role=evaluator_role,
        result=payload.status.value, notes=payload.evaluator_notes, rubric_scores=payload.rubric_scores,
    )
    if sub.context == SubmissionContext.ziyadah and payload.status == SubmissionStatus.passed:
        await hafalan_ranges.record_passed_range(db, sub)

    if sub.context == SubmissionContext.tahsin:
        if payload.status == SubmissionStatus.passed:
            member.tahsin_status = TahsinStatus.passed
            await gamification.add_xp(db, member.id, "tahsin_lulus")
        else:
            member.tahsin_status = TahsinStatus.failed
        db.add(
            models.TahsinAttempt(
                member_id=member.id,
                submission_id=sub.id,
                result=payload.status.value,
            )
        )

    if sub.context == SubmissionContext.ziyadah and sub.surah_id:
        prog = (
            await db.execute(
                select(models.MemberSurahProgress).where(
                    models.MemberSurahProgress.member_id == member.id,
                    models.MemberSurahProgress.surah_id == sub.surah_id,
                )
            )
        ).scalar_one_or_none()
        if prog:
            ayah_end = sub.ayah_end if sub.ayah_end is not None else sub.ayah_start
            if payload.status == SubmissionStatus.passed:
                surah = await db.get(models.Surah, sub.surah_id)
                total = surah.ayah_count if surah else None
                if ayah_end is not None:
                    prog.current_ayah = max(prog.current_ayah, min(ayah_end + 1, total or ayah_end + 1))
                if total is not None and ayah_end is not None and ayah_end >= total:
                    # Seluruh ayat sudah dihafal: surat lulus dan murajaah mulai dijadwalkan.
                    prog.status = SurahProgressStatus.passed
                    await progress.unlock_next_surah(db, member.id, sub.surah_id)
                    await murojaah.schedule_for_passed_surah(db, member.id, sub.surah_id)
                else:
                    prog.status = SurahProgressStatus.in_progress  # lanjut ke ayat berikutnya
                await gamification.add_xp(db, member.id, "setoran_lulus")
            else:
                prog.status = SurahProgressStatus.needs_retry
