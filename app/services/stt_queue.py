"""Antrean pra-cek STT di database: idempoten, ada timeout, retry berjeda, dan kegagalan yang bisa dipulihkan.

Alur:
- `enqueue` membuat (atau memakai ulang) satu pekerjaan per setoran. Memanggilnya berkali-kali tidak menggandakan.
- Pekerja mengklaim pekerjaan yang jatuh tempo dengan FOR UPDATE SKIP LOCKED; pekerjaan `processing` yang kuncinya
  kedaluwarsa (pekerja mati) diklaim ulang. Tiap klaim menambah `attempts`.
- Kegagalan sementara (jaringan, kuota, error API, timeout) dijadwalkan ulang dengan jeda berlipat sampai
  `max_attempts`; setelah itu pekerjaan `failed` dan setoran ditandai `ai_status = failed` dengan `retryable: true`.
  Penilaian TIDAK terblokir: setoran tetap bisa dinilai tanpa pra-cek, dan orang tua bisa mengantrekan ulang.
- Kegagalan permanen (tanpa izin, audio kosong, kunci ditolak, tidak ada ucapan) langsung dinyatakan "tidak tersedia".
- Hasil hanya ditulis bila `ai_status` belum `completed`, jadi pekerjaan ganda atau terlambat tidak menimpa hasil.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.config import settings
from app.services import storage, stt
from app.services.ai_analysis import analyze_recording, unavailable

log = logging.getLogger("stt_queue")

RETRYABLE = {"stt_network", "stt_quota", "stt_api", "stt_timeout"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def has_consent(db: AsyncSession, family_id: uuid.UUID) -> bool:
    row = (await db.execute(select(models.FamilyAiConsent).where(models.FamilyAiConsent.family_id == family_id))).scalar_one_or_none()
    return row is not None


async def job_of(db: AsyncSession, submission_id: uuid.UUID) -> models.SttJob | None:
    return (await db.execute(select(models.SttJob).where(models.SttJob.submission_id == submission_id))).scalar_one_or_none()


async def enqueue(db: AsyncSession, sub: models.Submission, *, force: bool = False) -> models.SttJob:
    """Antrekan pra-cek. Idempoten: pekerjaan yang sedang antre/diproses tidak diubah; `force` mengantrekan ulang
    pekerjaan yang sudah selesai atau gagal."""
    job = await job_of(db, sub.id)
    if job is None:
        job = models.SttJob(submission_id=sub.id, status="queued", attempts=0, max_attempts=settings.stt_job_max_attempts, next_attempt_at=_now())
        db.add(job)
    elif force and job.status in ("done", "failed"):
        job.status, job.attempts, job.last_error = "queued", 0, None
        job.max_attempts = settings.stt_job_max_attempts
        job.next_attempt_at, job.locked_until, job.finished_at = _now(), None, None
    if job.status in ("queued", "processing"):
        sub.ai_status = "queued"
    await db.flush()
    return job


def _backoff(attempts: int) -> timedelta:
    secs = min(settings.stt_job_backoff_seconds * (2 ** max(attempts - 1, 0)), settings.stt_job_backoff_max_seconds)
    return timedelta(seconds=secs)


async def _finish(db: AsyncSession, job: models.SttJob, sub: models.Submission | None, insights: dict | None, ai_status: str, status: str, err: str | None = None) -> None:
    job.status, job.last_error, job.finished_at, job.locked_until = status, err, _now(), None
    if sub is not None and sub.ai_status != "completed":  # jangan menimpa hasil yang sudah ada
        if insights is not None:
            sub.ai_insights = insights
        sub.ai_status = ai_status
    await db.flush()


async def _fail_or_retry(db: AsyncSession, job: models.SttJob, sub: models.Submission | None, err: str) -> str:
    if job.attempts >= job.max_attempts:
        await _finish(db, job, sub, {**unavailable(err), "retryable": True}, "failed", "failed", err)
        return "failed"
    job.status, job.last_error, job.locked_until = "queued", err, None
    job.next_attempt_at = _now() + _backoff(job.attempts)
    await db.flush()
    return "retry"


async def claim_next(db: AsyncSession, now: datetime | None = None) -> models.SttJob | None:
    now = now or _now()
    while True:
        job = (
            await db.execute(
                select(models.SttJob)
                .where(
                    or_(
                        and_(models.SttJob.status == "queued", models.SttJob.next_attempt_at <= now),
                        and_(models.SttJob.status == "processing", models.SttJob.locked_until < now),
                    )
                )
                .order_by(models.SttJob.next_attempt_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if job is None:
            return None
        if job.attempts >= job.max_attempts:  # pekerja berulang mati di tengah proses: jangan diulang selamanya
            sub = await db.get(models.Submission, job.submission_id)
            await _finish(db, job, sub, {**unavailable(job.last_error or "stt_timeout"), "retryable": True}, "failed", "failed", job.last_error or "stt_timeout")
            continue
        job.status, job.attempts = "processing", job.attempts + 1
        job.locked_until = now + timedelta(seconds=settings.stt_job_timeout_seconds + 30)
        await db.flush()
        return job


async def run_job(db: AsyncSession, job: models.SttJob) -> str:
    """Jalankan satu pekerjaan yang sudah diklaim. Mengembalikan done | retry | failed | skipped."""
    sub = await db.get(models.Submission, job.submission_id)
    if sub is None or sub.status == models.SubmissionStatus.superseded or sub.ai_status == "completed":
        await _finish(db, job, sub, None, "completed", "done")
        return "skipped"
    if sub.recording_deleted_at is not None:
        await _finish(db, job, sub, unavailable("recording_deleted"), "completed", "done")
        return "done"
    if not await has_consent(db, sub.family_id):  # persetujuan dicabut setelah antre: suara tidak dikirim
        await _finish(db, job, sub, unavailable("no_consent"), "completed", "done")
        return "done"
    audio = await asyncio.to_thread(storage.read_recording, sub.family_id, sub.id)
    if not audio:
        await _finish(db, job, sub, unavailable("empty_audio"), "completed", "done", "empty_audio")
        return "done"

    markup = None
    if sub.surah_id and sub.ayah_start:
        ayah = (await db.execute(select(models.Ayah).where(models.Ayah.surah_id == sub.surah_id, models.Ayah.ayah_number == sub.ayah_start))).scalar_one_or_none()
        markup = ayah.tajwid_markup if ayah else None
    reference, sid = sub.reference_text, sub.id

    try:
        res = await asyncio.wait_for(stt.transcribe(audio, "audio/webm", reference_hint=reference), timeout=settings.stt_job_timeout_seconds)
        text, failure = res.text, res.failure
    except asyncio.TimeoutError:
        text, failure = None, "stt_timeout"
    except Exception as e:  # noqa: BLE001
        log.warning("STT melempar %s", type(e).__name__)
        text, failure = None, "stt_api"

    sub = await db.get(models.Submission, sid)  # data bisa berubah selama menunggu STT
    await db.refresh(sub)
    if sub.ai_status == "completed" or sub.status == models.SubmissionStatus.superseded:
        await _finish(db, job, sub, None, "completed", "done")
        return "skipped"
    if text:
        await _finish(db, job, sub, analyze_recording(reference_text=reference, tajwid_markup=markup, transcript=text), "completed", "done")
        return "done"
    reason = failure or "no_transcript"
    if reason in RETRYABLE:
        return await _fail_or_retry(db, job, sub, reason)
    await _finish(db, job, sub, unavailable(reason), "completed", "done", reason)  # permanen: tidak dicoba lagi
    return "done"


async def process_due(db: AsyncSession, limit: int = 10) -> dict:
    """Proses pekerjaan yang jatuh tempo. Commit per pekerjaan agar hasilnya tidak hilang bila pekerja berhenti."""
    stats = {"done": 0, "retry": 0, "failed": 0, "skipped": 0}
    for _ in range(limit):
        job = await claim_next(db)
        if job is None:
            break
        await db.commit()  # klaim tampak oleh pekerja lain sebelum STT yang lama dimulai
        job = await db.get(models.SttJob, job.id)
        try:
            outcome = await run_job(db, job)
        except Exception:  # noqa: BLE001 — jangan matikan pekerja karena satu setoran
            log.exception("pekerjaan STT %s gagal tak terduga", job.id)
            await db.rollback()
            job = await db.get(models.SttJob, job.id)
            sub = await db.get(models.Submission, job.submission_id)
            outcome = await _fail_or_retry(db, job, sub, "stt_api")
        stats[outcome if outcome in stats else "done"] += 1
        await db.commit()
    return stats


async def run_forever(poll_seconds: float = 5.0) -> None:
    from app.database import AsyncSessionLocal

    log.info("Pekerja STT berjalan (poll %ss)", poll_seconds)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                stats = await process_due(db)
            if any(stats.values()):
                log.info("pra-cek: %s", stats)
                continue
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("pekerja STT: putaran gagal")
        await asyncio.sleep(poll_seconds)
