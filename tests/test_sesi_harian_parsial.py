import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import models, schemas
from app.models import MemberSurahProgress, MemorizedRange, MurojaahItem, Submission, SubmissionContext, SubmissionStatus, SurahProgressStatus
from app.services import corrections, daily_sessions as ds, hafalan_ranges, setor_flow


async def _sub(db, member, a, b):
    sub = Submission(id=uuid.uuid4(), member_id=member.id, family_id=member.family_id, context=SubmissionContext.ziyadah,
                     surah_id=114, ayah_start=a, ayah_end=b, reference_text="x", recording_key="k",
                     status=SubmissionStatus.pending_eval, ai_status="completed")
    db.add(sub)
    await db.flush()
    return sub


def _parts(*items, stars=None):
    return schemas.EvaluateSubmissionIn(
        parts=[schemas.EvaluationPart(ayah_start=a, ayah_end=b, status=SubmissionStatus(s)) for a, b, s in items], rubric_scores=stars,
    )


async def _ranges(db, sub):
    return (await db.execute(select(MemorizedRange).where(MemorizedRange.submission_id == sub.id).order_by(MemorizedRange.ayah_start))).scalars().all()


# ---------------------------------------------------------------- penilaian parsial

@pytest.mark.asyncio
async def test_sebagian_lulus_memecah_rentang_dan_sisanya_menunggu(db_session, member_with_ziyadah):
    m = member_with_ziyadah  # An-Nas 6 ayat, ayat aktif 2
    sub = await _sub(db_session, m, 2, 6)
    await setor_flow.apply_submission_evaluation(db_session, sub, m, _parts((2, 4, "passed")), evaluator_role="parent")
    assert sub.status == SubmissionStatus.pending_eval  # 5-6 belum dinilai, tidak diubah
    assert [(r.ayah_start, r.ayah_end, r.status) for r in await _ranges(db_session, sub)] == [(2, 4, "passed")]
    items = (await db_session.execute(select(MurojaahItem).where(MurojaahItem.member_id == m.id))).scalars().all()
    assert [(i.ayah_start, i.ayah_end) for i in items] == [(2, 4)]
    evals = await corrections.history(db_session, sub.id)
    assert [(e.ayah_start, e.ayah_end, e.result) for e in evals] == [(2, 4, "passed")]
    st = hafalan_ranges.range_status(sub, evals)
    assert [(x["ayah_start"], x["ayah_end"], x["status"]) for x in st] == [(2, 4, "passed"), (5, 6, "pending_eval")]
    prog = (await db_session.execute(select(MemberSurahProgress).where(MemberSurahProgress.member_id == m.id))).scalar_one()
    assert prog.current_ayah == 5 and prog.status == SurahProgressStatus.in_progress


