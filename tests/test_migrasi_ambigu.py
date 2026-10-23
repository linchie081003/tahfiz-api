"""Bukti bahwa data lama yang ambigu TIDAK pernah menjadi passed setelah migrasi/backfill."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app import models
from app.models import SubmissionContext, SubmissionStatus, SurahProgressStatus
from app.services import hafalan_ranges
from tests.test_rentang_penilaian import _setup, _sub


def _evaluated(s):
    s.evaluated_at = datetime.now(timezone.utc)
    return s


async def _scenario_posisi_saja(db, fam, m, prog):
    prog.current_ayah = 11


async def _scenario_surat_lulus_tanpa_riwayat(db, fam, m, prog):
    prog.status = SurahProgressStatus.passed


async def _scenario_lulus_tanpa_waktu_nilai(db, fam, m, prog):
    db.add(_sub(fam, m, 1, 10, status=SubmissionStatus.passed))  # evaluated_at kosong


async def _scenario_perlu_ulang(db, fam, m, prog):
    prog.current_ayah = 11
    db.add(_evaluated(_sub(fam, m, 1, 10, status=SubmissionStatus.needs_retry)))


async def _scenario_belum_lancar(db, fam, m, prog):
    db.add(_evaluated(_sub(fam, m, 1, 10, status=SubmissionStatus.not_fluent)))


async def _scenario_masih_menunggu(db, fam, m, prog):
    prog.current_ayah = 11
    db.add(_sub(fam, m, 1, 10, status=SubmissionStatus.pending_eval))


async def _scenario_superseded(db, fam, m, prog):
    db.add(_evaluated(_sub(fam, m, 1, 10, status=SubmissionStatus.superseded)))


SCENARIOS = [
    _scenario_posisi_saja, _scenario_surat_lulus_tanpa_riwayat, _scenario_lulus_tanpa_waktu_nilai, _scenario_perlu_ulang,
    _scenario_belum_lancar, _scenario_masih_menunggu, _scenario_superseded,
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda f: f.__name__.replace("_scenario_", ""))
async def test_data_ambigu_tidak_menjadi_passed(db_session, scenario):
    db = db_session
    fam, m = await _setup(db, ayah_count=40)
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    await scenario(db, fam, m, prog)
    await db.flush()
    await hafalan_ranges.backfill_member(db, m.id)
    await hafalan_ranges.backfill_member(db, m.id)  # ulang: tetap tidak ada yang naik menjadi passed

    ranges = (await db.execute(select(models.MemorizedRange))).scalars().all()
    assert [r for r in ranges if r.status == "passed"] == []
    assert await hafalan_ranges.covered_ayahs(db, m.id, 78) == set()
    assert (await db.execute(select(models.MurojaahItem))).scalars().all() == []  # tidak ada jadwal murajaah
    await db.refresh(prog)
    assert prog.status != SurahProgressStatus.passed  # progres surat tidak lebih maju dari bukti
    unv = [r for r in ranges if r.status == "unverified"]
    assert all(r.note for r in unv)
    if unv:
        assert prog.current_ayah <= min(r.ayah_start for r in unv)


async def test_kontrol_bukti_sah_tetap_passed(db_session):
    db = db_session
    fam, m = await _setup(db, ayah_count=40)
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    prog.current_ayah = 11
    db.add(_evaluated(_sub(fam, m, 1, 10, status=SubmissionStatus.passed)))
    await db.flush()
    await hafalan_ranges.backfill_member(db, m.id)
    assert await hafalan_ranges.covered_ayahs(db, m.id, 78) == set(range(1, 11))
    await db.refresh(prog)
    assert prog.current_ayah == 11 and (await db.execute(select(models.MurojaahItem))).scalars().first() is not None


async def test_progres_surat_lulus_tanpa_bukti_turun_lalu_pulih_setelah_verifikasi(db_session):
    from app.services import verification
    db = db_session
    fam, m = await _setup(db, ayah_count=40)
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    prog.status, prog.current_ayah = SurahProgressStatus.passed, 40
    await db.flush()
    made = await hafalan_ranges.backfill_member(db, m.id)
    assert made["progress_reset"] == 1
    await db.refresh(prog)
    assert prog.status == SurahProgressStatus.in_progress and prog.current_ayah == 1
    r = (await db.execute(select(models.MemorizedRange))).scalar_one()
    await verification.resolve(db, r, decision="lulus", note="didengar langsung", by=None, role="parent")
    await db.refresh(prog)
    assert prog.status == SurahProgressStatus.passed  # pulih hanya lewat keputusan manual
