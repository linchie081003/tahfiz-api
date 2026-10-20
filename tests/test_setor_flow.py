import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import schemas
from app.models import MemberStats, Submission, SubmissionContext, SubmissionStatus, TahsinStatus, XpConfig
from app.services import setor_flow


async def _evaluate_if_pending(db_session, sub, member, payload):
    if sub.status != SubmissionStatus.pending_eval:
        return
    await setor_flow.apply_submission_evaluation(db_session, sub, member, payload)


@pytest.mark.asyncio
async def test_evaluate_twice_adds_xp_once(db_session, member_with_ziyadah):
    member = member_with_ziyadah
    sub = Submission(
        id=uuid.uuid4(),
        member_id=member.id,
        family_id=member.family_id,
        context=SubmissionContext.ziyadah,
        surah_id=114,
        ayah_start=2,
        ayah_end=2,
        reference_text="test",
        recording_key="local/x",
        status=SubmissionStatus.pending_eval,
        ai_status="completed",
    )
    db_session.add(sub)
    await db_session.flush()

    payload = schemas.EvaluateSubmissionIn(status=SubmissionStatus.passed)
    await _evaluate_if_pending(db_session, sub, member, payload)
    await _evaluate_if_pending(
        db_session,
        sub,
        member,
        schemas.EvaluateSubmissionIn(status=SubmissionStatus.needs_retry),
    )

    stats = (await db_session.execute(select(MemberStats).where(MemberStats.member_id == member.id))).scalar_one()
    assert stats.xp == 30
    assert sub.status == SubmissionStatus.passed


@pytest.mark.asyncio
async def test_tahsin_evaluate_twice_adds_xp_once(db_session, member_with_ziyadah):
    member = member_with_ziyadah
    member.tahsin_status = TahsinStatus.pending_eval
    sub = Submission(
        id=uuid.uuid4(),
        member_id=member.id,
        family_id=member.family_id,
        context=SubmissionContext.tahsin,
        reference_text="t",
        recording_key="k",
        status=SubmissionStatus.pending_eval,
        ai_status="completed",
    )
    db_session.add(sub)
    db_session.add(XpConfig(activity_key="tahsin_lulus", xp_value=50, label="Tahsin"))
    await db_session.flush()

    passed = schemas.EvaluateSubmissionIn(status=SubmissionStatus.passed)
    await _evaluate_if_pending(db_session, sub, member, passed)
    await _evaluate_if_pending(db_session, sub, member, passed)

    stats = (await db_session.execute(select(MemberStats).where(MemberStats.member_id == member.id))).scalar_one()
    assert stats.xp == 50
    assert member.tahsin_status == TahsinStatus.passed


@pytest.mark.asyncio
async def test_ziyadah_setor_allows_current_and_next_ayah(db_session, member_with_ziyadah):
    member = member_with_ziyadah
    await setor_flow.assert_ziyadah_setor_allowed(db_session, member, 114, 2, 2)
    await setor_flow.assert_ziyadah_setor_allowed(db_session, member, 114, 3, 3)


@pytest.mark.asyncio
async def test_ziyadah_setor_rejects_wrong_surah(db_session, member_with_ziyadah):
    member = member_with_ziyadah
    with pytest.raises(HTTPException) as exc:
        await setor_flow.assert_ziyadah_setor_allowed(db_session, member, 113, 1, 1)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_ziyadah_setor_rejects_skipped_ayah(db_session, member_with_ziyadah):
    member = member_with_ziyadah
    with pytest.raises(HTTPException) as exc:
        await setor_flow.assert_ziyadah_setor_allowed(db_session, member, 114, 4, 4)
    assert exc.value.status_code == 409
