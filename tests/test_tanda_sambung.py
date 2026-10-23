import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import models
from app.services import tanda
from tests.helpers import H, add_child, register


async def _kid(db):
    fam = models.Family(name="K", access_code="ZZZ999")
    db.add(fam)
    await db.flush()
    m = models.Member(family_id=fam.id, name="Adik", age_mode=models.AgeMode.sd)
    db.add(m)
    db.add(models.Surah(id=78, name_ar="x", name_id="An-Naba'", ayah_count=40, juz_number=30, curriculum_order=1))
    db.add(models.Surah(id=114, name_ar="x", name_id="An-Nas", ayah_count=6, juz_number=30, curriculum_order=2))
    await db.flush()
    for k in range(1, 4):
        db.add(models.Ayah(surah_id=78, ayah_number=k, text_uthmani="a b c d"))
    await db.flush()
    return m


async def test_lupa_creates_auto_mark_once_and_lancar_three_times_clears(db_session):
    db = db_session
    m = await _kid(db)
    r = await tanda.record_results(db, m.id, "murajaah", [(78, 2, "lupa")])
    assert r["marks_created"] == 1
    again = await tanda.record_results(db, m.id, "murajaah", [(78, 2, "lupa")])
    assert again["marks_created"] == 0  # tidak dobel
    (mk,) = await tanda.active_marks(db, m.id)
    assert mk.source == "auto" and mk.streak == 0
    for _ in range(2):
        await tanda.record_results(db, m.id, "murajaah", [(78, 2, "lancar")])
    assert len(await tanda.active_marks(db, m.id)) == 1
    out = await tanda.record_results(db, m.id, "murajaah", [(78, 2, "lancar")])
    assert out["marks_cleared"] == 1 and await tanda.active_marks(db, m.id) == []


async def test_failure_resets_streak(db_session):
    db = db_session
    m = await _kid(db)
    await tanda.record_results(db, m.id, "murajaah", [(78, 1, "lupa")])
    await tanda.record_results(db, m.id, "murajaah", [(78, 1, "lancar")])
    await tanda.record_results(db, m.id, "murajaah", [(78, 1, "lancar")])
    await tanda.record_results(db, m.id, "murajaah", [(78, 1, "ragu")])
    (mk,) = await tanda.active_marks(db, m.id)
    assert mk.streak == 0


async def test_same_ayah_twice_in_one_call_counts_once(db_session):
    db = db_session
    m = await _kid(db)
    await tanda.create_mark(db, m.id, 78, 1)
    await tanda.record_results(db, m.id, "murajaah", [(78, 1, "lancar"), (78, 1, "lancar"), (78, 1, "lancar")])
    (mk,) = await tanda.active_marks(db, m.id)
    assert mk.streak == 1  # tiga percobaan harus berbeda


async def test_marks_are_separate_from_progress_and_schedule(db_session):
    db = db_session
    m = await _kid(db)
    await tanda.create_mark(db, m.id, 78, 1)
    await tanda.record_results(db, m.id, "murajaah", [(78, 1, "lupa")])
    assert (await db.execute(select(models.MurojaahItem))).first() is None
    assert (await db.execute(select(models.Submission))).first() is None


async def test_word_mark_validation_and_dedupe(db_session):
    db = db_session
    m = await _kid(db)
    mk = await tanda.create_mark(db, m.id, 78, 1, word_start=1, word_end=2)
    assert mk.word_text == "b c"
    same = await tanda.create_mark(db, m.id, 78, 1, word_start=1, word_end=2)
    assert same.id == mk.id
    with pytest.raises(HTTPException):
        await tanda.create_mark(db, m.id, 78, 1, word_start=3, word_end=9)
    # kata tidak berubah oleh latihan ayat penuh
    await tanda.record_results(db, m.id, "murajaah", [(78, 1, "lancar")] * 1)
    assert (await db.get(models.DifficultMark, mk.id)).streak == 0


async def test_evaluator_mark_not_removable_by_child_nor_auto_cleared(db_session):
    db = db_session
    m = await _kid(db)
    em = await tanda.create_mark(db, m.id, 78, 3, role="evaluator")
    with pytest.raises(HTTPException) as e:
        await tanda.deactivate_mark(db, m.id, em.id)
    assert e.value.status_code == 403
    for _ in range(4):
        await tanda.record_results(db, m.id, "murajaah", [(78, 3, "lancar")])
    assert (await db.get(models.DifficultMark, em.id)).status == "active"


