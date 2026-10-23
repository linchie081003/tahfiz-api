import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import models, schemas
from app.models import MemberSettings, MemberSurahProgress, MurojaahItem, Submission, SubmissionContext, SubmissionStatus, Surah, SurahProgressStatus
from app.services import progress, setor_flow


def test_plan_range_short_surah_is_whole_and_long_follows_target():
    assert progress.plan_range(6, 1, 1) == (1, 6, "seluruh_surat")
    assert progress.plan_range(6, 3, 1) == (3, 6, "seluruh_surat")  # lanjut sisa surat pendek
    assert progress.plan_range(10, 1, 1) == (1, 10, "seluruh_surat")
    assert progress.plan_range(30, 1, 3) == (1, 3, "target_harian")
    assert progress.plan_range(30, 29, 5) == (29, 30, "target_harian")  # tidak melebihi jumlah ayat
    assert progress.plan_range(286, 1, 5) == (1, 5, "target_harian")


async def _sub(db, member, surah_id, a, b):
    sub = Submission(id=uuid.uuid4(), member_id=member.id, family_id=member.family_id, context=SubmissionContext.ziyadah,
                     surah_id=surah_id, ayah_start=a, ayah_end=b, reference_text="x", recording_key="k",
                     status=SubmissionStatus.pending_eval, ai_status="completed")
    db.add(sub)
    await db.flush()
    return sub


@pytest.mark.asyncio
async def test_partial_pass_advances_and_full_pass_completes_and_starts_murajaah(db_session, member_with_ziyadah):
    m = member_with_ziyadah  # An-Nas 6 ayat, current_ayah=2
    ok = schemas.EvaluateSubmissionIn(status=SubmissionStatus.passed)
    sub = await _sub(db_session, m, 114, 2, 4)
    await setor_flow.apply_submission_evaluation(db_session, sub, m, ok)
    prog = (await db_session.execute(select(MemberSurahProgress).where(MemberSurahProgress.member_id == m.id))).scalar_one()
    assert prog.status == SurahProgressStatus.in_progress and prog.current_ayah == 5
    assert (await db_session.execute(select(MurojaahItem).where(MurojaahItem.member_id == m.id))).first() is None  # belum lengkap

    sub2 = await _sub(db_session, m, 114, 5, 6)
    await setor_flow.apply_submission_evaluation(db_session, sub2, m, ok)
    assert prog.status == SurahProgressStatus.passed
    assert (await db_session.execute(select(MurojaahItem).where(MurojaahItem.member_id == m.id))).first() is not None


