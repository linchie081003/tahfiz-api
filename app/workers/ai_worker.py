"""Redis worker: python -m app.workers.ai_worker"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import redis.asyncio as aioredis
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Ayah, Submission, SubmissionStatus
from app.services.ai_analysis import analyze_recording, mock_transcript_from_reference


async def process_one(submission_id: str):
    async with AsyncSessionLocal() as db:
        sub = await db.get(Submission, submission_id)
        if not sub:
            return
        markup = None
        if sub.surah_id and sub.ayah_start:
            ayah = (
                await db.execute(
                    select(Ayah).where(Ayah.surah_id == sub.surah_id, Ayah.ayah_number == sub.ayah_start)
                )
            ).scalar_one_or_none()
            markup = ayah.tajwid_markup if ayah else None
        transcript = mock_transcript_from_reference(sub.reference_text)
        sub.ai_insights = analyze_recording(
            reference_text=sub.reference_text, tajwid_markup=markup, transcript=transcript
        )
        sub.ai_status = "completed"
        sub.status = SubmissionStatus.pending_eval
        await db.commit()


async def main():
    r = aioredis.from_url(settings.redis_url)
    print("AI worker listening on hafiz:ai_jobs")
    while True:
        _, raw = await r.brpop("hafiz:ai_jobs", timeout=5)
        if raw:
            await process_one(raw.decode())


if __name__ == "__main__":
    asyncio.run(main())
