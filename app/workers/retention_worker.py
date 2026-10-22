"""Jalankan harian: python -m app.workers.retention_worker  (hapus rekaman kedaluwarsa dan selesaikan permintaan hapus)."""
import asyncio
import logging

from app.database import AsyncSessionLocal
from app.services import teaching

log = logging.getLogger(__name__)


async def run_once() -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        expired = await teaching.purge_expired_recordings(db)
        finished = await teaching.finalize_deletion_requests(db)
        await db.commit()
        return expired, finished


async def main(interval_seconds: int = 24 * 3600) -> None:
    while True:
        try:
            e, f = await run_once()
            log.info("retensi: %s rekaman kedaluwarsa dihapus, %s permintaan hapus selesai", e, f)
        except Exception:  # noqa: BLE001
            log.exception("retensi gagal")
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