@pytest.mark.asyncio
async def test_retry_keeps_position(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    sub = await _sub(db_session, m, 114, 2, 6)
    await setor_flow.apply_submission_evaluation(db_session, sub, m, schemas.EvaluateSubmissionIn(status=SubmissionStatus.needs_retry))
    prog = (await db_session.execute(select(MemberSurahProgress).where(MemberSurahProgress.member_id == m.id))).scalar_one()
    assert prog.status == SurahProgressStatus.needs_retry and prog.current_ayah == 2


@pytest.mark.asyncio
async def test_choose_surah_only_in_free_mode(db_session, member_with_ziyadah):
    m = member_with_ziyadah
    db_session.add(Surah(id=113, name_ar="الفلق", name_id="Al-Falaq", ayah_count=5, juz_number=30, curriculum_order=2))
    db_session.add(MemberSurahProgress(member_id=m.id, surah_id=113, status=SurahProgressStatus.locked, current_ayah=1))
    db_session.add(MemberSettings(member_id=m.id, coverage="juz30", daily_ayahs=1, murajaah_strong_days=14))
    await db_session.flush()
    with pytest.raises(HTTPException) as e:
        await progress.choose_surah(db_session, m.id, 113)
    assert e.value.status_code == 409

    ms = await progress.get_settings(db_session, m.id)
    ms.hafalan_order = "free"
    await progress.choose_surah(db_session, m.id, 113)
    active = await progress.get_active_surah(db_session, m.id)
    assert active.surah_id == 113
    plan = await progress.setor_plan(db_session, m.id)
    assert (plan["ayah_start"], plan["ayah_end"], plan["mode"]) == (1, 5, "seluruh_surat")
    await setor_flow.assert_ziyadah_setor_allowed(db_session, m, 113, 1, 5)

    # selesai -> fokus dilepas, surat lain tidak otomatis terbuka
    sub = await _sub(db_session, m, 113, 1, 5)
    await setor_flow.apply_submission_evaluation(db_session, sub, m, schemas.EvaluateSubmissionIn(status=SubmissionStatus.passed))
    assert ms.focus_surah_id is None
    with pytest.raises(HTTPException):
        await progress.choose_surah(db_session, m.id, 113)  # sudah hafal


@pytest.mark.asyncio
async def test_peta_exposes_plan_and_order_via_api(client):
    from tests.helpers import H, add_child, register

    tok = (await register(client))["access_token"]
    cid = await add_child(client, tok)
    r = await client.put(f"/members/{cid}/settings", json={"hafalan_order": "free"}, headers=H(tok))
    assert r.status_code == 200 and r.json()["hafalan_order"] == "free"
    r = await client.put(f"/members/{cid}/settings", json={"hafalan_order": "sequential"}, headers=H(tok))
    assert r.json()["hafalan_order"] == "sequential"


@pytest.mark.asyncio
async def test_peta_plan_and_pilih_surat_via_api(client):
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.database import get_db
    from app.main import app
    from tests.helpers import H, add_child, register

    reg = await register(client)
    tok = reg["access_token"]
    cid = await add_child(client, tok)
    child = (await client.post("/auth/child-login", json={"access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    db: AsyncSession = await app.dependency_overrides[get_db]().__anext__()
    for sid, name, n, juz in ((1, "Al-Fatihah", 7, 1), (2, "Al-Baqarah", 286, 1), (114, "An-Nas", 6, 30)):
        if not await db.get(models.Surah, sid):
            db.add(models.Surah(id=sid, name_ar="x", name_id=name, ayah_count=n, juz_number=juz, curriculum_order=sid))
    await db.commit()
    await client.put(f"/members/{cid}/settings", headers=H(tok), json={"parallel_hafalan": True, "coverage": "all", "hafalan_track": "mushaf", "daily_ayahs": 3})

    peta = (await client.get("/peta/juz/30", headers=H(child))).json()
    assert peta["hafalan_order"] == "sequential" and peta["planned"] is False and peta["plan"] is None  # belum ada rencana
    assert peta["suggested_surah_id"] == 1
    assert [n["surah_id"] for n in peta["nodes"] if n["selectable"]] == [1]  # berurutan: hanya surat berikutnya
    assert (await client.post("/peta/pilih", json={"surah_id": 2}, headers=H(child))).status_code == 409
    assert (await client.post("/peta/pilih", json={"surah_id": 1}, headers=H(child))).status_code == 200
    peta = (await client.get("/peta/juz/30", headers=H(child))).json()
    assert peta["planned"] is True and peta["active_surah_id"] == 1
    assert peta["plan"] == {"surah_id": 1, "name_id": "Al-Fatihah", "ayah_count": 7, "ayah_start": 1, "ayah_end": 7, "mode": "seluruh_surat", "done_ayahs": 0}

    await client.put(f"/members/{cid}/settings", headers=H(tok), json={"hafalan_order": "free"})
    peta = (await client.get("/peta/juz/30", headers=H(child))).json()
    assert [n["surah_id"] for n in peta["nodes"] if n["selectable"]] == [2, 114]  # surat rencana tidak perlu dipilih lagi
    r = await client.post("/peta/pilih", json={"surah_id": 2}, headers=H(child))
    assert r.status_code == 200
    peta = (await client.get("/peta/juz/30", headers=H(child))).json()
    assert peta["active_surah_id"] == 2
    assert (peta["plan"]["ayah_start"], peta["plan"]["ayah_end"], peta["plan"]["mode"]) == (1, 3, "target_harian")


def test_tilawah_reciter_is_alafasy_and_exists():
    from app.services import reciters as rc

    assert rc.TILAWAH_RECITER_ID == "alafasy"
    assert rc.everyayah_url(1, 1, rc.TILAWAH_RECITER_ID).endswith("Alafasy_128kbps/001001.mp3")


def test_surah_names_are_transliterated_not_meanings():
    from app.services.surah_translit import surah_name

    assert surah_name(80, "Ia Bermuka Masam") == "'Abasa"
    assert surah_name(1) == "Al-Fatihah" and surah_name(114) == "An-Nas" and surah_name(78) == "An-Naba'"
    assert surah_name(999, "x") == "x"
