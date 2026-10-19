from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.database import get_db
from app.deps import AuthContext, get_current_context, require_member_id
from app.services.quran_display import ayah_range_texts
from app.services.reciters import everyayah_url

router = APIRouter(prefix="/tahsin", tags=["tahsin"])

TAHSIN_SURAH_ID = 114
TAHSIN_AYAH_NUMBERS = (1, 2)
TAHSIN_REFERENCE = "قُلْ أَعُوذُ بِرَبِّ النَّاسِ مَلِكِ النَّاسِ"


async def _resolve_reciter(db: AsyncSession, family_id, reciter_id: str | None) -> str:
    if reciter_id:
        return reciter_id
    settings = (
        await db.execute(select(models.FamilySettings).where(models.FamilySettings.family_id == family_id))
    ).scalar_one_or_none()
    return settings.reciter_id if settings else "alafasy"


@router.get("/reference")
async def tahsin_reference(
    reciter_id: str | None = Query(None),
    member_id=Depends(require_member_id),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(models.Member, member_id)
    rid = await _resolve_reciter(db, ctx.family_id, reciter_id)
    audio_urls = [everyayah_url(TAHSIN_SURAH_ID, n, rid) for n in TAHSIN_AYAH_NUMBERS]
    ref_uthmani, ref_tajweed = await ayah_range_texts(db, TAHSIN_SURAH_ID, 1, 2)
    return {
        "reference_text": ref_uthmani or TAHSIN_REFERENCE,
        "text_tajweed": ref_tajweed,
        "surah_id": TAHSIN_SURAH_ID,
        "ayah_numbers": list(TAHSIN_AYAH_NUMBERS),
        "audio_urls": audio_urls,
        "reciter_id": rid,
        "status": member.tahsin_status.value if member else "not_started",
        "hint": "Dengarkan bacaan qori, tirukan pelafalannya, lalu rekam dan kirim untuk dinilai orang tua.",
    }
