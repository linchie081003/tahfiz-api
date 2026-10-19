"""Impor seluruh 114 surat + ayat dari Quran.com (jalankan sekali atau untuk refresh)."""
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import AsyncSessionLocal
from app.services.quran_com_import import fetch_chapters, import_surah_ayahs, upsert_surah_from_chapter


async def main():
    async with httpx.AsyncClient() as client:
        chapters = await fetch_chapters(client)
        async with AsyncSessionLocal() as db:
            for ch in chapters:
                sid = int(ch["id"])
                await upsert_surah_from_chapter(db, ch)
            await db.commit()
            print(f"Metadata {len(chapters)} surat disimpan.")
            for ch in chapters:
                sid = int(ch["id"])
                print(f"Surah {sid} …", end=" ", flush=True)
                n = await import_surah_ayahs(db, sid, client)
                await db.commit()
                print(f"{n} ayat")
    print("Impor Al-Qur'an selesai.")


if __name__ == "__main__":
    asyncio.run(main())
