"""Antrean verifikasi manual untuk hafalan lama yang tidak punya bukti penilaian lulus.

Rentang berstatus `unverified` tidak dihitung sebagai hafalan lulus (progres, murajaah, lencana, dasbor). Penilai
(orang tua, atau guru yang terhubung) memutuskan: lulus (jadi `passed`, murajaah dijadwalkan) atau tolak
(`rejected`, tetap tercatat; progres dihitung ulang). Dasar keputusan wajib diisi dan disimpan bersama pelakunya.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services import corrections, murojaah
from app.services.surah_translit import surah_name


async def pending_for_member(db: AsyncSession, member_id: uuid.UUID) -> list[models.MemorizedRange]:
    return list(
        (
            await db.execute(
                select(models.MemorizedRange)
                .where(models.MemorizedRange.member_id == member_id, models.MemorizedRange.status == "unverified")
                .order_by(models.MemorizedRange.surah_id, models.MemorizedRange.ayah_start)
            )
        ).scalars().all()
    )


async def count_pending(db: AsyncSession, member_id: uuid.UUID) -> int:
    return len(await pending_for_member(db, member_id))


async def as_dicts(db: AsyncSession, member: models.Member) -> list[dict]:
    out = []
    for r in await pending_for_member(db, member.id):
        surah = await db.get(models.Surah, r.surah_id)
        out.append({
            "id": r.id, "member_id": member.id, "member_name": member.name, "surah_id": r.surah_id,
            "surah_name": surah_name(r.surah_id, surah.name_id if surah else ""),
            "ayah_start": r.ayah_start, "ayah_end": r.ayah_end, "note": r.note,
        })
    return out


async def resolve(
    db: AsyncSession, rng: models.MemorizedRange, *, decision: str, note: str, by: uuid.UUID | None, role: str,
) -> models.MemorizedRange:
    if rng.status != "unverified":
        raise HTTPException(409, "Rentang ini sudah diputuskan atau tidak perlu verifikasi")
    note = (note or "").strip()
    if not note:
        raise HTTPException(422, "Dasar keputusan wajib diisi")
    if decision not in ("lulus", "tolak"):
        raise HTTPException(422, "Keputusan harus lulus atau tolak")
    member = await db.get(models.Member, rng.member_id)
    rng.verified_by, rng.verified_role, rng.verified_at = by, role, datetime.now(timezone.utc)
    rng.note = f"{rng.note or ''}\nKeputusan: {decision}. {note}".strip()
    if decision == "lulus":
        rng.status, rng.source = "passed", "verified"
        await db.flush()
        await murojaah.schedule_for_range(db, rng)
        await corrections._recompute_progress(db, member.id, rng.surah_id, True)
    else:
        rng.status = "rejected"
        await db.flush()
        await corrections._recompute_progress(db, member.id, rng.surah_id, False, (rng.ayah_start, rng.ayah_end))
    await db.flush()
    return rng
