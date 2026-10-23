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


async def test_hafalan_track_mushaf_starts_from_fatihah(client):
    from app import models
    from tests.helpers import add_child

    reg = await register(client)
    tok = reg["access_token"]
    cid = await add_child(client, tok)
    child = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    # katalog uji: Al-Fatihah, Al-Baqarah, dan satu surat juz 30
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database import get_db
    from app.main import app

    gen = app.dependency_overrides[get_db]()
    db: AsyncSession = await gen.__anext__()
    for sid, name, n, juz in ((1, "Al-Fatihah", 7, 1), (2, "Al-Baqarah", 286, 1), (114, "An-Nas", 6, 30)):
        if not await db.get(models.Surah, sid):
            db.add(models.Surah(id=sid, name_ar="x", name_id=name, ayah_count=n, juz_number=juz, curriculum_order=sid))
    await db.commit()
    await client.put(f"/members/{cid}/settings", headers=H(tok), json={"parallel_hafalan": True})
    # bawaan: jalur Juz 30
    assert (await client.get("/peta/juz/30", headers=H(child))).json()["track"] == "juz30"
    # semua surat + mulai dari Al-Fatihah
    r = await client.put(f"/members/{cid}/settings", headers=H(tok), json={"coverage": "all", "hafalan_track": "mushaf"})
    assert r.status_code == 200 and r.json()["hafalan_track"] == "mushaf"
    peta = (await client.get("/peta/juz/30", headers=H(child))).json()
    assert peta["track"] == "mushaf" and peta["active_surah_id"] == 1
    assert [n["surah_id"] for n in peta["nodes"]][:2] == [1, 2]
    # kembali ke Juz 30
    await client.put(f"/members/{cid}/settings", headers=H(tok), json={"hafalan_track": "juz30"})
    assert (await client.get("/peta/juz/30", headers=H(child))).json()["track"] == "juz30"


async def test_setor_allowed_for_any_in_progress_surah_and_repairs_missing_rows(client):
    from sqlalchemy import delete
    from app import models
    from app.database import get_db
    from app.main import app
    from tests.helpers import add_child

    reg = await register(client)
    tok = reg["access_token"]
    cid = await add_child(client, tok)
    gen = app.dependency_overrides[get_db]()
    db = await gen.__anext__()
    import uuid as _uuid
    for sid, order in ((113, 2), (114, 1)):
        if not await db.get(models.Surah, sid):
            db.add(models.Surah(id=sid, name_ar="x", name_id=f"S{sid}", ayah_count=5, juz_number=30, curriculum_order=order))
    await db.commit()
    mid = _uuid.UUID(cid)
    # data lama tanpa baris kemajuan: harus disusun ulang, bukan ditolak
    await db.execute(delete(models.MemberSurahProgress).where(models.MemberSurahProgress.member_id == mid))
    await db.commit()
    member = await db.get(models.Member, mid)
    from app.services import setor_flow
    await client.put(f"/members/{cid}/settings", headers=H(tok), json={"parallel_hafalan": True})
    member = await db.get(models.Member, mid)
    prog = await setor_flow.assert_ziyadah_setor_allowed(db, member, 114, 1, 1)
    assert prog.surah_id == 114


async def test_stt_preload_noop_when_disabled_and_load_is_lazy():
    from app.services import stt
    from app.config import settings

    old = settings.stt_enabled
    settings.stt_enabled = False
    try:
        await stt.preload()  # tidak memuat apa pun
        assert stt._whisper_model is None
    finally:
        settings.stt_enabled = old


async def test_http_engine_sends_reference_prompt(monkeypatch):
    import httpx
    from app.config import settings
    from app.services import stt

    seen = {}

    async def fake_post(self, url, headers=None, data=None, files=None, **kw):
        seen.update(url=url, data=data, auth=headers["Authorization"])
        return httpx.Response(200, json={"text": "ok"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(settings, "stt_enabled", True)
    monkeypatch.setattr(settings, "stt_engine", "openai")
    monkeypatch.setattr(settings, "stt_base_url", "https://stt.example.com/v1")
    monkeypatch.setattr(settings, "stt_api_key", "kunci")
    r = await stt.transcribe(b"abc", "audio/webm", "قُلْ هُوَ")
    assert r.text == "ok"
    assert seen["url"] == "https://stt.example.com/v1/audio/transcriptions"
    assert seen["data"]["prompt"] == "قُلْ هُوَ" and seen["data"]["language"] == "ar"
    assert seen["auth"] == "Bearer kunci"



async def test_stt_http_retries_once_on_timeout(monkeypatch):
    import httpx
    from app.services import stt

    calls = {"n": 0}

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ReadTimeout("t")
            return httpx.Response(200, json={"text": "بسم الله"})

    monkeypatch.setattr(stt.httpx, "AsyncClient", FakeClient)
    res = await stt._transcribe_openai_http(b"x", "audio/webm")
    assert res.text == "بسم الله" and calls["n"] == 2

    calls["n"] = -5  # selalu timeout
    class Always(FakeClient):
        async def post(self, *a, **k):
            raise httpx.ReadTimeout("t")
    monkeypatch.setattr(stt.httpx, "AsyncClient", Always)
    res = await stt._transcribe_openai_http(b"x", "audio/webm")
    assert res.failure == "stt_network"
