"""Redis worker: python -m app.workers.ai_worker"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import redis.asyncio as aioredis

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Submission, SubmissionStatus
from app.services.ai_analysis import unavailable


async def process_one(submission_id: str):
    async with AsyncSessionLocal() as db:
        sub = await db.get(Submission, submission_id)
        if not sub:
            return
        # Pra-cek kini diproses langsung saat setor (butuh audio + persetujuan keluarga).
        # Worker tidak boleh menimpa hasilnya dengan nilai karangan.
        if sub.ai_status == "completed" or sub.status == SubmissionStatus.superseded:
            return
        sub.ai_insights = unavailable("worker")
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
