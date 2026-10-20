import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

from app.database import Base
from app import models
from app.models import (
    AgeMode,
    Member,
    MemberStats,
    MemberSurahProgress,
    Submission,
    SubmissionContext,
    SubmissionStatus,
    Surah,
    SurahProgressStatus,
    TahsinStatus,
    XpConfig,
)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def member_with_ziyadah(db_session: AsyncSession):
    family_id = uuid.uuid4()
    member_id = uuid.uuid4()
    db_session.add(
        models.Family(id=family_id, name="Test", access_code="TESTCODE01"),
    )
    db_session.add(
        Member(
            id=member_id,
            family_id=family_id,
            name="Anak",
            age_mode=AgeMode.sd,
            tahsin_status=TahsinStatus.passed,
        ),
    )
    db_session.add(MemberStats(member_id=member_id, xp=0, level=1, streak_days=0))
    db_session.add(XpConfig(activity_key="setoran_lulus", xp_value=30, label="Setoran lulus"))
    db_session.add(
        Surah(id=114, name_ar="الناس", name_id="An-Nas", ayah_count=6, juz_number=30, curriculum_order=1),
    )
    db_session.add(
        MemberSurahProgress(
            member_id=member_id,
            surah_id=114,
            status=SurahProgressStatus.in_progress,
            current_ayah=2,
        ),
    )
    await db_session.flush()
    member = await db_session.get(Member, member_id)
    assert member is not None
    return member
