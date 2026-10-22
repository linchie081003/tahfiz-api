"""Materi latihan per Pulau tahsin (3 latihan per pulau).

DRAF: isi keagamaan ini harus divalidasi ustaz sebelum dipakai luas. Contoh ayat dipilih agar
anak bisa mendengar huruf/hukum dalam bacaan qori (tidak ada rekaman huruf tunggal).
`articulation`: raised (pangkal lidah naik, tebal) | flat (lidah rata, tipis) | throat (tenggorokan).
"""

DRAFT = True

_I = lambda arabic, title, tip, surah, ayah, art=None, vs=None: {  # noqa: E731
    "arabic": arabic, "title": title, "tip": tip, "example": {"surah_id": surah, "ayah": ayah},
    "articulation": art, "versus": vs,
}

CURRICULUM: dict[int, list[dict]] = {
    1: [
        _I("صَ", "Huruf ص (shad)", "Pangkal lidah naik ke langit-langit, bibir terbuka. Itu yang membuat suara ص tebal.", 1, 6, "raised", "س"),
        _I("عَ", "Huruf ع ('ain)", "Suara keluar dari tengah tenggorokan, bukan dari bibir atau mulut depan.", 1, 7, "throat", "ء"),
        _I("قَ", "Huruf ق (qaf)", "Pangkal lidah paling belakang menyentuh langit-langit. Suaranya tebal, berbeda dari ك.", 112, 1, "raised", "ك"),
    ],
    2: [
        _I("خ ص ض غ ط ق ظ", "Huruf tebal", "Tujuh huruf ini dibaca tebal: mulut agak membulat dan lidah naik.", 1, 6),
        _I("قَ طَ بَ جَ دَ", "Huruf qalqalah", "Saat sukun atau berhenti, huruf ini memantul sedikit.", 112, 1),
        _I("حَ هَ", "Huruf ح dan ه", "ح keluar dari tengah tenggorokan dan terdengar lebih berat. ه keluar dari pangkal tenggorokan dan lebih ringan.", 1, 2),
    ],
    3: [
        _I("بَ بِ بُ", "Fathah, kasrah, dhammah", "Fathah terbuka ke atas, kasrah ke bawah, dhammah bibir membulat.", 1, 1),
        _I("عَا لَا مِي", "Mad thabi'i", "Panjangkan huruf mad sebanyak dua harakat, tidak lebih dan tidak kurang.", 1, 2),
        _I("أَحَدٌ", "Tanwin", "Tanwin dibaca seperti ada huruf nun sukun di akhir kata.", 112, 1),
    ],
    4: [
        _I("ثَ سَ صَ", "ث, س, ص", "ث ujung lidah di antara gigi, س ujung lidah dekat gigi bawah, ص tebal.", 108, 1, None, "س"),
        _I("ذَ زَ ظَ", "ذ, ز, ظ", "ذ lidah di antara gigi, ز lidah dekat gigi dengan suara berdengung, ظ tebal.", 1, 7),
        _I("تَ طَ", "ت dan ط", "ت tipis dengan ujung lidah ke gigi atas, ط tebal dan lidah naik.", 1, 6),
    ],
    5: [
        _I("أَنْعَمْتَ", "Idzhar", "Nun sukun bertemu huruf tenggorokan dibaca jelas, tanpa dengung.", 1, 7),
        _I("مَن يَعْمَلْ", "Idgham bighunnah", "Nun sukun bertemu ي melebur dengan dengung di hidung.", 99, 7),
        _I("أَنتُمْ", "Ikhfa", "Nun sukun bertemu ت dibaca samar dengan dengung.", 109, 3),
    ],
    6: [
        _I("تَرْمِيهِم بِحِجَارَةٍ", "Ikhfa syafawi", "Mim sukun bertemu ب dibaca samar di bibir dengan dengung.", 105, 4),
        _I("عَلَيْهِمْ وَلَا", "Idzhar syafawi", "Mim sukun bertemu huruf selain م dan ب dibaca jelas.", 1, 7),
        _I("ثُمَّ", "Mim bertasydid", "Mim bertasydid dibaca dengan dengung sekitar dua harakat.", 102, 3),
    ],
    7: [
        _I("جَاءَ", "Mad wajib muttasil", "Mad bertemu hamzah dalam satu kata dibaca panjang.", 110, 1),
        _I("إِنَّا أَعْطَيْنَاكَ", "Mad jaiz munfasil", "Mad bertemu hamzah di kata berikutnya, boleh dipanjangkan.", 108, 1),
        _I("الْحَاقَّةُ", "Mad lazim", "Mad bertemu huruf bertasydid dibaca panjang tetap enam harakat.", 69, 1),
    ],
    8: [
        _I("اللَّهُ", "Lafzhul Jalalah tebal", "Setelah fathah atau dhammah, lam pada lafzhul Jalalah dibaca tebal.", 112, 1),
        _I("رَبِّ", "Ra tebal", "Ra berharakat fathah dibaca tebal.", 1, 2, "raised"),
        _I("فِرْعَوْنَ", "Ra tipis", "Ra sukun setelah kasrah dibaca tipis.", 89, 10, "flat"),
    ],
    9: [
        _I("أَحَدٌ", "Waqaf pada tanwin", "Saat berhenti, tanwin dhammah dibaca sukun.", 112, 1),
        _I("الْقَارِعَةُ", "Waqaf pada ta marbutah", "Saat berhenti, ta marbutah dibaca seperti ha sukun.", 101, 1),
        _I("الْفِيلِ", "Berhenti di akhir ayat", "Berhenti di akhir ayat dengan napas cukup, lalu mulai ayat berikutnya dengan jelas.", 105, 1),
    ],
}
