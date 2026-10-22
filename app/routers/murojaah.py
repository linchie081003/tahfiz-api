import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.database import get_db
from app.deps import AuthContext, get_current_context, optional_member_id, require_member_id
from app.services import gamification, murojaah

router = APIRouter(prefix="/murojaah", tags=["murojaah"])


@router.get("/due", response_model=list[schemas.MurojaahItemOut])
async def due(
    member_id=Depends(optional_member_id),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    if member_id is None:
        return []
    settings = (
        await db.execute(select(models.FamilySettings).where(models.FamilySettings.family_id == ctx.family_id))
    ).scalar_one_or_none()
    cap = settings.daily_murojaah_cap if settings else 5
    items = await murojaah.due_items(db, member_id, cap)
    out = []
    for it in items:
        surah = await db.get(models.Surah, it.surah_id)
        out.append(schemas.MurojaahItemOut(id=it.id, surah_id=it.surah_id, surah_name=surah.name_id if surah else "", due_date=it.due_date))
    return out


@router.post("/{item_id}/complete")
async def complete(item_id: uuid.UUID, payload: schemas.MurojaahCompleteIn, member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    item = await db.get(models.MurojaahItem, item_id)
    if not item or item.member_id != member_id:
        raise HTTPException(404, "Item tidak ditemukan")
    ms = (await db.execute(select(models.MemberSettings).where(models.MemberSettings.member_id == member_id))).scalar_one_or_none()
    await murojaah.complete_item(db, item, payload.rating, ms.murajaah_strong_days if ms else 14)
    await gamification.add_xp(db, member_id, "murojaah_done")
    return {"ok": True}
