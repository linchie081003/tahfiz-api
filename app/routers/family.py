import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, ratelimit, schemas, security
from app.config import settings
from app.database import get_db
from app.deps import AuthContext, require_parent

router = APIRouter(prefix="/family", tags=["family"])

INVITE_DAYS = 7


class InviteOut(BaseModel):
    code: str
    expires_at: datetime


class JoinIn(BaseModel):
    code: str
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8)


class ParentOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    family_role: str


async def require_owner(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)) -> AuthContext:
    parent = await db.get(models.ParentUser, ctx.subject_id)
    if not parent or parent.family_role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya pemilik keluarga")
    return ctx


@router.get("/parents", response_model=list[ParentOut])
async def list_parents(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(models.ParentUser).where(models.ParentUser.family_id == ctx.family_id))
    ).scalars().all()
    return [ParentOut(id=p.id, name=p.name, email=p.email, family_role=p.family_role) for p in rows]


@router.post("/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def create_invite(ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    """Pemilik mengundang pasangan (orang tua kedua). Maksimal dua orang tua per keluarga."""
    count = len(
        (await db.execute(select(models.ParentUser.id).where(models.ParentUser.family_id == ctx.family_id))).all()
    )
    if count >= 2:
        raise HTTPException(status.HTTP_409_CONFLICT, "Keluarga sudah punya dua orang tua")
    invite = models.FamilyInvite(
        family_id=ctx.family_id,
        code=secrets.token_urlsafe(12),
        created_by=ctx.subject_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_DAYS),
    )
    db.add(invite)
    await db.flush()
    return InviteOut(code=invite.code, expires_at=invite.expires_at)


@router.post("/join", response_model=schemas.TokenOut, status_code=status.HTTP_201_CREATED)
async def join_family(request: Request, payload: JoinIn, db: AsyncSession = Depends(get_db)):
    ratelimit.check_ip(request, "join", 10, 3600)
    invite = (
        await db.execute(select(models.FamilyInvite).where(models.FamilyInvite.code == payload.code))
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not invite or invite.used_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Undangan tidak valid")
    exp = invite.expires_at if invite.expires_at.tzinfo else invite.expires_at.replace(tzinfo=timezone.utc)
    if exp < now:
        raise HTTPException(status.HTTP_410_GONE, "Undangan sudah kedaluwarsa")
    if (await db.execute(select(models.ParentUser).where(models.ParentUser.email == payload.email))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email sudah terdaftar")
    parent = models.ParentUser(
        family_id=invite.family_id,
        email=payload.email,
        hashed_password=security.hash_secret(payload.password),
        name=payload.name,
        family_role="parent",
    )
    db.add(parent)
    await db.flush()
    invite.used_at = now
    invite.used_by = parent.id
    family = await db.get(models.Family, invite.family_id)
    token = security.create_token(
        subject=parent.id,
        family_id=invite.family_id,
        role="parent",
        member_id=None,
        expires_minutes=settings.parent_token_expire_minutes,
        pwv=security.password_fingerprint(parent.hashed_password),
    )
    return schemas.TokenOut(access_token=token, role="parent", family_access_code=family.access_code)
