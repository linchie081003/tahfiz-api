"""Antrean pra-cek STT: idempoten, timeout, retry berjeda, gagal permanen vs sementara, pemulihan."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import models
from app.config import settings
from app.models import SubmissionContext, SubmissionStatus
from app.services import stt, stt_queue
from tests.helpers import H, add_child, register, run_stt_jobs

AYAT = "قُلْ أَعُوذُ بِرَبِّ النَّاسِ"


@pytest.fixture
def engine_stub(monkeypatch):
    """STT palsu yang bisa diatur hasilnya per panggilan; audio ada di penyimpanan palsu."""
    state = {"calls": 0, "script": [stt.SttResult("قل اعوذ برب الناس", None)], "delay": 0.0}

    async def fake(audio, content_type="audio/webm", reference_hint=None):
        state["calls"] += 1
        if state["delay"]:
            await asyncio.sleep(state["delay"])
        item = state["script"][min(state["calls"] - 1, len(state["script"]) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(stt, "transcribe", fake)
    monkeypatch.setattr(stt, "is_configured", lambda: True)
    monkeypatch.setattr("app.services.storage.upload_recording", lambda *a, **k: "k")
    monkeypatch.setattr("app.services.storage.read_recording", lambda *a, **k: b"x" * 4000)
    return state


async def _sub(db, member, consent=True):
    if consent:
        pu = models.ParentUser(family_id=member.family_id, email=f"{uuid.uuid4().hex[:6]}@x.id", hashed_password="x", name="Ayah")
        db.add(pu)
        await db.flush()
        db.add(models.FamilyAiConsent(family_id=member.family_id, granted_by=pu.id))
    s = models.Submission(member_id=member.id, family_id=member.family_id, context=SubmissionContext.tahsin, reference_text=AYAT,
                          recording_key="k", status=SubmissionStatus.pending_eval, ai_status="pending")
    db.add(s)
    await db.flush()
    return s


async def _job(db, sub):
    return await stt_queue.job_of(db, sub.id)


async def _make_due(db, job):
    job.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.flush()


@pytest.mark.asyncio
async def test_enqueue_idempoten_dan_hasil_sukses(db_session, member_with_ziyadah, engine_stub):
    db, m = db_session, member_with_ziyadah
    sub = await _sub(db, m)
    j1 = await stt_queue.enqueue(db, sub)
    j2 = await stt_queue.enqueue(db, sub)
    assert j1.id == j2.id and sub.ai_status == "queued"
    assert len((await db.execute(select(models.SttJob))).scalars().all()) == 1
    stats = await stt_queue.process_due(db)
    assert stats["done"] == 1 and engine_stub["calls"] == 1
    await db.refresh(sub)
    assert sub.ai_status == "completed" and sub.ai_insights["available"] is True and sub.status == SubmissionStatus.pending_eval
    # putaran berikut tidak memproses ulang
    assert (await stt_queue.process_due(db)) == {"done": 0, "retry": 0, "failed": 0, "skipped": 0}
    assert engine_stub["calls"] == 1
    # mengantrekan lagi tanpa force tidak membuat pekerjaan baru
    await stt_queue.enqueue(db, sub)
    assert sub.ai_status == "completed" and engine_stub["calls"] == 1


@pytest.mark.asyncio
async def test_kegagalan_sementara_dicoba_ulang_dengan_jeda(db_session, member_with_ziyadah, engine_stub, monkeypatch):
    db, m = db_session, member_with_ziyadah
    monkeypatch.setattr(settings, "stt_job_backoff_seconds", 30.0)
    engine_stub["script"] = [stt.SttResult(None, "stt_network"), stt.SttResult(None, "stt_quota"), stt.SttResult("قل اعوذ برب الناس", None)]
    sub = await _sub(db, m)
    await stt_queue.enqueue(db, sub)
    assert (await stt_queue.process_due(db))["retry"] == 1
    job = await _job(db, sub)
    assert job.status == "queued" and job.attempts == 1 and job.last_error == "stt_network"
    assert job.next_attempt_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(seconds=20)  # ada jeda
    assert (await stt_queue.process_due(db)) == {"done": 0, "retry": 0, "failed": 0, "skipped": 0}  # belum jatuh tempo
    await _make_due(db, job)
    assert (await stt_queue.process_due(db))["retry"] == 1 and job.attempts == 2
    first_gap = job.next_attempt_at
    assert first_gap.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(seconds=45)  # jeda berlipat
    await _make_due(db, job)
    assert (await stt_queue.process_due(db))["done"] == 1
    await db.refresh(sub)
    assert sub.ai_status == "completed" and sub.ai_insights["available"] is True and job.status == "done"


@pytest.mark.asyncio
async def test_kehabisan_percobaan_gagal_tapi_bisa_dinilai_dan_dipulihkan(db_session, member_with_ziyadah, engine_stub, monkeypatch):
    db, m = db_session, member_with_ziyadah
    monkeypatch.setattr(settings, "stt_job_max_attempts", 2)
    engine_stub["script"] = [stt.SttResult(None, "stt_api")] * 2 + [stt.SttResult("قل اعوذ برب الناس", None)]
    sub = await _sub(db, m)
    job = await stt_queue.enqueue(db, sub)
    await stt_queue.process_due(db)
    await _make_due(db, job)
    assert (await stt_queue.process_due(db))["failed"] == 1
    await db.refresh(sub)
    assert job.status == "failed" and sub.ai_status == "failed" and sub.ai_insights["retryable"] is True
    assert sub.ai_insights["available"] is False and sub.status == SubmissionStatus.pending_eval  # penilaian tidak terblokir
    assert (await stt_queue.process_due(db)) == {"done": 0, "retry": 0, "failed": 0, "skipped": 0}  # tidak mencoba selamanya
    # pemulihan: antre ulang (force) -> berhasil
    await stt_queue.enqueue(db, sub, force=True)
    assert job.status == "queued" and job.attempts == 0 and sub.ai_status == "queued"
    assert (await stt_queue.process_due(db))["done"] == 1
    await db.refresh(sub)
    assert sub.ai_status == "completed" and sub.ai_insights["available"] is True


@pytest.mark.asyncio
async def test_timeout_dihitung_sebagai_gagal_sementara(db_session, member_with_ziyadah, engine_stub, monkeypatch):
    db, m = db_session, member_with_ziyadah
    monkeypatch.setattr(settings, "stt_job_timeout_seconds", 0.05)
    engine_stub["delay"] = 0.5
    sub = await _sub(db, m)
    await stt_queue.enqueue(db, sub)
    assert (await stt_queue.process_due(db))["retry"] == 1
    assert (await _job(db, sub)).last_error == "stt_timeout"


@pytest.mark.asyncio
async def test_exception_tak_terduga_tidak_mematikan_pekerja(db_session, member_with_ziyadah, engine_stub):
    db, m = db_session, member_with_ziyadah
    engine_stub["script"] = [RuntimeError("boom")]
    sub = await _sub(db, m)
    await stt_queue.enqueue(db, sub)
    assert (await stt_queue.process_due(db))["retry"] == 1
    job = await _job(db, sub)
    assert job.last_error == "stt_api" and job.status == "queued"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["stt_auth", "stt_empty", "stt_not_installed"])
async def test_kegagalan_permanen_tidak_diulang(db_session, member_with_ziyadah, engine_stub, failure):
    db, m = db_session, member_with_ziyadah
    engine_stub["script"] = [stt.SttResult(None, failure)]
    sub = await _sub(db, m)
    await stt_queue.enqueue(db, sub)
    assert (await stt_queue.process_due(db))["done"] == 1
    await db.refresh(sub)
    assert sub.ai_status == "completed" and sub.ai_insights == {**sub.ai_insights, "available": False, "reason": failure}
    assert engine_stub["calls"] == 1


@pytest.mark.asyncio
async def test_persetujuan_dicabut_setelah_antre_suara_tidak_dikirim(db_session, member_with_ziyadah, engine_stub):
    db, m = db_session, member_with_ziyadah
    sub = await _sub(db, m, consent=False)
    await stt_queue.enqueue(db, sub)
    await stt_queue.process_due(db)
    await db.refresh(sub)
    assert engine_stub["calls"] == 0 and sub.ai_insights["reason"] == "no_consent"


@pytest.mark.asyncio
async def test_pekerja_mati_kunci_kedaluwarsa_diklaim_ulang_lalu_berhenti(db_session, member_with_ziyadah, engine_stub, monkeypatch):
    db, m = db_session, member_with_ziyadah
    monkeypatch.setattr(settings, "stt_job_max_attempts", 2)
    sub = await _sub(db, m)
    job = await stt_queue.enqueue(db, sub)
    # simulasi pekerja mati di tengah proses: processing dengan kunci kedaluwarsa
    job.status, job.attempts, job.locked_until = "processing", 1, datetime.now(timezone.utc) - timedelta(seconds=5)
    await db.flush()
    assert (await stt_queue.process_due(db))["done"] == 1 and job.attempts == 2  # diklaim ulang dan selesai
    # kunci masih berlaku -> tidak diambil pekerja lain
    sub2 = await _sub(db, m, consent=False)
    j2 = await stt_queue.enqueue(db, sub2)
    j2.status, j2.attempts, j2.locked_until = "processing", 1, datetime.now(timezone.utc) + timedelta(minutes=5)
    await db.flush()
    assert await stt_queue.claim_next(db) is None
    # sudah mencapai batas percobaan dan kunci kedaluwarsa -> dinyatakan gagal (bukan diulang tanpa akhir)
    j2.attempts, j2.locked_until = 2, datetime.now(timezone.utc) - timedelta(seconds=5)
    await db.flush()
    assert await stt_queue.claim_next(db) is None
    await db.refresh(sub2)
    assert j2.status == "failed" and sub2.ai_status == "failed"


@pytest.mark.asyncio
async def test_setoran_digantikan_atau_rekaman_dihapus_dilewati(db_session, member_with_ziyadah, engine_stub):
    db, m = db_session, member_with_ziyadah
    sub = await _sub(db, m)
    await stt_queue.enqueue(db, sub)
    sub.status = SubmissionStatus.superseded
    await db.flush()
    assert (await stt_queue.process_due(db))["skipped"] == 1 and engine_stub["calls"] == 0
    sub2 = await _sub(db, m, consent=False)
    db.add(models.FamilyAiConsent) if False else None
    await stt_queue.enqueue(db, sub2)
    sub2.recording_deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await stt_queue.process_due(db)
    await db.refresh(sub2)
    assert sub2.ai_insights["reason"] == "recording_deleted" and engine_stub["calls"] == 0


@pytest.mark.asyncio
async def test_hasil_lama_tidak_menimpa_hasil_yang_sudah_ada(db_session, member_with_ziyadah, engine_stub):
    db, m = db_session, member_with_ziyadah
    sub = await _sub(db, m)
    await stt_queue.enqueue(db, sub)
    sub.ai_status, sub.ai_insights = "completed", {"available": True, "summaryPercent": 77}  # diselesaikan jalur lain
    await db.flush()
    assert (await stt_queue.process_due(db))["skipped"] == 1
    assert sub.ai_insights["summaryPercent"] == 77 and engine_stub["calls"] == 0


# ---------------------------------------------------------------- lewat API

async def test_api_setor_tidak_menunggu_stt_dan_reprocess_idempoten(client, engine_stub, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "local_recordings_dir", str(tmp_path))
    reg = await register(client)
    tok = reg["access_token"]
    cid = await add_child(client, tok)
    ctok = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    await client.post("/family/consent/recording", json={"granted": True}, headers=H(tok))
    await client.put("/settings/ai-consent", json={"granted": True}, headers=H(tok))
    r = await client.post("/setor", data={"context": "tahsin", "reference_text": AYAT}, files={"file": ("r.webm", b"x" * 4000, "audio/webm")}, headers=H(ctok))
    assert r.status_code == 200 and r.json()["ai_status"] == "queued" and r.json()["status"] == "pending_eval"
    sid = r.json()["id"]
    q = (await client.get("/setor/queue", headers=H(tok))).json()
    assert q[0]["ai_status"] == "queued" and q[0]["ai_insights"] is None  # parent sudah bisa menilai
    # reprocess dua kali -> tetap satu pekerjaan
    for _ in range(2):
        assert (await client.post(f"/setor/{sid}/reprocess-precheck", headers=H(tok))).status_code == 200
    assert engine_stub["calls"] == 0
    assert (await run_stt_jobs())["done"] == 1 and engine_stub["calls"] == 1
    q = (await client.get("/setor/queue", headers=H(tok))).json()
    assert q[0]["ai_status"] == "completed" and q[0]["ai_insights"]["available"] is True
    # menilai sebelum/sesudah pra-cek tidak bergantung padanya
    assert (await client.post(f"/setor/{sid}/evaluate", json={"status": "needs_retry"}, headers=H(tok))).status_code == 200
