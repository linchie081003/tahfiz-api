"""Sesi 3 hanya selesai dengan hasil atas sampel yang sah; tidak berlaku/dimatikan/permintaan cek tidak pernah menyelesaikannya."""
import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import models
from app.models import SubmissionContext, SubmissionStatus
from app.services import daily_sessions as ds
from tests.helpers import H, add_child, register


async def _with_sample(db, m):
    db.add(models.Submission(member_id=m.id, family_id=m.family_id, context=SubmissionContext.ziyadah, surah_id=114, ayah_start=1, ayah_end=4,
                             reference_text="x", recording_key="k", status=SubmissionStatus.pending_eval))
    await db.flush()
    row, plan = await ds.sesi3_plan(db, m)
    assert row.status == "available" and len(plan) == 3
    return row, plan


def _res(plan, r="lancar"):
    return [(p["surah_id"], p["ayah_number"], r) for p in plan]


async def _rejects(coro, code):
    with pytest.raises(HTTPException) as e:
        await coro
    assert e.value.status_code == code


async def test_sampel_dibekukan_dan_selesai_dengan_hasil_yang_cocok(db_session, member_with_ziyadah):
    db, m = db_session, member_with_ziyadah
    row, plan = await _with_sample(db, m)
    _, again = await ds.sesi3_plan(db, m)
    assert again == plan  # tidak diacak ulang
    row, summary = await ds.complete_sesi3(db, m, _res(plan))
    assert row.status == "completed" and row.completed_at and summary["recorded"] == 3
    await _rejects(ds.complete_sesi3(db, m, _res(plan)), 409)  # tidak bisa selesai dua kali


async def test_hasil_tidak_sesuai_sampel_ditolak_tanpa_efek(db_session, member_with_ziyadah):
    db, m = db_session, member_with_ziyadah
    row, plan = await _with_sample(db, m)
    await _rejects(ds.complete_sesi3(db, m, _res(plan)[:2]), 422)  # kurang
    await _rejects(ds.complete_sesi3(db, m, _res(plan) + [(114, 6, "lancar")]), 422)  # kelebihan / ayat di luar sampel
    await _rejects(ds.complete_sesi3(db, m, _res(plan)[:2] + [(114, 6, "lancar")]), 422)  # ayat lain
    await _rejects(ds.complete_sesi3(db, m, _res(plan)[:2] + [_res(plan)[0]]), 422)  # duplikat
    await _rejects(ds.complete_sesi3(db, m, _res(plan, "keren")), 422)  # nilai tidak sah
    assert row.status == "available"
    assert (await db.execute(select(models.PracticeAttempt))).scalars().all() == []  # tidak ada hasil yang tercatat


async def test_tanpa_sampel_yang_dikeluarkan_ditolak(db_session, member_with_ziyadah):
    db, m = db_session, member_with_ziyadah
    db.add(models.Submission(member_id=m.id, family_id=m.family_id, context=SubmissionContext.ziyadah, surah_id=114, ayah_start=1, ayah_end=4,
                             reference_text="x", recording_key="k", status=SubmissionStatus.pending_eval))
    await db.flush()
    await _rejects(ds.complete_sesi3(db, m, [(114, 1, "lancar"), (114, 2, "lancar"), (114, 3, "lancar")]), 409)
    assert (await ds._row(db, m.id, date.today(), "sesi3")).status == "available"


async def test_sesi_tidak_berlaku_tidak_bisa_selesai(db_session, member_with_ziyadah):
    db, m = db_session, member_with_ziyadah  # tidak ada setoran ziyadah -> tanpa sampel
    await _rejects(ds.complete_sesi3(db, m, [(114, 1, "lancar")]), 409)
    row = await ds.mark_completed(db, m, "sesi3", activity_type="sesi3_practice", activity_id=None)  # jalur langsung pun tidak
    assert row.status == "not_applicable" and row.completed_at is None
    k = await ds.consistency(db, m.id, date.today(), date.today())
    assert k["per_kind"]["sesi3"]["completed"] == 0 and k["per_kind"]["sesi3"]["not_applicable"] == 1


async def test_sesi_dimatikan_orang_tua_ditolak(db_session, member_with_ziyadah):
    db, m = db_session, member_with_ziyadah
    row, plan = await _with_sample(db, m)
    await ds.disable(db, m, "sesi3", date.today(), "Sakit", uuid.uuid4())
    await _rejects(ds.complete_sesi3(db, m, _res(plan)), 409)
    assert (await ds._row(db, m.id, date.today(), "sesi3")).status == "disabled_manually"


async def test_permintaan_cek_bukan_bukti_latihan(db_session, member_with_ziyadah):
    db, m = db_session, member_with_ziyadah
    row, plan = await _with_sample(db, m)
    row = await ds.mark_completed(db, m, "sesi3", activity_type="sesi3_request", activity_id=uuid.uuid4())
    assert row.status == "available" and row.completed_at is None
    assert len(await ds.activities(db, row.id)) == 1  # tercatat sebagai aktivitas, bukan penyelesaian
    # penyelesaian tanpa sampel terbit juga ditolak di lapisan bawah
    row.plan = None
    row = await ds.mark_completed(db, m, "sesi3", activity_type="sesi3_practice", activity_id=None)
    assert row.status == "available"


async def test_api_latihan_dan_selesai_menolak_permintaan_tidak_sah(client):
    reg = await register(client)
    cid = await add_child(client, reg["access_token"])
    tok = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    body = {"kind": "penguatan", "results": [{"surah_id": 114, "ayah_number": 1, "result": "lancar"}]}
    r = await client.post("/latihan", json=body, headers=H(tok))
    assert r.status_code == 409  # tidak ada sampel / sesi tidak berlaku
    assert (await client.post("/sesi-harian/sesi3/selesai", headers=H(tok))).status_code == 422  # tanpa hasil
    assert (await client.post("/sesi-harian/sesi3/selesai", json={"results": body["results"]}, headers=H(tok))).status_code == 409
    rows = (await client.get("/sesi-harian/hari-ini", headers=H(tok))).json()["sessions"]
    s3 = next(x for x in rows if x["kind"] == "sesi3")
    assert s3["status"] == "not_applicable"
