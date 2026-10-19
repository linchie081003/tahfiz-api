import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services import storage


async def delete_member_and_data(db: AsyncSession, member_id: uuid.UUID, family_id: uuid.UUID) -> None:
    member = await db.get(models.Member, member_id)
    if not member or member.family_id != family_id:
        raise ValueError("member_not_found")

    submissions = (
        await db.execute(select(models.Submission).where(models.Submission.member_id == member_id))
    ).scalars().all()
    for sub in submissions:
        path = storage.local_recording_path(sub.family_id, sub.id)
        if path.is_file():
            path.unlink(missing_ok=True)

    await db.execute(delete(models.TahsinAttempt).where(models.TahsinAttempt.member_id == member_id))
    await db.execute(delete(models.Submission).where(models.Submission.member_id == member_id))
    await db.execute(delete(models.MurojaahItem).where(models.MurojaahItem.member_id == member_id))
    await db.execute(delete(models.MemberSurahProgress).where(models.MemberSurahProgress.member_id == member_id))
    await db.execute(delete(models.MemberBadge).where(models.MemberBadge.member_id == member_id))
    await db.execute(delete(models.Mission).where(models.Mission.member_id == member_id))
    await db.execute(delete(models.MemberStats).where(models.MemberStats.member_id == member_id))
    await db.delete(member)
