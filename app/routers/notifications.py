from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.models import Submission, SubmissionStatus
from app.database import get_db
from app.deps import AuthContext, require_parent

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/push-subscribe")
async def push_subscribe(payload: schemas.PushSubscribeIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    db.add(
        models.PushSubscription(
            parent_user_id=ctx.subject_id,
            endpoint=payload.endpoint,
            p256dh=payload.keys.get("p256dh", ""),
            auth=payload.keys.get("auth", ""),
        )
    )
    return {"ok": True}


@router.get("/pending-count")
async def pending_count(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func, select

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
