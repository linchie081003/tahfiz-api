import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.config import settings
from app.database import get_db
from app.deps import AuthContext, get_current_context, require_parent
from app.models import Submission, SubmissionStatus

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()


@router.get("/vapid-public-key")
async def vapid_public_key():
    return {"public_key": settings.vapid_public_key, "enabled": bool(settings.vapid_public_key and settings.vapid_private_key)}


@router.post("/push-subscribe")
async def push_subscribe(
    payload: schemas.PushSubscribeIn,
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    """Orang tua -> langganan orang tua. Anak -> langganan perangkat anak (untuk pengingat murojaah)."""
    p256dh, auth = payload.keys.get("p256dh", ""), payload.keys.get("auth", "")
    if not p256dh or not auth:
        raise HTTPException(422, "Kunci langganan tidak lengkap")
    h = _hash(payload.endpoint)
    if ctx.role == "child":
        if not ctx.member_id:
            raise HTTPException(403, "Akses ditolak")
        existing = (
            await db.execute(select(models.MemberPushSubscription).where(models.MemberPushSubscription.endpoint_hash == h))
        ).scalar_one_or_none()
        if existing:
            existing.member_id, existing.p256dh, existing.auth = ctx.member_id, p256dh, auth
        else:
            db.add(
                models.MemberPushSubscription(
                    member_id=ctx.member_id, endpoint_hash=h, endpoint=payload.endpoint, p256dh=p256dh, auth=auth
                )
            )
        return {"ok": True, "scope": "child"}
    existing = (
        await db.execute(
            select(models.PushSubscription).where(
                models.PushSubscription.parent_user_id == ctx.subject_id, models.PushSubscription.endpoint == payload.endpoint
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.p256dh, existing.auth = p256dh, auth
    else:
        db.add(models.PushSubscription(parent_user_id=ctx.subject_id, endpoint=payload.endpoint, p256dh=p256dh, auth=auth))
    return {"ok": True, "scope": "parent"}


@router.post("/push-unsubscribe")
async def push_unsubscribe(
    payload: schemas.PushUnsubscribeIn,
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    if ctx.role == "child":
        await db.execute(
            delete(models.MemberPushSubscription).where(
                models.MemberPushSubscription.endpoint_hash == _hash(payload.endpoint),
                models.MemberPushSubscription.member_id == ctx.member_id,
            )
        )
    else:
        await db.execute(
            delete(models.PushSubscription).where(
                models.PushSubscription.endpoint == payload.endpoint,
                models.PushSubscription.parent_user_id == ctx.subject_id,
            )
        )
    return {"ok": True}


@router.get("/pending-count")
async def pending_count(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    count = (
        await db.execute(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.family_id == ctx.family_id,
                Submission.status == SubmissionStatus.pending_eval,
            )
        )
    ).scalar_one()
    return {"pending_evaluations": count}