async def test_child_can_remove_own_mark(db_session):
    db = db_session
    m = await _kid(db)
    mk = await tanda.create_mark(db, m.id, 78, 2, source="auto")
    await tanda.deactivate_mark(db, m.id, mk.id)
    assert await tanda.active_marks(db, m.id) == []


async def test_sambung_questions_skip_last_ayah_of_range_and_paud_choices(db_session):
    db = db_session
    m = await _kid(db)
    db.add(models.MemorizedRange(member_id=m.id, surah_id=78, ayah_start=1, ayah_end=3))
    db.add(models.MemorizedRange(member_id=m.id, surah_id=114, ayah_start=1, ayah_end=6))
    await db.flush()
    qs = await tanda.build_questions(db, m)
    assert len(qs) == 3 and all(q["mode"] == "ingat" for q in qs)
    assert not any(q["surah_id"] == 78 and q["ayah_from"] == 3 for q in qs)
    assert not any(q["surah_id"] == 114 and q["ayah_from"] == 6 for q in qs)
    m.age_mode = models.AgeMode.paud
    qs = await tanda.build_questions(db, m)
    assert len(qs) == 2 and all(q["mode"] == "pilihan" and len(q["options"]) == 3 for q in qs)
    for q in qs:
        assert {"surah_id": q["surah_id"], "ayah_number": q["ayah_from"] + 1} in q["options"]


async def test_sambung_pilihan_xp_only_when_correct_and_daily_cap(db_session):
    db = db_session
    m = await _kid(db)
    await gamification_ref(db)
    wrong = await tanda.answer_sambung(db, m.id, 78, 1, "pilihan", None, 78, 3)
    assert wrong["correct"] is False and wrong["rewarded"] is False
    right = await tanda.answer_sambung(db, m.id, 78, 1, "pilihan", None, 78, 2)
    assert right["correct"] is True and right["rewarded"] is True
    for _ in range(5):
        last = await tanda.answer_sambung(db, m.id, 78, 1, "ingat", "lancar", None, None)
    assert last["rewarded"] is False  # batas harian 3
    rewarded = (await db.execute(select(models.ConnectAttempt).where(models.ConnectAttempt.rewarded.is_(True)))).scalars().all()
    assert len(rewarded) == 3


async def test_sambung_result_feeds_marks(db_session):
    db = db_session
    m = await _kid(db)
    await gamification_ref(db)
    await tanda.answer_sambung(db, m.id, 78, 1, "ingat", "lupa", None, None)
    (mk,) = await tanda.active_marks(db, m.id)
    assert (mk.surah_id, mk.ayah_number, mk.source) == (78, 2, "auto")


async def gamification_ref(db):
    from app.services import gamification

    await gamification.ensure_reference_data(db)


async def test_api_latihan_and_tanda_roundtrip(client):
    from app.database import get_db
    from app.main import app

    reg = await register(client)
    tok = reg["access_token"]
    cid = await add_child(client, tok)
    child = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    gen = app.dependency_overrides[get_db]()
    db = await gen.__anext__()
    if not await db.get(models.Surah, 114):
        db.add(models.Surah(id=114, name_ar="x", name_id="An-Nas", ayah_count=6, juz_number=30, curriculum_order=1))
        await db.commit()
    r = await client.post("/latihan", headers=H(child), json={"kind": "murajaah", "results": [{"surah_id": 114, "ayah_number": 2, "result": "lupa"}]})
    assert r.status_code == 200 and r.json()["marks_created"] == 1
    marks = (await client.get("/tanda", headers=H(child))).json()
    assert len(marks) == 1 and marks[0]["source"] == "auto"
    d = await client.post(f"/tanda/{marks[0]['id']}/nonaktif", headers=H(child))
    assert d.status_code == 200 and (await client.get("/tanda", headers=H(child))).json() == []
    bad = await client.post("/latihan", headers=H(child), json={"kind": "murajaah", "results": [{"surah_id": 114, "ayah_number": 2, "result": "keren"}]})
    assert bad.status_code == 422
