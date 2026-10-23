"""Pekerja pengingat: python -m app.workers.reminder_worker  (jalankan 1 proses saja)"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database import AsyncSessionLocal
from app.services import daily_sessions
from app.services.escalation import run_escalation
from app.services.reminders import run_reminders

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("reminder_worker")


async def main():
    log.info("Reminder worker berjalan (cek tiap 60 detik)")
    last_day = None
    while True:
        try:
            if last_day != daily_sessions.today():
                async with AsyncSessionLocal() as db:
                    stats_day = await daily_sessions.run_daily(db)
                    await db.commit()
                last_day = daily_sessions.today()
                log.info("sesi harian: %s", stats_day)
            async with AsyncSessionLocal() as db:
                stats = await run_reminders(db)
                await db.commit()
            if stats["members_notified"]:
                log.info("pengingat: %s", stats)
            async with AsyncSessionLocal() as db:
                esc = await run_escalation(db)
                await db.commit()
            if esc["created"]:
                log.info("eskalasi penilaian: %s", esc)
        except Exception:
            log.exception("run_reminders gagal")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
