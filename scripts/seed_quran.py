"""Seed Juz 30 surahs + sample ayahs (Tanzil-style Uthmani) and tajwid markup."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import AsyncSessionLocal, Base, engine
from app.models import Ayah, BadgeDefinition, Surah, XpConfig

JUZ30 = [
    (114, "الناس", "An-Nas", 6),
    (113, "الفلق", "Al-Falaq", 5),
    (112, "الإخلاص", "Al-Ikhlas", 4),
    (111, "المسد", "Al-Lahab", 5),
    (110, "النصر", "An-Nasr", 3),
    (109, "الكافرون", "Al-Kafirun", 6),
    (108, "الكوثر", "Al-Kawthar", 3),
    (107, "الماعون", "Al-Ma'un", 7),
    (106, "قريش", "Quraysh", 4),
    (105, "الفيل", "Al-Fil", 5),
    (104, "ال humazah", "Al-Humazah", 9),
    (103, "العصر", "Al-Asr", 3),
    (102, "التكاثر", "At-Takathur", 8),
    (101, "القارعة", "Al-Qari'ah", 11),
    (100, "العاديات", "Al-Adiyat", 11),
    (99, "الزلزلة", "Az-Zalzalah", 8),
    (98, "ال bayyinah", "Al-Bayyinah", 8),
    (97, "القدر", "Al-Qadr", 5),
    (96, "العلق", "Al-Alaq", 19),
    (95, "التين", "At-Tin", 8),
    (94, "الشرح", "Ash-Sharh", 8),
    (93, "الضحى", "Ad-Duha", 11),
    (92, "الليل", "Al-Layl", 21),
    (91, "الشمس", "Ash-Shams", 15),
    (90, "البلد", "Al-Balad", 20),
    (89, "الفجر", "Al-Fajr", 30),
    (88, "الغاشية", "Al-Ghashiyah", 26),
    (87, "الأعلى", "Al-A'la", 19),
    (86, "الطارق", "At-Tariq", 17),
    (85, "البروج", "Al-Buruj", 22),
    (84, "الإنشقاق", "Al-Inshiqaq", 25),
    (83, "المطففين", "Al-Mutaffifin", 36),
    (82, "الإنفطار", "Al-Infitar", 19),
    (81, "التكوير", "At-Takwir", 29),
    (80, "عبس", "Abasa", 42),
    (79, "النازعات", "An-Nazi'at", 46),
    (78, "النبأ", "An-Naba", 40),
]

AN_NAS = [
    "قُلْ أَعُوذُ بِرَبِّ النَّاسِ",
    "مَلِكِ النَّاسِ",
    "إِلَٰهِ النَّاسِ",
    "مِن شَرِّ الْوَسْوَاسِ الْخَنَّاسِ",
    "الَّذِي يُوَسْوِسُ فِي صُدُورِ النَّاسِ",
    "مِنَ الْجِنَّةِ وَالنَّاسِ",
]

BADGES = [
    ("tahsin_lulus", "Tahsin Lulus", "Menyelesaikan gerbang tahsin", "tahsin"),
    ("juz30_progress", "Juz 30 Progress", "Melanjutkan perjalanan Juz Amma", "juz30"),
    ("murojaah_7", "Murojaah 7 Hari", "Murojaah 7 hari berturut", "streak"),
]

XP = [
    ("setoran_lulus", 30, "Setoran lulus"),
    ("murojaah_done", 15, "Murojaah selesai"),
    ("tahsin_lulus", 50, "Tahsin lulus"),
    ("daily_activity", 5, "Aktivitas harian"),
]


def audio_url(surah_id: int, ayah: int) -> str:
    return f"https://everyayah.com/data/Alafasy_128kbps/{surah_id:03d}{ayah:03d}.mp3"


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(Surah).limit(1))).scalar_one_or_none()
        if existing:
            print("Already seeded")
            return
        for order, (sid, ar, id_name, count) in enumerate(JUZ30, start=1):
            db.add(
                Surah(
                    id=sid,
                    name_ar=ar,
                    name_id=id_name,
                    ayah_count=count,
                    juz_number=30,
                    curriculum_order=order,
                )
            )
        await db.flush()
        for i, text in enumerate(AN_NAS, start=1):
            db.add(
                Ayah(
                    surah_id=114,
                    ayah_number=i,
                    text_uthmani=text,
                    audio_url=audio_url(114, i),
                    tajwid_markup={
                        "rules": [{"type": "ghunnah", "at": 0, "note": "Perhatikan ghunnah bila ada"}] if i == 1 else []
                    },
                )
            )
        for sid, _, _, count in JUZ30:
            if sid == 114:
                continue
            db.add(
                Ayah(
                    surah_id=sid,
                    ayah_number=1,
                    text_uthmani="بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
                    audio_url=audio_url(sid, 1),
                    tajwid_markup={"rules": [{"type": "mad", "at": 0, "note": "Mad thobi'i pada huruf alif"}]},
                )
            )
            if count > 1:
                db.add(
                    Ayah(
                        surah_id=sid,
                        ayah_number=2,
                        text_uthmani="…",
                        audio_url=audio_url(sid, 2),
                        tajwid_markup={"rules": []},
                    )
                )
        for b in BADGES:
            db.add(BadgeDefinition(id=b[0], title=b[1], description=b[2], requirement_key=b[3]))
        for key, val, label in XP:
            db.add(XpConfig(activity_key=key, xp_value=val, label=label))
        await db.commit()
        print("Seed complete")


if __name__ == "__main__":
    asyncio.run(seed())
