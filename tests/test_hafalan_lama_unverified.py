"""Migrasi hafalan lama: hanya bukti penilaian lulus yang menjadi passed; sisanya unverified + antrean verifikasi."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app import models
from app.models import SubmissionContext, SubmissionStatus, SurahProgressStatus
from app.services import hafalan_ranges, murojaah, verification
from tests.helpers import H, add_child, make_teacher, register
from tests.test_rentang_penilaian import _setup, _sub


async def _ranges(db):
    return (await db.execute(select(models.MemorizedRange).order_by(models.MemorizedRange.ayah_start))).scalars().all()


async def test_posisi_ayat_tanpa_bukti_tidak_jadi_lulus(db_session):
    db = db_session
    fam, m = await _setup(db)
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    prog.current_ayah = 11  # hanya posisi, tanpa setoran/penilaian
    await db.flush()
    await hafalan_ranges.backfill_member(db, m.id)
    rs = await _ranges(db)
    assert [(r.ayah_start, r.ayah_end, r.status) for r in rs] == [(1, 10, "unverified")]
    assert await hafalan_ranges.covered_ayahs(db, m.id, 78) == set()  # tidak dihitung lulus
    assert (await db.execute(select(models.MurojaahItem))).scalars().all() == []  # tidak ada jadwal murajaah


async def test_bukti_sah_tetap_passed_dan_sisanya_unverified(db_session):
    db = db_session
    fam, m = await _setup(db)
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    prog.current_ayah = 21
    s = _sub(fam, m, 1, 10, status=SubmissionStatus.passed)
    s.evaluated_at = datetime.now(timezone.utc)
    db.add(s)
    await db.flush()
    await hafalan_ranges.backfill_member(db, m.id)
    got = [(r.ayah_start, r.ayah_end, r.status) for r in await _ranges(db)]
    assert got == [(1, 10, "passed"), (11, 20, "unverified")]
    assert await hafalan_ranges.covered_ayahs(db, m.id, 78) == set(range(1, 11))


async def test_setoran_lulus_tanpa_waktu_penilaian_unverified(db_session):
    db = db_session
    fam, m = await _setup(db)
    db.add(_sub(fam, m, 1, 5, status=SubmissionStatus.passed))  # evaluated_at kosong
    await db.flush()
    await hafalan_ranges.backfill_member(db, m.id)
    assert [(r.ayah_start, r.ayah_end, r.status) for r in await _ranges(db)] == [(1, 5, "unverified")]


async def test_reklasifikasi_hasil_migrasi_lama_dan_jadwalnya(db_session):
    db = db_session
    fam, m = await _setup(db)
    old = models.MemorizedRange(member_id=m.id, surah_id=78, ayah_start=1, ayah_end=10, source="migration")  # passed (versi lama)
    real = models.MemorizedRange(member_id=m.id, surah_id=78, ayah_start=11, ayah_end=12, source="evaluation")
    db.add_all([old, real])
    await db.flush()
    await murojaah.schedule_for_range(db, old)
    await murojaah.schedule_for_range(db, real)
    made = await hafalan_ranges.backfill_member(db, m.id)
    assert made["reclassified"] == 1
    await db.refresh(old)
    await db.refresh(real)
    assert old.status == "unverified" and real.status == "passed"  # evaluasi nyata tidak disentuh
    items = (await db.execute(select(models.MurojaahItem))).scalars().all()
    assert {i.range_id: i.completed for i in items} == {old.id: True, real.id: False}
    assert (await hafalan_ranges.backfill_member(db, m.id)).get("reclassified") is None  # idempoten


async def test_ayat_yang_sudah_diputuskan_tidak_dibuat_ulang(db_session):
    db = db_session
    fam, m = await _setup(db)
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    prog.current_ayah = 6
    await db.flush()
    await hafalan_ranges.backfill_member(db, m.id)
    r = (await _ranges(db))[0]
    await verification.resolve(db, r, decision="tolak", note="belum lancar", by=None, role="parent")
    await hafalan_ranges.backfill_member(db, m.id)
    assert [x.status for x in await _ranges(db)] == ["rejected"]  # tidak muncul lagi di antrean


async def test_verifikasi_lulus_menjadwalkan_murajaah_dan_tolak_menghitung_ulang_progres(db_session):
    db = db_session
    fam, m = await _setup(db)
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    prog.current_ayah = 11
    await db.flush()
    await hafalan_ranges.backfill_member(db, m.id)
    r = (await _ranges(db))[0]
    pid = uuid.uuid4()
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        await verification.resolve(db, r, decision="lulus", note="  ", by=pid, role="parent")
    assert e.value.status_code == 422
    await verification.resolve(db, r, decision="lulus", note="Didengar langsung sudah lancar", by=pid, role="parent")
    assert r.status == "passed" and r.source == "verified" and r.verified_by == pid and r.verified_role == "parent" and r.verified_at
    assert await hafalan_ranges.covered_ayahs(db, m.id, 78) == set(range(1, 11))
    assert len((await db.execute(select(models.MurojaahItem))).scalars().all()) == 1
    with pytest.raises(HTTPException) as e:  # sudah diputuskan
        await verification.resolve(db, r, decision="tolak", note="x", by=pid, role="parent")
    assert e.value.status_code == 409


async def test_tolak_mengembalikan_posisi_ayat(db_session):
    db = db_session
    fam, m = await _setup(db)
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    prog.current_ayah = 11
    prog.status = SurahProgressStatus.in_progress
    await db.flush()
    await hafalan_ranges.backfill_member(db, m.id)
    r = (await _ranges(db))[0]
    await verification.resolve(db, r, decision="tolak", note="belum hafal", by=None, role="parent")
    await db.refresh(prog)
    assert r.status == "rejected" and prog.current_ayah == 1


async def test_api_verifikasi_lintas_keluarga(client, db_session):
    pa = (await register(client, email="a@x.com"))["access_token"]
    pb = (await register(client, email="b@x.com"))["access_token"]
    assert (await client.get("/hafalan/verifikasi", headers=H(pa))).json() == []
    assert (await client.post(f"/hafalan/verifikasi/{uuid.uuid4()}", json={"decision": "lulus", "note": "x"}, headers=H(pb))).status_code == 404


async def test_api_antrean_dan_keputusan_orang_tua(client):
    from app.database import get_db
    from app.main import app
    reg = await register(client)
    ptok = reg["access_token"]
    cid = await add_child(client, ptok)
    gen = app.dependency_overrides[get_db]()  # simpan referensi agar generator tidak ditutup GC
    db = await gen.__anext__()
    db.add(models.Surah(id=114, name_ar="x", name_id="An-Nas", ayah_count=6, juz_number=30, curriculum_order=1))
    await db.flush()
    rng = models.MemorizedRange(member_id=uuid.UUID(cid), surah_id=114, ayah_start=1, ayah_end=3, source="migration", status="unverified", note="data lama")
    db.add(rng)
    await db.commit()
    q = (await client.get("/hafalan/verifikasi", headers=H(ptok))).json()
    assert len(q) == 1 and q[0]["ayah_start"] == 1 and q[0]["note"] == "data lama"
    assert (await client.post(f"/hafalan/verifikasi/{rng.id}", json={"decision": "lulus", "note": ""}, headers=H(ptok))).status_code == 422
    r = await client.post(f"/hafalan/verifikasi/{rng.id}", json={"decision": "lulus", "note": "didengar langsung"}, headers=H(ptok))
    assert r.status_code == 200 and r.json()["status"] == "passed"
    assert (await client.get("/hafalan/verifikasi", headers=H(ptok))).json() == []
    assert (await client.post(f"/hafalan/verifikasi/{rng.id}", json={"decision": "tolak", "note": "x"}, headers=H(ptok))).status_code == 409
