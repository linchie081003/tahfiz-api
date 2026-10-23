import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import models, schemas
from app.models import SubmissionContext, SubmissionStatus
from app.services import setor_flow, sesi3, tanda
from tests.helpers import H, add_child, register


async def _kid(db):
    fam = models.Family(name="K", access_code="SSS333")
    db.add(fam)
    await db.flush()
    m = models.Member(family_id=fam.id, name="Adik", age_mode=models.AgeMode.sd)
    db.add(m)
    db.add(models.Surah(id=78, name_ar="x", name_id="An-Naba'", ayah_count=40, juz_number=30, curriculum_order=1))
    await db.flush()
    db.add(models.MemberSurahProgress(member_id=m.id, surah_id=78, status=models.SurahProgressStatus.in_progress, current_ayah=1))
    await db.flush()
    return fam, m


def _sub(fam, m, a, b, status=SubmissionStatus.pending_eval, **kw):
    return models.Submission(member_id=m.id, family_id=fam.id, context=SubmissionContext.ziyadah, surah_id=78, ayah_start=a, ayah_end=b,
                             reference_text="x", recording_key="k", status=status, **kw)


async def test_inactive_without_recent_ziyadah(db_session):
    fam, m = await _kid(db_session)
    r = await sesi3.build(db_session, m.id)
    assert r["active"] is False and r["sample"] == []


async def test_active_with_pending_or_recent_passed_but_not_old_passed(db_session):
    db = db_session
    fam, m = await _kid(db)
    old = datetime.now(timezone.utc) - timedelta(days=10)
    db.add(_sub(fam, m, 1, 5, SubmissionStatus.passed, created_at=old, evaluated_at=old))
    await db.flush()
    assert (await sesi3.build(db, m.id))["active"] is False  # lulus lebih dari 7 hari lalu
    db.add(_sub(fam, m, 6, 10))
    await db.flush()
    r = await sesi3.build(db, m.id, random.Random(1))
    assert r["active"] is True and len(r["sample"]) == 3
    assert all(6 <= c["ayah_number"] <= 10 and c["state"] == "pending" for c in r["sample"])


async def test_sample_prefers_marked_and_remedial(db_session):
    db = db_session
    fam, m = await _kid(db)
    now = datetime.now(timezone.utc)
    db.add(_sub(fam, m, 1, 10, SubmissionStatus.passed, evaluated_at=now))
    db.add(_sub(fam, m, 11, 15, SubmissionStatus.needs_retry, evaluated_at=now))
    await db.flush()
    await tanda.create_mark(db, m.id, 78, 3)
    r = await sesi3.build(db, m.id, random.Random(2))
    keys = [(c["ayah_number"], c["state"]) for c in r["sample"]]
    assert (3, "passed") in keys  # ayat bertanda masuk
    assert sum(1 for _, s in keys if s == "remedial") == 2  # sisanya remediasi didahulukan dari lulus


async def test_needs_retry_creates_correction_request_once(db_session):
    db = db_session
    fam, m = await _kid(db)
    s = _sub(fam, m, 1, 5)
    db.add(s)
    await db.flush()
    await setor_flow.apply_submission_evaluation(db, s, m, schemas.EvaluateSubmissionIn(status=SubmissionStatus.needs_retry))
    reqs = (await db.execute(select(models.EvaluationRequest))).scalars().all()
    assert len(reqs) == 1 and reqs[0].reason == "correction" and reqs[0].assignee_role == "parent"
    again = await sesi3.create_request(db, m, s.id, "parent_request")
    assert again.id == reqs[0].id  # satu permintaan terbuka per setoran


async def test_passed_evaluation_creates_no_request(db_session):
    db = db_session
    fam, m = await _kid(db)
    s = _sub(fam, m, 1, 5)
    db.add(s)
    await db.flush()
    await setor_flow.apply_submission_evaluation(db, s, m, schemas.EvaluateSubmissionIn(status=SubmissionStatus.passed))
    assert (await db.execute(select(models.EvaluationRequest))).first() is None


