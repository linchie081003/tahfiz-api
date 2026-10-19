"""Ambil teks Uthmani + tajwid dari Quran.com (API v4) untuk surah Juz 30."""
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Ayah, Surah

JUZ30_SURAH_IDS = list(range(78, 115))


async def fetch_chapter(client: httpx.AsyncClient, surah_id: int) -> list[dict]:
    url = f"https://api.quran.com/api/v4/verses/by_chapter/{surah_id}"
    params = {"per_page": 300, "words": "false", "fields": "text_uthmani,verse_key"}
    r = await client.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json().get("verses", [])


async def fetch_tajweed(client: httpx.AsyncClient, surah_id: int) -> dict[int, str]:
    url = "https://api.quran.com/api/v4/quran/verses/uthmani_tajweed"
    params = {"chapter_number": surah_id}
    r = await client.get(url, params=params, timeout=60)
    if r.status_code != 200:
        return {}
    verses = r.json().get("verses", [])
    out: dict[int, str] = {}
    for v in verses:
        key = v.get("verse_key", "")
        parts = key.split(":")
        if len(parts) == 2:
            out[int(parts[1])] = v.get("text_uthmani_tajweed") or v.get("text", "")
    return out


async def main():
    async with httpx.AsyncClient() as client:
        async with AsyncSessionLocal() as db:
            for sid in JUZ30_SURAH_IDS:
                surah = await db.get(Surah, sid)
                if not surah:
                    continue
                print(f"Surah {sid} …")
                try:
                    verses = await fetch_chapter(client, sid)
                    tajweed_map = await fetch_tajweed(client, sid)
                except Exception as e:
                    print(f"  gagal fetch: {e}")
                    continue
                for v in verses:
                    key = v.get("verse_key", "")
                    ayah_no = int(key.split(":")[-1]) if ":" in key else 0
                    if not ayah_no:
                        continue
                    text_u = v.get("text_uthmani") or ""
                    row = (
                        await db.execute(select(Ayah).where(Ayah.surah_id == sid, Ayah.ayah_number == ayah_no))
                    ).scalar_one_or_none()
                    if row:
                        row.text_uthmani = text_u
                        row.text_tajweed = tajweed_map.get(ayah_no) or text_u
                    else:
                        db.add(
                            Ayah(
                                surah_id=sid,
                                ayah_number=ayah_no,
                                text_uthmani=text_u,
                                text_tajweed=tajweed_map.get(ayah_no) or text_u,
                                tajwid_markup={"rules": []},
                            )
                        )
            await db.commit()
    print("Enrich selesai — teks ayat diperbarui dari Quran.com")


if __name__ == "__main__":
    asyncio.run(main())