@pytest.mark.asyncio
async def test_sisa_dinilai_belakangan_tanpa_mengubah_bagian_lulus(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    sub = await _sub(db_session, m, 2, 6)
    await setor_flow.apply_submission_evaluation(db_session, sub, m, _parts((2, 4, "passed")))
    first = (await corrections.history(db_session, sub.id))[0]
    await setor_flow.apply_submission_evaluation(db_session, sub, m, _parts((5, 6, "needs_retry")))
    assert sub.status == SubmissionStatus.needs_retry  # semua ayat sudah dinilai, ada yang belum lulus
    assert [(r.ayah_start, r.ayah_end) for r in await _ranges(db_session, sub)] == [(2, 4)]  # 5-6 tidak jadi rentang hafalan
    evals = await corrections.history(db_session, sub.id)
    assert len(evals) == 2 and first.id in {e.id for e in evals}
    assert first.result == "passed" and (first.ayah_start, first.ayah_end) == (2, 4)  # riwayat awal utuh
    prog = (await db_session.execute(select(MemberSurahProgress).where(MemberSurahProgress.member_id == m.id))).scalar_one()
    assert prog.current_ayah == 5


@pytest.mark.asyncio
async def test_rentang_tumpang_tindih_atau_di_luar_ditolak(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    sub = await _sub(db_session, m, 2, 6)
    with pytest.raises(HTTPException) as e:
        await setor_flow.apply_submission_evaluation(db_session, sub, m, _parts((1, 3, "passed")))
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        await setor_flow.apply_submission_evaluation(db_session, sub, m, _parts((2, 4, "passed"), (4, 5, "passed")))
    assert e.value.status_code == 422
    await setor_flow.apply_submission_evaluation(db_session, sub, m, _parts((2, 3, "passed")))
    with pytest.raises(HTTPException) as e:
        await setor_flow.apply_submission_evaluation(db_session, sub, m, _parts((3, 4, "needs_retry")))
    assert e.value.status_code == 409  # ayat 3 sudah dinilai; ubah lewat koreksi


@pytest.mark.asyncio
async def test_koreksi_per_rentang_menambah_riwayat(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    sub = await _sub(db_session, m, 2, 6)
    await setor_flow.apply_submission_evaluation(db_session, sub, m, _parts((2, 4, "passed"), (5, 6, "needs_retry")))
    assert sub.status == SubmissionStatus.needs_retry
    with pytest.raises(HTTPException) as e:  # dua rentang aktif: rentang wajib disebut
        await corrections.correct(db_session, sub, m, evaluator_id=uuid.uuid4(), evaluator_role="parent", status=SubmissionStatus.passed,
                                  notes=None, rubric_scores=None, reason="salah dengar")
    assert e.value.status_code == 422
    await corrections.correct(db_session, sub, m, evaluator_id=uuid.uuid4(), evaluator_role="parent", status=SubmissionStatus.passed,
                              notes=None, rubric_scores=None, reason="sudah lancar", ayah_start=5, ayah_end=6)
    assert sub.status == SubmissionStatus.passed
    assert [(r.ayah_start, r.ayah_end, r.status) for r in await _ranges(db_session, sub)] == [(2, 4, "passed"), (5, 6, "passed")]
    evals = await corrections.history(db_session, sub.id)
    assert len(evals) == 3  # tidak ada yang ditimpa
    assert len(corrections.active_ids(evals)) == 2
    prog = (await db_session.execute(select(MemberSurahProgress).where(MemberSurahProgress.member_id == m.id))).scalar_one()
    assert prog.status == SurahProgressStatus.passed


@pytest.mark.asyncio
async def test_penilaian_utuh_tetap_menyimpan_rentang(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    sub = await _sub(db_session, m, 2, 4)
    await setor_flow.apply_submission_evaluation(db_session, sub, m, schemas.EvaluateSubmissionIn(status=SubmissionStatus.passed))
    ev = (await corrections.history(db_session, sub.id))[0]
    assert (ev.ayah_start, ev.ayah_end) == (2, 4) and sub.status == SubmissionStatus.passed


def test_parts_lulus_butuh_bintang_minimal():
    with pytest.raises(ValueError):
        _parts((2, 4, "passed"), stars={"a": 1})


# ---------------------------------------------------------------- sesi harian

@pytest.mark.asyncio
async def test_sesi_berlaku_menurut_aturan(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    rows = {r.kind: r for r in await ds.ensure_day(db_session, m)}
    assert rows["sesi1"].status == "not_applicable" and "murajaah" in rows["sesi1"].reason
    assert rows["sesi2"].status == "available"  # jalur inti
    assert rows["sesi3"].status == "not_applicable" and rows["sesi3"].reason
    # rentang lulus dengan murajaah jatuh tempo hari ini dan sampel Sesi 3
    sub = await _sub(db_session, m, 2, 4)
    await setor_flow.apply_submission_evaluation(db_session, sub, m, schemas.EvaluateSubmissionIn(status=SubmissionStatus.passed))
    item = (await db_session.execute(select(MurojaahItem).where(MurojaahItem.member_id == m.id))).scalar_one()
    item.due_date = date.today()
    rows = {r.kind: r for r in await ds.ensure_day(db_session, m)}
    assert rows["sesi1"].status == "available" and rows["sesi1"].reason is None
    assert rows["sesi3"].status == "available"


@pytest.mark.asyncio
async def test_selesai_dicatat_dengan_referensi_aktivitas(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    sub = await _sub(db_session, m, 2, 3)
    row = await ds.mark_completed(db_session, m, "sesi2", activity_type="submission", activity_id=sub.id)
    assert row.status == "completed" and row.activity_id == sub.id and row.completed_at is not None
    await ds.ensure_day(db_session, m)
    again = await ds._row(db_session, m.id, date.today(), "sesi2")
    assert again.status == "completed"  # ensure_day tidak menimpa yang selesai


@pytest.mark.asyncio
async def test_sesi1_selesai_bila_batas_ayat_tercapai_atau_jatuh_tempo_habis(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    for a in (1, 11):
        db_session.add(MurojaahItem(member_id=m.id, surah_id=114, due_date=date.today(), ayah_start=a, ayah_end=a + 9))
    await db_session.flush()
    row = await ds.mark_completed(db_session, m, "sesi1", activity_type="murojaah_item", activity_id=uuid.uuid4(), ayah=4)
    assert row.status == "available" and row.ayah_done == 4  # masih ada jatuh tempo, batas belum tercapai
    row = await ds.mark_completed(db_session, m, "sesi1", activity_type="murojaah_item", activity_id=uuid.uuid4(), ayah=6)
    assert row.status == "completed"


@pytest.mark.asyncio
async def test_matikan_butuh_alasan_dan_tidak_menimpa_selesai(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    pid = uuid.uuid4()
    with pytest.raises(HTTPException) as e:
        await ds.disable(db_session, m, "sesi2", date.today(), "  ", pid)
    assert e.value.status_code == 422
    row = await ds.disable(db_session, m, "sesi2", date.today(), "Sedang sakit", pid)
    assert row.status == "disabled_manually" and row.reason == "Sedang sakit" and row.decided_by == pid
    row = await ds.enable(db_session, m, "sesi2", date.today(), pid)
    assert row.status == "available" and row.reason is None
    await ds.mark_completed(db_session, m, "sesi2", activity_type="submission", activity_id=None)
    with pytest.raises(HTTPException) as e:
        await ds.disable(db_session, m, "sesi2", date.today(), "x", pid)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_tutup_hari_dan_kpi_konsistensi(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    y, z = date.today() - timedelta(days=1), date.today() - timedelta(days=2)
    def add(day, kind, status):
        db_session.add(models.DailySession(member_id=m.id, family_id=m.family_id, day=day, kind=kind, status=status))
    add(z, "sesi2", "completed")
    add(y, "sesi2", "available")        # terlewat setelah hari ditutup
    add(y, "sesi1", "not_applicable")   # tidak dihitung
    add(y, "sesi3", "disabled_manually")  # tidak dihitung
    await db_session.flush()
    assert await ds.close_days(db_session) == 1
    k = await ds.consistency(db_session, m.id, z, date.today())
    assert k["per_kind"]["sesi2"]["completed"] == 1 and k["per_kind"]["sesi2"]["missed"] == 1
    assert k["per_kind"]["sesi2"]["rate"] == 0.5 and k["rate"] == 0.5 and k["applicable_closed"] == 2
    assert k["per_kind"]["sesi1"]["rate"] is None and k["per_kind"]["sesi1"]["not_applicable"] == 1


@pytest.mark.asyncio
async def test_api_sesi_harian_orang_tua(client):
    from tests.helpers import H, add_child, register
    reg = await register(client)
    cid = await add_child(client, reg["access_token"])
    ptok = reg["access_token"]
    r = await client.post(f"/sesi-harian/anak/{cid}/sesi1/nonaktif", json={"reason": "Libur"}, headers=H(ptok))
    assert r.status_code == 200 and r.json()["status"] == "disabled_manually"
    r = await client.get(f"/sesi-harian/anak/{cid}", headers=H(ptok))
    assert r.status_code == 200
    kinds = {s["kind"]: s for s in r.json()["sessions"]}
    assert set(kinds) == {"sesi1", "sesi2", "sesi3"} and kinds["sesi1"]["reason"] == "Libur"
    tok = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    assert (await client.post(f"/sesi-harian/anak/{cid}/sesi1/aktif", json={}, headers=H(tok))).status_code == 403  # hanya orang tua
    assert (await client.get("/sesi-harian/hari-ini", headers=H(tok))).status_code == 200


@pytest.mark.asyncio
async def test_sesi_dimatikan_menutup_layar_anak(client):
    import io
    from tests.helpers import H, add_child, register
    reg = await register(client)
    cid = await add_child(client, reg["access_token"])
    ptok = reg["access_token"]
    tok = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    for kind in ("sesi1", "sesi3"):
        assert (await client.post(f"/sesi-harian/anak/{cid}/{kind}/nonaktif", json={"reason": "Libur"}, headers=H(ptok))).status_code == 200
    m = (await client.get("/murojaah/sesi", headers=H(tok))).json()
    assert m["active"] is False and m["disabled_reason"] == "Libur"
    s3 = (await client.get("/sesi3", headers=H(tok))).json()
    assert s3["active"] is False and s3["disabled_reason"] == "Libur"
    assert (await client.post(f"/sesi-harian/anak/{cid}/sesi2/nonaktif", json={"reason": "Sakit"}, headers=H(ptok))).status_code == 200
    r = await client.post("/setor", headers=H(tok), data={"context": "ziyadah", "reference_text": "x", "surah_id": "114", "ayah_start": "1", "ayah_end": "1"},
                          files={"file": ("r.webm", io.BytesIO(b"x" * 10), "audio/webm")})
    assert r.status_code == 409 and "Sakit" in r.text
