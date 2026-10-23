from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.surah_translit import surah_name
from app import models, schemas
from app.database import get_db
from app.deps import AuthContext, get_current_context
from app.models import AgeMode
from app.services.juz30 import list_juz30_surahs
from app.services.quran_com_import import ensure_chapter_catalog, ensure_surah_ayahs, ensure_tajweed
from app.services.reciters import (
    TILAWAH_RECITER_ID,
    default_reciter_for_age,
    everyayah_url,
    list_reciters,
    reciter_for_learning,
)
from app.services.surah_names_id import indonesian_surah_name

router = APIRouter(prefix="/quran", tags=["quran"])


def _surah_out(row: models.Surah) -> schemas.SurahOut:
    return schemas.SurahOut(
        id=row.id,
        name_ar=row.name_ar,
        name_id=surah_name(row.id, indonesian_surah_name(row.id, row.name_id)),
        ayah_count=row.ayah_count,
        juz_number=row.juz_number,
        curriculum_order=row.curriculum_order,
    )


async def _member_age_mode(db: AsyncSession, ctx: AuthContext) -> AgeMode | None:
    if not ctx.member_id:
        return None
    member = await db.get(models.Member, ctx.member_id)
    return member.age_mode if member else None


@router.get("/surahs", response_model=list[schemas.SurahOut])
async def list_surahs(
    juz: int | None = Query(None, ge=1, le=30),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    if juz == 30:
        rows = await list_juz30_surahs(db)
        return [_surah_out(r) for r in rows]
    await ensure_chapter_catalog(db)
    q = select(models.Surah).order_by(models.Surah.id)
    if juz is not None:
        q = q.where(models.Surah.juz_number == juz)
    rows = (await db.execute(q)).scalars().all()
    return [_surah_out(r) for r in rows]


@router.get("/reciters", response_model=list[schemas.ReciterOut])
async def reciters(
    gender: str | None = Query(None, pattern="^(male|female)$"),
    age_mode: AgeMode | None = Query(None),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    mode = age_mode or await _member_age_mode(db, ctx)
    default_id = default_reciter_for_age(mode)
    return [
        schemas.ReciterOut(
            id=r.id,
            label=r.label,
            gender=r.gender,
            description=r.description,
            style=r.style,
            default_for_age=r.id == default_id,
        )
        for r in list_reciters(gender, age_mode=mode, for_settings=True)
    ]


@router.get("/surahs/juz/{juz_number}", response_model=list[schemas.SurahOut])
async def surahs_by_juz(juz_number: int, db: AsyncSession = Depends(get_db)):
    if juz_number == 30:
        rows = await list_juz30_surahs(db)
        return [_surah_out(r) for r in rows]
    rows = (
        await db.execute(
            select(models.Surah).where(models.Surah.juz_number == juz_number).order_by(models.Surah.curriculum_order)
        )
    ).scalars().all()
    return [_surah_out(r) for r in rows]


async def _resolve_reciter(
    db: AsyncSession,
    family_id,
    reciter_id: str | None,
    age_mode: AgeMode | None,
) -> str:
    rid = reciter_id
    if not rid:
        settings = (
            await db.execute(select(models.FamilySettings).where(models.FamilySettings.family_id == family_id))
        ).scalar_one_or_none()
        rid = settings.reciter_id if settings else None
    return reciter_for_learning(rid, age_mode)


@router.get("/surahs/{surah_id}/ayahs", response_model=list[schemas.AyahOut])
async def ayahs(
    surah_id: int,
    reciter_id: str | None = Query(None),
    purpose: str | None = Query(None, pattern="^(tilawah)$"),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    await ensure_chapter_catalog(db)
    surah = await db.get(models.Surah, surah_id)
    if not surah:
        raise HTTPException(404, "Surat tidak ditemukan")
    await ensure_surah_ayahs(db, surah_id)
    await ensure_tajweed(db, surah_id)
    rows = (
        await db.execute(select(models.Ayah).where(models.Ayah.surah_id == surah_id).order_by(models.Ayah.ayah_number))
    ).scalars().all()
    if not rows:
        raise HTTPException(404, "Ayat surat belum tersedia — coba lagi atau jalankan scripts/import_full_quran.py")
    age_mode = await _member_age_mode(db, ctx)
    # Tilawah (mendengarkan) selalu memakai Mishary Rashid Alafasy; belajar mengikuti qari belajar anak.
    rid = TILAWAH_RECITER_ID if purpose == "tilawah" else await _resolve_reciter(db, ctx.family_id, reciter_id, age_mode)
    out: list[schemas.AyahOut] = []
    for a in rows:
        out.append(
            schemas.AyahOut(
                id=a.id,
                surah_id=a.surah_id,
                ayah_number=a.ayah_number,
                text_uthmani=a.text_uthmani,
                text_tajweed=a.text_tajweed,
                tajwid_markup=a.tajwid_markup,
                audio_url=everyayah_url(surah_id, a.ayah_number, rid),
                reciter_id=rid,
            )
        )
    return out
