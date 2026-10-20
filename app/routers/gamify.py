from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.database import get_db
from app.deps import AuthContext, get_current_context, optional_member_id
from app.services import gamification

router = APIRouter(prefix="/gamify", tags=["gamify"])


@router.get("", response_model=schemas.GamificationOut)
async def gamification_view(
    member_id=Depends(optional_member_id),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    if member_id is None:
        return schemas.GamificationOut(
            xp=0,
            level=1,
            rank_title="Orang tua",
            streak_days=0,
            badges=[],
        )
    stats = await gamification.ensure_member_stats(db, member_id)
    badges = await gamification.list_badges(db, member_id)
    return schemas.GamificationOut(
        xp=stats.xp,
        level=stats.level,
        rank_title=stats.rank_title,
        streak_days=stats.streak_days,
        badges=[schemas.BadgeOut(**b) for b in badges],
    )
