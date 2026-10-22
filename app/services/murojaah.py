from datetime import date, timedelta
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MemberSurahProgress, MurojaahItem, Surah, SurahProgressStatus


async def schedule_for_passed_surah(db: AsyncSession, member_id: uuid.UUID, surah_id: int):
    exists = await db.execute(
        select(MurojaahItem).where(MurojaahItem.member_id == member_id, MurojaahItem.surah_id == surah_id)
    )
    if exists.scalar_one_or_none():
        return
    db.add(
        MurojaahItem(
            member_id=member_id,
            surah_id=surah_id,
            due_date=date.today() + timedelta(days=1),
        )
    )


async def due_items(db: AsyncSession, member_id: uuid.UUID, cap: int) -> list[MurojaahItem]:
    today = date.today()
    q = (
        select(MurojaahItem)
        .where(MurojaahItem.member_id == member_id, MurojaahItem.completed.is_(False), MurojaahItem.due_date <= today)
        .order_by(MurojaahItem.weak_score.desc(), MurojaahItem.due_date)
        .limit(cap)
    )
    return list((await db.execute(q)).scalars().all())


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
