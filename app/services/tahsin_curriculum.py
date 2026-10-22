"""Materi latihan per Pulau tahsin (5 latihan per pulau).

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
        _I("خَ", "Huruf خ (kha)", "Pangkal lidah naik mendekati tenggorokan, suara bergesek dan tebal. Beda dari ح yang keluar dari tengah tenggorokan.", 99, 7, "raised", "ح"),
        _I("غَ", "Huruf غ (ghain)", "Suara keluar dari tenggorokan bagian atas dan bergesek lembut, tebal. Beda dari ع.", 1, 7, "raised", "ع"),
    ],
    2: [
        _I("خ ص ض غ ط ق ظ", "Huruf tebal", "Tujuh huruf ini dibaca tebal: mulut agak membulat dan lidah naik.", 1, 6),
        _I("قَ طَ بَ جَ دَ", "Huruf qalqalah", "Saat sukun atau berhenti, huruf ini memantul sedikit.", 112, 1),
        _I("حَ هَ", "Huruf ح dan ه", "ح keluar dari tengah tenggorokan dan terdengar lebih berat. ه keluar dari pangkal tenggorokan dan lebih ringan.", 1, 2),
        _I("سَ شَ", "Huruf desis", "س dan ش keluar dengan desis. س tipis dengan ujung lidah dekat gigi, ش lidah lebih ke tengah.", 1, 5),
        _I("ظَ", "Huruf ظ (zha)", "Ujung lidah di antara gigi seperti ذ, tetapi dibaca tebal dengan lidah naik.", 94, 3, "raised", "ذ"),
    ],
    3: [
        _I("بَ بِ بُ", "Fathah, kasrah, dhammah", "Fathah terbuka ke atas, kasrah ke bawah, dhammah bibir membulat.", 1, 1),
        _I("عَا لَا مِي", "Mad thabi'i", "Panjangkan huruf mad sebanyak dua harakat, tidak lebih dan tidak kurang.", 1, 2),
        _I("أَحَدٌ", "Tanwin", "Tanwin dibaca seperti ada huruf nun sukun di akhir kata.", 112, 1),
        _I("يُولَدْ", "Mad thabi'i huruf waw", "Dhammah lalu waw sukun dibaca panjang dua harakat dengan bibir membulat.", 112, 3),
        _I("ٱلدِّينِ", "Mad thabi'i huruf ya", "Kasrah lalu ya sukun dibaca panjang dua harakat dengan bibir melebar.", 1, 4),
    ],
    4: [
        _I("ثَ سَ صَ", "ث, س, ص", "ث ujung lidah di antara gigi, س ujung lidah dekat gigi bawah, ص tebal.", 108, 1, None, "س"),
        _I("ذَ ضَ", "ذ dan ض", "ذ ujung lidah di antara gigi dan suaranya tipis, ض tebal dengan lidah naik.", 1, 7),
        _I("تَ طَ", "ت dan ط", "ت tipis dengan ujung lidah ke gigi atas, ط tebal dan lidah naik.", 1, 6),
        _I("كَ قَ", "ك dan ق", "ك keluar dari pangkal lidah agak ke depan dan tipis. ق lebih ke belakang dan tebal.", 109, 1, None, "ك"),
        _I("حَ خَ", "ح dan خ", "ح keluar dari tengah tenggorokan dan tipis. خ dari tenggorokan atas dan tebal.", 1, 2),
    ],
    5: [
        _I("أَنْعَمْتَ", "Idzhar", "Nun sukun bertemu huruf tenggorokan dibaca jelas, tanpa dengung.", 1, 7),
        _I("مَن يَعْمَلْ", "Idgham bighunnah", "Nun sukun bertemu ي melebur dengan dengung di hidung.", 99, 7),
        _I("أَنتُمْ", "Ikhfa", "Nun sukun bertemu ت dibaca samar dengan dengung.", 109, 3),
        _I("لَيُنۢبَذَنَّ", "Iqlab", "Nun sukun bertemu ب diubah menjadi mim samar dengan dengung dan bibir merapat.", 104, 4),
        _I("طَيْرًا أَبَابِيلَ", "Idzhar pada tanwin", "Tanwin bertemu huruf tenggorokan seperti hamzah dibaca jelas tanpa dengung.", 105, 3),
    ],
    6: [
        _I("تَرْمِيهِم بِحِجَارَةٍ", "Ikhfa syafawi", "Mim sukun bertemu ب dibaca samar di bibir dengan dengung.", 105, 4),
        _I("عَلَيْهِمْ وَلَا", "Idzhar syafawi", "Mim sukun bertemu huruf selain م dan ب dibaca jelas.", 1, 7),
        _I("ثُمَّ", "Mim bertasydid", "Mim bertasydid dibaca dengan dengung sekitar dua harakat.", 102, 4),
        _I("أَطْعَمَهُم مِّن", "Idgham mimi", "Mim sukun bertemu mim melebur menjadi satu mim bertasydid dengan dengung.", 106, 4),
        _I("إِنَّ", "Nun bertasydid", "Nun bertasydid dibaca dengan dengung sekitar dua harakat.", 108, 1),
    ],
    7: [
        _I("جَاءَ", "Mad wajib muttasil", "Mad bertemu hamzah dalam satu kata dibaca panjang.", 110, 1),
        _I("إِنَّا أَعْطَيْنَاكَ", "Mad jaiz munfasil", "Mad bertemu hamzah di kata berikutnya, boleh dipanjangkan.", 108, 1),
        _I("الْحَاقَّةُ", "Mad lazim", "Mad bertemu huruf bertasydid dibaca panjang tetap enam harakat.", 69, 1),
        _I("تَوَّابًا", "Mad 'iwadh", "Saat berhenti pada tanwin fathah, tanwin dibaca alif panjang dua harakat.", 110, 3),
        _I("إِنَّهُۥ كَانَ", "Mad shilah qashirah", "Ha dhamir di antara dua huruf berharakat dibaca panjang dua harakat.", 110, 3),
    ],
    8: [
        _I("اللَّهُ", "Lafzhul Jalalah tebal", "Setelah fathah atau dhammah, lam pada lafzhul Jalalah dibaca tebal.", 112, 1),
        _I("رَبِّ", "Ra tebal", "Ra berharakat fathah dibaca tebal.", 1, 2, "raised"),
        _I("فِرْعَوْنَ", "Ra tipis", "Ra sukun setelah kasrah dibaca tipis.", 89, 10, "flat"),
        _I("لِلَّهِ", "Lam tipis", "Setelah kasrah, lam pada lafzhul Jalalah dibaca tipis.", 1, 2, "flat"),
        _I("وَٱنْحَرْ", "Ra sukun setelah fathah", "Ra sukun setelah fathah dibaca tebal.", 108, 2, "raised"),
    ],
    9: [
        _I("أَحَدٌ", "Waqaf pada tanwin", "Saat berhenti, tanwin dhammah dibaca sukun.", 112, 1),
        _I("الْقَارِعَةُ", "Waqaf pada ta marbutah", "Saat berhenti, ta marbutah dibaca seperti ha sukun.", 101, 1),
        _I("الْفِيلِ", "Berhenti di akhir ayat", "Berhenti di akhir ayat dengan napas cukup, lalu mulai ayat berikutnya dengan jelas.", 105, 1),
        _I("ٱلْفَلَقِ", "Waqaf pada kasrah", "Saat berhenti, harakat akhir kata dibaca sukun.", 113, 1),
        _I("ٱلصَّمَدُ", "Ibtida' dengan hamzah wasl", "Saat memulai kata berawalan alif lam, mulai dengan hamzah berharakat fathah.", 112, 2),
    ],
}


# Kata contoh per latihan: (surat, ayat, nomor kata). Audio per kata dari Quran.com (wbw), sehingga
# yang terdengar adalah kata pendek yang memuat huruf/hukum tersebut, bukan seluruh ayat.
# Urutan kata mengikuti urutan huruf yang tampil di layar. DRAF: perlu divalidasi ustaz.
WORDS: dict[tuple[int, int], list[tuple[int, int, int]]] = {
    (1, 1): [(1, 6, 2)], (1, 2): [(1, 7, 3)], (1, 3): [(112, 1, 1)],
    (2, 1): [(1, 6, 2), (99, 7, 5), (1, 7, 9), (1, 7, 5), (112, 1, 1)],
    (2, 2): [(112, 1, 4)], (2, 3): [(1, 2, 1), (1, 2, 2)],
    (3, 1): [(1, 1, 1)], (3, 2): [(1, 2, 4)], (3, 3): [(112, 1, 4)],
    (4, 1): [(108, 1, 3), (1, 6, 3), (1, 6, 2)], (4, 2): [(1, 7, 2), (1, 7, 9)], (4, 3): [(1, 6, 3), (1, 6, 2)],
    (5, 1): [(1, 7, 3)], (5, 2): [(99, 7, 1), (99, 7, 2)], (5, 3): [(109, 3, 2)],
    (6, 1): [(105, 4, 1), (105, 4, 2)], (6, 2): [(1, 7, 7), (1, 7, 8)], (6, 3): [(102, 4, 1)],
    (7, 1): [(110, 1, 2)], (7, 2): [(108, 1, 1), (108, 1, 2)], (7, 3): [(69, 1, 1)],
    (8, 1): [(112, 1, 3)], (8, 2): [(1, 2, 3)], (8, 3): [(89, 10, 1)],
    (9, 1): [(112, 1, 4)], (9, 2): [(101, 1, 1)], (9, 3): [(105, 1, 7)],
    (1, 4): [(99, 7, 5)],
    (1, 5): [(1, 7, 5)],
    (2, 4): [(1, 5, 4), (113, 3, 2)],
    (2, 5): [(94, 3, 3)],
    (3, 4): [(112, 3, 4)],
    (3, 5): [(1, 4, 3)],
    (4, 4): [(109, 1, 3), (112, 1, 1)],
    (4, 5): [(1, 2, 1), (99, 7, 5)],
    (5, 4): [(104, 4, 2)],
    (5, 5): [(105, 3, 3), (105, 3, 4)],
    (6, 4): [(106, 4, 2), (106, 4, 3)],
    (6, 5): [(108, 1, 1)],
    (7, 4): [(110, 3, 7)],
    (7, 5): [(110, 3, 5), (110, 3, 6)],
    (8, 4): [(1, 2, 2)],
    (8, 5): [(108, 2, 3)],
    (9, 4): [(113, 1, 4)],
    (9, 5): [(112, 2, 2)],
}
WBW_BASE = "https://audio.qurancdn.com/wbw/"
WBW_FALLBACK_BASE = "https://verses.quran.com/wbw/"


def word_urls(point: int, index: int, base: str = WBW_BASE) -> list[str]:
    return [f"{base}{s:03d}_{a:03d}_{w:03d}.mp3" for s, a, w in WORDS.get((point, index), [])]
