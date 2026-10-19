"""Layer 1 word alignment + Layer 2 tajwid/makhraj heuristics (evaluator aid only)."""

from __future__ import annotations

import re
from typing import Any

MAKHRAJ_GROUPS: dict[str, list[str]] = {
    "halq": list("ءه"),
    "lisan": list("لر"),
    "syafat": list("ف"),
    "tsanaf": list("ن"),
}


def _tokenize_arabic(text: str) -> list[str]:
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
    parts = [p for p in re.split(r"\s+", text.strip()) if p]
    return parts


def analyze_recording(*, reference_text: str, tajwid_markup: dict | None, transcript: str | None) -> dict[str, Any]:
    ref_tokens = _tokenize_arabic(reference_text)
    hyp_tokens = _tokenize_arabic(transcript or "")

    word_marks: list[dict[str, Any]] = []
    correct = 0
    for i, token in enumerate(ref_tokens):
        hyp = hyp_tokens[i] if i < len(hyp_tokens) else ""
        ok = hyp == token
        if ok:
            correct += 1
        word_marks.append({"index": i, "word": token, "status": "benar" if ok else "perlu_di_perbaiki", "heard": hyp})

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

    overall_confidence = 0.85 if transcript else 0.4
    if pct < 70:
        overall_confidence = min(overall_confidence, 0.55)

    return {
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
        "modelVersion": "hafiz-heuristic-v1",
        "overallConfidence": overall_confidence,
        "disclaimer": "Rekomendasi AI — keputusan akhir pada evaluator.",
    }


def mock_transcript_from_reference(reference_text: str) -> str:
    """MVP placeholder when no STT model wired; worker can replace with real STT."""
    return reference_text
