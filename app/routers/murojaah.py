import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.database import get_db
from app.deps import require_member_id
from app.services import gamification, murojaah

router = APIRouter(prefix="/murojaah", tags=["murojaah"])


@router.get("/due", response_model=list[schemas.MurojaahItemOut])
async def due(member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    items = await murojaah.due_items(db, member_id, 10)
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
    await murojaah.complete_item(db, item, payload.rating)
    await gamification.add_xp(db, member_id, "murojaah_done")
    return {"ok": True}
