"""Muat metadata surat + ayat dari Quran.com API v4 (on-demand atau batch)."""

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ayah, Surah
from app.services.surah_names_id import indonesian_surah_name


async def fetch_chapters(client: httpx.AsyncClient, *, language: str = "id") -> list[dict]:
    r = await client.get(
        "https://api.quran.com/api/v4/chapters",
        params={"language": language},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("chapters", [])


async def fetch_chapter_verses(client: httpx.AsyncClient, surah_id: int) -> list[dict]:
    url = f"https://api.quran.com/api/v4/verses/by_chapter/{surah_id}"
    params = {"per_page": 300, "words": "false", "fields": "text_uthmani,verse_key"}
    r = await client.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json().get("verses", [])


async def fetch_tajweed_map(client: httpx.AsyncClient, surah_id: int) -> dict[int, str]:
    url = "https://api.quran.com/api/v4/quran/verses/uthmani_tajweed"
    params = {"chapter_number": surah_id}
    r = await client.get(url, params=params, timeout=60)
    if r.status_code != 200:
        return {}
    out: dict[int, str] = {}
    for v in r.json().get("verses", []):
        key = v.get("verse_key", "")
        parts = key.split(":")
        if len(parts) == 2:
            out[int(parts[1])] = v.get("text_uthmani_tajweed") or v.get("text", "")
    return out


async def upsert_surah_from_chapter(db: AsyncSession, ch: dict) -> Surah:
    sid = int(ch["id"])
    juz = int(ch.get("juz_number") or 1)
    api_name = (ch.get("translated_name") or {}).get("name")
    name_id = indonesian_surah_name(sid, api_name)
    name_ar = ch.get("name_arabic") or ch.get("name_simple") or ""
    ayah_count = int(ch.get("verses_count") or 0)
    row = await db.get(Surah, sid)
    if row:
        row.name_ar = name_ar or row.name_ar
        row.name_id = name_id
        row.ayah_count = ayah_count or row.ayah_count
        row.juz_number = juz
        if sid < 78:
            row.curriculum_order = sid
        return row
    row = Surah(
        id=sid,
        name_ar=name_ar,
        name_id=name_id,
        ayah_count=ayah_count,
        juz_number=juz,
        curriculum_order=sid if sid < 78 else sid,
    )
    db.add(row)
    await db.flush()
    return row


async def import_surah_ayahs(db: AsyncSession, surah_id: int, client: httpx.AsyncClient | None = None) -> int:
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient()
    try:
        surah = await db.get(Surah, surah_id)
        if not surah:
            chapters = await fetch_chapters(client)
            ch = next((c for c in chapters if int(c["id"]) == surah_id), None)
            if not ch:
                return 0
            surah = await upsert_surah_from_chapter(db, ch)
        verses = await fetch_chapter_verses(client, surah_id)
        tajweed_map = await fetch_tajweed_map(client, surah_id)
        written = 0
        for v in verses:
            key = v.get("verse_key", "")
            ayah_no = int(key.split(":")[-1]) if ":" in key else 0
            if not ayah_no:
                continue
            text_u = v.get("text_uthmani") or ""
            row = (
                await db.execute(select(Ayah).where(Ayah.surah_id == surah_id, Ayah.ayah_number == ayah_no))
            ).scalar_one_or_none()
            taj = tajweed_map.get(ayah_no) or text_u
            if row:
                row.text_uthmani = text_u
                row.text_tajweed = taj
            else:
                db.add(
                    Ayah(
                        surah_id=surah_id,
                        ayah_number=ayah_no,
                        text_uthmani=text_u,
                        text_tajweed=taj,
                        tajwid_markup={"rules": []},
                    )
                )
            written += 1
        await db.flush()
        return written
    finally:
        if own_client:
            await client.aclose()


async def ensure_chapter_catalog(db: AsyncSession) -> None:
    count = (await db.execute(select(func.count()).select_from(Surah))).scalar_one()
    juz30 = (
        await db.execute(select(func.count()).select_from(Surah).where(Surah.juz_number == 30))
    ).scalar_one()
    if count >= 114 and juz30 > 0:
        return
    async with httpx.AsyncClient() as client:
        for ch in await fetch_chapters(client):
            await upsert_surah_from_chapter(db, ch)
    await db.commit()


async def ensure_surah_ayahs(db: AsyncSession, surah_id: int) -> None:
    surah = await db.get(Surah, surah_id)
    if not surah:
        async with httpx.AsyncClient() as client:
            chapters = await fetch_chapters(client)
            ch = next((c for c in chapters if int(c["id"]) == surah_id), None)
            if not ch:
                return
            await upsert_surah_from_chapter(db, ch)
            await db.commit()
            surah = await db.get(Surah, surah_id)
    if not surah:
        return
    loaded = (
        await db.execute(select(func.count()).select_from(Ayah).where(Ayah.surah_id == surah_id))
    ).scalar_one()
    if loaded >= surah.ayah_count:
        return
    async with httpx.AsyncClient() as client:
        await import_surah_ayahs(db, surah_id, client)
    await db.commit()