async def test_child_request_requires_mark_and_has_daily_cap(db_session):
    db = db_session
    fam, m = await _kid(db)
    s1, s2 = _sub(fam, m, 1, 5), _sub(fam, m, 6, 10)
    db.add_all([s1, s2])
    await db.flush()
    with pytest.raises(HTTPException) as e:
        await sesi3.create_request(db, m, s1.id, "child_mark", ayah_number=2)
    assert e.value.status_code == 422  # belum ditandai
    await tanda.create_mark(db, m.id, 78, 2)
    await tanda.create_mark(db, m.id, 78, 7)
    r = await sesi3.create_request(db, m, s1.id, "child_mark", ayah_number=2)
    assert r.reason == "child_mark"
    with pytest.raises(HTTPException) as e2:
        await sesi3.create_request(db, m, s2.id, "child_mark", ayah_number=7)
    assert e2.value.status_code == 409  # batas satu per hari


async def test_offer_rules(db_session):
    db = db_session
    fam, m = await _kid(db)
    s = _sub(fam, m, 1, 5)
    db.add(s)
    await db.flush()
    mk = await tanda.create_mark(db, m.id, 78, 2)
    assert await sesi3.offer(db, m.id) is None  # tanda baru, belum cukup
    await tanda.record_results(db, m.id, "murajaah", [(78, 2, "lupa")])
    await tanda.record_results(db, m.id, "murajaah", [(78, 2, "lupa")])
    off = await sesi3.offer(db, m.id)
    assert off and off["reason"] == "lupa_berulang" and off["ayah_number"] == 2
    mk.created_at = datetime.now(timezone.utc) - timedelta(days=3)
    assert (await sesi3.offer(db, m.id))["reason"] == "tanda_lama"
    await sesi3.create_request(db, m, s.id, "child_mark", ayah_number=2)
    assert await sesi3.offer(db, m.id) is None  # sudah ada permintaan dan batas harian


async def test_evaluator_marks_and_resolution_via_api(client):
    from app.database import get_db
    from app.main import app

    reg = await register(client)
    tok = reg["access_token"]
    cid = await add_child(client, tok)
    child = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    gen = app.dependency_overrides[get_db]()
    db = await gen.__anext__()
    if not await db.get(models.Surah, 78):
        db.add(models.Surah(id=78, name_ar="x", name_id="An-Naba'", ayah_count=40, juz_number=30, curriculum_order=1))
        await db.flush()
    member = await db.get(models.Member, uuid.UUID(cid))
    sub = models.Submission(member_id=member.id, family_id=member.family_id, context=SubmissionContext.ziyadah, surah_id=78, ayah_start=1, ayah_end=5,
                            reference_text="x", recording_key="k", status=SubmissionStatus.pending_eval)
    db.add(sub)
    await db.commit()
    s3 = (await client.get("/sesi3", headers=H(child))).json()
    assert s3["active"] is True and len(s3["sample"]) == 3

    r = await client.post(f"/penilai/anak/{cid}/permintaan", headers=H(tok), json={"submission_id": str(sub.id), "ayah_number": 2})
    assert r.status_code == 201
    lst = (await client.get("/penilai/permintaan", headers=H(tok))).json()
    assert len(lst) == 1 and lst[0]["reason"] == "parent_request" and lst[0]["surah_name"] == "An-Naba'"

    mk = await client.post(f"/penilai/anak/{cid}/tanda", headers=H(tok), json={"surah_id": 78, "ayah_number": 2})
    assert mk.status_code == 201
    marks = (await client.get("/tanda", headers=H(child))).json()
    assert marks[0]["created_by_role"] == "evaluator"
    # anak tidak bisa menghapus tanda penilai, penilai bisa
    assert (await client.post(f"/tanda/{marks[0]['id']}/nonaktif", headers=H(child))).status_code == 403
    assert (await client.post(f"/penilai/tanda/{marks[0]['id']}/nonaktif", headers=H(tok))).status_code == 200
    done = await client.post(f"/penilai/permintaan/{lst[0]['id']}/selesai", headers=H(tok), json={"note": "sudah dicek"})
    assert done.status_code == 200
    assert (await client.get("/penilai/permintaan", headers=H(tok))).json() == []
    # anak tidak bisa memakai sisi penilai
    assert (await client.get("/penilai/permintaan", headers=H(child))).status_code == 403
