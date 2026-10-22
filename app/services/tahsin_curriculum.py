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



# Huruf/tanda yang menjadi poin penilaian tiap latihan (diberi warna di layar anak).
# Tiap karakter harus ada pada teks `arabic` latihan itu (dijaga oleh tes). DRAF: perlu validasi ustaz.
FOCUS: dict[tuple[int, int], str] = {
    (1, 1): "ص", (1, 2): "ع", (1, 3): "ق", (1, 4): "خ", (1, 5): "غ",
    (2, 1): "خصضغطقظ", (2, 2): "قطبجد", (2, 3): "حه", (2, 4): "سش", (2, 5): "ظ",
    (3, 1): "\u064e\u0650\u064f", (3, 2): "اي", (3, 3): "\u064c", (3, 4): "و", (3, 5): "ي",
    (4, 1): "ثسص", (4, 2): "ذض", (4, 3): "تط", (4, 4): "كق", (4, 5): "حخ",
    (5, 1): "نع", (5, 2): "ني", (5, 3): "نت", (5, 4): "نب\u06e2", (5, 5): "\u064bأ",
    (6, 1): "مب", (6, 2): "مو", (6, 3): "م", (6, 4): "مم", (6, 5): "ن",
    (7, 1): "اء", (7, 2): "اأ", (7, 3): "اق", (7, 4): "\u064bا", (7, 5): "ه\u06e5",
    (8, 1): "ل", (8, 2): "ر", (8, 3): "ر", (8, 4): "ل", (8, 5): "ر",
    (9, 1): "\u064c", (9, 2): "ة", (9, 3): "ل", (9, 4): "ق", (9, 5): "\u0671",
}
for (_p, _i), _f in FOCUS.items():
    CURRICULUM[_p][_i - 1]["focus"] = _f

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
EXTRA_WORDS: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
# Latihan tambahan (6-10 per Pulau): kata dari juz 30 yang urutan katanya sudah dicek ke Quran.com.
# Format: (pulau, arabic, judul, tip, (surat, ayat), articulation, versus, fokus, kata[(surat, ayat, no. kata)])
_EXTRA = [
    (1, "طَ", "Huruf ط (tha)", "Pangkal lidah naik, ujung lidah menyentuh langit-langit depan. Suaranya tebal, berbeda dari ت.", (111, 4), "raised", "ت", "ط", [(111, 4, 3)]),
    (1, "ضَ", "Huruf ض (dhad)", "Sisi lidah menempel pada geraham atas dan lidah naik. Suaranya tebal, berbeda dari د.", (100, 1), "raised", "د", "ض", [(100, 1, 2)]),
    (1, "ثَ", "Huruf ث (tsa)", "Ujung lidah keluar sedikit di antara gigi atas dan bawah, napas mengalir lembut.", (102, 4), None, "س", "ث", [(102, 4, 1)]),
    (1, "ذَ", "Huruf ذ (dzal)", "Ujung lidah di antara gigi seperti ث, tetapi suara bergetar dan lembut. Beda dari ز.", (106, 3), None, "ز", "ذ", [(106, 3, 3)]),
    (1, "جَ", "Huruf ج (jim)", "Tengah lidah menempel langit-langit lalu dilepas. Bibir tidak membulat.", (111, 5), None, "ش", "ج", [(111, 5, 2)]),
    (1, "أَ", "Huruf ا (alif/hamzah)", "Keluar dari pangkal tenggorokan, singkat dan tegas. Alif sendiri hanya memanjangkan suara.", (93, 6), 'throat', None, "أ", [(93, 6, 1)]),
    (1, "بَ", "Huruf ب (ba)", "Dua bibir menutup lalu dilepas dengan lembut.", (96, 1), None, 'م', "ب", [(96, 1, 2)]),
    (1, "تَ", "Huruf ت (ta)", "Ujung lidah menyentuh pangkal gigi atas. Tipis, berbeda dari ط.", (111, 1), None, 'ط', "ت", [(111, 1, 1)]),
    (1, "حَ", "Huruf ح (ha)", "Keluar dari tengah tenggorokan, napas mengalir dan terdengar berat. Beda dari ه.", (93, 11), 'throat', 'ه', "ح", [(93, 11, 4)]),
    (1, "دَ", "Huruf د (dal)", "Ujung lidah menempel gigi atas lalu dilepas. Tipis, berbeda dari ض.", (111, 1), None, 'ض', "د", [(111, 1, 2)]),
    (1, "رَ", "Huruf ر (ra)", "Ujung lidah bergetar ringan di langit-langit depan.", (93, 3), None, None, "ر", [(93, 3, 3)]),
    (1, "زَ", "Huruf ز (zay)", "Seperti س tetapi pita suara bergetar. Ujung lidah dekat gigi bawah.", (96, 18), None, 'س', "ز", [(96, 18, 2)]),
    (1, "سَ", "Huruf س (sin)", "Desis tipis dengan ujung lidah dekat gigi bawah.", (96, 18), None, 'ص', "س", [(96, 18, 1)]),
    (1, "شَ", "Huruf ش (syin)", "Desis dengan tengah lidah naik, lebih lebar dari س.", (113, 2), None, 'س', "ش", [(113, 2, 2)]),
    (1, "ظَ", "Huruf ظ (zha)", "Ujung lidah di antara gigi seperti ذ, tetapi dibaca tebal dengan lidah naik.", (94, 3), 'raised', 'ذ', "ظ", [(94, 3, 3)]),
    (1, "فَ", "Huruf ف (fa)", "Gigi atas menyentuh bibir bawah dan napas keluar.", (106, 3), None, None, "ف", [(106, 3, 1)]),
    (1, "كَ", "Huruf ك (kaf)", "Pangkal lidah menyentuh langit-langit, agak ke depan dari ق. Tipis.", (96, 6), None, 'ق', "ك", [(96, 6, 1)]),
    (1, "لَ", "Huruf ل (lam)", "Ujung lidah menyentuh langit-langit depan, suara keluar dari sisi lidah.", (97, 1), None, None, "ل", [(97, 1, 4)]),
    (1, "مَ", "Huruf م (mim)", "Dua bibir menutup, suara keluar dari hidung.", (111, 2), None, 'ب', "م", [(111, 2, 1)]),
    (1, "نَ", "Huruf ن (nun)", "Ujung lidah menyentuh langit-langit depan, suara keluar dari hidung.", (111, 3), None, None, "ن", [(111, 3, 2)]),
    (1, "هَ", "Huruf ه (ha)", "Keluar dari pangkal tenggorokan, ringan seperti menghembus napas. Beda dari ح.", (106, 3), 'throat', 'ح', "ه", [(106, 3, 3)]),
    (1, "وَ", "Huruf و (waw)", "Bibir membulat kecil lalu terbuka.", (93, 1), None, None, "و", [(93, 1, 1)]),
    (1, "يَ", "Huruf ي (ya)", "Tengah lidah mendekati langit-langit, bibir melebar.", (96, 5), None, None, "ي", [(96, 5, 5)]),
    (2, "ٱقْرَأْ", "Qalqalah di tengah kata", "Qaf sukun memantul sedikit, jangan ditahan.", (96, 1), None, None, "ق", [(96, 1, 1)]),
    (2, "خَلَقَ", "Huruf tebal dalam kata", "خ dan ق dibaca tebal: pangkal lidah naik. Lalu mulut kembali rata untuk huruf berikutnya.", (96, 2), "raised", None, "خق", [(96, 2, 1)]),
    (2, "صُبْحًا", "Huruf ص dalam kata", "ص tebal dengan dhammah, bibir sedikit membulat. Bandingkan dengan س yang tipis.", (100, 3), "raised", "س", "ص", [(100, 3, 2)]),
    (2, "لَيَطْغَىٰ", "ط dan غ dalam kata", "ط dan غ sama-sama tebal. ط ujung lidah menempel langit-langit, غ dari tenggorokan atas.", (96, 6), "raised", None, "طغ", [(96, 6, 4)]),
    (2, "لَهَبٍ", "Qalqalah di akhir ayat", "Saat berhenti pada huruf qalqalah di akhir ayat, pantulannya lebih jelas.", (111, 1), None, None, "ب", [(111, 1, 4)]),
    (3, "سَاهُونَ", "Mad alif dan waw", "Alif dan waw sukun dibaca panjang dua harakat. Alif bibir terbuka, waw bibir membulat.", (107, 5), None, None, "او", [(107, 5, 5)]),
    (3, "ٱلنَّاسِ", "Mad thabi'i pada alif", "Fathah lalu alif dibaca panjang dua harakat: na-a-s.", (114, 1), None, None, "ا", [(114, 1, 4)]),
    (3, "فِي", "Mad thabi'i pada ya", "Kasrah lalu ya sukun dibaca panjang dua harakat, bibir melebar.", (114, 5), None, None, "ي", [(114, 5, 3)]),
    (3, "غَاسِقٍ", "Tanwin kasrah", "Tanwin kasrah dibaca seperti kasrah lalu nun sukun: iqin.", (113, 3), None, None, "\u064d", [(113, 3, 3)]),
    (3, "ضَبْحًا", "Tanwin fathah", "Tanwin fathah dibaca seperti fathah lalu nun sukun: an.", (100, 1), None, None, "\u064b", [(100, 1, 2)]),
    (4, "أَ عَ", "ء dan ع", "ء keluar dari pangkal tenggorokan dan singkat. ع dari tengah tenggorokan dan terdengar mengalir.", (93, 6), "throat", None, "أع", [(93, 6, 1), (93, 3, 2)]),
    (4, "هَ حَ", "ه dan ح", "ه ringan seperti menghembus napas. ح dari tengah tenggorokan dan lebih berat.", (93, 11), "throat", None, "هح", [(93, 11, 4), (106, 3, 3)]),
    (4, "ضَ دَ", "ض dan د", "ض tebal dengan sisi lidah, د tipis dengan ujung lidah ke gigi atas.", (100, 1), None, None, "ضد", [(100, 1, 2), (93, 3, 2)]),
    (4, "زَ سَ", "ز dan س", "ز bergetar di pita suara, س hanya desis tanpa getar. Keduanya tipis.", (96, 18), None, None, "زس", [(96, 18, 2), (96, 18, 1)]),
    (4, "غَ قَ", "غ dan ق", "غ bergesek di tenggorokan atas, ق menyentuh langit-langit belakang dan memantul.", (113, 3), "raised", None, "غق", [(113, 3, 3), (100, 2, 2)]),
    (5, "مِن شَرِّ", "Ikhfa pada ش", "Nun sukun bertemu ش dibaca samar dengan dengung.", (114, 4), None, None, "نش", [(114, 4, 1), (114, 4, 2)]),
    (5, "مِنْ عَلَقٍ", "Idzhar pada ع", "Nun sukun bertemu ع dibaca jelas tanpa dengung.", (96, 2), None, None, "نع", [(96, 2, 3), (96, 2, 4)]),
    (5, "مِّن مَّسَدٍ", "Idgham bighunnah pada م", "Nun sukun bertemu م melebur menjadi mim bertasydid dengan dengung.", (111, 5), None, None, "نم", [(111, 5, 4), (111, 5, 5)]),
    (5, "عَن صَلَاتِهِمْ", "Ikhfa pada ص", "Nun sukun bertemu ص dibaca samar dengan dengung, dan ص tetap tebal.", (107, 5), None, None, "نص", [(107, 5, 3), (107, 5, 4)]),
    (5, "نَارًا ذَاتَ", "Ikhfa pada tanwin", "Tanwin bertemu ذ dibaca samar dengan dengung.", (111, 3), None, None, "\u064bذ", [(111, 3, 2), (111, 3, 3)]),
    (6, "هُمْ يُرَاءُونَ", "Idzhar syafawi pada ي", "Mim sukun bertemu ي dibaca jelas, bibir menutup sebentar.", (107, 6), None, None, "مي", [(107, 6, 2), (107, 6, 3)]),
    (6, "هُمْ عَن", "Idzhar syafawi pada ع", "Mim sukun bertemu ع dibaca jelas tanpa dengung panjang.", (107, 5), None, None, "مع", [(107, 5, 2), (107, 5, 3)]),
    (6, "رَبَّهُم بِهِمْ", "Ikhfa syafawi pada ب", "Mim sukun bertemu ب dibaca samar di bibir dengan dengung.", (100, 11), None, None, "مب", [(100, 11, 2), (100, 11, 3)]),
    (6, "فَأَمَّا", "Mim bertasydid", "Mim bertasydid dibaca dengan dengung sekitar dua harakat.", (93, 9), None, None, "م", [(93, 9, 1)]),
    (6, "إِنَّهَا", "Nun bertasydid dengan ha", "Nun bertasydid dibaca dengan dengung sekitar dua harakat.", (104, 8), None, None, "ن", [(104, 8, 1)]),
    (7, "ٱلسَّائِلَ", "Mad wajib muttasil", "Alif bertemu hamzah dalam satu kata dibaca panjang, sekitar empat sampai lima harakat.", (93, 10), None, None, "ائ", [(93, 10, 2)]),
    (7, "وَمَا أَدْرَاكَ", "Mad jaiz munfasil", "Alif bertemu hamzah di kata berikutnya, boleh dipanjangkan empat harakat.", (97, 2), None, None, "اأ", [(97, 2, 1), (97, 2, 2)]),
    (7, "تَعْلَمُونَ", "Mad 'arid lissukun", "Saat berhenti pada huruf setelah mad, mad boleh dibaca dua, empat, atau enam harakat.", (102, 3), None, None, "و", [(102, 3, 3)]),
    (7, "قُرَيْشٍ", "Mad liin", "Ya sukun setelah fathah dibaca lembut. Saat berhenti, boleh dipanjangkan.", (106, 1), None, None, "ي", [(106, 1, 2)]),
    (7, "مَالَهُ أَخْلَدَهُ", "Mad shilah thawilah", "Ha dhamir bertemu hamzah di kata berikutnya dibaca panjang empat sampai lima harakat.", (104, 3), None, None, "هأ", [(104, 3, 3), (104, 3, 4)]),
    (8, "ٱلْأَكْرَمُ", "Ra tebal", "Ra berharakat fathah atau dhammah dibaca tebal, lidah agak naik.", (96, 3), "raised", None, "ر", [(96, 3, 3)]),
    (8, "رِحْلَةَ", "Ra tipis", "Ra berharakat kasrah dibaca tipis, ujung lidah rata dan bibir melebar.", (106, 2), "flat", None, "ر", [(106, 2, 2)]),
    (8, "وَٱلرُّوحُ", "Ra dhammah tebal", "Ra berharakat dhammah dibaca tebal dengan bibir membulat.", (97, 4), "raised", None, "ر", [(97, 4, 3)]),
    (8, "أَنَّ ٱللَّهَ", "Lafzhul Jalalah setelah fathah", "Setelah fathah, lam pada lafzhul Jalalah dibaca tebal.", (96, 14), "raised", None, "ل", [(96, 14, 3), (96, 14, 4)]),
    (8, "نَارُ ٱللَّهِ", "Lafzhul Jalalah setelah dhammah", "Setelah dhammah, lam pada lafzhul Jalalah juga dibaca tebal.", (104, 6), "raised", None, "ل", [(104, 6, 1), (104, 6, 2)]),
    (9, "جَمْعًا", "Waqaf pada tanwin fathah", "Saat berhenti, tanwin fathah dibaca alif panjang dua harakat.", (100, 5), None, None, "\u064b", [(100, 5, 3)]),
    (9, "هُمَزَةٍ", "Waqaf pada tanwin kasrah", "Saat berhenti, tanwin kasrah dibaca sukun dan ta marbutah dibaca ha.", (104, 1), None, None, "ة", [(104, 1, 3)]),
    (9, "ٱلْقَدْرِ", "Berhenti pada ra", "Saat berhenti, harakat akhir dibaca sukun. Ra tetap jelas, tidak ditahan.", (97, 1), None, None, "ر", [(97, 1, 5)]),
    (9, "ٱقْرَأْ", "Mulai dengan hamzah wasl", "Saat memulai kata berawalan alif wasl pada kata kerja ini, mulai dengan hamzah berkasrah: iqra'.", (96, 1), None, None, "\u0671", [(96, 1, 1)]),
    (9, "وَٱلنَّاسِ", "Berhenti di akhir surat", "Berhenti di akhir surat dengan napas cukup, lalu tutup dengan jelas.", (114, 6), None, None, "س", [(114, 6, 3)]),
]
for _p, _ar, _title, _tip, (_s, _a), _art, _vs, _focus, _words in _EXTRA:
    CURRICULUM[_p].append(_I(_ar, _title, _tip, _s, _a, _art, _vs))
    _n = len(CURRICULUM[_p])
    CURRICULUM[_p][-1]["focus"] = _focus
    EXTRA_WORDS[(_p, _n)] = _words

WORDS.update(EXTRA_WORDS)
WBW_BASE = "https://audio.qurancdn.com/wbw/"
WBW_FALLBACK_BASE = "https://verses.quran.com/wbw/"


def word_urls(point: int, index: int, base: str = WBW_BASE) -> list[str]:
    return [f"{base}{s:03d}_{a:03d}_{w:03d}.mp3" for s, a, w in WORDS.get((point, index), [])]
