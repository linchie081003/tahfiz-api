import uuid

from tests.helpers import make_teacher
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import models, schemas
from app.models import SubmissionContext, SubmissionStatus
from app.services import escalation, setor_flow, sesi3
from tests.helpers import H, add_child, register

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


async def _kid(db, with_teacher=False):
    fam = models.Family(name="K", access_code="EEE555")
    db.add(fam)
    await db.flush()
    m = models.Member(family_id=fam.id, name="Adik", age_mode=models.AgeMode.sd)
    db.add(m)
    db.add(models.Surah(id=78, name_ar="x", name_id="An-Naba'", ayah_count=40, juz_number=30, curriculum_order=1))
    await db.flush()
    db.add(models.MemberSurahProgress(member_id=m.id, surah_id=78, status=models.SurahProgressStatus.in_progress, current_ayah=1))
    teacher_id = None
    if with_teacher:
        teacher_id = await make_teacher(db)
        db.add(models.TeacherLink(teacher_id=teacher_id, family_id=fam.id, member_id=m.id, status="active", requested_by=uuid.uuid4()))
    await db.flush()
    return fam, m, teacher_id


def _sub(fam, m, hours_ago):
    return models.Submission(member_id=m.id, family_id=fam.id, context=SubmissionContext.ziyadah, surah_id=78, ayah_start=1, ayah_end=5,
                             reference_text="x", recording_key="k", status=SubmissionStatus.pending_eval, created_at=NOW - timedelta(hours=hours_ago))


async def _notes(db):
    return (await db.execute(select(models.AppNotification).order_by(models.AppNotification.kind))).scalars().all()


def test_stage_for():
    assert [escalation.stage_for(h) for h in (0, 23.9, 24, 47, 48, 71.9, 72, 200)] == [None, None, 24, 24, 48, 48, 72, 72]


async def test_no_notification_before_24h(db_session):
    fam, m, _ = await _kid(db_session, True)
    db_session.add(_sub(fam, m, 10))
    await db_session.flush()
    assert (await escalation.run_escalation(db_session, NOW))["created"] == 0


async def test_teacher_stages(db_session):
    db = db_session
    fam, m, tid = await _kid(db, True)
    s = _sub(fam, m, 25)
    db.add(s)
    await db.flush()
    await escalation.run_escalation(db, NOW)
    n = await _notes(db)
    assert [(x.recipient_role, x.kind) for x in n] == [("teacher", "pending_24")] and n[0].recipient_id == tid
    await escalation.run_escalation(db, NOW)  # idempoten
    assert len(await _notes(db)) == 1
    later = NOW + timedelta(hours=24)  # 49 jam
    await escalation.run_escalation(db, later)
    kinds = sorted((x.recipient_role, x.kind) for x in await _notes(db))
    assert kinds == [("parent", "pending_48"), ("teacher", "pending_24"), ("teacher", "pending_48")]
    await escalation.run_escalation(db, NOW + timedelta(hours=48))  # 73 jam
    parent72 = [x for x in await _notes(db) if x.kind == "pending_72"]
    assert len(parent72) == 1 and parent72[0].recipient_role == "parent" and parent72[0].recipient_id == fam.id


async def test_first_run_on_old_submission_creates_only_current_stage(db_session):
    db = db_session
    fam, m, _ = await _kid(db, True)
    db.add(_sub(fam, m, 80))
    await db.flush()
    await escalation.run_escalation(db, NOW)
    assert [(x.recipient_role, x.kind) for x in await _notes(db)] == [("parent", "pending_72")]


async def test_ignores_very_old_and_evaluated(db_session):
    db = db_session
    fam, m, _ = await _kid(db, True)
    db.add(_sub(fam, m, 24 * 30))
    done = _sub(fam, m, 50)
    done.status = SubmissionStatus.passed
    db.add(done)
    await db.flush()
    assert (await escalation.run_escalation(db, NOW))["created"] == 0


async def test_parent_is_notified_when_no_teacher(db_session):
    db = db_session
    fam, m, _ = await _kid(db, False)
    db.add(_sub(fam, m, 30))
    await db.flush()
    await escalation.run_escalation(db, NOW)
    assert [(x.recipient_role, x.kind) for x in await _notes(db)] == [("parent", "pending_24")]


