"""EveryAyah.com folder names — murattal per ayat."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Reciter:
    id: str
    label: str
    gender: str  # male | female
    folder: str
    description: str


RECITERS: list[Reciter] = [
    Reciter("alafasy", "Misyari Al-Afasy", "male", "Alafasy_128kbps", "Jelas, cocok anak & pemula"),
    Reciter("saad", "Saad Al-Ghamdi", "male", "Ghamadi_40kbps", "Tenang, tempo sedang"),
    Reciter("sudais", "Abdurrahman As-Sudais", "male", "Abdurrahmaan_As-Sudais_192kbps", "Imam Masjidil Haram"),
    Reciter("yasser", "Yasser Al-Dosari", "male", "Yasser_Ad-Dussary_128kbps", "Murattal jelas"),
    Reciter("salah_budair", "Salah Al-Budair", "male", "Salah_Al_Budair_128kbps", "Murattal jelas"),
    Reciter("ayyoub", "Muhammad Ayyoub", "male", "Muhammad_Ayyoub_128kbps", "Pelafalan tajwid rapi"),
]

DEFAULT_RECITER_ID = "alafasy"

# Pengaturan lama / folder EveryAyah yang sudah tidak ada
_LEGACY_RECITER_IDS: dict[str, str] = {
    "huda": "alafasy",
    "salah_bukhatir": "salah_budair",
}


def get_reciter(reciter_id: str | None) -> Reciter:
    rid = reciter_id or DEFAULT_RECITER_ID
    rid = _LEGACY_RECITER_IDS.get(rid, rid)
    for r in RECITERS:
        if r.id == rid:
            return r
    return RECITERS[0]


def list_reciters(gender: str | None = None) -> list[Reciter]:
    if gender in ("male", "female"):
        return [r for r in RECITERS if r.gender == gender]
    return list(RECITERS)


def everyayah_url(surah_id: int, ayah_number: int, reciter_id: str | None = None) -> str:
    r = get_reciter(reciter_id)
    return f"https://everyayah.com/data/{r.folder}/{surah_id:03d}{ayah_number:03d}.mp3"
