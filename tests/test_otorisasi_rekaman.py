"""Akses rekaman: hanya pemilik (anak yang menyetor) dan orang tua keluarga itu."""
import pytest

from app.config import settings
from tests.helpers import H, add_child, register

AYAT = "قُلْ أَعُوذُ بِرَبِّ النَّاسِ"


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_recordings_dir", str(tmp_path))
    monkeypatch.setattr(settings, "use_local_storage", True)


async def _family(client, email):
    reg = await register(client, email=email)
    ptok = reg["access_token"]
    await client.post("/family/consent/recording", json={"granted": True}, headers=H(ptok))  # tanpa ini rekaman tidak disimpan
    kids = []
    for name in ("Kakak", "Adik"):
        cid = await add_child(client, ptok, name)
        tok = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
        kids.append((cid, tok))
    return ptok, kids


async def _submit(client, ctok):
    r = await client.post("/setor", data={"context": "tahsin", "reference_text": AYAT},
                          files={"file": ("r.webm", b"suara-kakak" * 300, "audio/webm")}, headers=H(ctok))
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def test_rekaman_hanya_untuk_pemilik_dan_orang_tua(client):
    ptok, [(c1, t1), (c2, t2)] = await _family(client, "a@x.com")
    sid = await _submit(client, t1)
    # pemilik dan orang tua
    r = await client.get(f"/setor/media/{sid}", headers=H(t1))
    assert r.status_code == 200 and r.content.startswith(b"suara-kakak")
    assert (await client.get(f"/setor/media/{sid}", headers=H(ptok))).status_code == 200
    # saudara satu keluarga TIDAK boleh mendengar
    assert (await client.get(f"/setor/media/{sid}", headers=H(t2))).status_code == 404


async def test_rekaman_tidak_bisa_dibuka_keluarga_lain_atau_tanpa_login(client):
    ptok, [(c1, t1), _] = await _family(client, "a@x.com")
    pb, [(cb, tb), _] = await _family(client, "b@x.com")
    sid = await _submit(client, t1)
    assert (await client.get(f"/setor/media/{sid}", headers=H(pb))).status_code == 404
    assert (await client.get(f"/setor/media/{sid}", headers=H(tb))).status_code == 404
    assert (await client.get(f"/setor/media/{sid}")).status_code in (401, 403)


async def test_guru_tanpa_izin_tidak_bisa_mendengar(client):
    ptok, [(c1, t1), _] = await _family(client, "a@x.com")
    sid = await _submit(client, t1)
    gt = (await client.post("/teacher/register", json={"name": "Guru", "email": "g@x.com", "password": "rahasia123"})).json()["access_token"]
    assert (await client.get(f"/teacher/media/{sid}", headers=H(gt))).status_code == 403
    assert (await client.get(f"/setor/media/{sid}", headers=H(gt))).status_code in (401, 403, 404)


async def test_url_rekaman_hanya_muncul_untuk_yang_berhak(client):
    ptok, [(c1, t1), (c2, t2)] = await _family(client, "a@x.com")
    sid = await _submit(client, t1)
    # antrean hanya untuk orang tua; anak tidak punya akses ke antrean (yang memuat recording_url)
    assert (await client.get("/setor/queue", headers=H(t2))).status_code == 403
    assert (await client.get(f"/setor/{sid}", headers=H(t2))).status_code == 404
    own = await client.get(f"/setor/{sid}", headers=H(t1))
    assert own.status_code == 200 and own.json().get("recording_url") is None  # anak tidak diberi URL rekaman
