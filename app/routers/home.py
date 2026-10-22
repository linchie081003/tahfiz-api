from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.database import get_db
from app.deps import AuthContext, get_current_context, optional_member_id
from app.models import SubmissionContext, SubmissionStatus
from app.services import gamification, murojaah, progress
from app.services.gamification import level_from_xp
from app.services.reciters import beauty_audio_urls

router = APIRouter(prefix="/home", tags=["home"])


def _parent_menu_locks() -> dict[str, str]:
    return {
        "ziyadah": "",
        "murojaah": "",
        "ujian": "Segera",
        "laporan": "Segera",
    }


@router.get("", response_model=schemas.HomeOut)
async def home(
    member_id=Depends(optional_member_id),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    settings = (
        await db.execute(select(models.FamilySettings).where(models.FamilySettings.family_id == ctx.family_id))
    ).scalar_one_or_none()

    if ctx.role == "parent" and member_id is None:
        parent = await db.get(models.ParentUser, ctx.subject_id)
        return schemas.HomeOut(
            greeting_name=parent.name if parent else "Orang tua",
            streak_days=0,
            xp=0,
            level=1,
            rank_title="Orang tua",
            xp_next_level=100,
            mission_title="MISI HARI INI",
            mission_detail="Jelajahi Tahsin, Ziyadah, Murojaah, dan Alquran — atau pilih profil anak untuk progress",
            mission_xp=0,
            mission_action="home",
            tahsin_status=models.TahsinStatus.passed,
            menu_locks=_parent_menu_locks(),
            level_progress=0,
            beauty_reward=None,
            parent_preview=True,
        )

    assert member_id is not None
    member = await db.get(models.Member, member_id)
    stats = await gamification.ensure_member_stats(db, member_id)
    level, rank, next_xp = level_from_xp(stats.xp)
    cap = settings.daily_murojaah_cap if settings else 5
    ms = (await db.execute(select(models.MemberSettings).where(models.MemberSettings.member_id == member_id))).scalar_one_or_none()
    member_target = ms.daily_ayahs if ms else 1
    due = await murojaah.due_items(db, member_id, cap)
    active = await progress.get_active_surah(db, member_id)
    tahsin_ok = member.tahsin_status == models.TahsinStatus.passed

    if ctx.role == "parent":
        menu_locks = _parent_menu_locks()
    else:
        menu_locks = {
            "ziyadah": "" if tahsin_ok else "Selesaikan Tahsin dulu",
            "murojaah": "" if tahsin_ok else "Selesaikan Tahsin dulu",
            "ujian": "Segera",
            "laporan": "Segera",
        }

    if ctx.role == "parent":
        if due:
            mission_title = "MISI HARI INI"
            surah = await db.get(models.Surah, due[0].surah_id)
            mission_detail = f"Murojaah {member.name}: {surah.name_id if surah else 'surat'}"
            mission_action = "murojaah"
            mission_xp = 15
        elif active:
            surah = await db.get(models.Surah, active.surah_id)
            target = member_target
            mission_detail = f"Ziyadah {member.name}: {target} ayat {surah.name_id if surah else ''}"
            mission_action = "ziyadah"
            mission_xp = 30
            mission_title = "MISI HARI INI"
        else:
            mission_title = "MISI HARI INI"
            mission_detail = f"Progress {member.name} — jelajahi modul"
            mission_action = "home"
            mission_xp = 0
    elif not tahsin_ok:
        mission_title = "MISI HARI INI"
        mission_detail = "Selesaikan evaluasi Tahsin"
        mission_action = "tahsin"
        mission_xp = 20
    elif due:
        mission_title = "MISI HARI INI"
        surah = await db.get(models.Surah, due[0].surah_id)
        mission_detail = f"Murojaah: {surah.name_id if surah else 'surat'}"
        mission_action = "murojaah"
        mission_xp = 15
    elif active:
        surah = await db.get(models.Surah, active.surah_id)
        target = member_target
        mission_detail = f"Setor {target} ayat {surah.name_id if surah else ''}"
        mission_action = "ziyadah"
        mission_xp = 30
        mission_title = "MISI HARI INI"
    else:
        mission_title = "MISI HARI INI"
        mission_detail = "Semua misi hari ini selesai"
        mission_action = "home"
        mission_xp = 0

    beauty_reward = None
    if settings is None or settings.celebrations_enabled:
        last_passed = (
            await db.execute(
                select(models.Submission)
                .where(
                    models.Submission.member_id == member_id,
                    models.Submission.context == SubmissionContext.ziyadah,
                    models.Submission.status == SubmissionStatus.passed,
                    models.Submission.surah_id.isnot(None),
                    models.Submission.ayah_start.isnot(None),
                    models.Submission.evaluated_at.isnot(None),
                )
                .order_by(models.Submission.evaluated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if last_passed and last_passed.surah_id and last_passed.ayah_start is not None:
            ayah_end = last_passed.ayah_end or last_passed.ayah_start
            beauty_reward = schemas.BeautyRewardOut(
                submission_id=last_passed.id,
                surah_id=last_passed.surah_id,
                ayah_start=last_passed.ayah_start,
                ayah_end=ayah_end,
                audio_urls=beauty_audio_urls(last_passed.surah_id, last_passed.ayah_start, ayah_end),
                label="Dengarkan versi indah (Mujawwad) — hadiah setelah lulus",
            )

    return schemas.HomeOut(
        greeting_name=member.name,
        age_mode=member.age_mode,
        streak_days=stats.streak_days,
        xp=stats.xp,
        level=stats.level,
        rank_title=stats.rank_title,
        xp_next_level=next_xp,
        mission_title=mission_title,
        mission_detail=mission_detail,
        mission_xp=mission_xp,
        mission_action=mission_action,
        tahsin_status=member.tahsin_status,
        menu_locks=menu_locks,
        level_progress=min(1.0, stats.xp / max(next_xp, 1)),
        beauty_reward=beauty_reward,
        parent_preview=False,
    )
