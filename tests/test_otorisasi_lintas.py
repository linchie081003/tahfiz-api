"""Otorisasi lintas keluarga/anak/peran untuk endpoint sesi harian, penilaian, dan setoran."""
import io

from tests.helpers import H, add_child, register


async def _family(client, email):
    reg = await register(client, email=email)
    cid = await add_child(client, reg["access_token"])
    ctok = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    return reg["access_token"], cid, ctok, reg


async def _submit(client, ctok):
    r = await client.post("/setor", headers=H(ctok), data={"context": "tahsin", "reference_text": "x", "tahsin_point": "1"},
                          files={"file": ("r.webm", io.BytesIO(b"x" * 10), "audio/webm")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def test_sesi_harian_lintas_keluarga_dan_peran(client):
    pa, ca, ta, _ = await _family(client, "a@x.com")
    pb, cb, tb, _ = await _family(client, "b@x.com")
    # orang tua B tidak boleh melihat/ubah anak A
    assert (await client.get(f"/sesi-harian/anak/{ca}", headers=H(pb))).status_code == 404
    assert (await client.post(f"/sesi-harian/anak/{ca}/sesi1/nonaktif", json={"reason": "x"}, headers=H(pb))).status_code == 404
    assert (await client.post(f"/sesi-harian/anak/{ca}/sesi1/aktif", json={}, headers=H(pb))).status_code == 404
    # bukti aktivitas: id sesi milik A tidak bisa dibuka lewat anak B atau oleh orang tua B
    sid = (await client.get(f"/sesi-harian/anak/{ca}", headers=H(pa))).json()["sessions"][0]["id"]
    assert (await client.get(f"/sesi-harian/anak/{ca}/{sid}/aktivitas", headers=H(pb))).status_code == 404
    assert (await client.get(f"/sesi-harian/anak/{cb}/{sid}/aktivitas", headers=H(pb))).status_code == 404
    assert (await client.get(f"/sesi-harian/anak/{ca}/{sid}/aktivitas", headers=H(pa))).status_code == 200
    # anak tidak boleh memakai endpoint orang tua
    assert (await client.get(f"/sesi-harian/anak/{ca}", headers=H(ta))).status_code == 403
    assert (await client.post(f"/sesi-harian/anak/{ca}/sesi2/nonaktif", json={"reason": "x"}, headers=H(ta))).status_code == 403
    assert (await client.get(f"/sesi-harian/anak/{ca}/{sid}/aktivitas", headers=H(ta))).status_code == 403
    # tanpa token
    assert (await client.get("/sesi-harian/hari-ini")).status_code in (401, 403)


async def test_penilaian_dan_setoran_lintas_keluarga_dan_anak(client):
    pa, ca, ta, reg_a = await _family(client, "a@x.com")
    pb, cb, tb, _ = await _family(client, "b@x.com")
    sid = await _submit(client, ta)
    body = {"status": "needs_retry"}
    # keluarga lain
    assert (await client.post(f"/setor/{sid}/evaluate", json=body, headers=H(pb))).status_code == 404
    assert (await client.post(f"/setor/{sid}/koreksi", json={**body, "reason": "x"}, headers=H(pb))).status_code == 404
    assert (await client.get(f"/setor/{sid}/riwayat-penilaian", headers=H(pb))).status_code == 404
    assert (await client.get(f"/setor/{sid}/rentang", headers=H(pb))).status_code == 404
    assert (await client.get(f"/setor/{sid}/rentang", headers=H(tb)) ).status_code == 404
    assert (await client.get(f"/setor/{sid}", headers=H(tb))).status_code == 404
    # anak tidak boleh menilai setorannya sendiri
    assert (await client.post(f"/setor/{sid}/evaluate", json=body, headers=H(ta))).status_code == 403
    # saudara satu keluarga tidak boleh membuka rentang setoran anak lain
    cid2 = await add_child(client, pa, "Kakak")
    t2 = (await client.post("/auth/child-login", json={"access_code": reg_a["family_access_code"], "child_id": cid2, "pin": ""})).json()["access_token"]
    assert (await client.get(f"/setor/{sid}/rentang", headers=H(t2))).status_code == 404
    # pemilik sah tetap bisa
    assert (await client.get(f"/setor/{sid}/rentang", headers=H(pa))).status_code == 200
    assert (await client.post(f"/setor/{sid}/evaluate", json=body, headers=H(pa))).status_code == 200


async def test_guru_tanpa_tautan_tidak_bisa_menilai(client):
    pa, ca, ta, _ = await _family(client, "a@x.com")
    sid = await _submit(client, ta)
    r = await client.post("/teacher/register", json={"name": "Guru", "email": "g@x.com", "password": "rahasia123"})
    gt = r.json()["access_token"]
    for path, method in ((f"/teacher/submissions/{sid}/evaluate", "post"), (f"/teacher/submissions/{sid}/koreksi", "post")):
        resp = await getattr(client, method)(path, json={"status": "needs_retry", "reason": "x"}, headers=H(gt))
        assert resp.status_code in (403, 404), (path, resp.status_code)
    assert (await client.get(f"/teacher/submissions/{sid}/riwayat-penilaian", headers=H(gt))).status_code in (403, 404)
    # parent token tidak boleh memakai endpoint guru
    assert (await client.post(f"/teacher/submissions/{sid}/evaluate", json={"status": "needs_retry"}, headers=H(pa))).status_code in (401, 403)