async def test_never_changes_evaluator_or_status(db_session):
    db = db_session
    fam, m, _ = await _kid(db, True)
    s = _sub(fam, m, 100)
    db.add(s)
    await db.flush()
    await escalation.run_escalation(db, NOW)
    assert s.status == SubmissionStatus.pending_eval
    assert (await db.execute(select(models.EvaluationTakeover))).first() is None
    assert (await db.execute(select(models.Evaluation))).first() is None


async def test_takeover_requires_reason_teacher_and_pending(db_session):
    db = db_session
    fam, m, tid = await _kid(db, True)
    s = _sub(fam, m, 80)
    db.add(s)
    await db.flush()
    pid = uuid.uuid4()
    with pytest.raises(HTTPException) as e:
        await escalation.take_over(db, s, pid, "  ")
    assert e.value.status_code == 422
    t = await escalation.take_over(db, s, pid, "Guru sedang berhalangan")
    assert (t.from_role, t.from_id, t.to_role, t.to_id, t.reason) == ("teacher", tid, "parent", pid, "Guru sedang berhalangan")
    with pytest.raises(HTTPException) as e2:
        await escalation.take_over(db, s, pid, "lagi")
    assert e2.value.status_code == 409
    # setelah diambil alih tidak ada eskalasi lagi
    await escalation.run_escalation(db, NOW)
    assert await _notes(db) == []


async def test_nudge_once_and_only_with_teacher(db_session):
    db = db_session
    fam, m, tid = await _kid(db, True)
    s = _sub(fam, m, 80)
    db.add(s)
    await db.flush()
    assert await escalation.nudge_teacher(db, s, m) is True
    assert await escalation.nudge_teacher(db, s, m) is False
    fam2 = models.Family(name="K2", access_code="FFF666")
    db.add(fam2)
    await db.flush()
    m2 = models.Member(family_id=fam2.id, name="B", age_mode=models.AgeMode.sd)
    db.add(m2)
    await db.flush()
    s2 = _sub(fam2, m2, 80)
    db.add(s2)
    await db.flush()
    with pytest.raises(HTTPException):
        await escalation.nudge_teacher(db, s2, m2)


async def test_api_parent_flow_takeover_then_parent_can_evaluate(client):
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
    db.add(models.MemberSurahProgress(member_id=member.id, surah_id=78, status=models.SurahProgressStatus.in_progress, current_ayah=1))
    db.add(models.TeacherLink(teacher_id=await make_teacher(db), family_id=member.family_id, member_id=member.id, status="active", requested_by=uuid.uuid4()))
    sub = models.Submission(member_id=member.id, family_id=member.family_id, context=SubmissionContext.ziyadah, surah_id=78, ayah_start=1, ayah_end=5,
                            reference_text="x", recording_key="k", status=SubmissionStatus.pending_eval, created_at=datetime.now(timezone.utc) - timedelta(hours=80))
    db.add(sub)
    await db.commit()
    sid = str(sub.id)
    # daftar notifikasi menjalankan eskalasi: orang tua menerima pending_72 dengan pilihan tindakan
    lst = (await client.get("/notifikasi", headers=H(tok))).json()
    assert len(lst) == 1 and lst[0]["kind"] == "pending_72" and lst[0]["can_act"] is True
    # belum diambil alih: orang tua tidak boleh menilai
    assert (await client.post(f"/setor/{sid}/evaluate", headers=H(tok), json={"status": "passed"})).status_code == 403
    assert (await client.post(f"/setor/{sid}/ingatkan-guru", headers=H(tok))).status_code == 200
    assert (await client.post(f"/setor/{sid}/ambil-alih", headers=H(tok), json={"reason": ""})).status_code == 422
    assert (await client.post(f"/setor/{sid}/ambil-alih", headers=H(tok), json={"reason": "Guru tidak merespons"})).status_code == 200
    ev = await client.post(f"/setor/{sid}/evaluate", headers=H(tok), json={"status": "passed"})
    assert ev.status_code == 200
    evals = (await db.execute(select(models.Evaluation).where(models.Evaluation.submission_id == uuid.UUID(sid)))).scalars().all()
    assert len(evals) == 1 and evals[0].evaluator_role == "parent"
    # baca notifikasi
    assert (await client.post(f"/notifikasi/{lst[0]['id']}/baca", headers=H(tok))).status_code == 200
    assert (await client.get("/notifikasi", headers=H(tok))).json() == []
