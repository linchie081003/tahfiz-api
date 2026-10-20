"""Pekerja pengingat: python -m app.workers.reminder_worker  (jalankan 1 proses saja)"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database import AsyncSessionLocal
from app.services.reminders import run_reminders

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("reminder_worker")


async def main():
    log.info("Reminder worker berjalan (cek tiap 60 detik)")
    while True:
        try:
            async with AsyncSessionLocal() as db:
                stats = await run_reminders(db)
                await db.commit()
            if stats["members_notified"]:
                log.info("pengingat: %s", stats)
        except Exception:
            log.exception("run_reminders gagal")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
