import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.surah_translit import surah_name
from app import models, schemas
from app.database import get_db
from app.deps import AuthContext, require_parent
from app.services import gamification, murojaah, progress, weekly_report

router = APIRouter(prefix="/parent", tags=["parent"])


@router.get("/dashboard", response_model=schemas.ParentDashboardOut)
async def parent_dashboard(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    family = await db.get(models.Family, ctx.family_id)
    members = (
        await db.execute(
            select(models.Member).where(models.Member.family_id == ctx.family_id).order_by(models.Member.created_at)
        )
    ).scalars().all()

    queue_total = (
        await db.execute(
            select(func.count())
            .select_from(models.Submission)
            .where(
                models.Submission.family_id == ctx.family_id,
                models.Submission.status == models.SubmissionStatus.pending_eval,
            )
        )
    ).scalar_one()

    children: list[schemas.ParentChildSummaryOut] = []
    for m in members:
        stats = await gamification.ensure_member_stats(db, m.id)
        passed = (
            await db.execute(
                select(func.count())
                .select_from(models.MemberSurahProgress)
                .where(
                    models.MemberSurahProgress.member_id == m.id,
                    models.MemberSurahProgress.status == models.SurahProgressStatus.passed,
                )
            )
        ).scalar_one()
        pending = (
            await db.execute(
                select(func.count())
                .select_from(models.Submission)
                .where(
                    models.Submission.member_id == m.id,
                    models.Submission.status == models.SubmissionStatus.pending_eval,
                )
            )
        ).scalar_one()
        pts = (
            await db.execute(select(models.TahsinPointProgress).where(models.TahsinPointProgress.member_id == m.id))
        ).scalars().all()
        done_pts = {r.point for r in pts if r.passed}
        nxt = next((n for n in range(1, 10) if n not in done_pts), None)
        tahsin_line = "Semua Pulau lulus" if nxt is None else f"Pulau {nxt}, {len(done_pts)} dari 9 lulus"
        active = await progress.get_active_surah(db, m.id)
        hafalan_line = ""
        if active:
            sr = await db.get(models.Surah, active.surah_id)
            hafalan_line = f"{surah_name(sr.id, sr.name_id) if sr else 'Surat'}, ayat {active.current_ayah}"
        due = await murojaah.due_items(db, m.id, 50) if await progress.hafalan_unlocked(db, m) else []
        due_name = ""
        if due:
            ds = await db.get(models.Surah, due[0].surah_id)
            due_name = surah_name(ds.id, ds.name_id) if ds else ""
        children.append(
            schemas.ParentChildSummaryOut(
                id=m.id,
                name=m.name,
                color=m.color,
                age_mode=m.age_mode,
                tahsin_status=m.tahsin_status,
                xp=stats.xp,
                streak_days=stats.streak_days,
                level=stats.level,
                passed_surahs=passed,
                pending_setor=pending,
                tahsin_line=tahsin_line,
                hafalan_open=await progress.hafalan_unlocked(db, m),
                mandatory_passed=len(done_pts & {1, 2, 3}),
                hafalan_line=hafalan_line,
                murajaah_due=len(due),
                murajaah_surah=due_name,
            )
        )

    return schemas.ParentDashboardOut(
        family_name=family.name if family else "",
        family_access_code=family.access_code if family else "",
        queue_total=queue_total,
        active_member_id=ctx.member_id,
        children=children,
    )


@router.get("/weekly-report", response_model=schemas.WeeklyReportOut)
async def weekly_report_for_member(
    member_id: uuid.UUID,
    ctx: AuthContext = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(models.Member, member_id)
    if not member or member.family_id != ctx.family_id:
        raise HTTPException(404, "Anak tidak ditemukan")
    today = datetime.now(timezone.utc).date()
    return await weekly_report.build_weekly_report(db, ctx.family_id, member, today)
