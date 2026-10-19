from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


async def ayah_range_texts(
    db: AsyncSession,
    surah_id: int,
    ayah_start: int,
    ayah_end: int | None = None,
) -> tuple[str, str | None]:
    end = ayah_end if ayah_end is not None else ayah_start
    rows = (
        await db.execute(
            select(models.Ayah)
            .where(
                models.Ayah.surah_id == surah_id,
                models.Ayah.ayah_number >= ayah_start,
                models.Ayah.ayah_number <= end,
            )
            .order_by(models.Ayah.ayah_number)
        )
    ).scalars().all()
    if not rows:
        return "", None
    uthmani = " ".join(r.text_uthmani for r in rows)
    if any(r.text_tajweed for r in rows):
        tajweed = " ".join(r.text_tajweed or r.text_uthmani for r in rows)
    else:
        tajweed = None
    return uthmani, tajweed
