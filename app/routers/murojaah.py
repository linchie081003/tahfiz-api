import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.surah_translit import surah_name
from app import models, schemas
from app.database import get_db
from app.deps import AuthContext, get_current_context, optional_member_id, require_member_id
from app.services import daily_sessions, gamification, murojaah

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
        out.append(schemas.MurojaahItemOut(
            id=it.id, surah_id=it.surah_id, surah_name=surah_name(surah.id, surah.name_id) if surah else "",
            due_date=it.due_date, ayah_start=it.ayah_start, ayah_end=it.ayah_end,
        ))
    return out


@router.get("/sesi", response_model=schemas.MurojaahSessionOut)
async def sesi(
    member_id=Depends(optional_member_id),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    """Sesi 1: murajaah hafalan lama. Aktif bila ada minimal satu ayat yang sudah lulus."""
    if member_id is None:
        return schemas.MurojaahSessionOut(active=False, max_ayah=murojaah.SESI1_MAX_AYAH, total_ayah=0, blocks=[])
    off = await daily_sessions.disabled_reason(db, member_id, "sesi1")
    if off:
        return schemas.MurojaahSessionOut(active=False, max_ayah=murojaah.SESI1_MAX_AYAH, total_ayah=0, blocks=[], disabled_reason=off)
    has_range = (
        await db.execute(select(models.MurojaahItem.id).where(models.MurojaahItem.member_id == member_id).limit(1))
    ).first() is not None
    items = await murojaah.due_items(db, member_id, 50)
    from app.services import tanda

    marked = {(m.surah_id, m.ayah_number) for m in await tanda.active_marks(db, member_id)}

    def has_mark(it):
        return any((it.surah_id, n) in marked for n in range(it.ayah_start or 1, (it.ayah_end or it.ayah_start or 1) + 1))

    # prioritas: lemah, lalu ayat bertanda, lalu yang paling lama jatuh tempo
    items = sorted(items, key=lambda it: (-it.weak_score, not has_mark(it), it.due_date))
    chosen = murojaah.pick_for_session(items)
    blocks = []
    for b in murojaah.to_blocks(chosen):
        surah = await db.get(models.Surah, b["surah_id"])
        blocks.append(schemas.MurojaahBlockOut(
            surah_id=b["surah_id"], surah_name=surah_name(b["surah_id"], surah.name_id if surah else ""),
            ayah_start=b["ayah_start"], ayah_end=b["ayah_end"],
            items=[schemas.MurojaahSessionItemOut(**i) for i in b["items"]],
        ))
    total = sum(b.ayah_end - b.ayah_start + 1 for b in blocks)
    return schemas.MurojaahSessionOut(active=has_range, max_ayah=murojaah.SESI1_MAX_AYAH, total_ayah=total, blocks=blocks)


@router.post("/{item_id}/complete")
async def complete(item_id: uuid.UUID, payload: schemas.MurojaahCompleteIn, member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    item = await db.get(models.MurojaahItem, item_id)
    if not item or item.member_id != member_id:
        raise HTTPException(404, "Item tidak ditemukan")
    ms = (await db.execute(select(models.MemberSettings).where(models.MemberSettings.member_id == member_id))).scalar_one_or_none()
    await murojaah.complete_item(db, item, payload.rating, ms.murajaah_strong_days if ms else 14)
    member = await db.get(models.Member, member_id)
    size = (item.ayah_end or 1) - (item.ayah_start or 1) + 1
    await daily_sessions.mark_completed(db, member, "sesi1", activity_type="murojaah_item", activity_id=item.id, ayah=size)
    await gamification.add_xp(db, member_id, "murojaah_done")
    return {"ok": True}
