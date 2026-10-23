from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import badges
from app.models import BadgeDefinition, Member, MemberBadge, MemberStats, TahsinStatus, XpConfig

# Data rujukan yang dibutuhkan kode; dijamin ada walau skrip seed tidak pernah dijalankan (mis. di produksi).
REFERENCE_BADGES = [(c[0], c[1], c[2], c[3]) for c in badges.CATALOG]
REFERENCE_XP = [
    ("setoran_lulus", 30, "Setoran lulus"),
    ("murojaah_done", 15, "Murojaah selesai"),
    ("tahsin_lulus", 50, "Tahsin lulus"),
    ("daily_activity", 5, "Aktivitas harian"),
    ("sambung_benar", 3, "Sambung ayat benar"),
    ("sambung_selesai", 2, "Sambung ayat selesai"),
]


async def ensure_reference_data(db: AsyncSession) -> None:
    """Idempoten: menambah lencana dan konfigurasi XP yang belum ada, tanpa mengubah yang sudah ada."""
    have_b = {b.id: b for b in (await db.execute(select(BadgeDefinition))).scalars().all()}
    for bid, title, desc, req in REFERENCE_BADGES:
        row = have_b.get(bid)
        if row is None:
            db.add(BadgeDefinition(id=bid, title=title, description=desc, requirement_key=req))
        elif (row.title, row.description, row.requirement_key) != (title, desc, req):
            row.title, row.description, row.requirement_key = title, desc, req  # rujukan diperbarui
    have_x = {r for r in (await db.execute(select(XpConfig.activity_key))).scalars().all()}
    for key, val, label in REFERENCE_XP:
        if key not in have_x:
            db.add(XpConfig(activity_key=key, xp_value=val, label=label))
    await db.flush()


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
    await ensure_reference_data(db)
    await badges.award(db, member, stats)


async def list_badges(db: AsyncSession, member_id) -> list[dict]:
    member = await db.get(Member, member_id)
    stats = await ensure_member_stats(db, member_id)
    await ensure_reference_data(db)
    m = await badges.award(db, member, stats)  # menyusul kemajuan lama; idempoten
    defs = {d.id: d for d in (await db.execute(select(BadgeDefinition))).scalars().all()}
    got = {b.badge_id: b for b in (await db.execute(select(MemberBadge).where(MemberBadge.member_id == member_id))).scalars().all()}
    out = []
    for bid, title, desc, kind, metric, target in badges.CATALOG:
        d = defs.get(bid)
        earned = bid in got
        out.append({
            "id": bid, "title": d.title if d else title, "description": d.description if d else desc, "earned": earned, "kind": kind,
            "earned_at": got[bid].earned_at if earned else None,
            "progress": target if earned else min(m.get(metric, 0), target), "target": target,
        })
    return out
