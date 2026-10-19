from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.database import get_db
from app.deps import require_member_id
from app.services import progress

router = APIRouter(prefix="/peta", tags=["peta"])


@router.get("/juz/30", response_model=schemas.PetaOut)
async def peta_juz30(member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    surahs = (
        await db.execute(select(models.Surah).where(models.Surah.juz_number == 30).order_by(models.Surah.curriculum_order))
    ).scalars().all()
    progress_rows = {
        r.surah_id: r
        for r in (
            await db.execute(select(models.MemberSurahProgress).where(models.MemberSurahProgress.member_id == member_id))
        ).scalars().all()
    }
    nodes: list[schemas.PetaNodeOut] = []
    passed = 0
    active_id = None
    active_name = None
    unlock_hint = None
    for s in surahs:
        pr = progress_rows.get(s.id)
        if not pr:
            status = "locked"
        elif pr.status == models.SurahProgressStatus.passed:
            status = "passed"
            passed += 1
        elif pr.status in (models.SurahProgressStatus.in_progress, models.SurahProgressStatus.needs_retry):
            status = "active"
            active_id = s.id
            active_name = s.name_id
        else:
            status = "locked"
        nodes.append(
            schemas.PetaNodeOut(
                surah_id=s.id,
                name_id=s.name_id,
                ayah_count=s.ayah_count,
                status=status,
                curriculum_order=s.curriculum_order,
            )
        )
    if active_id:
        nxt = next((n for n in nodes if n.status == "locked"), None)
        if nxt:
            unlock_hint = f"Lulus {active_name} untuk membuka {nxt.name_id}"
    return schemas.PetaOut(
        juz_number=30,
        passed_count=passed,
        total_count=len(surahs),
        active_surah_id=active_id,
        active_surah_name=active_name,
        unlock_hint=unlock_hint,
        nodes=nodes,
    )
