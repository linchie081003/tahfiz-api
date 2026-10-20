import pytest

from app.services import stt
from app.services.ai_analysis import analyze_recording
from tests.helpers import H, add_child, register

AYAT = "قُلْ أَعُوذُ بِرَبِّ النَّاسِ"


def test_exact_and_diacritic_free_transcript_matches():
    r = analyze_recording(reference_text=AYAT, tajwid_markup=None, transcript="قل اعوذ برب الناس")
    assert r["available"] and r["summaryPercent"] == 100


def test_missing_word_lowers_score_and_marks_it():
    r = analyze_recording(reference_text=AYAT, tajwid_markup=None, transcript="قل اعوذ الناس")
    assert r["summaryPercent"] == 75
    assert [w["status"] for w in r["wordMarks"]].count("perlu_di_perbaiki") == 1


def test_empty_transcript_is_unavailable_not_100_percent():
    r = analyze_recording(reference_text=AYAT, tajwid_markup=None, transcript=None)
    assert r["available"] is False and "summaryPercent" not in r


@pytest.fixture
def fake_stt(monkeypatch):
    calls = []

    async def fake(audio, content_type="audio/webm", reference_hint=None):
        calls.append(len(audio))
        return stt.SttResult("قل اعوذ برب الناس", None)

    monkeypatch.setattr(stt, "is_configured", lambda: True)
    monkeypatch.setattr(stt, "transcribe", fake)
    monkeypatch.setattr("app.services.storage.upload_recording", lambda *a, **k: "k")
    return calls


async def _submit(client, ctok):
    return await client.post(
        "/setor",
        data={"context": "tahsin", "reference_text": AYAT},
        files={"file": ("r.webm", b"x" * 5000, "audio/webm")},
        headers=H(ctok),
    )


async def _child_token(client, reg, cid):
    r = await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})
    return r.json()["access_token"]


async def test_no_consent_means_no_audio_sent_and_unavailable(client, fake_stt):
    reg = await register(client)
    cid = await add_child(client, reg["access_token"])
    ctok = await _child_token(client, reg, cid)
    assert (await _submit(client, ctok)).status_code == 200
    assert fake_stt == []  # suara anak TIDAK dikirim tanpa persetujuan
    q = (await client.get("/setor/queue", headers=H(reg["access_token"]))).json()
    assert q[0]["ai_insights"]["available"] is False and q[0]["ai_insights"]["reason"] == "no_consent"


async def test_with_consent_precheck_runs_and_can_be_revoked(client, fake_stt):
    reg = await register(client)
    tok = reg["access_token"]
    cid = await add_child(client, tok)
    ctok = await _child_token(client, reg, cid)
    assert (await client.put("/settings/ai-consent", json={"granted": True}, headers=H(tok))).json()["granted"] is True
    assert (await _submit(client, ctok)).status_code == 200
    assert fake_stt == [5000]
    q = (await client.get("/setor/queue", headers=H(tok))).json()
    assert q[0]["ai_insights"]["available"] is True and q[0]["ai_insights"]["summaryPercent"] == 100
    await client.put("/settings/ai-consent", json={"granted": False}, headers=H(tok))
    assert (await client.get("/settings/ai-consent", headers=H(tok))).json()["granted"] is False


async def test_child_cannot_grant_consent(client, fake_stt):
    reg = await register(client)
    cid = await add_child(client, reg["access_token"])
    ctok = await _child_token(client, reg, cid)
    assert (await client.put("/settings/ai-consent", json={"granted": True}, headers=H(ctok))).status_code == 403
