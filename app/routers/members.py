import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas, security
from app.config import settings
from app.database import get_db
from app.deps import AuthContext, require_parent
from app.services import gamification, progress
from app.services.member_lifecycle import delete_member_and_data

router = APIRouter(prefix="/members", tags=["members"])


@router.post("", response_model=schemas.MemberOut, status_code=status.HTTP_201_CREATED)
async def create_member(payload: schemas.MemberCreateIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    member = models.Member(
        family_id=ctx.family_id,
        name=payload.name,
        birth_date=payload.birth_date,
        age_mode=payload.age_mode,
    )
    db.add(member)
    await db.flush()
    await gamification.ensure_member_stats(db, member.id)
    await progress.init_member_progress(db, member.id)
    return member


@router.get("", response_model=list[schemas.MemberOut])
async def list_members(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(models.Member).where(models.Member.family_id == ctx.family_id))).scalars().all()
    return rows


@router.delete("/{member_id}", response_model=schemas.MemberDeleteOut)
async def remove_member(
    member_id: uuid.UUID,
    ctx: AuthContext = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_member_and_data(db, member_id, ctx.family_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anak tidak ditemukan")
    await db.commit()
    new_token = None
    if ctx.member_id == member_id:
        parent = await db.get(models.ParentUser, ctx.subject_id)
        if parent:
            new_token = security.create_token(
                subject=parent.id,
                family_id=ctx.family_id,
                role="parent",
                member_id=None,
                expires_minutes=settings.parent_token_expire_minutes,
            )
    return schemas.MemberDeleteOut(access_token=new_token)


@router.post("/{member_id}/impersonate", response_model=schemas.TokenOut)
async def impersonate_child(member_id: uuid.UUID, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    member = await db.get(models.Member, member_id)
    if not member or member.family_id != ctx.family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anak tidak ditemukan")
    parent = await db.get(models.ParentUser, ctx.subject_id)
    token = security.create_token(
        subject=parent.id,
        family_id=ctx.family_id,
        role="parent",
        member_id=member.id,
        expires_minutes=settings.parent_token_expire_minutes,
    )
    family = await db.get(models.Family, ctx.family_id)
    return schemas.TokenOut(access_token=token, role="parent", family_access_code=family.access_code)


@router.post("/verify-settings-pin")
async def verify_settings_pin(payload: schemas.PinVerifyIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    parent = await db.get(models.ParentUser, ctx.subject_id)
    if not parent or not parent.settings_pin_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PIN belum diatur")
    if not security.verify_secret(payload.pin, parent.settings_pin_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "PIN salah")
    return {"ok": True}


@router.put("/settings-pin")
async def set_settings_pin(payload: schemas.PinVerifyIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    parent = await db.get(models.ParentUser, ctx.subject_id)
    if not parent:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    parent.settings_pin_hash = security.hash_secret(payload.pin)
    return {"ok": True}
