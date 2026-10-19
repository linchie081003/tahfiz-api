from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BadgeDefinition, Member, MemberBadge, MemberStats, TahsinStatus, XpConfig

LEVEL_THRESHOLDS = [0, 100, 300, 600, 1000, 1500, 2200, 3000, 4000, 5000]
RANKS = ["Santri Pemula", "Penghafal Juz Amma", "Hafizh Muda", "Hafizh 30 Juz"]


def level_from_xp(xp: int) -> tuple[int, str, int]:
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS[1:], start=2):
        if xp >= threshold:
            level = i
    next_xp = LEVEL_THRESHOLDS[level] if level < len(LEVEL_THRESHOLDS) else LEVEL_THRESHOLDS[-1] + 1000
    rank = RANKS[min(level // 3, len(RANKS) - 1)]
    return level, rank, next_xp


async def ensure_member_stats(db: AsyncSession, member_id) -> MemberStats:
    result = await db.execute(select(MemberStats).where(MemberStats.member_id == member_id))
    stats = result.scalar_one_or_none()
    if stats:
        return stats
    stats = MemberStats(member_id=member_id)
    db.add(stats)
    await db.flush()
    return stats


async def add_xp(db: AsyncSession, member_id, activity_key: str) -> MemberStats:
    stats = await ensure_member_stats(db, member_id)
    cfg = await db.execute(select(XpConfig).where(XpConfig.activity_key == activity_key))
    row = cfg.scalar_one_or_none()
    if row:
        stats.xp += row.xp_value
    level, rank, _ = level_from_xp(stats.xp)
    stats.level = level
    stats.rank_title = rank
    today = date.today()
    if stats.last_active_date:
        diff = (today - stats.last_active_date).days
        if diff == 1:
            stats.streak_days += 1
        elif diff == 0:
            pass
        elif diff == 2 and stats.streak_freeze_remaining > 0:
            stats.streak_freeze_remaining -= 1
            stats.streak_days += 1
        else:
            stats.streak_days = 1
    else:
        stats.streak_days = 1
    stats.last_active_date = today
    await maybe_award_badges(db, member_id, stats)
    return stats


async def maybe_award_badges(db: AsyncSession, member_id, stats: MemberStats):
    member = await db.get(Member, member_id)
    if not member:
        return
    candidates: list[tuple[str, bool]] = [
        ("tahsin_lulus", member.tahsin_status == TahsinStatus.passed),
        ("murojaah_7", stats.streak_days >= 7),
    ]
    for badge_id, ok in candidates:
        if not ok:
            continue
        exists = await db.execute(
            select(MemberBadge).where(MemberBadge.member_id == member_id, MemberBadge.badge_id == badge_id)
        )
        if exists.scalar_one_or_none():
            continue
        db.add(MemberBadge(member_id=member_id, badge_id=badge_id))


async def list_badges(db: AsyncSession, member_id) -> list[dict]:
    defs = (await db.execute(select(BadgeDefinition))).scalars().all()
    earned = {
        b.badge_id
        for b in (await db.execute(select(MemberBadge).where(MemberBadge.member_id == member_id))).scalars().all()
    }
    return [{"id": d.id, "title": d.title, "description": d.description, "earned": d.id in earned} for d in defs]
