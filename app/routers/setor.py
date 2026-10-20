import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.config import settings
from app.database import get_db
from app.deps import AuthContext, get_current_context, require_member_id, require_parent
from app.services import setor_flow, storage
from app.services.ai_analysis import analyze_recording, mock_transcript_from_reference
from app.services.quran_display import ayah_range_texts

router = APIRouter(prefix="/setor", tags=["setor"])


@router.get("/media/{submission_id}")
async def stream_recording(submission_id: uuid.UUID, ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    sub = await db.get(models.Submission, submission_id)
    if not sub or sub.family_id != ctx.family_id:
        raise HTTPException(404, "Rekaman tidak ditemukan")
    path = storage.local_recording_path(sub.family_id, sub.id)
    if not path.is_file():
        raise HTTPException(404, "File rekaman tidak ada")
    return FileResponse(path, media_type="audio/webm")


async def _enqueue_ai(submission_id: str):
    try:
        r = aioredis.from_url(settings.redis_url)
        await r.lpush("hafiz:ai_jobs", submission_id)
        await r.aclose()
    except Exception:
        pass


@router.post("", response_model=schemas.SubmissionCreateOut)
async def create_submission(
    context: models.SubmissionContext = Form(...),
    reference_text: str = Form(...),
    surah_id: int | None = Form(None),
    ayah_start: int | None = Form(None),
    ayah_end: int | None = Form(None),
    file: UploadFile = File(...),
    member_id: uuid.UUID = Depends(require_member_id),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(models.Member, member_id)
    if not member or member.family_id != ctx.family_id:
        raise HTTPException(403, "Akses ditolak")
    if context == models.SubmissionContext.ziyadah:
        await setor_flow.assert_ziyadah_setor_allowed(db, member, surah_id, ayah_start, ayah_end)
    data = await file.read()
    sub = models.Submission(
        member_id=member_id,
        family_id=ctx.family_id,
        context=context,
        surah_id=surah_id,
        ayah_start=ayah_start,
        ayah_end=ayah_end,
        reference_text=reference_text,
        recording_key="pending",
        status=models.SubmissionStatus.pending_ai,
        ai_status="pending",
    )
    db.add(sub)
    await db.flush()
    key = storage.upload_recording(data, file.content_type or "audio/webm", ctx.family_id, sub.id)
    sub.recording_key = key
    if context == models.SubmissionContext.tahsin:
        member.tahsin_status = models.TahsinStatus.pending_eval
    await _enqueue_ai(str(sub.id))
    await _process_ai_inline(db, sub)
    return schemas.SubmissionCreateOut(id=sub.id, status=sub.status, ai_status=sub.ai_status)


async def _process_ai_inline(db: AsyncSession, sub: models.Submission):
    """Process immediately if Redis unavailable; worker uses same logic."""
    markup = None
    if sub.surah_id and sub.ayah_start:
        ayah = (
            await db.execute(
                select(models.Ayah).where(models.Ayah.surah_id == sub.surah_id, models.Ayah.ayah_number == sub.ayah_start)
            )
        ).scalar_one_or_none()
        markup = ayah.tajwid_markup if ayah else None
    transcript = mock_transcript_from_reference(sub.reference_text)
    insights = analyze_recording(reference_text=sub.reference_text, tajwid_markup=markup, transcript=transcript)
    sub.ai_insights = insights
    sub.ai_status = "completed"
    sub.status = models.SubmissionStatus.pending_eval


@router.get("/queue", response_model=list[schemas.SubmissionOut])
async def evaluator_queue(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    subs = (
        await db.execute(
            select(models.Submission)
            .where(
                models.Submission.family_id == ctx.family_id,
                models.Submission.status == models.SubmissionStatus.pending_eval,
            )
            .order_by(models.Submission.created_at.desc())
        )
    ).scalars().all()
    out = []
    for s in subs:
        member = await db.get(models.Member, s.member_id)
        ref_tajweed = None
        if s.surah_id and s.ayah_start:
            _, ref_tajweed = await ayah_range_texts(db, s.surah_id, s.ayah_start, s.ayah_end)
        out.append(
            schemas.SubmissionOut(
                id=s.id,
                context=s.context,
                surah_id=s.surah_id,
                reference_text=s.reference_text,
                reference_text_tajweed=ref_tajweed,
                status=s.status,
                ai_status=s.ai_status,
                ai_insights=s.ai_insights,
                rubric_scores=s.rubric_scores,
                recording_url=storage.presigned_recording_url(s.recording_key, s.family_id, s.id),
                created_at=s.created_at,
                member_name=member.name if member else None,
            )
        )
    return out


def _submission_out(sub: models.Submission, member: models.Member | None) -> schemas.SubmissionOut:
    return schemas.SubmissionOut(
        id=sub.id,
        context=sub.context,
        surah_id=sub.surah_id,
        reference_text=sub.reference_text,
        status=sub.status,
        ai_status=sub.ai_status,
        ai_insights=sub.ai_insights,
        rubric_scores=sub.rubric_scores,
        recording_url=storage.presigned_recording_url(sub.recording_key, sub.family_id, sub.id),
        created_at=sub.created_at,
        member_name=member.name if member else None,
    )


@router.post("/{submission_id}/evaluate", response_model=schemas.SubmissionOut)
async def evaluate_submission(
    submission_id: uuid.UUID,
    payload: schemas.EvaluateSubmissionIn,
    ctx: AuthContext = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    sub = await setor_flow.load_submission_for_evaluate(db, submission_id, ctx.family_id)
    if not sub:
        raise HTTPException(404, "Setoran tidak ditemukan")
    member = await db.get(models.Member, sub.member_id)
    if not member:
        raise HTTPException(404, "Profil tidak ditemukan")

    if sub.status != models.SubmissionStatus.pending_eval:
        return _submission_out(sub, member)

    await setor_flow.apply_submission_evaluation(db, sub, member, payload)
    return _submission_out(sub, member)
