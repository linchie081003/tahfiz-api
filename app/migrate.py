"""Jalankan migrasi Alembic otomatis saat API start (aman untuk beberapa instance dan untuk database buatan create_all)."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

log = logging.getLogger("app.migrate")
ROOT = Path(__file__).resolve().parent.parent
LOCK_KEY = 7_420_231_021  # kunci advisory PostgreSQL: hanya satu instance yang bermigrasi pada satu waktu


def _config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


def _upgrade() -> None:
    command.upgrade(_config(), "head")  # env.py memakai asyncio.run sendiri, jadi dijalankan di thread terpisah


async def run_migrations() -> None:
    """Naikkan skema ke head. Migrasi bersifat idempoten (dijaga inspect) sehingga database lama tanpa alembic_version aman."""
    url = settings.database_url
    if not url.startswith("postgresql"):
        return  # SQLite/dev memakai create_all; migrasi otomatis hanya untuk PostgreSQL
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:  # koneksi ini memegang kunci selama migrasi berjalan
            await conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_KEY})
            try:
                log.info("Menjalankan alembic upgrade head")
                await asyncio.to_thread(_upgrade)
                log.info("Migrasi selesai")
            finally:
                await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
                await conn.commit()
    finally:
        await engine.dispose()
