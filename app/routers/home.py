from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.database import get_db
from app.deps import AuthContext, get_current_context, require_member_id
from app.services import gamification, murojaah, progress
from app.services.gamification import level_from_xp

router = APIRouter(prefix="/home", tags=["home"])


@router.get("", response_model=schemas.HomeOut)
async def home(member_id=Depends(require_member_id), ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    member = await db.get(models.Member, member_id)
    stats = await gamification.ensure_member_stats(db, member_id)
    level, rank, next_xp = level_from_xp(stats.xp)
    settings = (
        await db.execute(select(models.FamilySettings).where(models.FamilySettings.family_id == ctx.family_id))
    ).scalar_one_or_none()
    cap = settings.daily_murojaah_cap if settings else 5
    due = await murojaah.due_items(db, member_id, cap)
    active = await progress.get_active_surah(db, member_id)
    tahsin_ok = member.tahsin_status == models.TahsinStatus.passed

    menu_locks = {
        "ziyadah": "" if tahsin_ok else "Selesaikan Tahsin dulu",
        "murojaah": "" if tahsin_ok else "Selesaikan Tahsin dulu",
        "ujian": "Segera",
        "laporan": "Segera",
    }

    if not tahsin_ok:
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
        target = settings.daily_ziyadah_ayahs if settings else 3
        mission_detail = f"Setor {target} ayat {surah.name_id if surah else ''}"
        mission_action = "ziyadah"
        mission_xp = 30
        mission_title = "MISI HARI INI"
    else:
        mission_title = "MISI HARI INI"
        mission_detail = "Semua misi hari ini selesai"
        mission_action = "home"
        mission_xp = 0

    return schemas.HomeOut(
        greeting_name=member.name,
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
    )
