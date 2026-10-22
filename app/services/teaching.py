"""Aturan guru-anak, izin rekaman, retensi dan penghapusan suara."""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.config import settings
from app.services import storage

DELETE_WITHIN_DAYS = 7
EXPORT_HOURS = 24


def new_code(n: int = 9) -> str:
    return secrets.token_urlsafe(n)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def active_link(db: AsyncSession, member_id: uuid.UUID) -> models.TeacherLink | None:
    return (
        await db.execute(
            select(models.TeacherLink).where(
                models.TeacherLink.member_id == member_id, models.TeacherLink.status == "active"
            )
        )
    ).scalars().first()


async def teacher_can_hear(db: AsyncSession, teacher_id: uuid.UUID, member_id: uuid.UUID) -> bool:
    link = await active_link(db, member_id)
    return bool(link and link.teacher_id == teacher_id and link.recording_consent)


def due_at(sub: models.Submission, teacher: models.Teacher) -> datetime:
    return _aware(sub.created_at) + timedelta(hours=teacher.grading_target_hours)


def is_overdue(sub: models.Submission, teacher: models.Teacher, now: datetime | None = None) -> bool:
    return sub.status == models.SubmissionStatus.pending_eval and (now or datetime.now(timezone.utc)) > due_at(sub, teacher)


async def mark_recording_deleted(db: AsyncSession, sub: models.Submission, now: datetime) -> bool:
    """Sembunyikan dari aplikasi seketika dan hapus berkas. Skor dan catatan tetap tersimpan."""
    if sub.recording_deleted_at is not None:
        return False
    storage.delete_recording(sub.family_id, sub.id)
    sub.recording_deleted_at = now
    return True


async def delete_recordings(
    db: AsyncSession, family_id: uuid.UUID, requested_by: uuid.UUID, member_id: uuid.UUID | None = None
) -> models.DeletionRequest:
    now = datetime.now(timezone.utc)
    q = select(models.Submission).where(
        models.Submission.family_id == family_id, models.Submission.recording_deleted_at.is_(None)
    )
    if member_id:
        q = q.where(models.Submission.member_id == member_id)
    count = 0
    for sub in (await db.execute(q)).scalars().all():
        if await mark_recording_deleted(db, sub, now):
            count += 1
    req = models.DeletionRequest(
        family_id=family_id,
        member_id=member_id,
        requested_by=requested_by,
        purge_due_at=now + timedelta(days=DELETE_WITHIN_DAYS),
        recording_count=count,
    )
    db.add(req)
    await db.flush()
    return req


async def purge_expired_recordings(db: AsyncSession, now: datetime | None = None) -> int:
    """Retensi: rekaman lebih tua dari recording_retention_days dihapus otomatis."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.recording_retention_days)
    subs = (
        await db.execute(
            select(models.Submission).where(
                models.Submission.recording_deleted_at.is_(None), models.Submission.created_at < cutoff
            )
        )
    ).scalars().all()
    n = 0
    for sub in subs:
        if await mark_recording_deleted(db, sub, now):
            n += 1
    return n


async def finalize_deletion_requests(db: AsyncSession, now: datetime | None = None) -> int:
    """Pastikan permintaan hapus yang jatuh tempo benar-benar selesai (berkas sudah tidak ada)."""
    now = now or datetime.now(timezone.utc)
    reqs = (
        await db.execute(select(models.DeletionRequest).where(models.DeletionRequest.status == "pending"))
    ).scalars().all()
    done = 0
    for r in reqs:
        if _aware(r.purge_due_at) <= now:
            r.status = "purged"
            done += 1
    return done
