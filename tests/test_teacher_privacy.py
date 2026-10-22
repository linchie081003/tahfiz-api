import io
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.config import settings
from app.services import teaching
from tests.helpers import H, add_child, register

AYAT = "قُلْ أَعُوذُ بِرَبِّ النَّاسِ"


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_recordings_dir", str(tmp_path))


async def reg_teacher(c, email="guru@x.com", code=None):
    body = {"name": "Ustadzah Rina", "email": email, "password": "rahasia123"}
    if code:
        body["institution_code"] = code
    r = await c.post("/teacher/register", json=body)
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


async def setup_family(c):
    reg = await register(c)
    tok = reg["access_token"]
    cid = await add_child(c, tok)
    inv = (await c.post("/family/invites", headers=H(tok))).json()["code"]
    tok2 = (await c.post("/family/join", json={"code": inv, "name": "Ibu", "email": "ibu@x.com", "password": "rahasia123"})).json()["access_token"]
    ch = await c.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})
    return tok, tok2, cid, ch.json()["access_token"]


async def link_teacher(c, tok, tok2, cid, ttok):
    code = (await c.get("/teacher/me", headers=H(ttok))).json()["invite_code"]
    r = await c.post("/family/teachers/connect", json={"code": code, "member_id": cid}, headers=H(tok))
    assert r.status_code == 201, r.text
    assert r.json()["needs_review"] is True
    link_id = r.json()["link_id"]
    # guru belum terverifikasi tidak bisa menerima murid
    reqs = (await c.get("/teacher/requests", headers=H(ttok))).json()
    assert (await c.post(f"/teacher/requests/{reqs[0]['link_id']}/respond", json={"accept": True}, headers=H(ttok))).status_code == 409
    # orang tua kedua boleh meninjau; platform tidak memeriksa dokumen
    await c.post("/teacher/documents", json={"title": "Ijazah tahsin"}, headers=H(ttok))
    rv = (await c.get("/family/teachers/review", headers=H(tok2))).json()
    assert rv[0]["teacher"]["documents"][0]["title"] == "Ijazah tahsin"
    assert (await c.post(f"/family/links/{link_id}/review", json={"approve": True}, headers=H(tok2))).json()["teacher_status"] == "verified"
    assert (await c.post(f"/teacher/requests/{link_id}/respond", json={"accept": True}, headers=H(ttok))).json()["status"] == "active"
    return link_id


async def submit(c, ctok):
    return await c.post("/setor", data={"context": "tahsin", "reference_text": AYAT},
                        files={"file": ("r.webm", b"x" * 3000, "audio/webm")}, headers=H(ctok))


async def test_teacher_verification_by_parent_and_exclusive_control(client):
    tok, tok2, cid, ctok = await setup_family(client)
    ttok = await reg_teacher(client)
    link_id = await link_teacher(client, tok, tok2, cid, ttok)
    # satu guru aktif per anak
    other = await reg_teacher(client, "guru2@x.com")
    code2 = (await client.get("/teacher/me", headers=H(other))).json()["invite_code"]
    assert (await client.post("/family/teachers/connect", json={"code": code2, "member_id": cid}, headers=H(tok))).status_code == 409
    # orang tua tidak lagi mengatur; guru mengatur
    assert (await client.put(f"/members/{cid}/settings", json={"daily_ayahs": 2}, headers=H(tok))).status_code == 403
    r = await client.put(f"/teacher/students/{cid}/settings", json={"daily_ayahs": 2}, headers=H(ttok))
    assert r.status_code == 200 and r.json()["set_by"] == "teacher"
    assert (await client.post(f"/teacher/students/{cid}/points/1/result", json={"score": 9}, headers=H(ttok))).status_code == 200
    # mengganti guru hanya pemilik
    assert (await client.post(f"/family/links/{link_id}/revoke", headers=H(tok2))).status_code == 403
    assert (await client.post(f"/family/links/{link_id}/revoke", headers=H(tok))).json()["status"] == "revoked"
    assert (await client.put(f"/members/{cid}/settings", json={"daily_ayahs": 3}, headers=H(tok))).status_code == 200


