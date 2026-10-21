import uuid

from app.config import settings
from app.services import storage
from tests.helpers import H, add_child, register
from tests.test_precheck import AYAT, _child_token


def test_sniff_audio_type():
    assert storage.sniff_audio_type(b"\x00\x00\x00\x18ftypmp42") == "audio/mp4"
    assert storage.sniff_audio_type(b"\x1a\x45\xdf\xa3....") == "audio/webm"
    assert storage.sniff_audio_type(b"OggS....") == "audio/ogg"


def test_url_rekaman_lewat_api_juga_untuk_s3(monkeypatch):
    monkeypatch.setattr(settings, "use_local_storage", False)
    monkeypatch.setattr(settings, "api_public_base", "https://api.contoh.com/")
    sid = uuid.uuid4()
    assert storage.presigned_recording_url("k", uuid.uuid4(), sid) == f"https://api.contoh.com/setor/media/{sid}"


async def test_media_dibaca_lewat_storage_dan_tipe_dari_isi(client, monkeypatch):
    monkeypatch.setattr(storage, "upload_recording", lambda *a, **k: "k")
    monkeypatch.setattr(storage, "read_recording", lambda key, f, s: b"\x00\x00\x00\x18ftypM4A rekaman")
    reg = await register(client)
    cid = await add_child(client, reg["access_token"])
    ctok = await _child_token(client, reg, cid)
    r = await client.post(
        "/setor",
        data={"context": "tahsin", "reference_text": AYAT},
        files={"file": ("r.m4a", b"x" * 5000, "audio/mp4")},
        headers=H(ctok),
    )
    sid = r.json()["id"]
    ok = await client.get(f"/setor/media/{sid}", headers=H(reg["access_token"]))
    assert ok.status_code == 200 and ok.headers["content-type"] == "audio/mp4"
    assert (await client.get(f"/setor/media/{sid}")).status_code in (401, 403)
    monkeypatch.setattr(storage, "read_recording", lambda key, f, s: None)
    assert (await client.get(f"/setor/media/{sid}", headers=H(reg["access_token"]))).status_code == 404
