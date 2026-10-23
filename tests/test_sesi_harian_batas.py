"""Kasus batas sesi harian: bukti aktivitas lengkap, sesi dimatikan, tidak berlaku lalu berlaku, pergantian hari."""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app import models
from app.models import MurojaahItem
from app.services import daily_sessions as ds


async def _row(db, m, day, kind):
    return await ds._row(db, m.id, day, kind)


@pytest.mark.asyncio
async def test_aktivitas_berulang_tidak_menimpa_bukti(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    ids = [uuid.uuid4() for _ in range(3)]
    for i, a in enumerate(ids):
        db_session.add(MurojaahItem(member_id=m.id, surah_id=114, due_date=date.today(), ayah_start=1, ayah_end=6))
        await ds.mark_completed(db_session, m, "sesi1", activity_type="murojaah_item", activity_id=a, ayah=2)
    row = await _row(db_session, m, date.today(), "sesi1")
    acts = await ds.activities(db_session, row.id)
    assert [a.activity_id for a in acts] == ids  # urutan dan isi utuh
    assert sum(a.ayah for a in acts) == row.ayah_done == 6
    assert row.activity_id == ids[-1]  # penunjuk hanya yang terakhir, bukti ada di tabel aktivitas


@pytest.mark.asyncio
async def test_sesi1_selesai_tepat_di_batas_10_ayat(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    db_session.add(MurojaahItem(member_id=m.id, surah_id=114, due_date=date.today(), ayah_start=1, ayah_end=6))
    await db_session.flush()
    r = await ds.mark_completed(db_session, m, "sesi1", activity_type="murojaah_item", activity_id=uuid.uuid4(), ayah=9)
    assert r.status == "available"
    r = await ds.mark_completed(db_session, m, "sesi1", activity_type="murojaah_item", activity_id=uuid.uuid4(), ayah=1)
    assert r.status == "completed" and r.ayah_done == 10


@pytest.mark.asyncio
async def test_sesi_dimatikan_tetap_mencatat_aktivitas_tanpa_mengubah_status(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    pid = uuid.uuid4()
    await ds.disable(db_session, m, "sesi2", date.today(), "Sakit", pid)
    a = uuid.uuid4()
    row = await ds.mark_completed(db_session, m, "sesi2", activity_type="submission", activity_id=a)
    assert row.status == "disabled_manually" and row.reason == "Sakit" and row.completed_at is None
    assert [x.activity_id for x in await ds.activities(db_session, row.id)] == [a]
    k = await ds.consistency(db_session, m.id, date.today(), date.today())
    assert k["per_kind"]["sesi2"]["disabled_manually"] == 1 and k["per_kind"]["sesi2"]["rate"] is None  # tidak dihitung
    # dimatikan hari ini tidak memengaruhi besok
    tomorrow = date.today() + timedelta(days=1)
    rows = {r.kind: r for r in await ds.ensure_day(db_session, m, tomorrow)}
    assert rows["sesi2"].status == "available"


@pytest.mark.asyncio
async def test_tidak_berlaku_lalu_berlaku_dan_selesai(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    rows = {r.kind: r for r in await ds.ensure_day(db_session, m)}
    assert rows["sesi1"].status == "not_applicable" and rows["sesi1"].reason
    item = MurojaahItem(member_id=m.id, surah_id=114, due_date=date.today(), ayah_start=1, ayah_end=3)
    db_session.add(item)
    await db_session.flush()
    rows = {r.kind: r for r in await ds.ensure_day(db_session, m)}
    assert rows["sesi1"].status == "available" and rows["sesi1"].reason is None
    assert rows["sesi1"].id == (await _row(db_session, m, date.today(), "sesi1")).id  # baris yang sama, bukan baris baru
    item.completed = True  # seperti murojaah.complete_item: item selesai, jadwal berikutnya di masa depan
    r = await ds.mark_completed(db_session, m, "sesi1", activity_type="murojaah_item", activity_id=item.id, ayah=3)
    assert r.status == "completed"
    # sudah selesai: tidak ada jatuh tempo lagi tidak mengubahnya kembali
    item.due_date = date.today() + timedelta(days=9)
    rows = {r.kind: r for r in await ds.ensure_day(db_session, m)}
    assert rows["sesi1"].status == "completed"


@pytest.mark.asyncio
async def test_sesi_available_tidak_berbalik_tidak_berlaku(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    it = MurojaahItem(member_id=m.id, surah_id=114, due_date=date.today(), ayah_start=1, ayah_end=3)
    db_session.add(it)
    await db_session.flush()
    await ds.ensure_day(db_session, m)
    it.due_date = date.today() + timedelta(days=5)  # mis. dijadwalkan ulang di tengah hari
    rows = {r.kind: r for r in await ds.ensure_day(db_session, m)}
    assert rows["sesi1"].status == "available"  # bukti bahwa sesi pernah berlaku hari itu tetap ada


@pytest.mark.asyncio
async def test_pergantian_hari_menutup_kemarin_dan_aktivitas_masuk_hari_baru(db_session, member_with_ziyadah, monkeypatch):
    m = member_with_ziyadah
    d1 = date(2026, 3, 10)
    d2 = d1 + timedelta(days=1)
    clock = {"d": d1}
    monkeypatch.setattr(ds, "today", lambda: clock["d"])
    await ds.ensure_day(db_session, m)
    s2_d1 = await _row(db_session, m, d1, "sesi2")
    assert s2_d1.status == "available"

    clock["d"] = d2  # lewat tengah malam
    out = await ds.run_daily(db_session)
    assert out["closed"] >= 1
    await db_session.refresh(s2_d1)
    assert s2_d1.status == "missed"
    s2_d2 = await _row(db_session, m, d2, "sesi2")
    assert s2_d2 is not None and s2_d2.status == "available" and s2_d2.id != s2_d1.id

    a = uuid.uuid4()
    await ds.mark_completed(db_session, m, "sesi2", activity_type="submission", activity_id=a)
    await db_session.refresh(s2_d1)
    assert s2_d1.status == "missed" and await ds.activities(db_session, s2_d1.id) == []  # kemarin tidak ikut berubah
    assert (await _row(db_session, m, d2, "sesi2")).status == "completed"
    k = await ds.consistency(db_session, m.id, d1, d2)
    assert k["per_kind"]["sesi2"]["completed"] == 1 and k["per_kind"]["sesi2"]["missed"] == 1 and k["per_kind"]["sesi2"]["rate"] == 0.5
    # menutup lagi tidak mengubah apa pun (idempoten)
    assert (await ds.run_daily(db_session))["closed"] == 0


@pytest.mark.asyncio
async def test_hari_lalu_tidak_bisa_diubah_orang_tua(db_session, member_with_ziyadah):
    from fastapi import HTTPException
    m = member_with_ziyadah
    with pytest.raises(HTTPException) as e:
        await ds.disable(db_session, m, "sesi2", date.today() - timedelta(days=1), "x", None)
    assert e.value.status_code == 409
