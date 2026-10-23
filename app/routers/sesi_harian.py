import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.database import get_db
from app.deps import AuthContext, get_current_context, require_member_id, require_parent
from app.services import daily_sessions as ds

router = APIRouter(prefix="/sesi-harian", tags=["sesi-harian"])


class DisableIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    day: date | None = None


class EnableIn(BaseModel):
    day: date | None = None


def _out(r: models.DailySession) -> dict:
    return {
        "id": r.id, "day": r.day, "kind": r.kind, "status": r.status, "reason": r.reason,
        "activity_type": r.activity_type, "activity_id": r.activity_id, "ayah_done": r.ayah_done,
        "completed_at": r.completed_at,
    }


async def _family_member(db: AsyncSession, ctx: AuthContext, member_id: uuid.UUID) -> models.Member:
    m = await db.get(models.Member, member_id)
    if not m or m.family_id != ctx.family_id:
        raise HTTPException(404, "Profil tidak ditemukan")
    return m


@router.get("/hari-ini")
async def today_sessions(member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    member = await db.get(models.Member, member_id)
    rows = await ds.ensure_day(db, member)
    return {"day": ds.today(), "sessions": [_out(r) for r in rows]}


class Sesi3Result(BaseModel):
    surah_id: int = Field(ge=1, le=114)
    ayah_number: int = Field(ge=1, le=286)
    result: str


class Sesi3FinishIn(BaseModel):
    results: list[Sesi3Result] = Field(min_length=1, max_length=100)


@router.post("/sesi3/selesai")
async def finish_sesi3(payload: Sesi3FinishIn, member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    """Selesai hanya bila hasil mencakup tepat sampel Sesi 3 hari ini; tanpa hasil yang sah ditolak."""
    member = await db.get(models.Member, member_id)
    row, _ = await ds.complete_sesi3(db, member, [(r.surah_id, r.ayah_number, r.result) for r in payload.results])
    return _out(row)


@router.get("/anak/{member_id}")
async def child_sessions(
    member_id: uuid.UUID, dari: date | None = None, sampai: date | None = None,
    ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db),
):
    """Riwayat sesi harian dan KPI konsistensi (orang tua keluarga itu)."""
    if ctx.role != "parent":
        raise HTTPException(403, "Hanya orang tua")
    member = await _family_member(db, ctx, member_id)
    end = sampai or ds.today()
    start = dari or end - timedelta(days=29)
    if start > end or (end - start).days > 366:
        raise HTTPException(422, "Rentang tanggal tidak valid")
    await ds.ensure_day(db, member)
    rows = (
        await db.execute(
            select(models.DailySession)
            .where(models.DailySession.member_id == member_id, models.DailySession.day >= start, models.DailySession.day <= end)
            .order_by(models.DailySession.day.desc(), models.DailySession.kind)
        )
    ).scalars().all()
    return {"sessions": [_out(r) for r in rows], "kpi": await ds.consistency(db, member_id, start, end)}


@router.get("/anak/{member_id}/{session_id}/aktivitas")
async def session_activities(member_id: uuid.UUID, session_id: uuid.UUID, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    """Bukti aktivitas lengkap untuk satu sesi harian."""
    await _family_member(db, ctx, member_id)
    row = await db.get(models.DailySession, session_id)
    if not row or row.member_id != member_id:
        raise HTTPException(404, "Sesi tidak ditemukan")
    return [
        {"id": a.id, "activity_type": a.activity_type, "activity_id": a.activity_id, "ayah": a.ayah, "created_at": a.created_at}
        for a in await ds.activities(db, session_id)
    ]


@router.post("/anak/{member_id}/{kind}/nonaktif")
async def disable_session(member_id: uuid.UUID, kind: str, payload: DisableIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    member = await _family_member(db, ctx, member_id)
    row = await ds.disable(db, member, kind, payload.day or ds.today(), payload.reason, ctx.subject_id)
    return _out(row)


@router.post("/anak/{member_id}/{kind}/aktif")
async def enable_session(member_id: uuid.UUID, kind: str, payload: EnableIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    member = await _family_member(db, ctx, member_id)
    row = await ds.enable(db, member, kind, payload.day or ds.today(), ctx.subject_id)
    return _out(row)
