"""Perbarui name_id semua surat ke bahasa Indonesia."""
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Surah
from app.services.quran_com_import import fetch_chapters, upsert_surah_from_chapter


async def main():
    async with httpx.AsyncClient() as client:
        chapters = await fetch_chapters(client, language="id")
        async with AsyncSessionLocal() as db:
            for ch in chapters:
                await upsert_surah_from_chapter(db, ch)
            await db.commit()
            rows = (await db.execute(select(Surah).order_by(Surah.id))).scalars().all()
            print(f"Diperbarui {len(rows)} surat (contoh: 114 = {rows[-1].name_id})")


if __name__ == "__main__":
    asyncio.run(main())
