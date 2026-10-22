"""Kemajuan Tilawah per orang (anak atau orang tua), supaya ayat terakhir ikut pindah perangkat."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.database import get_db
from app.deps import AuthContext, get_current_context

router = APIRouter(prefix="/tilawah", tags=["tilawah"])


class Pos(BaseModel):
    surah: int = Field(ge=1, le=114)
    ayah: int = Field(ge=1, le=286)
    at: int = 0  # ms sejak epoch, untuk memilih yang terbaru saat digabung


class TilawahIn(BaseModel):
    last: Pos | None = None
    bookmark: Pos | None = None
    bookmark_cleared_at: int = 0  # kapan penanda dilepas (agar pelepasan ikut tersinkron)
    target: int | None = Field(None, ge=1, le=20)
    target_at: int = 0
    days: dict[str, list[str]] = Field(default_factory=dict, max_length=90)
    max: int | None = Field(None, ge=0, le=6236)


def _owner(ctx: AuthContext):
    if ctx.role not in ("child", "parent"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tilawah hanya untuk anak dan orang tua")
    return ctx.member_id or ctx.subject_id


def _merge(old: dict, new: dict) -> dict:
    out = dict(old)
    for key in ("last",):
        a, b = old.get(key), new.get(key)
        out[key] = b if b and (not a or b.get("at", 0) >= a.get("at", 0)) else a
    bm_old, bm_new = old.get("bookmark"), new.get("bookmark")
    cleared = max(old.get("bookmark_cleared_at", 0), new.get("bookmark_cleared_at", 0))
    best = max((x for x in (bm_old, bm_new) if x), key=lambda x: x.get("at", 0), default=None)
    out["bookmark"] = best if best and best.get("at", 0) > cleared else None
    out["bookmark_cleared_at"] = cleared
    if new.get("target") is not None and new.get("target_at", 0) >= old.get("target_at", 0):
        out["target"], out["target_at"] = new["target"], new.get("target_at", 0)
    days = {k: set(v) for k, v in (old.get("days") or {}).items()}
    for k, v in (new.get("days") or {}).items():
        days.setdefault(k, set()).update(v)
    keep = sorted(days)[-60:]
    out["days"] = {k: sorted(days[k]) for k in keep}
    out["max"] = max(old.get("max") or 0, new.get("max") or 0)
    return out


@router.get("")
async def get_state(ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    row = await db.get(models.TilawahState, _owner(ctx))
    return row.data if row else {}


@router.put("")
async def put_state(body: TilawahIn, ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    oid = _owner(ctx)
    row = await db.get(models.TilawahState, oid)
    merged = _merge(row.data if row else {}, body.model_dump())
    if row:
        row.data = merged
    else:
        db.add(models.TilawahState(owner_id=oid, data=merged))
    await db.commit()
    return merged
