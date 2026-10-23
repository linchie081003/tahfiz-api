"""Eskalasi penilaian tertunda: 24, 48, 72 jam kalender sejak setoran tersimpan (MVP, tetap untuk semua guru).

Tidak pernah mengganti penilai atau meluluskan hafalan karena waktu. Berhenti begitu setoran dinilai.
Kanal MVP: notifikasi dalam aplikasi. Email menyusul setelah verifikasi alamat dan penyedia siap (keputusan F).
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services import sesi3, teaching

STAGES = (24, 48, 72)
WINDOW_DAYS = 14  # setoran lebih tua dari ini tidak dieskalasi (mencegah banjir saat pertama dijalankan)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def stage_for(hours: float) -> int | None:
    reached = [s for s in STAGES if hours >= s]
    return reached[-1] if reached else None


async def _notify(db: AsyncSession, role: str, rid: uuid.UUID, kind: str, sub: models.Submission, title: str, body: str) -> bool:
    exists = (
        await db.execute(
            select(models.AppNotification.id).where(
                models.AppNotification.recipient_role == role, models.AppNotification.recipient_id == rid,
                models.AppNotification.kind == kind, models.AppNotification.submission_id == sub.id,
            )
        )
    ).first()
    if exists:
        return False
    db.add(models.AppNotification(recipient_role=role, recipient_id=rid, kind=kind, submission_id=sub.id, member_id=sub.member_id, title=title, body=body))
    await db.flush()
    return True


async def run_escalation(db: AsyncSession, now: datetime | None = None, member_ids: list[uuid.UUID] | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    q = select(models.Submission).where(
        models.Submission.status == models.SubmissionStatus.pending_eval,
        models.Submission.created_at >= now - timedelta(days=WINDOW_DAYS),
    )
    if member_ids is not None:
        if not member_ids:
            return {"created": 0}
        q = q.where(models.Submission.member_id.in_(member_ids))
    created = 0
    for sub in (await db.execute(q)).scalars().all():
        stage = stage_for((now - _aware(sub.created_at)).total_seconds() / 3600)
        if stage is None:
            continue
        if await teaching.takeover_for(db, sub.id):
            continue  # sudah diambil alih secara manual; penilainya jelas
        member = await db.get(models.Member, sub.member_id)
        if not member:
            continue
        role, rid = await sesi3.responsible(db, sub.member_id)
        name = member.name
        if role == "teacher" and rid:
            if stage == 24:
                created += await _notify(db, "teacher", rid, "pending_24", sub, "Setoran menunggu penilaian", f"Setoran {name} sudah lebih dari 24 jam menunggu penilaian.")
            elif stage == 48:
                created += await _notify(db, "teacher", rid, "pending_48", sub, "Pengingat penilaian", f"Setoran {name} sudah lebih dari 48 jam menunggu penilaian.")
                created += await _notify(db, "parent", member.family_id, "pending_48", sub, "Penilaian guru masih tertunda", f"Setoran {name} belum dinilai guru setelah 48 jam. Guru sudah diingatkan.")
            else:
                created += await _notify(db, "parent", member.family_id, "pending_72", sub, "Penilaian masih tertunda 72 jam", f"Setoran {name} belum dinilai guru. Anda bisa mengingatkan guru, menunggu, atau menilai sendiri.")
        else:
            kind = "pending_24" if stage == 24 else "pending_48"  # orang tua penilainya: pengingat 24 dan 48 jam
            created += await _notify(db, "parent", member.family_id, kind, sub, "Setoran menunggu penilaian Anda", f"Ada setoran {name} yang menunggu penilaian.")
    return {"created": created}


async def take_over(db: AsyncSession, sub: models.Submission, parent_id: uuid.UUID, reason: str) -> models.EvaluationTakeover:
    """Orang tua mengambil alih penilaian dari guru secara manual. Mencatat penilai lama, baru, waktu, dan alasan."""
    if sub.status != models.SubmissionStatus.pending_eval:
        raise HTTPException(409, "Setoran sudah dinilai")
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(422, "Alasan pengambilalihan wajib diisi")
    link = await teaching.active_link(db, sub.member_id)
    if not link:
        raise HTTPException(409, "Tidak ada guru yang perlu digantikan")
    if await teaching.takeover_for(db, sub.id):
        raise HTTPException(409, "Setoran sudah diambil alih")
    t = models.EvaluationTakeover(
        submission_id=sub.id, from_role="teacher", from_id=link.teacher_id, to_role="parent", to_id=parent_id, reason=reason, created_by=parent_id,
    )
    db.add(t)
    await db.flush()
    return t


async def nudge_teacher(db: AsyncSession, sub: models.Submission, member: models.Member) -> bool:
    """Orang tua mengingatkan guru. Satu pengingat per setoran."""
    role, rid = await sesi3.responsible(db, sub.member_id)
    if role != "teacher" or not rid:
        raise HTTPException(409, "Tidak ada guru yang bertanggung jawab")
    if sub.status != models.SubmissionStatus.pending_eval:
        raise HTTPException(409, "Setoran sudah dinilai")
    return await _notify(db, "teacher", rid, "parent_nudge", sub, "Orang tua mengingatkan", f"Orang tua {member.name} menanyakan penilaian setoran yang masih menunggu.")
