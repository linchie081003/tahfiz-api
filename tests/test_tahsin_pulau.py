import uuid

from app import models, schemas
from app.models import SubmissionContext, SubmissionStatus, TahsinStatus
from app.services import setor_flow, tahsin_points
from tests.test_koreksi import _kid


async def _sub(db, fam, m, point):
    s = models.Submission(member_id=m.id, family_id=fam.id, context=SubmissionContext.tahsin, tahsin_point=point,
                          reference_text="x", recording_key="k", status=SubmissionStatus.pending_eval)
    db.add(s)
    await db.flush()
    return s


async def _judge(db, s, m, status):
    await setor_flow.apply_submission_evaluation(db, s, m, schemas.EvaluateSubmissionIn(status=status), evaluator_id=uuid.uuid4(), evaluator_role="parent")


async def test_pulau_lulus_tercatat_dan_gerbang_baru_terbuka_setelah_tiga_pulau(db_session):
    db = db_session
    fam, m = await _kid(db)
    m.tahsin_status = TahsinStatus.pending_eval
    await _judge(db, await _sub(db, fam, m, 1), m, SubmissionStatus.passed)
    ov = await tahsin_points.overview(db, m.id)
    assert [p["passed"] for p in ov["points"][:3]] == [True, False, False]
    assert ov["gate_open"] is False and m.tahsin_status != TahsinStatus.passed  # satu Pulau belum membuka Hafalan
    await _judge(db, await _sub(db, fam, m, 2), m, SubmissionStatus.passed)
    await _judge(db, await _sub(db, fam, m, 3), m, SubmissionStatus.passed)
    ov = await tahsin_points.overview(db, m.id)
    assert ov["gate_open"] is True and m.tahsin_status == TahsinStatus.passed


async def test_pulau_gagal_tidak_mengubah_pulau_dan_tidak_menutup_gerbang(db_session):
    db = db_session
    fam, m = await _kid(db)
    await _judge(db, await _sub(db, fam, m, 1), m, SubmissionStatus.needs_retry)
    ov = await tahsin_points.overview(db, m.id)
    assert ov["points"][0]["passed"] is False and m.tahsin_status == TahsinStatus.failed
    for p in (1, 2, 3):
        await _judge(db, await _sub(db, fam, m, p), m, SubmissionStatus.passed)
    assert m.tahsin_status == TahsinStatus.passed
    await _judge(db, await _sub(db, fam, m, 4), m, SubmissionStatus.needs_retry)
    assert m.tahsin_status == TahsinStatus.passed  # sudah lulus tidak turun


async def test_setoran_tahsin_tanpa_pulau_tetap_alur_lama(db_session):
    db = db_session
    fam, m = await _kid(db)
    await _judge(db, await _sub(db, fam, m, None), m, SubmissionStatus.passed)
    assert m.tahsin_status == TahsinStatus.passed
