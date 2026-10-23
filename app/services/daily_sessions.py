"""Catatan sesi harian: bukti sesi mana yang berlaku bagi seorang anak pada suatu hari dan hasilnya.

Tiga jenis sesi:
- sesi1 (murajaah): berlaku hanya bila ada murajaah jatuh tempo.
- sesi2 (ziyadah): jalur inti; berlaku selama Hafalan terbuka dan ada surat aktif.
- sesi3 (penguatan): berlaku bila ada sampel ayat yang memenuhi syarat.

Status: available | completed | missed | not_applicable | disabled_manually.
Hanya orang tua yang mematikan atau menyalakan sesi, dengan alasan. Hari yang sudah lewat ditutup oleh `close_days`:
sesi yang masih available menjadi missed. KPI konsistensi = completed / (completed + missed); sesi tidak berlaku
atau dimatikan tidak dihitung, begitu pula hari yang masih berjalan.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services import murojaah, progress, sesi3

KINDS = ("sesi1", "sesi2", "sesi3")
AVAILABLE, COMPLETED, MISSED, NOT_APPLICABLE, DISABLED = "available", "completed", "missed", "not_applicable", "disabled_manually"
FINAL = (COMPLETED, MISSED)


def today() -> date:
    return date.today()


async def applicability(db: AsyncSession, member: models.Member, day: date) -> dict[str, tuple[bool, str | None]]:
    """Apakah tiap sesi berlaku bagi anak ini (alasan bila tidak). Dihitung dari keadaan saat ini."""
    out: dict[str, tuple[bool, str | None]] = {}
    due = (
        await db.execute(
            select(models.MurojaahItem.id)
            .where(models.MurojaahItem.member_id == member.id, models.MurojaahItem.completed.is_(False), models.MurojaahItem.due_date <= day)
            .limit(1)
        )
    ).first()
    out["sesi1"] = (True, None) if due else (False, "Tidak ada murajaah yang jatuh tempo")
    if not await progress.hafalan_unlocked(db, member):
        out["sesi2"] = (False, "Hafalan belum terbuka (Tahsin wajib belum lulus)")
    elif not await progress.get_active_surah(db, member.id):
        out["sesi2"] = (False, "Belum ada surat aktif")
    else:
        out["sesi2"] = (True, None)
    built = await sesi3.build(db, member.id)
    out["sesi3"] = (True, None) if built.get("sample") else (False, "Belum ada ayat hafalan baru yang memenuhi syarat untuk dikuatkan")
    return out


async def _row(db: AsyncSession, member_id: uuid.UUID, day: date, kind: str) -> models.DailySession | None:
    return (
        await db.execute(
            select(models.DailySession).where(models.DailySession.member_id == member_id, models.DailySession.day == day, models.DailySession.kind == kind)
        )
    ).scalar_one_or_none()


async def disabled_reason(db: AsyncSession, member_id: uuid.UUID, kind: str, day: date | None = None) -> str | None:
    """Alasan bila orang tua mematikan sesi ini hari ini (tanpa membuat baris baru); selain itu None."""
    row = await _row(db, member_id, day or today(), kind)
    return (row.reason or "Dimatikan orang tua") if row and row.status == DISABLED else None


async def ensure_day(db: AsyncSession, member: models.Member, day: date | None = None) -> list[models.DailySession]:
    """Pastikan tiga baris sesi untuk hari itu ada. Sesi yang sudah available/selesai/terlewat/dimatikan tidak berubah;
    not_applicable bisa naik menjadi available bila syaratnya terpenuhi di hari yang sama."""
    day = day or today()
    app = await applicability(db, member, day) if day >= today() else None
    rows: list[models.DailySession] = []
    for kind in KINDS:
        row = await _row(db, member.id, day, kind)
        if row is None:
            ok, why = app[kind] if app else (False, "Tidak tercatat")
            row = models.DailySession(
                member_id=member.id, family_id=member.family_id, day=day, kind=kind,
                status=AVAILABLE if ok else NOT_APPLICABLE, reason=None if ok else why,
            )
            db.add(row)
        elif row.status == NOT_APPLICABLE and app and app[kind][0]:
            row.status, row.reason = AVAILABLE, None
        elif row.status == NOT_APPLICABLE and app and row.reason != app[kind][1]:
            row.reason = app[kind][1]
        rows.append(row)
    await db.flush()
    return rows


async def mark_completed(
    db: AsyncSession, member: models.Member, kind: str, *, activity_type: str, activity_id: uuid.UUID | None, ayah: int = 0, day: date | None = None,
) -> models.DailySession:
    """Catat aktivitas sesi. Sesi1 selesai setelah batas ayat tercapai atau murajaah jatuh tempo habis."""
    from datetime import datetime, timezone

    day = day or today()
    await ensure_day(db, member, day)
    row = await _row(db, member.id, day, kind)
    row.activity_type, row.activity_id = activity_type, activity_id or row.activity_id
    row.ayah_done = (row.ayah_done or 0) + ayah
    if row.status in (DISABLED,):
        await db.flush()
        return row  # aktivitas tetap tercatat, tetapi status tetap dimatikan orang tua
    done = True
    if kind == "sesi1":
        remaining = (
            await db.execute(
                select(models.MurojaahItem.id)
                .where(models.MurojaahItem.member_id == member.id, models.MurojaahItem.completed.is_(False), models.MurojaahItem.due_date <= day)
                .limit(1)
            )
        ).first()
        done = row.ayah_done >= murojaah.SESI1_MAX_AYAH or remaining is None
    if done and row.status != COMPLETED:
        row.status, row.reason = COMPLETED, None
        row.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return row


async def disable(db: AsyncSession, member: models.Member, kind: str, day: date, reason: str, by: uuid.UUID | None) -> models.DailySession:
    if kind not in KINDS:
        raise HTTPException(404, "Jenis sesi tidak dikenal")
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(422, "Alasan mematikan sesi wajib diisi")
    if day < today():
        raise HTTPException(409, "Hari yang sudah lewat tidak bisa diubah")
    await ensure_day(db, member, day)
    row = await _row(db, member.id, day, kind)
    if row.status == COMPLETED:
        raise HTTPException(409, "Sesi ini sudah selesai")
    row.status, row.reason, row.decided_by = DISABLED, reason, by
    await db.flush()
    return row


async def enable(db: AsyncSession, member: models.Member, kind: str, day: date, by: uuid.UUID | None) -> models.DailySession:
    if kind not in KINDS:
        raise HTTPException(404, "Jenis sesi tidak dikenal")
    if day < today():
        raise HTTPException(409, "Hari yang sudah lewat tidak bisa diubah")
    await ensure_day(db, member, day)
    row = await _row(db, member.id, day, kind)
    if row.status != DISABLED:
        raise HTTPException(409, "Sesi ini tidak sedang dimatikan")
    ok, why = (await applicability(db, member, day))[kind]
    row.status, row.reason, row.decided_by = (AVAILABLE if ok else NOT_APPLICABLE), (None if ok else why), by
    await db.flush()
    return row


async def close_days(db: AsyncSession, before: date | None = None) -> int:
    """Tutup hari yang sudah lewat: sesi yang masih available menjadi missed."""
    before = before or today()
    rows = (await db.execute(select(models.DailySession).where(models.DailySession.day < before, models.DailySession.status == AVAILABLE))).scalars().all()
    for r in rows:
        r.status = MISSED
    await db.flush()
    return len(rows)


async def run_daily(db: AsyncSession) -> dict:
    """Dipanggil pekerja latar sekali sehari (aman diulang): tutup kemarin, siapkan baris hari ini untuk semua anak."""
    closed = await close_days(db)
    members = (await db.execute(select(models.Member))).scalars().all()
    for m in members:
        await ensure_day(db, m, today())
    return {"closed": closed, "members": len(members)}


async def consistency(db: AsyncSession, member_id: uuid.UUID, start: date, end: date) -> dict:
    rows = (
        await db.execute(
            select(models.DailySession).where(models.DailySession.member_id == member_id, models.DailySession.day >= start, models.DailySession.day <= end)
        )
    ).scalars().all()
    per: dict[str, dict] = {k: {"completed": 0, "missed": 0, "not_applicable": 0, "disabled_manually": 0, "open": 0} for k in KINDS}
    for r in rows:
        bucket = per[r.kind]
        if r.status == AVAILABLE:
            # hari yang sudah lewat tapi belum ditutup pekerja dihitung terlewat; hari ini masih berjalan
            bucket["missed" if r.day < today() else "open"] += 1
        else:
            bucket[r.status] += 1
    for b in per.values():
        denom = b["completed"] + b["missed"]
        b["rate"] = round(b["completed"] / denom, 3) if denom else None
    comp = sum(b["completed"] for b in per.values())
    den = comp + sum(b["missed"] for b in per.values())
    return {"from": start, "to": end, "per_kind": per, "rate": round(comp / den, 3) if den else None, "completed": comp, "applicable_closed": den}
