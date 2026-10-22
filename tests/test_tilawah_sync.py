from tests.helpers import H, add_child, register


async def test_bookmark_syncs_across_devices_and_clears(client):
    tok = (await register(client))["access_token"]
    assert (await client.get("/tilawah", headers=H(tok))).json() == {}
    r = await client.put("/tilawah", headers=H(tok), json={"bookmark": {"surah": 2, "ayah": 7, "at": 100}, "last": {"surah": 2, "ayah": 7, "at": 100}, "days": {"2026-10-22": ["2:7"]}})
    assert r.status_code == 200
    # perangkat lain: ambil, lalu tulis tanpa penanda lama
    got = (await client.get("/tilawah", headers=H(tok))).json()
    assert got["bookmark"]["ayah"] == 7 and got["days"]["2026-10-22"] == ["2:7"]
    # penanda yang lebih baru menang; pelepasan yang lebih baru menghapus
    await client.put("/tilawah", headers=H(tok), json={"bookmark": {"surah": 3, "ayah": 1, "at": 200}})
    assert (await client.get("/tilawah", headers=H(tok))).json()["bookmark"]["surah"] == 3
    await client.put("/tilawah", headers=H(tok), json={"bookmark_cleared_at": 300})
    assert (await client.get("/tilawah", headers=H(tok))).json()["bookmark"] is None


async def test_state_is_per_child(client):
    tok = (await register(client))["access_token"]
    c1 = await add_child(client, tok)
    await client.put("/tilawah", headers=H(tok), json={"last": {"surah": 1, "ayah": 3, "at": 1}})
    imp = (await client.post(f"/members/{c1}/impersonate", headers=H(tok)))
    assert imp.status_code == 200
    if True:
        ct = imp.json()["access_token"]
        assert (await client.get("/tilawah", headers=H(ct))).json() == {}


async def test_parallel_hafalan_unlocks_menus_without_tahsin(client):
    from tests.helpers import add_child

    reg = await register(client)
    tok = reg["access_token"]
    cid = await add_child(client, tok)
    child = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    home = (await client.get("/home", headers=H(child))).json()
    assert home["menu_locks"]["ziyadah"] and home["menu_locks"]["murojaah"]
    r = await client.put(f"/members/{cid}/settings", headers=H(tok), json={"parallel_hafalan": True})
    assert r.status_code == 200 and r.json()["parallel_hafalan"] is True
    home = (await client.get("/home", headers=H(child))).json()
    assert home["menu_locks"]["ziyadah"] == "" and home["menu_locks"]["murojaah"] == ""
    await client.put(f"/members/{cid}/settings", headers=H(tok), json={"parallel_hafalan": False})
    assert (await client.get("/home", headers=H(child))).json()["menu_locks"]["ziyadah"]
