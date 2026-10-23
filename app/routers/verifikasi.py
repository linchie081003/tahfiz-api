import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.database import get_db
from app.deps import AuthContext, require_parent
from app.services import corrections, teaching, verification

router = APIRouter(prefix="/hafalan/verifikasi", tags=["verifikasi"])


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(lulus|tolak)$")
    note: str = Field(min_length=1, max_length=500)


@router.get("")
async def pending(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    """Hafalan lama tanpa bukti penilaian lulus yang menunggu keputusan orang tua."""
    kids = (await db.execute(select(models.Member).where(models.Member.family_id == ctx.family_id))).scalars().all()
    out: list[dict] = []
    for m in kids:
        out.extend(await verification.as_dicts(db, m))
    return out


@router.post("/{range_id}")
async def decide(range_id: uuid.UUID, payload: DecisionIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    rng = await db.get(models.MemorizedRange, range_id)
    member = await db.get(models.Member, rng.member_id) if rng else None
    if not rng or not member or member.family_id != ctx.family_id:
        raise HTTPException(404, "Rentang tidak ditemukan")
    if not await corrections.parent_may_evaluate(db, member.family_id):
        raise HTTPException(403, "Kewenangan menilai orang tua dinonaktifkan")
    if await teaching.active_link(db, member.id):
        raise HTTPException(403, "Verifikasi dilakukan guru yang terhubung")
    r = await verification.resolve(db, rng, decision=payload.decision, note=payload.note, by=ctx.subject_id, role="parent")
    return {"id": r.id, "status": r.status}
