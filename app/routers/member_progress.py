"""Pengaturan per anak dan kemajuan 9 Pulau tahsin."""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.database import get_db
from app.deps import AuthContext, get_current_context, require_parent
from app.services import tahsin_points, teaching

router = APIRouter(tags=["member-progress"])

DAILY_AYAHS = (1, 2, 3, 5)
STRONG_DAYS = (7, 14)


class MemberSettingsOut(BaseModel):
    coverage: str = "juz30"
    daily_ayahs: int = 1
    murajaah_strong_days: int = 14
    set_by: str = "parent"
    parallel_hafalan: bool = False


class MemberSettingsIn(BaseModel):
    coverage: Literal["juz30", "all"] | None = None
    daily_ayahs: int | None = None
    murajaah_strong_days: int | None = None
    parallel_hafalan: bool | None = None


class PointResultIn(BaseModel):
    score: float = Field(ge=0, le=10)
    approve_below_threshold: bool = False


async def _member_of_family(db: AsyncSession, member_id: uuid.UUID, family_id: uuid.UUID) -> models.Member:
    member = await db.get(models.Member, member_id)
    if not member or member.family_id != family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anak tidak ditemukan")
    return member


async def get_member_settings(db: AsyncSession, member_id: uuid.UUID) -> models.MemberSettings | None:
    return (
        await db.execute(select(models.MemberSettings).where(models.MemberSettings.member_id == member_id))
    ).scalar_one_or_none()


@router.get("/members/{member_id}/settings", response_model=MemberSettingsOut)
async def read_member_settings(
    member_id: uuid.UUID, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)
):
    await _member_of_family(db, member_id, ctx.family_id)
    row = await get_member_settings(db, member_id)
    if not row:
        return MemberSettingsOut()
    return MemberSettingsOut(
        coverage=row.coverage, daily_ayahs=row.daily_ayahs,
        murajaah_strong_days=row.murajaah_strong_days, set_by=row.set_by,
        parallel_hafalan=bool(row.parallel_hafalan),
    )


@router.put("/members/{member_id}/settings", response_model=MemberSettingsOut)
async def update_member_settings(
    member_id: uuid.UUID,
    payload: MemberSettingsIn,
    ctx: AuthContext = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    """Kedua orang tua boleh mengatur (tanpa guru). Setelah ada guru terhubung, guru yang mengatur."""
    await _member_of_family(db, member_id, ctx.family_id)
    if await teaching.active_link(db, member_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Pengaturan ini diatur guru yang terhubung")
    if payload.daily_ayahs is not None and payload.daily_ayahs not in DAILY_AYAHS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kecepatan harus 1, 2, 3, atau 5 ayat per hari")
    if payload.murajaah_strong_days is not None and payload.murajaah_strong_days not in STRONG_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Interval 'Kuat' harus 7 atau 14 hari")
    row = await get_member_settings(db, member_id)
    if not row:
        row = models.MemberSettings(member_id=member_id, coverage="juz30", daily_ayahs=1,
                                    murajaah_strong_days=14, set_by="parent")
        db.add(row)
    for field in ("coverage", "daily_ayahs", "murajaah_strong_days", "parallel_hafalan"):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    row.set_by = "parent"
    await db.flush()
    return MemberSettingsOut(
        coverage=row.coverage, daily_ayahs=row.daily_ayahs,
        murajaah_strong_days=row.murajaah_strong_days, set_by=row.set_by,
        parallel_hafalan=bool(row.parallel_hafalan),
    )


async def _resolve_member(ctx: AuthContext, member_id: uuid.UUID | None, db: AsyncSession) -> models.Member:
    mid = ctx.member_id if ctx.role == "child" else (member_id or ctx.member_id)
    if not mid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pilih profil anak terlebih dahulu")
    return await _member_of_family(db, mid, ctx.family_id)


@router.get("/tahsin/points")
async def tahsin_points_overview(
    member_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    member = await _resolve_member(ctx, member_id, db)
    return await tahsin_points.overview(db, member.id)


@router.post("/tahsin/points/{point}/result")
async def tahsin_point_result(
    point: int,
    payload: PointResultIn,
    member_id: uuid.UUID,
    ctx: AuthContext = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    """Keputusan lulus ada pada orang tua (belum ada guru). Skor AI hanya pra-cek."""
    if point < 1 or point > 9:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pulau tidak ditemukan")
    member = await _member_of_family(db, member_id, ctx.family_id)
    if await teaching.active_link(db, member_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Penilaian dilakukan guru yang terhubung")
    await tahsin_points.record_result(
        db, member, point, payload.score, "parent", ctx.subject_id, payload.approve_below_threshold
    )
    return await tahsin_points.overview(db, member.id)


PLACEMENTS = ("none", "basic", "fluent")


class PlacementIn(BaseModel):
    level: Literal["none", "basic", "fluent"]


async def _own_member_id(ctx: AuthContext) -> uuid.UUID:
    if not ctx.member_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pilih profil anak dulu")
    return ctx.member_id


@router.get("/placement")
async def read_placement(ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    """Tingkat awal bacaan anak yang sedang masuk. Null berarti onboarding belum diisi."""
    row = await get_member_settings(db, await _own_member_id(ctx))
    return {"placement": row.placement if row else None}


@router.put("/placement")
async def write_placement(payload: PlacementIn, ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    mid = await _own_member_id(ctx)
    row = await get_member_settings(db, mid)
    if not row:
        row = models.MemberSettings(member_id=mid, coverage="juz30", daily_ayahs=1, murajaah_strong_days=14)
        db.add(row)
    row.placement = payload.level
    await db.flush()
    return {"placement": row.placement}
