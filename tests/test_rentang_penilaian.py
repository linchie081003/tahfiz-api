import uuid

from sqlalchemy import func, select

from app import models, schemas
from app.models import Surah, SubmissionContext, SubmissionStatus, SurahProgressStatus
from app.services import hafalan_ranges, setor_flow


async def _setup(db, ayah_count=40):
    from app.models import AgeMode
    fam = models.Family(name="K", access_code="ABC123")
    db.add(fam)
    await db.flush()
    m = models.Member(family_id=fam.id, name="Adik", age_mode=AgeMode.sd)
    db.add(m)
    if not await db.get(Surah, 78):
        db.add(Surah(id=78, name_ar="x", name_id="An-Naba'", ayah_count=ayah_count, juz_number=30, curriculum_order=1))
    await db.flush()
    db.add(models.MemberSurahProgress(member_id=m.id, surah_id=78, status=SurahProgressStatus.in_progress, current_ayah=1))
    await db.flush()
    return fam, m


def _sub(fam, m, a, b, status=SubmissionStatus.pending_eval):
    return models.Submission(
        member_id=m.id, family_id=fam.id, context=SubmissionContext.ziyadah, surah_id=78,
        ayah_start=a, ayah_end=b, reference_text="x", recording_key="k", status=status,
    )


async def test_evaluation_is_appended_and_range_recorded(db_session):
    db = db_session
    fam, m = await _setup(db)
    s = _sub(fam, m, 1, 20)
    db.add(s)
    await db.flush()
    pid = uuid.uuid4()
    await setor_flow.apply_submission_evaluation(
        db, s, m, schemas.EvaluateSubmissionIn(status=SubmissionStatus.passed), evaluator_id=pid, evaluator_role="parent"
    )
    evs = (await db.execute(select(models.Evaluation))).scalars().all()
    assert len(evs) == 1 and evs[0].evaluator_id == pid and evs[0].evaluator_role == "parent" and evs[0].result == "passed"
    rg = (await db.execute(select(models.MemorizedRange))).scalars().all()
    assert [(r.ayah_start, r.ayah_end) for r in rg] == [(1, 20)]


async def test_needs_retry_creates_no_range(db_session):
    db = db_session
    fam, m = await _setup(db)
    s = _sub(fam, m, 1, 5)
    db.add(s)
    await db.flush()
    await setor_flow.apply_submission_evaluation(db, s, m, schemas.EvaluateSubmissionIn(status=SubmissionStatus.needs_retry))
    assert (await db.execute(select(func.count()).select_from(models.MemorizedRange))).scalar_one() == 0
    assert (await db.execute(select(func.count()).select_from(models.Evaluation))).scalar_one() == 1


async def test_adjacent_ranges_stay_separate_but_view_merges(db_session):
    db = db_session
    fam, m = await _setup(db)
    for a, b in ((1, 20), (21, 40)):
        s = _sub(fam, m, a, b)
        db.add(s)
        await db.flush()
        await setor_flow.apply_submission_evaluation(db, s, m, schemas.EvaluateSubmissionIn(status=SubmissionStatus.passed))
    rows = (await db.execute(select(models.MemorizedRange).order_by(models.MemorizedRange.ayah_start))).scalars().all()
    assert [(r.ayah_start, r.ayah_end) for r in rows] == [(1, 20), (21, 40)]
    assert hafalan_ranges.merged_view([(r.ayah_start, r.ayah_end) for r in rows]) == [(1, 40)]
    assert await hafalan_ranges.covered_ayahs(db, m.id, 78) == set(range(1, 41))


async def test_backfill_is_idempotent_and_covers_old_progress(db_session):
    db = db_session
    fam, m = await _setup(db, ayah_count=40)
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    prog.status = SurahProgressStatus.passed  # data lama: surat lulus tanpa riwayat setoran
    await db.flush()
    first = await hafalan_ranges.backfill_member(db, m.id)
    assert first["ranges"] == 1 and first["assignments"] == 1
    second = await hafalan_ranges.backfill_member(db, m.id)
    assert second == {"ranges": 0, "evaluations": 0, "assignments": 0}
    assert await hafalan_ranges.covered_ayahs(db, m.id, 78) == set(range(1, 41))


async def test_backfill_partial_progress_and_old_evaluation(db_session):
    db = db_session
    fam, m = await _setup(db)
    prog = (await db.execute(select(models.MemberSurahProgress))).scalar_one()
    prog.current_ayah = 11  # ayat 1-10 sudah lulus menurut data lama
    s = _sub(fam, m, 1, 10, status=SubmissionStatus.passed)
    from datetime import datetime, timezone
    s.evaluated_at = datetime.now(timezone.utc)
    s.evaluator_notes = "bagus"
    db.add(s)
    await db.flush()
    await hafalan_ranges.backfill_member(db, m.id)
    ev = (await db.execute(select(models.Evaluation))).scalar_one()
    assert ev.source == "migration" and ev.notes == "bagus" and ev.evaluator_role == "unknown"
    assert await hafalan_ranges.covered_ayahs(db, m.id, 78) == set(range(1, 11))
    again = await hafalan_ranges.backfill_member(db, m.id)
    assert again["ranges"] == 0 and again["evaluations"] == 0


async def test_assignment_uses_active_teacher_link(db_session):
    db = db_session
    fam, m = await _setup(db)
    teacher_id = uuid.uuid4()
    db.add(models.TeacherLink(teacher_id=teacher_id, family_id=fam.id, member_id=m.id, status="active", requested_by=uuid.uuid4()))
    await db.flush()
    await hafalan_ranges.backfill_member(db, m.id)
    a = await hafalan_ranges.current_assignment(db, m.id)
    assert a.evaluator_role == "teacher" and a.evaluator_id == teacher_id
