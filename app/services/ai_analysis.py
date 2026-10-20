"""Layer 1 word alignment + Layer 2 tajwid/makhraj heuristics (evaluator aid only)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

MAKHRAJ_GROUPS: dict[str, list[str]] = {
    "halq": list("ءه"),
    "lisan": list("لر"),
    "syafat": list("ف"),
    "tsanaf": list("ن"),
}


def _tokenize_arabic(text: str) -> list[str]:
    text = re.sub(r"[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]", "", text)  # harakat, tanda waqaf, tatwil
    return [p for p in re.split(r"\s+", text.strip()) if p]


_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def normalize_word(w: str) -> str:
    return re.sub(r"[^\u0621-\u064A]", "", w.translate(_NORM))


def _similar(a: str, b: str) -> bool:
    a, b = normalize_word(a), normalize_word(b)
    if not a or not b:
        return False
    return a == b or SequenceMatcher(None, a, b).ratio() >= 0.8


def _align(ref: list[str], hyp: list[str]) -> list[str]:
    """Kembalikan heard-per-ref ('' bila tidak terdengar), selaras lewat SequenceMatcher."""
    heard = [""] * len(ref)
    nr = [normalize_word(w) for w in ref]
    nh = [normalize_word(w) for w in hyp]
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, nr, nh, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                heard[i1 + k] = hyp[j1 + k]
        elif tag == "replace":
            for k in range(min(i2 - i1, j2 - j1)):
                heard[i1 + k] = hyp[j1 + k]
    return heard


def unavailable(reason: str = "no_transcript") -> dict[str, Any]:
    """Pra-cek tidak tersedia: tidak ada angka yang dikarang."""
    return {
        "available": False,
        "reason": reason,
        "modelVersion": "none",
        "disclaimer": "Pra-cek otomatis tidak tersedia. Nilai berdasarkan rekaman.",
    }


def analyze_recording(*, reference_text: str, tajwid_markup: dict | None, transcript: str | None) -> dict[str, Any]:
    if not transcript or not transcript.strip():
        return unavailable()
    ref_tokens = _tokenize_arabic(reference_text)
    hyp_tokens = _tokenize_arabic(transcript)
    heard = _align(ref_tokens, hyp_tokens)

    word_marks: list[dict[str, Any]] = []
    correct = 0
    for i, token in enumerate(ref_tokens):
        ok = _similar(token, heard[i])
        if ok:
            correct += 1
        word_marks.append({"index": i, "word": token, "status": "benar" if ok else "perlu_di_perbaiki", "heard": heard[i]})

    pct = round(100 * correct / max(len(ref_tokens), 1))

    tajwid_flags: list[dict[str, Any]] = []
    if tajwid_markup and tajwid_markup.get("rules"):
        for rule in tajwid_markup["rules"]:
            tajwid_flags.append(
                {
                    "rule": rule.get("type", "tajwid"),
                    "position": rule.get("at", 0),
                    "note": rule.get("note", "Periksa hukum bacaan pada bagian ini"),
                    "confidence": 0.55 if pct < 90 else 0.75,
                }
            )

    makhraj_flags: list[dict[str, Any]] = []
    for wm in word_marks:
        if wm["status"] == "perlu_di_perbaiki" and wm["word"]:
            ch = wm["word"][0]
            for group, letters in MAKHRAJ_GROUPS.items():
                if ch in letters:
                    makhraj_flags.append(
                        {
                            "word_index": wm["index"],
                            "group": group,
                            "message": f"Kemungkinan makhraj huruf perlu diperbaiki ({group})",
                            "confidence": 0.5,
                        }
                    )
                    break

    kelancaran = min(5, max(1, round(pct / 20)))
    tajwid_score = min(5, max(1, 5 - len(tajwid_flags)))
    makhraj_score = min(5, max(1, 5 - len(makhraj_flags)))

    overall_confidence = 0.7
    if pct < 70:
        overall_confidence = min(overall_confidence, 0.55)

    return {
        "available": True,
        "wordMarks": word_marks,
        "summaryPercent": pct,
        "tajwidFlags": tajwid_flags,
        "makhrajFlags": makhraj_flags,
        "rubricSuggestion": {
            "kelancaran": kelancaran,
            "tajwid": tajwid_score,
            "makhraj": makhraj_score,
            "focus": [f"Ulangi kata ke-{wm['index'] + 1}" for wm in word_marks if wm["status"] != "benar"][:3],
        },
        "modelVersion": "hafiz-stt-align-v2",
        "overallConfidence": overall_confidence,
        "disclaimer": "Rekomendasi AI — keputusan akhir pada evaluator.",
    }
