"""Isi tabel rentang hafalan, penilaian, dan penugasan penilai dari data lama, lalu bandingkan jumlahnya.

Aman dijalankan berulang (tidak menggandakan data).
  python -m scripts.backfill_rentang          # jalankan dan cetak ringkasan
  python -m scripts.backfill_rentang --check  # hanya periksa, tanpa menulis
"""

import asyncio
import sys

from sqlalchemy import func, select

from app import models
from app.database import AsyncSessionLocal
from app.services import hafalan_ranges


async def main(check_only: bool) -> int:
    async with AsyncSessionLocal() as db:
        if not check_only:
            made = await hafalan_ranges.backfill_all(db)
            await db.commit()
            print("dibuat:", made)
        bad = 0
        members = (await db.execute(select(models.Member.id))).scalars().all()
        for mid in members:
            progs = (await db.execute(select(models.MemberSurahProgress).where(models.MemberSurahProgress.member_id == mid))).scalars().all()
            for p in progs:
                surah = await db.get(models.Surah, p.surah_id)
                if not surah:
                    continue
                cov = await hafalan_ranges.covered_ayahs(db, mid, p.surah_id)
                if p.status == models.SurahProgressStatus.passed and len(cov) < surah.ayah_count:
                    bad += 1
                    print("TIDAK SAMA: surat lulus belum tertutup rentang", mid, p.surah_id, len(cov), surah.ayah_count)
        n_ev = (await db.execute(select(func.count()).select_from(models.Evaluation))).scalar_one()
        n_rg = (await db.execute(select(func.count()).select_from(models.MemorizedRange))).scalar_one()
        print(f"penilaian={n_ev} rentang={n_rg} ketidaksamaan={bad}")
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--check" in sys.argv)))
