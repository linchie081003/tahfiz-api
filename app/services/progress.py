import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Member, MemberSurahProgress, Surah, SurahProgressStatus, TahsinStatus


async def init_member_progress(db: AsyncSession, member_id: uuid.UUID):
    surahs = (
        await db.execute(select(Surah).where(Surah.juz_number == 30).order_by(Surah.curriculum_order))
    ).scalars().all()
    for i, surah in enumerate(surahs):
        status = SurahProgressStatus.in_progress if i == 0 else SurahProgressStatus.locked
        db.add(MemberSurahProgress(member_id=member_id, surah_id=surah.id, status=status, current_ayah=1))


async def can_access_ziyadah(member: Member) -> bool:
    return member.tahsin_status == TahsinStatus.passed


async def hafalan_unlocked(db: AsyncSession, member: Member) -> bool:
    """Hafalan dan murajaah terbuka jika 3 Pulau wajib tahsin lulus, atau jika diatur paralel (orang tua atau guru)."""
    if member.tahsin_status == TahsinStatus.passed:
        return True
    from app.models import MemberSettings

    ms = (await db.execute(select(MemberSettings).where(MemberSettings.member_id == member.id))).scalar_one_or_none()
    return bool(ms and ms.parallel_hafalan)


async def get_active_surah(db: AsyncSession, member_id: uuid.UUID) -> MemberSurahProgress | None:
    q = (
        select(MemberSurahProgress)
        .where(
            MemberSurahProgress.member_id == member_id,
            MemberSurahProgress.status.in_([SurahProgressStatus.in_progress, SurahProgressStatus.needs_retry]),
        )
        .order_by(MemberSurahProgress.id)
        .limit(1)
    )
    return (await db.execute(q)).scalar_one_or_none()


async def unlock_next_surah(db: AsyncSession, member_id: uuid.UUID, current_surah_id: int):
    current = await db.execute(
        select(Surah).where(Surah.id == current_surah_id)
    )
    cur = current.scalar_one()
    nxt = await db.execute(
        select(Surah).where(Surah.juz_number == 30, Surah.curriculum_order == cur.curriculum_order + 1)
    )
    next_surah = nxt.scalar_one_or_none()
    if not next_surah:
        return
    prog = await db.execute(
        select(MemberSurahProgress).where(
            MemberSurahProgress.member_id == member_id, MemberSurahProgress.surah_id == next_surah.id
        )
    )
    row = prog.scalar_one_or_none()
    if row and row.status == SurahProgressStatus.locked:
        row.status = SurahProgressStatus.in_progress
