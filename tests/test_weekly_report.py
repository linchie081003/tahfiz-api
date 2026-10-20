import uuid
from datetime import date, datetime, timedelta, timezone

from app import models
from app.models import (
    MemberSurahProgress, MurojaahItem, Submission, SubmissionContext, SubmissionStatus, Surah, SurahProgressStatus,
)
from app.services.weekly_report import build_weekly_report
from tests.conftest import *  # noqa: F401,F403  (fixtures)


async def test_weekly_report_counts_only_last_7_days_and_passed(db_session, member_with_ziyadah):
    member = member_with_ziyadah
    today = date(2026, 10, 20)
    now = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)

    def sub(days_ago, a1, a2, status=SubmissionStatus.passed):
        return Submission(
            member_id=member.id, family_id=member.family_id, context=SubmissionContext.ziyadah,
            surah_id=114, ayah_start=a1, ayah_end=a2, reference_text="x", recording_key="k",
            status=status, evaluated_at=now - timedelta(days=days_ago),
        )

    db_session.add_all([
        sub(0, 1, 3),                                   # hari ini: 3 ayat
        sub(2, 4, 5),                                   # 2 hari lalu: 2 ayat
        sub(10, 1, 6),                                  # di luar 7 hari
        sub(1, 1, 6, SubmissionStatus.needs_retry),     # tidak lulus
    ])
    prog = (await db_session.execute(
        models.MemberSurahProgress.__table__.select().where(MemberSurahProgress.member_id == member.id)
    )).first()
    assert prog is not None
    await db_session.flush()

    r = await build_weekly_report(db_session, member.family_id, member, today)
    assert r["ayat_total"] == 5
    assert r["active_days"] == 2
    assert len(r["daily"]) == 7
    assert r["daily"][-1]["ayat"] == 3
    assert r["week_start"] == date(2026, 10, 14)
    assert "Aktif 2 hari" in r["note"]


async def test_weekly_report_lists_overdue_murojaah(db_session, member_with_ziyadah):
    member = member_with_ziyadah
    today = date(2026, 10, 20)
    db_session.add(MurojaahItem(member_id=member.id, surah_id=114, due_date=today - timedelta(days=1), completed=False))
    db_session.add(MurojaahItem(member_id=member.id, surah_id=114, due_date=today + timedelta(days=3), completed=False))
    await db_session.flush()
    r = await build_weekly_report(db_session, member.family_id, member, today)
    assert r["overdue_murojaah_count"] == 1
    assert r["overdue_murojaah_surahs"] == ["An-Nas"]
    assert r["ayat_total"] == 0 and "Belum ada hafalan" in r["note"]
