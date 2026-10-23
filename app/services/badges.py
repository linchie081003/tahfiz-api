"""Katalog lencana dan aturan pemberiannya. Tiap lencana = satu metrik dengan ambang (target)."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.models import TahsinStatus

JUZ30_SURAHS = 37  # An-Naba' (78) sampai An-Nas (114)

# (id, judul, syarat, jenis ikon, metrik, target)
CATALOG: list[tuple[str, str, str, str, str, int]] = [
    ("pulau_pertama", "Pulau Pertama", "Lulus satu Pulau tahsin", "tahsin", "pulau_lulus", 1),
    ("tahsin_lulus", "Tahsin Lulus", "Lulus Pulau 1 sampai 3 (gerbang tahsin)", "tahsin", "pulau_wajib_lulus", 3),
    ("sembilan_pulau", "Penjelajah 9 Pulau", "Lulus semua 9 Pulau tahsin", "tahsin", "pulau_lulus", 9),
    ("ayat_1", "Ayat Pertama", "Lulus satu ayat hafalan", "hafalan", "ayat_lulus", 1),
    ("ayat_10", "Sepuluh Ayat", "Lulus 10 ayat hafalan", "hafalan", "ayat_lulus", 10),
    ("ayat_50", "Lima Puluh Ayat", "Lulus 50 ayat hafalan", "hafalan", "ayat_lulus", 50),
    ("ayat_100", "Seratus Ayat", "Lulus 100 ayat hafalan", "hafalan", "ayat_lulus", 100),
    ("surat_1", "Surat Pertama", "Lulus satu surat penuh", "hafalan", "surat_lulus", 1),
    ("juz30_progress", "Juz 30 Progress", "Lulus 3 surat Juz Amma", "juz30", "juz30_lulus", 3),
    ("juz30_tamat", "Hafizh Juz Amma", "Lulus seluruh 37 surat Juz Amma", "juz30", "juz30_lulus", JUZ30_SURAHS),
    ("murojaah_1", "Murajaah Perdana", "Selesaikan satu murajaah", "murojaah", "murojaah_selesai", 1),
    ("murojaah_20", "Rajin Murajaah", "Selesaikan 20 murajaah", "murojaah", "murojaah_selesai", 20),
    ("streak_3", "Tiga Hari Berturut", "Belajar 3 hari berturut-turut", "streak", "streak", 3),
    ("murojaah_7", "Tujuh Hari Berturut", "Belajar 7 hari berturut-turut", "streak", "streak", 7),
    ("streak_30", "Tiga Puluh Hari", "Belajar 30 hari berturut-turut", "streak", "streak", 30),
    ("sambung_10", "Penyambung Ayat", "Jawab 10 sambung ayat dengan benar", "sambung", "sambung_benar", 10),
    ("sambung_50", "Ahli Sambung Ayat", "Jawab 50 sambung ayat dengan benar", "sambung", "sambung_benar", 50),
    ("tanda_1", "Tahu yang Sulit", "Tandai ayat atau kata yang sulit untuk dilatih", "tanda", "tanda_anak", 1),
    ("level_5", "Level 5", "Capai Level 5", "level", "level", 5),
]
BY_ID = {c[0]: c for c in CATALOG}


async def metrics(db: AsyncSession, member: models.Member, stats: models.MemberStats) -> dict[str, int]:
    mid = member.id
    rows = (
        await db.execute(
            select(models.MemorizedRange.surah_id, models.MemorizedRange.ayah_start, models.MemorizedRange.ayah_end).where(
                models.MemorizedRange.member_id == mid, models.MemorizedRange.status == "passed"
            )
        )
    ).all()
    per: dict[int, set[int]] = {}
    for sid, a, b in rows:
        per.setdefault(sid, set()).update(range(a, b + 1))
    passed_surahs = set(
        (
            await db.execute(
                select(models.MemberSurahProgress.surah_id).where(
                    models.MemberSurahProgress.member_id == mid, models.MemberSurahProgress.status == models.SurahProgressStatus.passed
                )
            )
        ).scalars().all()
    )
    pts = (
        await db.execute(select(models.TahsinPointProgress).where(models.TahsinPointProgress.member_id == mid, models.TahsinPointProgress.passed.is_(True)))
    ).scalars().all()
    pulau = {p.point for p in pts}
    legacy_gate = member.tahsin_status == TahsinStatus.passed and not pulau  # data lama tanpa catatan per Pulau
    murojaah = (await db.execute(select(func.count()).select_from(models.MurojaahItem).where(models.MurojaahItem.member_id == mid, models.MurojaahItem.completed.is_(True)))).scalar_one()
    sambung = (await db.execute(select(func.count()).select_from(models.ConnectAttempt).where(models.ConnectAttempt.member_id == mid, models.ConnectAttempt.correct.is_(True)))).scalar_one()
    tanda = (await db.execute(select(func.count()).select_from(models.DifficultMark).where(models.DifficultMark.member_id == mid, models.DifficultMark.created_by_role == "child"))).scalar_one()
    return {
        "pulau_lulus": len(pulau),
        "pulau_wajib_lulus": 3 if legacy_gate else len(pulau & {1, 2, 3}),
        "ayat_lulus": sum(len(v) for v in per.values()),
        "surat_lulus": len(passed_surahs),
        "juz30_lulus": len([s for s in passed_surahs if 78 <= s <= 114]),
        "murojaah_selesai": int(murojaah),
        "streak": stats.streak_days,
        "sambung_benar": int(sambung),
        "tanda_anak": int(tanda),
        "level": stats.level,
    }


async def award(db: AsyncSession, member: models.Member, stats: models.MemberStats) -> dict[str, int]:
    """Beri lencana yang syaratnya terpenuhi (idempoten, juga menyusul kemajuan lama). Mengembalikan metrik."""
    m = await metrics(db, member, stats)
    have = set((await db.execute(select(models.MemberBadge.badge_id).where(models.MemberBadge.member_id == member.id))).scalars().all())
    for bid, _t, _d, _k, metric, target in CATALOG:
        if bid not in have and m.get(metric, 0) >= target:
            db.add(models.MemberBadge(member_id=member.id, badge_id=bid))
    await db.flush()
    return m
