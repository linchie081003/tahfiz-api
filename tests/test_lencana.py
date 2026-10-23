import uuid

from sqlalchemy import func, select

from app import models, schemas
from app.models import SubmissionContext, SubmissionStatus
from app.services import gamification, setor_flow, tahsin_points
from tests.test_koreksi import _kid


async def _earned(db, m):
    return {b["id"]: b for b in await gamification.list_badges(db, m.id)}


async def test_lencana_baru_belum_ada_dan_menampilkan_kemajuan(db_session):
    db = db_session
    fam, m = await _kid(db)
    got = await _earned(db, m)
    assert len(got) == 19 and not any(b["earned"] for b in got.values())
    assert got["ayat_10"]["progress"] == 0 and got["ayat_10"]["target"] == 10


async def test_hafalan_lulus_memberi_lencana_ayat_dan_kemajuan_sebagian(db_session):
    db = db_session
    fam, m = await _kid(db)
    s = models.Submission(member_id=m.id, family_id=fam.id, context=SubmissionContext.ziyadah, surah_id=78, ayah_start=1, ayah_end=10,
                          reference_text="x", recording_key="k", status=SubmissionStatus.pending_eval)
    db.add(s)
    await db.flush()
    await setor_flow.apply_submission_evaluation(db, s, m, schemas.EvaluateSubmissionIn(status=SubmissionStatus.passed), evaluator_id=uuid.uuid4(), evaluator_role="parent")
    got = await _earned(db, m)
    assert got["ayat_1"]["earned"] and got["ayat_10"]["earned"] and not got["ayat_50"]["earned"]
    assert got["ayat_50"]["progress"] == 10 and got["ayat_50"]["target"] == 50
    assert got["ayat_10"]["earned_at"] is not None


async def test_lencana_pulau_dan_gerbang_lama_tetap_dihitung(db_session):
    db = db_session
    fam, m = await _kid(db)
    await tahsin_points.record_result(db, m, 1, 9.0, "parent", uuid.uuid4())
    got = await _earned(db, m)
    assert got["pulau_pertama"]["earned"] and not got["tahsin_lulus"]["earned"] and got["tahsin_lulus"]["progress"] == 1
    # data lama: status lulus tanpa catatan per Pulau tetap dianggap lulus gerbang
    m2 = models.Member(family_id=fam.id, name="Kakak", age_mode=models.AgeMode.sd)
    db.add(m2)
    await db.flush()
    m2.tahsin_status = models.TahsinStatus.passed
    got2 = await _earned(db, m2)
    assert got2["tahsin_lulus"]["earned"]


async def test_lencana_idempoten_dan_streak_level(db_session):
    db = db_session
    fam, m = await _kid(db)
    stats = await gamification.ensure_member_stats(db, m.id)
    stats.streak_days, stats.level = 7, 5
    first = await _earned(db, m)
    again = await _earned(db, m)
    assert first["streak_3"]["earned"] and first["murojaah_7"]["earned"] and not first["streak_30"]["earned"] and first["level_5"]["earned"]
    n = (await db.execute(select(func.count()).select_from(models.MemberBadge))).scalar_one()
    assert n == sum(1 for b in again.values() if b["earned"])  # tidak dobel
