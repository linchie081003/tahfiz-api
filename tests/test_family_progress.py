from tests.helpers import H, add_child, register


async def test_owner_invites_second_parent(client):
    tok = (await register(client))["access_token"]
    inv = await client.post("/family/invites", headers=H(tok))
    assert inv.status_code == 201
    j = await client.post("/family/join", json={
        "code": inv.json()["code"], "name": "Ibu", "email": "ibu@x.com", "password": "rahasia123"})
    assert j.status_code == 201
    tok2 = j.json()["access_token"]
    parents = (await client.get("/family/parents", headers=H(tok2))).json()
    assert sorted(p["family_role"] for p in parents) == ["owner", "parent"]
    # undangan sekali pakai
    again = await client.post("/family/join", json={
        "code": inv.json()["code"], "name": "X", "email": "x@x.com", "password": "rahasia123"})
    assert again.status_code == 404
    # orang tua kedua tidak boleh mengundang; pemilik tidak boleh melebihi dua orang tua
    assert (await client.post("/family/invites", headers=H(tok2))).status_code == 403
    assert (await client.post("/family/invites", headers=H(tok))).status_code == 409


async def test_both_parents_see_same_children(client):
    tok = (await register(client))["access_token"]
    cid = await add_child(client, tok)
    code = (await client.post("/family/invites", headers=H(tok))).json()["code"]
    tok2 = (await client.post("/family/join", json={
        "code": code, "name": "Ibu", "email": "ibu@x.com", "password": "rahasia123"})).json()["access_token"]
    kids = (await client.get("/members", headers=H(tok2))).json()
    assert [k["id"] for k in kids] == [cid]


async def test_member_settings_defaults_and_validation(client):
    tok = (await register(client))["access_token"]
    cid = await add_child(client, tok)
    d = (await client.get(f"/members/{cid}/settings", headers=H(tok))).json()
    assert (d["daily_ayahs"], d["murajaah_strong_days"], d["coverage"]) == (1, 14, "juz30")
    ok = await client.put(f"/members/{cid}/settings", json={"daily_ayahs": 3, "murajaah_strong_days": 7}, headers=H(tok))
    assert ok.status_code == 200 and ok.json()["daily_ayahs"] == 3
    assert (await client.put(f"/members/{cid}/settings", json={"daily_ayahs": 4}, headers=H(tok))).status_code == 422
    assert (await client.put(f"/members/{cid}/settings", json={"murajaah_strong_days": 10}, headers=H(tok))).status_code == 422


async def test_tahsin_points_gate(client):
    tok = (await register(client))["access_token"]
    cid = await add_child(client, tok)
    ov = (await client.get(f"/tahsin/points?member_id={cid}", headers=H(tok))).json()
    assert len(ov["points"]) == 9 and ov["gate_open"] is False
    url = lambda p: f"/tahsin/points/{p}/result?member_id={cid}"
    # skor 7 tidak lulus tanpa persetujuan pemutus
    r = (await client.post(url(1), json={"score": 7}, headers=H(tok))).json()
    assert r["points"][0]["passed"] is False
    # pemutus boleh meluluskan di bawah 8
    r = (await client.post(url(1), json={"score": 7, "approve_below_threshold": True}, headers=H(tok))).json()
    assert r["points"][0]["passed"] and r["points"][0]["approved_below_threshold"]
    await client.post(url(2), json={"score": 9}, headers=H(tok))
    # poin pilihan tidak membuka gerbang
    await client.post(url(5), json={"score": 10}, headers=H(tok))
    ov = (await client.get(f"/tahsin/points?member_id={cid}", headers=H(tok))).json()
    assert ov["gate_open"] is False
    r = (await client.post(url(3), json={"score": 8}, headers=H(tok))).json()
    assert r["gate_open"] is True
    kids = (await client.get("/members", headers=H(tok))).json()
    assert kids[0]["tahsin_status"] == "passed"
    assert (await client.post(url(10), json={"score": 9}, headers=H(tok))).status_code == 404


async def test_placement_child_sets_and_reads(client):
    from tests.helpers import H, add_child, register
    reg = await register(client)
    cid = await add_child(client, reg["access_token"])
    r = await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})
    h = H(r.json()["access_token"])
    assert (await client.get("/placement", headers=h)).json() == {"placement": None}
    assert (await client.put("/placement", json={"level": "basic"}, headers=h)).json() == {"placement": "basic"}
    assert (await client.get("/placement", headers=h)).json()["placement"] == "basic"
    assert (await client.put("/placement", json={"level": "zzz"}, headers=h)).status_code == 422


async def test_badge_awarded_without_seeded_definitions(db_session):
    """Regresi produksi: lencana tahsin_lulus gagal FK bila badge_definitions belum di-seed."""
    from sqlalchemy import select
    from app import models
    from app.services import gamification
    fam = models.Family(name="K", access_code="123456")
    db_session.add(fam)
    await db_session.flush()
    m = models.Member(family_id=fam.id, name="A", tahsin_status=models.TahsinStatus.passed)
    db_session.add(m)
    await db_session.flush()
    stats = await gamification.ensure_member_stats(db_session, m.id)
    await gamification.maybe_award_badges(db_session, m.id, stats)
    await db_session.flush()
    got = (await db_session.execute(select(models.MemberBadge).where(models.MemberBadge.member_id == m.id))).scalars().all()
    assert [b.badge_id for b in got] == ["tahsin_lulus"]


async def test_tahsin_curriculum_has_five_items_per_point(client):
    from tests.helpers import H, register
    reg = await register(client)
    h = H(reg["access_token"])
    for p in range(1, 10):
        r = await client.get(f"/tahsin/curriculum/{p}", headers=h)
        assert r.status_code == 200, r.text
        assert len(r.json()["items"]) == 5 and r.json()["items"][0]["audio_url"]
    assert (await client.get("/tahsin/curriculum/10", headers=h)).status_code == 404


async def test_tahsin_curriculum_has_word_audio_for_every_item(client):
    from app.services import tahsin_curriculum as tc
    for p, items in tc.CURRICULUM.items():
        for i in range(1, len(items) + 1):
            urls = tc.word_urls(p, i)
            assert urls and all(u.endswith(".mp3") and "/wbw/" in u for u in urls), (p, i)


async def test_ensure_tajweed_fills_markup(db_session, monkeypatch):
    from app.models import Ayah, Surah
    from app.services import quran_com_import as q

    async def fake_map(_client, surah_id):
        return {1: "<tajweed class=ham_wasl>ٱ</tajweed>للَّهِ"}

    monkeypatch.setattr(q, "fetch_tajweed_map", fake_map)
    q._TAJWEED_TRIED.discard(114)
    db_session.add(Surah(id=114, name_ar="الناس", name_id="An-Nas", ayah_count=1, juz_number=30, curriculum_order=1))
    db_session.add(Ayah(surah_id=114, ayah_number=1, text_uthmani="ٱللَّهِ", text_tajweed="ٱللَّهِ", tajwid_markup={"rules": []}))
    await db_session.flush()
    await q.ensure_tajweed(db_session, 114)
    a = (await db_session.execute(__import__("sqlalchemy").select(Ayah).where(Ayah.surah_id == 114))).scalars().first()
    assert "<tajweed" in a.text_tajweed
