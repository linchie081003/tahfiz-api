"""Setoran: validasi urutan ziyadah + evaluasi idempoten."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.models import SubmissionContext, SubmissionStatus, SurahProgressStatus, TahsinStatus
from app.services import corrections, gamification, hafalan_ranges, murojaah, progress, sesi3, tahsin_points


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


async def lock_member(db: AsyncSession, member_id: uuid.UUID) -> None:
    """Serialkan setoran per anak (FOR UPDATE) agar dua kiriman bersamaan tidak lolos pemeriksaan sekaligus."""
    await db.execute(select(models.Member.id).where(models.Member.id == member_id).with_for_update())


async def supersede_pending_ziyadah(
    db: AsyncSession, member_id: uuid.UUID, surah_id: int, ayah_start: int, ayah_end: int,
) -> list[models.Submission]:
    """Tandai setoran ziyadah yang masih menunggu pada rentang yang beririsan sebagai superseded (riwayat tetap).

    Dipanggil sebelum setoran baru disimpan, dalam transaksi yang sama dan setelah lock_member.
    Ayat yang sudah dinilai pada setoran lama tidak disentuh (rentang dan penilaiannya tetap).
    """
    old = (
        await db.execute(
            select(models.Submission).where(
                models.Submission.member_id == member_id,
                models.Submission.context == SubmissionContext.ziyadah,
                models.Submission.surah_id == surah_id,
                models.Submission.status.in_([SubmissionStatus.pending_ai, SubmissionStatus.pending_eval]),
                models.Submission.ayah_start <= ayah_end,
                func.coalesce(models.Submission.ayah_end, models.Submission.ayah_start) >= ayah_start,
            )
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for o in old:
        o.status, o.superseded_at = SubmissionStatus.superseded, now
    if old:
        await db.flush()  # bebaskan indeks unik sebelum baris baru dimasukkan
    return list(old)


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


def _normalize_parts(sub: models.Submission, payload: schemas.EvaluateSubmissionIn, already: set[int]) -> list[schemas.EvaluationPart]:
    """Daftar rentang yang dinilai. Tanpa parts: seluruh setoran dengan satu hasil."""
    b = hafalan_ranges.sub_bounds(sub)
    if not payload.parts:
        if b is None or sub.context != SubmissionContext.ziyadah:
            return []
        return [schemas.EvaluationPart(ayah_start=b[0], ayah_end=b[1], status=payload.status)]
    if sub.context != SubmissionContext.ziyadah or b is None:
        raise HTTPException(422, "Penilaian per rentang hanya untuk setoran ziyadah")
    seen: set[int] = set()
    for p in sorted(payload.parts, key=lambda x: x.ayah_start):
        if p.ayah_start < b[0] or p.ayah_end > b[1]:
            raise HTTPException(422, f"Rentang {p.ayah_start}-{p.ayah_end} di luar setoran ({b[0]}-{b[1]})")
        span = set(range(p.ayah_start, p.ayah_end + 1))
        if span & seen:
            raise HTTPException(422, "Rentang yang dinilai tidak boleh tumpang tindih")
        if span & already:
            raise HTTPException(409, "Sebagian ayat sudah dinilai; gunakan koreksi untuk mengubahnya")
        seen |= span
    return sorted(payload.parts, key=lambda x: x.ayah_start)


async def apply_submission_evaluation(
    db: AsyncSession,
    sub: models.Submission,
    member: models.Member,
    payload: schemas.EvaluateSubmissionIn,
    *,
    evaluator_id: uuid.UUID | None = None,
    evaluator_role: str = "parent",
) -> None:
    """Penilaian pertama atau lanjutan (caller memastikan status pending_eval).

    Setoran ziyadah dinilai per rentang ayat: tiap rentang menjadi satu baris Evaluation (riwayat tidak ditimpa),
    hanya rentang lulus yang menjadi MemorizedRange, dan ayat yang belum dinilai tetap menunggu.
    """
    now = datetime.now(timezone.utc)
    ziyadah_ranged = sub.context == SubmissionContext.ziyadah and sub.surah_id and hafalan_ranges.sub_bounds(sub)
    if payload.parts and not ziyadah_ranged:
        raise HTTPException(422, "Penilaian per rentang hanya untuk setoran ziyadah")
    if not payload.parts and payload.status is None:
        raise HTTPException(422, "Isi status penilaian")
    sub.rubric_scores = payload.rubric_scores
    sub.evaluator_notes = payload.evaluator_notes

    if ziyadah_ranged:
        prior = await corrections.history(db, sub.id)
        parts = _normalize_parts(sub, payload, hafalan_ranges.evaluated_ayahs(prior))
        ever_passed = any(e.result == "passed" for e in prior)
        any_pass = any_fail = False
        for p in parts:
            await hafalan_ranges.record_evaluation(
                db, sub, evaluator_id=evaluator_id, evaluator_role=evaluator_role, result=p.status.value,
                notes=payload.evaluator_notes, rubric_scores=payload.rubric_scores, ayah_start=p.ayah_start, ayah_end=p.ayah_end,
            )
            if p.status == SubmissionStatus.passed:
                any_pass = True
                rng = await hafalan_ranges.record_passed_range(db, sub, ayah_start=p.ayah_start, ayah_end=p.ayah_end)
                if rng:
                    await murojaah.schedule_for_range(db, rng)
            else:
                any_fail = True
        evals = await corrections.history(db, sub.id)
        final = hafalan_ranges.overall_status(sub, evals)
        if final is not None:
            sub.status, sub.evaluated_at = final, now  # semua ayat sudah dinilai
        # jika belum semua ayat dinilai, status tetap pending_eval dan sisanya menunggu
        if any_fail:
            await sesi3.create_request(db, member, sub.id, "correction")
        await progress_after_ziyadah(db, member, sub, any_pass=any_pass, any_fail=any_fail)
        if any_pass and not ever_passed:
            await gamification.add_xp(db, member.id, "setoran_lulus")
        return

    sub.status = payload.status
    sub.evaluated_at = now
    await hafalan_ranges.record_evaluation(
        db, sub, evaluator_id=evaluator_id, evaluator_role=evaluator_role,
        result=payload.status.value, notes=payload.evaluator_notes, rubric_scores=payload.rubric_scores,
    )
    if sub.context == SubmissionContext.tahsin:
        if sub.tahsin_point:
            # Latihan per Pulau: kelulusan dicatat ke Pulau itu; gerbang Hafalan terbuka bila Pulau 1-3 lulus semua.
            was_passed = (await tahsin_points._rows(db, member.id)).get(sub.tahsin_point)
            if payload.status == SubmissionStatus.passed:
                await tahsin_points.record_result(
                    db, member, sub.tahsin_point, tahsin_points.PASS_THRESHOLD, evaluator_role, evaluator_id, enforce_order=False,
                )
                if not (was_passed and was_passed.passed):
                    await gamification.add_xp(db, member.id, "tahsin_lulus")
                if member.tahsin_status != TahsinStatus.passed:
                    member.tahsin_status = TahsinStatus.not_started  # belum semua Pulau wajib lulus
            elif member.tahsin_status != TahsinStatus.passed:
                member.tahsin_status = TahsinStatus.failed
        elif payload.status == SubmissionStatus.passed:
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


async def progress_after_ziyadah(db: AsyncSession, member: models.Member, sub: models.Submission, *, any_pass: bool, any_fail: bool) -> None:
    """Perbarui kemajuan surat dari rentang lulus: ayat aktif = ayat pertama yang belum tertutup."""
    prog = (
        await db.execute(
            select(models.MemberSurahProgress).where(
                models.MemberSurahProgress.member_id == member.id,
                models.MemberSurahProgress.surah_id == sub.surah_id,
            )
        )
    ).scalar_one_or_none()
    if not prog:
        return
    surah = await db.get(models.Surah, sub.surah_id)
    total = surah.ayah_count if surah else None
    if any_pass:
        covered = await hafalan_ranges.covered_ayahs(db, member.id, sub.surah_id)
        nxt = prog.current_ayah or 1  # ayat aktif = ayat pertama sejak posisi sekarang yang belum tertutup
        while nxt in covered:
            nxt += 1
        reached_end = total is not None and nxt > total
        if total is not None:
            nxt = min(nxt, total)
        prog.current_ayah = nxt
        if reached_end:
            # Seluruh ayat sudah dihafal: surat lulus dan murajaah mulai dijadwalkan.
            prog.status = SurahProgressStatus.passed
            await progress.unlock_next_surah(db, member.id, sub.surah_id)
        else:
            prog.status = SurahProgressStatus.in_progress  # lanjut ke ayat berikutnya
    elif any_fail:
        prog.status = SurahProgressStatus.needs_retry
