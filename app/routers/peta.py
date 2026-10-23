from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.database import get_db
from app.deps import AuthContext, get_current_context, optional_member_id
from app.services import progress as progress_svc
from app.services.juz30 import list_juz30_surahs

router = APIRouter(prefix="/peta", tags=["peta"])


@router.get("/juz/30", response_model=schemas.PetaOut)
async def peta_juz30(
    member_id=Depends(optional_member_id),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    track = await progress_svc.effective_track(db, member_id) if member_id else "juz30"
    ms = await progress_svc.get_settings(db, member_id) if member_id else None
    order = ms.hafalan_order if ms and ms.hafalan_order else "sequential"
    surahs = await progress_svc.track_surahs(db, track)

    if ctx.role == "parent" and member_id is None:
        nodes = [
            schemas.PetaNodeOut(
                surah_id=s.id,
                name_id=s.name_id,
                ayah_count=s.ayah_count,
                status="active",
                curriculum_order=s.curriculum_order,
            )
            for s in surahs
        ]
        first = surahs[0] if surahs else None
        return schemas.PetaOut(
            juz_number=30,
            track="juz30",
            passed_count=0,
            total_count=len(surahs),
            active_surah_id=first.id if first else None,
            active_surah_name=first.name_id if first else None,
            unlock_hint="Mode orang tua — semua surat Juz 30 terbuka untuk eksplorasi",
            nodes=nodes,
        )

    assert member_id is not None
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
    chosen = await progress_svc.get_active_surah(db, member_id)
    unlock_hint = None
    parent_open = ctx.role == "parent"

    for s in surahs:
        pr = progress_rows.get(s.id)
        if parent_open:
            status = "active"
            if pr and pr.status == models.SurahProgressStatus.passed:
                status = "passed"
                passed += 1
            elif pr and pr.status in (
                models.SurahProgressStatus.in_progress,
                models.SurahProgressStatus.needs_retry,
            ):
                status = "active"
                if active_id is None:
                    active_id = s.id
                    active_name = s.name_id
        elif not pr:
            status = "locked"
        elif pr.status == models.SurahProgressStatus.passed:
            status = "passed"
            passed += 1
        elif pr.status in (models.SurahProgressStatus.in_progress, models.SurahProgressStatus.needs_retry):
            status = "active"
            if active_id is None:
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
                selectable=order == "free" and not (pr and pr.status == models.SurahProgressStatus.passed)
                and not (chosen and chosen.surah_id == s.id),
            )
        )
    if chosen and order == "free":  # surat pilihan anak (mode bebas) didahulukan; selain itu yang pertama aktif
        cs = next((x for x in surahs if x.id == chosen.surah_id), None)
        if cs:
            active_id, active_name = cs.id, cs.name_id
    if active_id and not parent_open:
        nxt = next((n for n in nodes if n.status == "locked"), None)
        if nxt and order != "free":
            unlock_hint = f"Lulus {active_name} untuk membuka {nxt.name_id}"
    elif parent_open:
        unlock_hint = "Orang tua — semua modul terbuka; progress mengikuti profil anak yang dipilih"
    plan = await progress_svc.setor_plan(db, member_id)
    return schemas.PetaOut(
        juz_number=30 if track == "juz30" else 0,
        track=track,
        passed_count=passed,
        total_count=len(surahs),
        active_surah_id=active_id,
        active_surah_name=active_name,
        unlock_hint=unlock_hint,
        nodes=nodes,
        hafalan_order=order,
        plan=schemas.SetorPlanOut(**plan) if plan else None,
    )


class PilihSuratIn(BaseModel):
    surah_id: int


@router.post("/pilih")
async def pilih_surat(
    payload: PilihSuratIn,
    member_id=Depends(optional_member_id),
    ctx: AuthContext = Depends(get_current_context),
    db: AsyncSession = Depends(get_db),
):
    """Mode hafalan bebas: pindah ke surat lain. Mode berurutan: ditolak (409)."""
    if member_id is None:
        raise HTTPException(400, "Pilih profil anak terlebih dahulu")
    await progress_svc.choose_surah(db, member_id, payload.surah_id)
    plan = await progress_svc.setor_plan(db, member_id)
    return {"ok": True, "plan": plan}
