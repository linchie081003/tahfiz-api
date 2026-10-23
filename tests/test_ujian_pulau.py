import io
import uuid

from app import models
from tests.helpers import H, add_child, register


async def _child(client):
    reg = await register(client)
    cid = await add_child(client, reg["access_token"])
    tok = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    return reg, cid, tok


def _form(point):
    return {"context": "tahsin", "reference_text": "x", "tahsin_point": str(point)}, {"file": ("r.webm", io.BytesIO(b"x" * 10), "audio/webm")}


async def test_ujian_pulau_membawa_nomor_pulau_dan_muncul_di_antrean(client):
    reg, cid, tok = await _child(client)
    data, files = _form(1)
    r = await client.post("/setor", headers=H(tok), data=data, files=files)
    assert r.status_code == 200, r.text
    q = (await client.get("/setor/queue", headers=H(reg["access_token"]))).json()
    assert q and q[0]["tahsin_point"] == 1 and q[0]["context"] == "tahsin"


async def test_ujian_pulau_2_butuh_pulau_1_lulus(client):
    reg, cid, tok = await _child(client)
    data, files = _form(2)
    r = await client.post("/setor", headers=H(tok), data=data, files=files)
    assert r.status_code == 409 and "Pulau 1" in r.text
