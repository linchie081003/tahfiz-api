import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.database import get_db
from app.deps import AuthContext, get_current_context
from app.services import escalation

router = APIRouter(prefix="/notifikasi", tags=["notifikasi"])


def _recipient(ctx: AuthContext) -> tuple[str, uuid.UUID]:
    if ctx.role == "parent":
        return "parent", ctx.family_id
    if ctx.role == "teacher":
        return "teacher", ctx.subject_id
    raise HTTPException(403, "Notifikasi hanya untuk orang tua dan guru")


@router.get("")
async def list_notifications(ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    """Daftar notifikasi belum dibaca. Eskalasi dijalankan lebih dulu untuk anak di cakupan penerima,
    jadi tidak bergantung pada pekerja latar belakang."""
    role, rid = _recipient(ctx)
    if role == "parent":
        member_ids = list((await db.execute(select(models.Member.id).where(models.Member.family_id == rid))).scalars().all())
    else:
        member_ids = list(
            (await db.execute(select(models.TeacherLink.member_id).where(models.TeacherLink.teacher_id == rid, models.TeacherLink.status == "active"))).scalars().all()
        )
    await escalation.run_escalation(db, member_ids=member_ids)
    rows = (
        await db.execute(
            select(models.AppNotification)
            .where(models.AppNotification.recipient_role == role, models.AppNotification.recipient_id == rid, models.AppNotification.read_at.is_(None))
            .order_by(models.AppNotification.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    out = []
    for n in rows:
        sub = await db.get(models.Submission, n.submission_id)
        pending = bool(sub and sub.status == models.SubmissionStatus.pending_eval)
        has_teacher = False
        if role == "parent":
            from app.services import teaching

            has_teacher = bool(await teaching.active_link(db, n.member_id)) and not await teaching.takeover_for(db, n.submission_id)
        out.append({
            "id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "submission_id": n.submission_id, "member_id": n.member_id,
            "created_at": n.created_at, "still_pending": pending, "can_act": role == "parent" and n.kind == "pending_72" and pending and has_teacher,
        })
    return out


@router.post("/{notification_id}/baca")
async def mark_read(notification_id: uuid.UUID, ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    role, rid = _recipient(ctx)
    n = await db.get(models.AppNotification, notification_id)
    if not n or n.recipient_role != role or n.recipient_id != rid:
        raise HTTPException(404, "Notifikasi tidak ditemukan")
    if n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
    await db.flush()
    return {"ok": True}
