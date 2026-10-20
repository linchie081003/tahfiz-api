import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.database import get_db
from app.deps import AuthContext, require_parent
from app.services import gamification

router = APIRouter(prefix="/parent", tags=["parent"])


@router.get("/dashboard", response_model=schemas.ParentDashboardOut)
async def parent_dashboard(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    family = await db.get(models.Family, ctx.family_id)
    members = (
        await db.execute(
            select(models.Member).where(models.Member.family_id == ctx.family_id).order_by(models.Member.created_at)
        )
    ).scalars().all()

    queue_total = (
        await db.execute(
            select(func.count())
            .select_from(models.Submission)
            .where(
                models.Submission.family_id == ctx.family_id,
                models.Submission.status == models.SubmissionStatus.pending_eval,
            )
        )
    ).scalar_one()

    children: list[schemas.ParentChildSummaryOut] = []
    for m in members:
        stats = await gamification.ensure_member_stats(db, m.id)
        passed = (
            await db.execute(
                select(func.count())
                .select_from(models.MemberSurahProgress)
                .where(
                    models.MemberSurahProgress.member_id == m.id,
                    models.MemberSurahProgress.status == models.SurahProgressStatus.passed,
                )
            )
        ).scalar_one()
        pending = (
            await db.execute(
                select(func.count())
                .select_from(models.Submission)
                .where(
                    models.Submission.member_id == m.id,
                    models.Submission.status == models.SubmissionStatus.pending_eval,
                )
            )
        ).scalar_one()
        children.append(
            schemas.ParentChildSummaryOut(
                id=m.id,
                name=m.name,
                color=m.color,
                age_mode=m.age_mode,
                tahsin_status=m.tahsin_status,
                xp=stats.xp,
                streak_days=stats.streak_days,
                level=stats.level,
                passed_surahs=passed,
                pending_setor=pending,
            )
        )

    return schemas.ParentDashboardOut(
        family_name=family.name if family else "",
        family_access_code=family.access_code if family else "",
        queue_total=queue_total,
        active_member_id=ctx.member_id,
        children=children,
    )
