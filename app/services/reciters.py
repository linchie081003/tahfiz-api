"""EveryAyah.com folder names — per-ayat audio."""

from dataclasses import dataclass

from app.models import AgeMode


@dataclass(frozen=True)
class Reciter:
    id: str
    label: str
    gender: str  # male | female
    folder: str
    description: str
    style: str  # muallim | murattal | mujawwad


RECITERS: list[Reciter] = [
    Reciter(
        "husary_muallim",
        "Mahmud Khalil Al-Husary (Muallim)",
        "male",
        "Husary_Muallim_128kbps",
        "Pelan, per ayat — utama PAUD & SD",
        "muallim",
    ),
    Reciter(
        "husary",
        "Mahmud Khalil Al-Husary (Murattal)",
        "male",
        "Husary_128kbps",
        "Murattal — pilihan kedua anak & utama remaja/dewasa",
        "murattal",
    ),
    Reciter(
        "minshawi",
        "Muhammad Siddiq Al-Minshawi (Murattal)",
        "male",
        "Minshawy_Murattal_128kbps",
        "Murattal jelas — remaja & dewasa",
        "murattal",
    ),
    Reciter("alafasy", "Misyari Al-Afasy", "male", "Alafasy_128kbps", "Murattal jelas, alternatif", "murattal"),
    Reciter("saad", "Saad Al-Ghamdi", "male", "Ghamadi_40kbps", "Murattal tenang", "murattal"),
    Reciter("sudais", "Abdurrahman As-Sudais", "male", "Abdurrahmaan_As-Sudais_192kbps", "Murattal Imam Haram", "murattal"),
    Reciter("yasser", "Yasser Al-Dosari", "male", "Yasser_Ad-Dussary_128kbps", "Murattal jelas", "murattal"),
    Reciter("salah_budair", "Salah Al-Budair", "male", "Salah_Al_Budair_128kbps", "Murattal jelas", "murattal"),
    Reciter("ayyoub", "Muhammad Ayyoub", "male", "Muhammad_Ayyoub_128kbps", "Murattal tajwid rapi", "murattal"),
    Reciter(
        "husary_mujawwad",
        "Mahmud Khalil Al-Husary (Mujawwad)",
        "male",
        "Husary_Mujawwad_128kbps",
        "Versi indah — hadiah setelah ayat lulus (bukan untuk meniru)",
        "mujawwad",
    ),
]

DEFAULT_RECITER_ID = "husary_muallim"
BEAUTY_RECITER_ID = "husary_mujawwad"
TILAWAH_RECITER_ID = "alafasy"  # Tilawah: Mishary Rashid Alafasy

_DEFAULT_BY_AGE: dict[AgeMode, str] = {
    AgeMode.paud: "husary_muallim",
    AgeMode.sd: "husary_muallim",
    AgeMode.teen: "husary",
    AgeMode.adult: "husary",
}

_SETTINGS_IDS_BY_AGE: dict[AgeMode, tuple[str, ...]] = {
    AgeMode.paud: ("husary_muallim", "husary", "minshawi", "alafasy", "saad", "yasser", "salah_budair"),
    AgeMode.sd: ("husary_muallim", "husary", "minshawi", "alafasy", "saad", "sudais", "yasser", "salah_budair", "ayyoub"),
    AgeMode.teen: ("husary", "minshawi", "alafasy", "saad", "sudais", "yasser", "salah_budair", "ayyoub"),
    AgeMode.adult: ("husary", "minshawi", "alafasy", "saad", "sudais", "yasser", "salah_budair", "ayyoub"),
}

_LEGACY_RECITER_IDS: dict[str, str] = {
    "huda": "alafasy",
    "salah_bukhatir": "salah_budair",
}


def normalize_reciter_id(reciter_id: str | None) -> str:
    rid = reciter_id or DEFAULT_RECITER_ID
    return _LEGACY_RECITER_IDS.get(rid, rid)


def get_reciter(reciter_id: str | None) -> Reciter:
    rid = normalize_reciter_id(reciter_id)
    for r in RECITERS:
        if r.id == rid:
            return r
    return RECITERS[0]


def default_reciter_for_age(age_mode: AgeMode | str | None) -> str:
    if isinstance(age_mode, str):
        try:
            age_mode = AgeMode(age_mode)
        except ValueError:
            age_mode = AgeMode.sd
    if age_mode is None:
        age_mode = AgeMode.sd
    return _DEFAULT_BY_AGE.get(age_mode, DEFAULT_RECITER_ID)


def reciter_for_learning(reciter_id: str | None, age_mode: AgeMode | str | None = None) -> str:
    """Audio referensi belajar — mujawwad tidak dipakai."""
    rid = normalize_reciter_id(reciter_id) if reciter_id else default_reciter_for_age(age_mode)
    r = get_reciter(rid)
    if r.style == "mujawwad":
        return default_reciter_for_age(age_mode)
    allowed = set(_SETTINGS_IDS_BY_AGE.get(_coerce_age(age_mode), ()))
    if allowed and rid not in allowed:
        return default_reciter_for_age(age_mode)
    return rid


def _coerce_age(age_mode: AgeMode | str | None) -> AgeMode:
    if isinstance(age_mode, AgeMode):
        return age_mode
    if isinstance(age_mode, str):
        try:
            return AgeMode(age_mode)
        except ValueError:
            pass
    return AgeMode.sd


def list_reciters(
    gender: str | None = None,
    *,
    age_mode: AgeMode | str | None = None,
    for_settings: bool = False,
) -> list[Reciter]:
    rows = list(RECITERS)
    if for_settings:
        allowed = _SETTINGS_IDS_BY_AGE.get(_coerce_age(age_mode), ())
        if allowed:
            order = {rid: i for i, rid in enumerate(allowed)}
            rows = [r for r in rows if r.id in order and r.style != "mujawwad"]
            rows.sort(key=lambda r: order.get(r.id, 999))
    else:
        rows = [r for r in rows if r.style != "mujawwad"]
    if gender in ("male", "female"):
        filtered = [r for r in rows if r.gender == gender]
        return filtered if filtered else [r for r in rows if r.gender == "male"]
    return rows


def beauty_audio_urls(surah_id: int, ayah_start: int, ayah_end: int) -> list[str]:
    start, end = min(ayah_start, ayah_end), max(ayah_start, ayah_end)
    return [everyayah_url(surah_id, n, BEAUTY_RECITER_ID) for n in range(start, end + 1)]


def everyayah_url(surah_id: int, ayah_number: int, reciter_id: str | None = None) -> str:
    r = get_reciter(reciter_id)
    return f"https://everyayah.com/data/{r.folder}/{surah_id:03d}{ayah_number:03d}.mp3"
