"""Tambah kolom audio/tampilan Arab — jalankan sekali pada DB yang sudah ada."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.database import engine


async def main():
    stmts = [
        "ALTER TABLE ayahs ADD COLUMN IF NOT EXISTS text_tajweed TEXT",
        "ALTER TABLE family_settings ADD COLUMN IF NOT EXISTS reciter_id VARCHAR(64) DEFAULT 'alafasy'",
        "ALTER TABLE family_settings ADD COLUMN IF NOT EXISTS playback_speed DOUBLE PRECISION DEFAULT 1.0",
        "ALTER TABLE family_settings ADD COLUMN IF NOT EXISTS arabic_font_size VARCHAR(16) DEFAULT 'large'",
        "ALTER TABLE family_settings ADD COLUMN IF NOT EXISTS show_tajweed_colors BOOLEAN DEFAULT TRUE",
    ]
    async with engine.begin() as conn:
        for s in stmts:
            try:
                await conn.execute(text(s))
            except Exception as e:
                print("Skip or ok:", s[:50], e)
    print("Migration selesai.")


if __name__ == "__main__":
    asyncio.run(main())
