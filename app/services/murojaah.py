from datetime import date, timedelta
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.models import MemberSurahProgress, MemorizedRange, MurojaahItem, Surah, SurahProgressStatus

# Batas Sesi 1 per anak dalam ayat (usulan 4). Rentang jatuh tempo yang bersebelahan jadi satu blok latihan.
SESI1_MAX_AYAH = 10


async def schedule_for_range(db: AsyncSession, rng: MemorizedRange) -> MurojaahItem | None:
    """Jadwalkan murajaah untuk rentang lulus. Satu rentang paling banyak punya satu rantai jadwal."""
    covering = (
        await db.execute(
            select(MurojaahItem).where(
                MurojaahItem.member_id == rng.member_id,
                MurojaahItem.surah_id == rng.surah_id,
                MurojaahItem.ayah_start <= rng.ayah_start,
                MurojaahItem.ayah_end >= rng.ayah_end,
            )
        )
    ).first()
    if covering:
        return None
    item = MurojaahItem(
        member_id=rng.member_id,
        surah_id=rng.surah_id,
        due_date=date.today() + timedelta(days=1),
        range_id=rng.id,
        ayah_start=rng.ayah_start,
        ayah_end=rng.ayah_end,
    )
    db.add(item)
    await db.flush()
    return item


async def normalize_legacy_items(db: AsyncSession, member_id: uuid.UUID) -> int:
    """Item murajaah lama (per surat) menjadi rentang seluruh surat. Idempoten."""
    items = (
        await db.execute(select(MurojaahItem).where(MurojaahItem.member_id == member_id, MurojaahItem.ayah_start.is_(None)))
    ).scalars().all()
    n = 0
    for it in items:
        surah = await db.get(Surah, it.surah_id)
        if not surah:
            continue
        it.ayah_start, it.ayah_end = 1, surah.ayah_count
        n += 1
    await db.flush()
    return n


async def schedule_for_passed_surah(db: AsyncSession, member_id: uuid.UUID, surah_id: int):
    """Tetap tersedia untuk kompatibilitas: jadwalkan seluruh surat sebagai satu rentang."""
    surah = await db.get(Surah, surah_id)
    if not surah:
        return
    exists = (
        await db.execute(select(MurojaahItem).where(MurojaahItem.member_id == member_id, MurojaahItem.surah_id == surah_id))
    ).first()
    if exists:
        return
    db.add(
        MurojaahItem(member_id=member_id, surah_id=surah_id, due_date=date.today() + timedelta(days=1), ayah_start=1, ayah_end=surah.ayah_count)
    )


async def due_items(db: AsyncSession, member_id: uuid.UUID, cap: int) -> list[MurojaahItem]:
    """Rentang yang sudah lulus boleh dimurajaah tanpa menunggu surat selesai (item hanya dibuat saat rentang lulus)."""
    today = date.today()
    q = (
        select(MurojaahItem)
        .where(MurojaahItem.member_id == member_id, MurojaahItem.completed.is_(False), MurojaahItem.due_date <= today)
        .order_by(MurojaahItem.weak_score.desc(), MurojaahItem.due_date, MurojaahItem.surah_id, MurojaahItem.ayah_start)
        .limit(cap)
    )
    return list((await db.execute(q)).scalars().all())


def pick_for_session(items: list[MurojaahItem], max_ayah: int = SESI1_MAX_AYAH) -> list[MurojaahItem]:
    """Pilih rentang sesuai prioritas sampai batas ayat. Minimal satu rentang selalu diambil."""
    out: list[MurojaahItem] = []
    total = 0
    for it in items:
        size = (it.ayah_end or 1) - (it.ayah_start or 1) + 1
        if out and total + size > max_ayah:
            continue
        out.append(it)
        total += size
        if total >= max_ayah:
            break
    return out


def to_blocks(items: list[MurojaahItem]) -> list[dict]:
    """Gabungkan rentang bersebelahan jadi blok latihan sementara. Data dan jadwal asli tidak diubah."""
    blocks: list[dict] = []
    for it in sorted(items, key=lambda i: (i.surah_id, i.ayah_start or 1)):
        a, b = it.ayah_start or 1, it.ayah_end or it.ayah_start or 1
        last = blocks[-1] if blocks else None
        if last and last["surah_id"] == it.surah_id and a <= last["ayah_end"] + 1:
            last["ayah_end"] = max(last["ayah_end"], b)
            last["items"].append({"id": it.id, "ayah_start": a, "ayah_end": b})
        else:
            blocks.append({"surah_id": it.surah_id, "ayah_start": a, "ayah_end": b, "items": [{"id": it.id, "ayah_start": a, "ayah_end": b}]})
    return blocks


async def complete_item(db: AsyncSession, item: MurojaahItem, rating: str, strong_days: int = 14):
    """Kuat: 7 atau 14 hari (atur per anak). Cukup: 7 hari. Lemah: besok."""
    if rating == "lupa":
        item.weak_score += 2
        item.interval_days = 1
    elif rating == "ragu":
        item.weak_score += 1
        item.interval_days = 7
    else:
        item.interval_days = strong_days
        item.weak_score = max(0, item.weak_score - 1)
    item.completed = True
    db.add(
        MurojaahItem(
            member_id=item.member_id,
            surah_id=item.surah_id,
            due_date=date.today() + timedelta(days=item.interval_days),
            ease_factor=item.ease_factor,
            interval_days=item.interval_days,
            weak_score=item.weak_score,
            range_id=item.range_id,
            ayah_start=item.ayah_start,
            ayah_end=item.ayah_end,
        )
    )


async def seed_murojaah_from_progress(db: AsyncSession, member_id: uuid.UUID):
    passed = await db.execute(
        select(MemberSurahProgress).where(
            MemberSurahProgress.member_id == member_id,
            MemberSurahProgress.status == SurahProgressStatus.passed,
        )
    )
    for row in passed.scalars().all():
        await schedule_for_passed_surah(db, member_id, row.surah_id)
