import uuid
from datetime import date

from sqlalchemy import select

from app import models
from app.services import murojaah
from tests.helpers import H, add_child, register


def _item(surah, a, b, weak=0, due=None):
    return models.MurojaahItem(id=uuid.uuid4(), member_id=uuid.uuid4(), surah_id=surah, ayah_start=a, ayah_end=b,
                               weak_score=weak, due_date=due or date.today())


def test_pick_respects_ayah_limit_and_takes_at_least_one():
    items = [_item(2, 1, 6), _item(2, 7, 12), _item(3, 1, 4)]
    picked = murojaah.pick_for_session(items, 10)
    assert [(i.ayah_start, i.ayah_end) for i in picked] == [(1, 6), (1, 4)]  # 6+6 melewati batas, dilewati
    big = [_item(2, 1, 40)]
    assert len(murojaah.pick_for_session(big, 10)) == 1  # satu rentang selalu diambil


def test_adjacent_due_ranges_become_one_block_but_items_stay_separate():
    a, b, c = _item(78, 1, 5), _item(78, 6, 10), _item(78, 20, 25)
    blocks = murojaah.to_blocks([c, b, a])
    assert [(x["ayah_start"], x["ayah_end"], len(x["items"])) for x in blocks] == [(1, 10, 2), (20, 25, 1)]
    assert [(i["ayah_start"], i["ayah_end"]) for i in blocks[0]["items"]] == [(1, 5), (6, 10)]


async def test_complete_item_keeps_range_on_next_schedule(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    it = models.MurojaahItem(member_id=m.id, surah_id=114, due_date=date.today(), ayah_start=2, ayah_end=4)
    db_session.add(it)
    await db_session.flush()
    await murojaah.complete_item(db_session, it, "lupa")
    await db_session.flush()
    rows = (await db_session.execute(select(models.MurojaahItem).where(models.MurojaahItem.completed.is_(False)))).scalars().all()
    assert len(rows) == 1 and (rows[0].ayah_start, rows[0].ayah_end) == (2, 4) and rows[0].interval_days == 1


async def test_legacy_item_normalized_to_whole_surah(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    db_session.add(models.MurojaahItem(member_id=m.id, surah_id=114, due_date=date.today()))
    await db_session.flush()
    assert await murojaah.normalize_legacy_items(db_session, m.id) == 1
    assert await murojaah.normalize_legacy_items(db_session, m.id) == 0
    it = (await db_session.execute(select(models.MurojaahItem))).scalar_one()
    assert (it.ayah_start, it.ayah_end) == (1, 6)


async def test_sesi_endpoint_inactive_without_passed_range_and_active_with(client):
    from app.database import get_db
    from app.main import app

    reg = await register(client)
    tok = reg["access_token"]
    cid = await add_child(client, tok)
    child = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    r = (await client.get("/murojaah/sesi", headers=H(child))).json()
    assert r["active"] is False and r["blocks"] == []

    gen = app.dependency_overrides[get_db]()
    db = await gen.__anext__()
    if not await db.get(models.Surah, 114):
        db.add(models.Surah(id=114, name_ar="x", name_id="An-Nas", ayah_count=6, juz_number=30, curriculum_order=1))
        await db.flush()
    mid = uuid.UUID(cid)
    db.add(models.MurojaahItem(member_id=mid, surah_id=114, due_date=date.today(), ayah_start=1, ayah_end=3))
    db.add(models.MurojaahItem(member_id=mid, surah_id=114, due_date=date.today(), ayah_start=4, ayah_end=6))
    await db.commit()
    r = (await client.get("/murojaah/sesi", headers=H(child))).json()
    assert r["active"] is True and r["total_ayah"] == 6
    assert len(r["blocks"]) == 1 and (r["blocks"][0]["ayah_start"], r["blocks"][0]["ayah_end"]) == (1, 6)
    assert len(r["blocks"][0]["items"]) == 2 and r["blocks"][0]["surah_name"] == "An-Nas"
