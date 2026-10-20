"""Surat Juz 30 (Amma) — query + urutan kurikulum."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Surah
from app.services.quran_com_import import ensure_chapter_catalog

JUZ30_ID_MIN = 78
JUZ30_ID_MAX = 114


async def list_juz30_surahs(db: AsyncSession) -> list[Surah]:
    await ensure_chapter_catalog(db)
    by_juz = (
        await db.execute(select(Surah).where(Surah.juz_number == 30).order_by(Surah.curriculum_order, Surah.id))
    ).scalars().all()
    if by_juz:
        return list(by_juz)
    by_id = (
        await db.execute(
            select(Surah)
            .where(Surah.id >= JUZ30_ID_MIN, Surah.id <= JUZ30_ID_MAX)
            .order_by(Surah.curriculum_order, Surah.id)
        )
    ).scalars().all()
    if by_id:
        for row in by_id:
            if row.juz_number != 30:
                row.juz_number = 30
        await db.flush()
        return list(by_id)
    return []
