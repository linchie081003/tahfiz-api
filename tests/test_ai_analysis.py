from app.services.ai_analysis import analyze_recording


def test_analyze_exact_match():
    text = "قُلْ أَعُوذُ بِرَبِّ النَّاسِ"
    result = analyze_recording(reference_text=text, tajwid_markup=None, transcript=text)
    assert result["summaryPercent"] == 100
    assert result["rubricSuggestion"]["kelancaran"] >= 4
