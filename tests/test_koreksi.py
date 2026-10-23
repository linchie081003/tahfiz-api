import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import models, schemas
from app.models import SubmissionContext, SubmissionStatus, SurahProgressStatus
from app.services import corrections, escalation, setor_flow, sesi3
from tests.helpers import H, add_child, register


async def _kid(db, ayah_count=40):
    fam = models.Family(name="K", access_code="KKK777")
    db.add(fam)
    await db.flush()
    m = models.Member(family_id=fam.id, name="Adik", age_mode=models.AgeMode.sd)
    db.add(m)
    db.add(models.Surah(id=78, name_ar="x", name_id="An-Naba'", ayah_count=ayah_count, juz_number=30, curriculum_order=1))
    await db.flush()
    db.add(models.MemberSurahProgress(member_id=m.id, surah_id=78, status=SurahProgressStatus.in_progress, current_ayah=1))
    await gam(db)
    await db.flush()
    return fam, m


async def gam(db):
    from app.services import gamification

    await gamification.ensure_reference_data(db)


async def _judged(db, fam, m, a, b, status):
    s = models.Submission(member_id=m.id, family_id=fam.id, context=SubmissionContext.ziyadah, surah_id=78, ayah_start=a, ayah_end=b,
                          reference_text="x", recording_key="k", status=SubmissionStatus.pending_eval)
    db.add(s)
    await db.flush()
    await setor_flow.apply_submission_evaluation(db, s, m, schemas.EvaluateSubmissionIn(status=status), evaluator_id=uuid.uuid4(), evaluator_role="parent")
    return s


async def test_correction_appends_never_overwrites_and_keeps_history(db_session):
    db = db_session
    fam, m = await _kid(db)
    s = await _judged(db, fam, m, 1, 5, SubmissionStatus.needs_retry)
    first = (await corrections.history(db, s.id))[0]
    pid = uuid.uuid4()
    ev = await corrections.correct(db, s, m, evaluator_id=pid, evaluator_role="parent", status=SubmissionStatus.passed, notes="ok", rubric_scores=None, reason="Salah menilai")
    hist = await corrections.history(db, s.id)
    assert [e.result for e in hist] == ["needs_retry", "passed"]
    assert hist[0].id == first.id and hist[0].result == "needs_retry"  # asli tidak berubah
    assert ev.corrects_id == first.id and ev.correction_reason == "Salah menilai"
    assert corrections.active_of(hist).id == ev.id
    assert s.status == SubmissionStatus.passed


async def test_correction_needs_reason_and_judged_submission(db_session):
    db = db_session
    fam, m = await _kid(db)
    s = await _judged(db, fam, m, 1, 5, SubmissionStatus.passed)
    with pytest.raises(HTTPException) as e:
        await corrections.correct(db, s, m, evaluator_id=uuid.uuid4(), evaluator_role="parent", status=SubmissionStatus.needs_retry, notes=None, rubric_scores=None, reason=" ")
    assert e.value.status_code == 422
    pending = models.Submission(member_id=m.id, family_id=fam.id, context=SubmissionContext.ziyadah, surah_id=78, ayah_start=6, ayah_end=7,
                                reference_text="x", recording_key="k", status=SubmissionStatus.pending_eval)
    db.add(pending)
    await db.flush()
    with pytest.raises(HTTPException) as e2:
        await corrections.correct(db, pending, m, evaluator_id=uuid.uuid4(), evaluator_role="parent", status=SubmissionStatus.passed, notes=None, rubric_scores=None, reason="x")
    assert e2.value.status_code == 409


async def test_passed_to_needs_retry_supersedes_range_stops_schedule_and_recomputes_progress(db_session):
    db = db_session
    fam, m = await _kid(db)
    s1 = await _judged(db, fam, m, 1, 5, SubmissionStatus.passed)
    s2 = await _judged(db, fam, m, 6, 10, SubmissionStatus.passed)
    assert len((await db.execute(select(models.MurojaahItem).where(models.MurojaahItem.completed.is_(False)))).scalars().all()) == 2
    await corrections.correct(db, s2, m, evaluator_id=uuid.uuid4(), evaluator_role="teacher", status=SubmissionStatus.needs_retry, notes=None, rubric_scores=None, reason="Ada ayat keliru")
    rngs = {(r.ayah_start, r.status) for r in (await db.execute(select(models.MemorizedRange))).scalars().all()}
    assert rngs == {(1, "passed"), (6, "superseded")}
    open_items = (await db.execute(select(models.MurojaahItem).where(models.MurojaahItem.completed.is_(False)))).scalars().all()
    assert [(i.ayah_start, i.ayah_end) for i in open_items] == [(1, 5)]  # jadwal rentang 6-10 berhenti
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    assert prog.current_ayah == 6 and prog.status == SurahProgressStatus.needs_retry  # sama dengan alur penilaian biasa
    # XP tidak ditarik, dan permintaan cek lanjutan dibuat
    assert (await db.execute(select(models.EvaluationRequest).where(models.EvaluationRequest.reason == "correction"))).scalars().first()


