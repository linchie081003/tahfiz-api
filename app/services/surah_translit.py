"""Nama surat transliterasi (Al-Fatihah, An-Naba', 'Abasa, ...). Dipakai di semua teks untuk anak dan orang tua, bukan arti Indonesia."""

_NAMES = "Al-Fatihah,Al-Baqarah,Ali 'Imran,An-Nisa',Al-Ma'idah,Al-An'am,Al-A'raf,Al-Anfal,At-Taubah,Yunus,Hud,Yusuf,Ar-Ra'd,Ibrahim,Al-Hijr,An-Nahl,Al-Isra',Al-Kahf,Maryam,Ta Ha,Al-Anbiya',Al-Hajj,Al-Mu'minun,An-Nur,Al-Furqan,Asy-Syu'ara',An-Naml,Al-Qasas,Al-'Ankabut,Ar-Rum,Luqman,As-Sajdah,Al-Ahzab,Saba',Fatir,Ya Sin,As-Saffat,Sad,Az-Zumar,Gafir,Fussilat,Asy-Syura,Az-Zukhruf,Ad-Dukhan,Al-Jasiyah,Al-Ahqaf,Muhammad,Al-Fath,Al-Hujurat,Qaf,Az-Zariyat,At-Tur,An-Najm,Al-Qamar,Ar-Rahman,Al-Waqi'ah,Al-Hadid,Al-Mujadalah,Al-Hasyr,Al-Mumtahanah,As-Saff,Al-Jumu'ah,Al-Munafiqun,At-Tagabun,At-Talaq,At-Tahrim,Al-Mulk,Al-Qalam,Al-Haqqah,Al-Ma'arij,Nuh,Al-Jinn,Al-Muzzammil,Al-Muddassir,Al-Qiyamah,Al-Insan,Al-Mursalat,An-Naba',An-Nazi'at,'Abasa,At-Takwir,Al-Infitar,Al-Mutaffifin,Al-Insyiqaq,Al-Buruj,At-Tariq,Al-A'la,Al-Gasyiyah,Al-Fajr,Al-Balad,Asy-Syams,Al-Lail,Ad-Duha,Asy-Syarh,At-Tin,Al-'Alaq,Al-Qadr,Al-Bayyinah,Az-Zalzalah,Al-'Adiyat,Al-Qari'ah,At-Takasur,Al-'Asr,Al-Humazah,Al-Fil,Quraisy,Al-Ma'un,Al-Kausar,Al-Kafirun,An-Nasr,Al-Lahab,Al-Ikhlas,Al-Falaq,An-Nas".split(",")


def surah_name(surah_id: int, fallback: str = "") -> str:
    return _NAMES[surah_id - 1] if 1 <= surah_id <= len(_NAMES) else fallback
