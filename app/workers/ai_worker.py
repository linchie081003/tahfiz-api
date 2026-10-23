"""Pekerja pra-cek STT: python -m app.workers.ai_worker

Antrean ada di tabel stt_jobs (bukan Redis), tahan restart. Bila rekaman disimpan di disk lokal, pekerja harus berjalan di
host yang sama dengan API (atau pakai STT_INLINE_WORKER=true dan tidak perlu proses terpisah); dengan S3 boleh terpisah.
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services import stt_queue

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    asyncio.run(stt_queue.run_forever())