async def test_needs_retry_to_passed_creates_range_schedule_and_xp_once(db_session):
    db = db_session
    fam, m = await _kid(db, ayah_count=10)
    s = await _judged(db, fam, m, 1, 10, SubmissionStatus.needs_retry)
    stats = await __import__("app.services.gamification", fromlist=["x"]).ensure_member_stats(db, m.id)
    xp0 = stats.xp
    await corrections.correct(db, s, m, evaluator_id=uuid.uuid4(), evaluator_role="parent", status=SubmissionStatus.passed, notes=None, rubric_scores=None, reason="Sudah lancar")
    rng = (await db.execute(select(models.MemorizedRange))).scalar_one()
    assert (rng.ayah_start, rng.ayah_end, rng.status) == (1, 10, "passed")
    assert (await db.execute(select(models.MurojaahItem))).scalar_one().range_id == rng.id
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    assert prog.status == SurahProgressStatus.passed
    assert stats.xp == xp0 + 30
    await corrections.correct(db, s, m, evaluator_id=uuid.uuid4(), evaluator_role="parent", status=SubmissionStatus.needs_retry, notes=None, rubric_scores=None, reason="Koreksi lagi")
    await corrections.correct(db, s, m, evaluator_id=uuid.uuid4(), evaluator_role="parent", status=SubmissionStatus.passed, notes=None, rubric_scores=None, reason="Benar lulus")
    assert stats.xp == xp0 + 30  # XP tidak dobel
    assert len((await db.execute(select(models.MemorizedRange))).scalars().all()) == 1  # rentang dipakai ulang, tidak ganda


async def test_parent_switch_off_blocks_evaluating_and_notifications(db_session):
    db = db_session
    fam, m = await _kid(db)
    db.add(models.FamilySettings(family_id=fam.id, parent_can_evaluate=False))
    await db.flush()
    assert await sesi3.responsible(db, m.id) == ("none", None)
    assert await corrections.parent_may_evaluate(db, fam.id) is False
    from datetime import timedelta
    s = models.Submission(member_id=m.id, family_id=fam.id, context=SubmissionContext.ziyadah, surah_id=78, ayah_start=1, ayah_end=5, reference_text="x",
                          recording_key="k", status=SubmissionStatus.pending_eval, created_at=datetime.now(timezone.utc) - timedelta(hours=60))
    db.add(s)
    await db.flush()
    assert (await escalation.run_escalation(db))["created"] == 0  # tidak ada penilai, tidak ada pengingat
    assert s.status == SubmissionStatus.pending_eval


async def test_api_switch_and_correction_flow(client):
    from app.database import get_db
    from app.main import app

    reg = await register(client)
    tok = reg["access_token"]
    cid = await add_child(client, tok)
    gen = app.dependency_overrides[get_db]()
    db = await gen.__anext__()
    if not await db.get(models.Surah, 78):
        db.add(models.Surah(id=78, name_ar="x", name_id="An-Naba'", ayah_count=40, juz_number=30, curriculum_order=1))
        await db.flush()
    member = await db.get(models.Member, uuid.UUID(cid))
    db.add(models.MemberSurahProgress(member_id=member.id, surah_id=78, status=SurahProgressStatus.in_progress, current_ayah=1))
    sub = models.Submission(member_id=member.id, family_id=member.family_id, context=SubmissionContext.ziyadah, surah_id=78, ayah_start=1, ayah_end=5,
                            reference_text="x", recording_key="k", status=SubmissionStatus.pending_eval)
    db.add(sub)
    await db.commit()
    sid = str(sub.id)
    # saklar mati: orang tua tidak boleh menilai
    r = await client.patch("/settings/family", headers=H(tok), json={"parent_can_evaluate": False})
    assert r.status_code == 200 and r.json()["parent_can_evaluate"] is False
    assert (await client.post(f"/setor/{sid}/evaluate", headers=H(tok), json={"status": "passed"})).status_code == 403
    await client.patch("/settings/family", headers=H(tok), json={"parent_can_evaluate": True})
    assert (await client.post(f"/setor/{sid}/evaluate", headers=H(tok), json={"status": "needs_retry"})).status_code == 200
    bad = await client.post(f"/setor/{sid}/koreksi", headers=H(tok), json={"status": "passed", "reason": ""})
    assert bad.status_code == 422
    ok = await client.post(f"/setor/{sid}/koreksi", headers=H(tok), json={"status": "passed", "reason": "Ternyata sudah lancar"})
    assert ok.status_code == 200 and ok.json()["status"] == "passed"
    hist = (await client.get(f"/setor/{sid}/riwayat-penilaian", headers=H(tok))).json()
    assert [h["result"] for h in hist] == ["needs_retry", "passed"] and [h["active"] for h in hist] == [False, True]
    assert hist[1]["correction_reason"] == "Ternyata sudah lancar"
