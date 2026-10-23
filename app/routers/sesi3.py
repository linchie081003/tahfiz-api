import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.database import get_db
from app.deps import AuthContext, get_current_context, require_member_id
from app.services import daily_sessions, sesi3, tanda, teaching
from app.services.surah_translit import surah_name

router = APIRouter(tags=["sesi3"])


class AskIn(BaseModel):
    submission_id: uuid.UUID
    ayah_number: int = Field(ge=1, le=286)


class MarkIn(BaseModel):
    surah_id: int = Field(ge=1, le=114)
    ayah_number: int = Field(ge=1, le=286)
    word_start: int | None = Field(None, ge=0)
    word_end: int | None = Field(None, ge=0)
    reason: str | None = Field(None, max_length=200)


class ResolveIn(BaseModel):
    note: str | None = Field(None, max_length=500)


@router.get("/sesi3")
async def sesi3_today(member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    return await sesi3.build(db, member_id)


@router.post("/sesi3/minta", status_code=201)
async def ask_check(payload: AskIn, member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    member = await db.get(models.Member, member_id)
    req = await sesi3.create_request(db, member, payload.submission_id, "child_mark", ayah_number=payload.ayah_number, created_by=member_id)
    await daily_sessions.mark_completed(db, member, "sesi3", activity_type="sesi3_request", activity_id=req.id)
    return {"id": req.id, "status": req.status}


# ---- sisi penilai (orang tua keluarga atau guru dengan tautan aktif) --------------------------

async def _can_review(db: AsyncSession, ctx: AuthContext, member: models.Member) -> None:
    if ctx.role == "parent" and member.family_id == ctx.family_id:
        return
    if ctx.role == "teacher":
        link = await teaching.active_link(db, member.id)
        if link and link.teacher_id == ctx.subject_id:
            return
    raise HTTPException(403, "Tidak berwenang untuk anak ini")


async def _reviewable_members(db: AsyncSession, ctx: AuthContext) -> list[models.Member]:
    if ctx.role == "parent":
        return list((await db.execute(select(models.Member).where(models.Member.family_id == ctx.family_id))).scalars().all())
    if ctx.role == "teacher":
        links = (
            await db.execute(select(models.TeacherLink).where(models.TeacherLink.teacher_id == ctx.subject_id, models.TeacherLink.status == "active"))
        ).scalars().all()
        out = []
        for l in links:
            m = await db.get(models.Member, l.member_id)
            if m:
                out.append(m)
        return out
    raise HTTPException(403, "Hanya orang tua atau guru")


@router.get("/penilai/permintaan")
async def open_requests(ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    members = {m.id: m for m in await _reviewable_members(db, ctx)}
    if not members:
        return []
    rows = (
        await db.execute(
            select(models.EvaluationRequest)
            .where(models.EvaluationRequest.member_id.in_(list(members)), models.EvaluationRequest.status == "open")
            .order_by(models.EvaluationRequest.created_at)
        )
    ).scalars().all()
    out = []
    for r in rows:
        sub = await db.get(models.Submission, r.submission_id)
        marks = [m for m in await tanda.active_marks(db, r.member_id, r.surah_id)]
        out.append({
            "id": r.id, "member_id": r.member_id, "member_name": members[r.member_id].name, "reason": r.reason,
            "surah_id": r.surah_id, "surah_name": surah_name(r.surah_id, ""),
            "ayah_start": sub.ayah_start if sub else None, "ayah_end": (sub.ayah_end if sub and sub.ayah_end is not None else (sub.ayah_start if sub else None)),
            "ayah_number": r.ayah_number, "created_at": r.created_at,
            "marks": [{"id": m.id, "ayah_number": m.ayah_number, "word_text": m.word_text, "created_by_role": m.created_by_role} for m in marks],
        })
    return out


@router.post("/penilai/permintaan/{request_id}/selesai")
async def resolve_request(request_id: uuid.UUID, payload: ResolveIn, ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    req = await db.get(models.EvaluationRequest, request_id)
    if not req:
        raise HTTPException(404, "Permintaan tidak ditemukan")
    member = await db.get(models.Member, req.member_id)
    await _can_review(db, ctx, member)
    await sesi3.resolve(db, req, ctx.subject_id, ctx.role, payload.note)
    return {"ok": True}


@router.post("/penilai/anak/{member_id}/permintaan", status_code=201)
async def parent_requests_check(member_id: uuid.UUID, payload: AskIn, ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    """Orang tua meminta cek pada setoran anaknya (pemicu penilaian di Sesi 3)."""
    member = await db.get(models.Member, member_id)
    if not member:
        raise HTTPException(404, "Anak tidak ditemukan")
    if ctx.role != "parent" or member.family_id != ctx.family_id:
        raise HTTPException(403, "Hanya orang tua anak ini")
    req = await sesi3.create_request(db, member, payload.submission_id, "parent_request", ayah_number=payload.ayah_number, created_by=ctx.subject_id)
    return {"id": req.id, "status": req.status}


@router.post("/penilai/anak/{member_id}/tanda", status_code=201)
async def evaluator_mark(member_id: uuid.UUID, payload: MarkIn, ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    member = await db.get(models.Member, member_id)
    if not member:
        raise HTTPException(404, "Anak tidak ditemukan")
    await _can_review(db, ctx, member)
    m = await tanda.create_mark(
        db, member_id, payload.surah_id, payload.ayah_number, word_start=payload.word_start, word_end=payload.word_end,
        reason=payload.reason, role="evaluator",
    )
    return {"id": m.id}


@router.post("/penilai/tanda/{mark_id}/nonaktif")
async def evaluator_clear(mark_id: uuid.UUID, ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    """Penilai mengonfirmasi tanda sudah teratasi. Hanya penilai yang bisa menonaktifkan tandanya."""
    mark = await db.get(models.DifficultMark, mark_id)
    if not mark:
        raise HTTPException(404, "Tanda tidak ditemukan")
    member = await db.get(models.Member, mark.member_id)
    await _can_review(db, ctx, member)
    mark.status, mark.inactive_reason = "inactive", "dikonfirmasi_penilai"
    await db.flush()
    return {"ok": True}
