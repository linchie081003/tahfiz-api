from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.database import get_db
from app.deps import AuthContext, require_parent

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/family", response_model=schemas.FamilySettingsOut)
async def get_family_settings(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(models.FamilySettings).where(models.FamilySettings.family_id == ctx.family_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Settings tidak ditemukan")
    return row


@router.patch("/family", response_model=schemas.FamilySettingsOut)
async def update_family_settings(
    payload: schemas.FamilySettingsUpdateIn,
    ctx: AuthContext = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(models.FamilySettings).where(models.FamilySettings.family_id == ctx.family_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Settings tidak ditemukan")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    return row