async def test_parent_rejects_teacher(client):
    tok, tok2, cid, _ = await setup_family(client)
    ttok = await reg_teacher(client)
    code = (await client.get("/teacher/me", headers=H(ttok))).json()["invite_code"]
    link_id = (await client.post("/family/teachers/connect", json={"code": code, "member_id": cid}, headers=H(tok))).json()["link_id"]
    r = await client.post(f"/family/links/{link_id}/review", json={"approve": False}, headers=H(tok))
    assert r.json() == {"teacher_status": "rejected", "link_status": "rejected"}
    assert (await client.get("/teacher/me", headers=H(ttok))).json()["status"] == "rejected"


async def test_recording_consent_access_log_and_lock(client):
    tok, tok2, cid, ctok = await setup_family(client)
    ttok = await reg_teacher(client)
    link_id = await link_teacher(client, tok, tok2, cid, ttok)
    await client.post("/family/consent/recording", json={"granted": True}, headers=H(tok))
    sid = (await submit(client, ctok)).json()["id"]
    q = (await client.get("/teacher/queue", headers=H(ttok))).json()
    assert q[0]["can_hear"] is False and q[0]["overdue"] is False
    assert (await client.get(f"/teacher/media/{sid}", headers=H(ttok))).status_code == 403  # izin belum aktif
    # hanya pemilik memberi izin
    assert (await client.post(f"/family/links/{link_id}/consent", json={"granted": True}, headers=H(tok2))).status_code == 403
    assert (await client.post(f"/family/links/{link_id}/consent", json={"granted": True}, headers=H(tok))).status_code == 200
    assert (await client.get(f"/teacher/media/{sid}", headers=H(ttok))).status_code == 200
    log = (await client.get("/family/access-log", headers=H(tok))).json()
    assert len(log) == 1 and log[0]["teacher"] == "Ustadzah Rina"
    assert (await client.get("/family/access-log", headers=H(tok2))).status_code == 403
    # cabut izin menutup akses seketika
    await client.post(f"/family/links/{link_id}/consent", json={"granted": False}, headers=H(tok))
    assert (await client.get(f"/teacher/media/{sid}", headers=H(ttok))).status_code == 403


async def test_teacher_evaluates_and_parent_cannot(client):
    tok, tok2, cid, ctok = await setup_family(client)
    ttok = await reg_teacher(client)
    await link_teacher(client, tok, tok2, cid, ttok)
    sid = (await submit(client, ctok)).json()["id"]
    body = {"status": "passed", "rubric_scores": {"makhraj": 5}, "evaluator_notes": "Bagus, latih huruf ص"}
    assert (await client.post(f"/setor/{sid}/evaluate", json=body, headers=H(tok))).status_code == 403
    assert (await client.post(f"/teacher/submissions/{sid}/evaluate", json=body, headers=H(ttok))).json()["status"] == "passed"
    assert (await client.post("/family/messages/reply", json={"member_id": cid, "body": "Terima kasih"}, headers=H(tok2))).status_code == 201
    assert "Terima kasih" in (await client.get("/teacher/inbox", headers=H(ttok))).json()[0]["body"]
    msgs = (await client.get("/family/messages", headers=H(tok2))).json()
    assert msgs["unread"] == 1 and "huruf" in msgs["messages"][0]["body"]
    await client.post("/family/messages/read", headers=H(tok2))
    assert (await client.get("/family/messages", headers=H(tok2))).json()["unread"] == 0


async def test_without_consent_recording_is_not_stored(client):
    tok, _, cid, ctok = await setup_family(client)
    sid = (await submit(client, ctok)).json()["id"]
    assert (await client.get(f"/setor/media/{sid}", headers=H(tok))).status_code == 404
    q = (await client.get("/setor/queue", headers=H(tok))).json()
    assert len(q) == 1  # tetap masuk penilai tanpa audio


