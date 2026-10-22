from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.database import get_db
from app.deps import AuthContext, get_current_context, optional_member_id
from app.models import AgeMode, TahsinStatus
from app.services import tahsin_curriculum
from app.services.quran_display import ayah_range_texts
from app.services.reciters import everyayah_url, reciter_for_learning

router = APIRouter(prefix="/tahsin", tags=["tahsin"])

TAHSIN_SURAH_ID = 114
TAHSIN_AYAH_NUMBERS = (1, 2)
TAHSIN_REFERENCE = "قُلْ أَعُوذُ بِرَبِّ النَّاسِ مَلِكِ النَّاسِ"


async def _resolve_reciter(db: AsyncSession, family_id, reciter_id: str | None, age_mode) -> str:
    rid = reciter_id
    if not rid:
        settings = (
            await db.execute(select(models.FamilySettings).where(models.FamilySettings.family_id == family_id))
        ).scalar_one_or_none()
        rid = settings.reciter_id if settings else None
    return reciter_for_learning(rid, age_mode)


@router.get("/reference")
async def tahsin_reference(
    reciter_id: str | None = Query(None),
    member_id=Depends(optional_member_id),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(models.Member, member_id) if member_id else None
    age_mode = member.age_mode if member else AgeMode.adult
    rid = await _resolve_reciter(db, ctx.family_id, reciter_id, age_mode)
    audio_urls = [everyayah_url(TAHSIN_SURAH_ID, n, rid) for n in TAHSIN_AYAH_NUMBERS]
    ref_uthmani, ref_tajweed = await ayah_range_texts(db, TAHSIN_SURAH_ID, 1, 2)
    return {
        "reference_text": ref_uthmani or TAHSIN_REFERENCE,
        "text_tajweed": ref_tajweed,
        "surah_id": TAHSIN_SURAH_ID,
        "ayah_numbers": list(TAHSIN_AYAH_NUMBERS),
        "audio_urls": audio_urls,
        "reciter_id": rid,
        "status": (
            TahsinStatus.passed.value
            if ctx.role == "parent" and not member
            else (member.tahsin_status.value if member else "not_started")
        ),
        "hint": (
            "Mode orang tua — dengar dan latih bebas. Untuk setoran & penilaian, pilih profil anak dulu."
            if ctx.role == "parent" and not member
            else "Dengarkan bacaan qori, tirukan pelafalannya, lalu rekam dan kirim untuk dinilai orang tua."
        ),
    }


@router.get("/curriculum/{point}")
async def tahsin_curriculum_for_point(
    point: int,
    reciter_id: str | None = Query(None),
    member_id=Depends(optional_member_id),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    """Lima latihan untuk satu Pulau, lengkap dengan audio ayat contoh. Materi masih draf (perlu validasi ustaz)."""
    items = tahsin_curriculum.CURRICULUM.get(point)
    if not items:
        raise HTTPException(404, "Pulau tidak ditemukan")
    member = await db.get(models.Member, member_id) if member_id else None
    rid = await _resolve_reciter(db, ctx.family_id, reciter_id, member.age_mode if member else AgeMode.adult)
    out = []
    for i, it in enumerate(items, start=1):
        ex = it["example"]
        out.append({
            **it, "index": i,
            "audio_urls": tahsin_curriculum.word_urls(point, i),
            "audio_fallback_urls": tahsin_curriculum.word_urls(point, i, tahsin_curriculum.WBW_FALLBACK_BASE),
            "audio_url": everyayah_url(ex["surah_id"], ex["ayah"], rid),  # cadangan: seluruh ayat contoh
        })
    return {"point": point, "items": out, "draft": tahsin_curriculum.DRAFT}