async def test_second_parent_can_delete_recordings_and_download(client):
    tok, tok2, cid, ctok = await setup_family(client)
    await client.post("/family/consent/recording", json={"granted": True}, headers=H(tok))
    sid = (await submit(client, ctok)).json()["id"]
    assert (await client.get(f"/setor/media/{sid}", headers=H(tok2))).status_code == 200
    tkn = (await client.post("/family/export", json={"member_id": cid}, headers=H(tok2))).json()["token"]
    z = await client.get(f"/family/export/download?token={tkn}")
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "data.json" in names and f"rekaman/{sid}.webm" in names
    assert (await client.get("/family/export/download?token=salah")).status_code == 410
    assert (await client.post("/family/recordings/delete", json={"member_id": cid, "pin": "1234"}, headers=H(tok2))).status_code == 409  # belum ada PIN
    assert (await client.put("/family/pin", json={"pin": "1234"}, headers=H(tok2))).json()["has_pin"] is True
    assert (await client.put("/family/pin", json={"pin": "9999"}, headers=H(tok2))).status_code == 403  # perlu PIN lama
    assert (await client.post("/family/recordings/delete", json={"member_id": cid, "pin": "0000"}, headers=H(tok2))).status_code == 403
    summ = (await client.get(f"/family/privacy-summary?member_id={cid}", headers=H(tok2))).json()
    assert summ["recordings"] == 1 and summ["retention_days"] == 30
    r = (await client.post("/family/recordings/delete", json={"member_id": cid, "pin": "1234"}, headers=H(tok2))).json()
    assert r["deleted"] == 1 and "7 hari" in r["message"]
    assert (await client.get(f"/setor/media/{sid}", headers=H(tok2))).status_code == 404
    reqs = (await client.get("/family/recordings/deletions", headers=H(tok))).json()
    assert reqs[0]["status"] == "pending" and reqs[0]["recording_count"] == 1


async def test_institution_flow_and_transfer(client):
    tok, tok2, cid, ctok = await setup_family(client)
    admin = await reg_teacher(client, "admin@x.com")
    inst = (await client.post("/institution", json={"name": "TPQ Al-Hikmah"}, headers=H(admin))).json()
    member_teacher = await reg_teacher(client, "guru-inst@x.com", code=inst["invite_code"])
    me = (await client.get("/teacher/me", headers=H(member_teacher))).json()
    assert me["kind"] == "institution" and me["status"] == "verified"  # diverifikasi lewat kode instansi
    ttok = await reg_teacher(client, "mandiri@x.com")
    await link_teacher(client, tok, tok2, cid, ttok)
    assert (await client.post("/family/transfer", json={"institution_code": inst["invite_code"]}, headers=H(tok2))).status_code == 403
    r = await client.post("/family/transfer", json={"institution_code": inst["invite_code"]}, headers=H(tok))
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert (await client.get("/institution/transfers", headers=H(ttok))).status_code == 403
    pend = (await client.get("/institution/transfers", headers=H(admin))).json()
    assert (await client.post(f"/institution/transfers/{pend[0]['id']}/decide", json={"approve": True}, headers=H(admin))).json()["status"] == "approved"
    assert (await client.get("/teacher/students", headers=H(ttok))).json() == []  # guru lama tidak lagi melihat anak


async def test_retention_purges_old_recordings(db_session):
    fam = models.Family(id=uuid.uuid4(), name="K", access_code="RET001")
    mem = models.Member(id=uuid.uuid4(), family_id=fam.id, name="A")
    old = models.Submission(member_id=mem.id, family_id=fam.id, context=models.SubmissionContext.tahsin, reference_text="x",
                            recording_key="k", status=models.SubmissionStatus.pending_eval, ai_status="completed",
                            created_at=datetime.now(timezone.utc) - timedelta(days=31))
    new = models.Submission(member_id=mem.id, family_id=fam.id, context=models.SubmissionContext.tahsin, reference_text="x",
                            recording_key="k", status=models.SubmissionStatus.pending_eval, ai_status="completed",
                            created_at=datetime.now(timezone.utc) - timedelta(days=5))
    db_session.add_all([fam, mem, old, new])
    await db_session.flush()
    assert settings.recording_retention_days == 30
    assert await teaching.purge_expired_recordings(db_session) == 1
    assert old.recording_deleted_at is not None and new.recording_deleted_at is None


def test_overdue_follows_teacher_target():
    t = models.Teacher(grading_target_hours=24)
    s = models.Submission(status=models.SubmissionStatus.pending_eval, created_at=datetime.now(timezone.utc) - timedelta(hours=25))
    assert teaching.is_overdue(s, t)
    t.grading_target_hours = 48
    assert not teaching.is_overdue(s, t)
