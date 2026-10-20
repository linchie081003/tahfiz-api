import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ratelimit, models, schemas, security
from app.config import settings
from app.database import get_db
from app.deps import AuthContext, get_current_context
from app.services import gamification, progress

router = APIRouter(prefix="/auth", tags=["auth"])


def _access_code() -> str:
    """Kode mudah diingat anak: 6 angka. Keamanannya ditopang pembatas percobaan, bukan panjang kode."""
    return str(secrets.randbelow(900_000) + 100_000)


@router.post("/register-family", response_model=schemas.TokenOut, status_code=status.HTTP_201_CREATED)
async def register_family(request: Request, payload: schemas.RegisterFamilyIn, db: AsyncSession = Depends(get_db)):
    ratelimit.check_ip(request, "register", 10, 3600)
    if (await db.execute(select(models.ParentUser).where(models.ParentUser.email == payload.admin_email))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email sudah terdaftar")
    for _ in range(5):
        code = _access_code()
        if not (await db.execute(select(models.Family).where(models.Family.access_code == code))).scalar_one_or_none():
            break
    else:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Gagal membuat kode keluarga")

    family = models.Family(name=payload.family_name, access_code=code)
    db.add(family)
    await db.flush()
    parent = models.ParentUser(
        family_id=family.id,
        email=payload.admin_email,
        hashed_password=security.hash_secret(payload.admin_password),
        name=payload.admin_name,
    )
    db.add(parent)
    db.add(models.FamilySettings(family_id=family.id))
    # Jenis misi bersifat global (slug unik): buat sekali saja, jangan per keluarga.
    if not (
        await db.execute(select(models.MissionType).where(models.MissionType.slug == "quran_memorization"))
    ).scalar_one_or_none():
        db.add(models.MissionType(slug="quran_memorization", name="Hafalan Qur'an"))
    await db.flush()
    token = security.create_token(
        subject=parent.id,
        family_id=family.id,
        role="parent",
        member_id=None,
        expires_minutes=settings.parent_token_expire_minutes,
        pwv=security.password_fingerprint(parent.hashed_password),
    )
    return schemas.TokenOut(access_token=token, role="parent", family_access_code=family.access_code)


@router.get("/session", response_model=schemas.SessionOut)
async def session(ctx: AuthContext = Depends(get_current_context), db: AsyncSession = Depends(get_db)):
    family = await db.get(models.Family, ctx.family_id)
    member_name = None
    age_mode = None
    if ctx.member_id:
        member = await db.get(models.Member, ctx.member_id)
        if member:
            member_name = member.name
            age_mode = member.age_mode
    return schemas.SessionOut(
        role=ctx.role,
        member_id=ctx.member_id,
        member_name=member_name,
        age_mode=age_mode,
        family_name=family.name if family else "",
        family_access_code=family.access_code if family else "",
        needs_child_profile=False,
    )


@router.post("/reset-password")
async def reset_password(request: Request, payload: schemas.PasswordResetIn, db: AsyncSession = Depends(get_db)):
    """Reset kata sandi orang tua dengan email + kode keluarga (6 angka) — tanpa email SMTP."""
    code = _normalize_access_code(payload.access_code)
    # Batasi ketat: kode keluarga hanya 6 angka, jadi tebakan beruntun harus dihentikan.
    ratelimit.check_ip(request, "reset:ip", 5, 3600)
    ratelimit.check("reset:email", payload.email.lower(), 5, 3600)
    ratelimit.check("reset:code", code, 10, 3600)
    if len(code) < 4:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kode keluarga tidak valid")
    family = (
        await db.execute(select(models.Family).where(models.Family.access_code == code))
    ).scalar_one_or_none()
    if not family:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kode keluarga tidak ditemukan")
    user = (
        await db.execute(select(models.ParentUser).where(models.ParentUser.email == payload.email))
    ).scalar_one_or_none()
    if not user or user.family_id != family.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email tidak cocok dengan kode keluarga ini")
    user.hashed_password = security.hash_secret(payload.new_password)
    await db.flush()
    # Sidik jari sandi berubah -> seluruh token orang tua lama otomatis tidak berlaku.
    return {"ok": True}


@router.post("/login", response_model=schemas.TokenOut)
async def login(request: Request, payload: schemas.LoginIn, db: AsyncSession = Depends(get_db)):
    ratelimit.check_ip(request, "login:ip", 20, 300)
    ratelimit.check("login:email", payload.email.lower(), 8, 300)
    user = (await db.execute(select(models.ParentUser).where(models.ParentUser.email == payload.email))).scalar_one_or_none()
    if not user or not security.verify_secret(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email atau password salah")
    token = security.create_token(
        subject=user.id,
        family_id=user.family_id,
        role="parent",
        member_id=None,
        expires_minutes=settings.parent_token_expire_minutes,
        pwv=security.password_fingerprint(user.hashed_password),
    )
    family = await db.get(models.Family, user.family_id)
    return schemas.TokenOut(access_token=token, role="parent", family_access_code=family.access_code)


def _normalize_access_code(raw: str) -> str:
    return "".join(ch for ch in raw.upper() if ch.isalnum())


@router.get("/family-children", response_model=schemas.PublicFamilyChildrenOut)
async def family_children(request: Request, access_code: str, db: AsyncSession = Depends(get_db)):
    ratelimit.check_ip(request, "family-children:ip", 20, 300)
    ratelimit.check("family-children:code", _normalize_access_code(access_code), 30, 300)
    code = _normalize_access_code(access_code)
    family = (
        await db.execute(select(models.Family).where(models.Family.access_code == code))
    ).scalar_one_or_none()
    if not family:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kode keluarga tidak ditemukan")
    children = (
        await db.execute(select(models.Member).where(models.Member.family_id == family.id).order_by(models.Member.created_at))
    ).scalars().all()
    return schemas.PublicFamilyChildrenOut(
        family_name=family.name,
        children=[schemas.PublicChildOut(id=c.id, name=c.name, color=c.color, has_pin=bool(c.pin_hash)) for c in children],
    )


@router.post("/child-login", response_model=schemas.TokenOut)
async def child_login(request: Request, payload: schemas.ChildLoginIn, db: AsyncSession = Depends(get_db)):
    code = _normalize_access_code(payload.access_code)
    ratelimit.check_ip(request, "child-login:ip", 30, 300)
    ratelimit.check("child-login:child", f"{code}:{payload.child_id}", 10, 300)
    family = (
        await db.execute(select(models.Family).where(models.Family.access_code == code))
    ).scalar_one_or_none()
    if not family:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kode keluarga tidak ditemukan")
    member = await db.get(models.Member, payload.child_id)
    if not member or member.family_id != family.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profil anak tidak ditemukan")
    if member.pin_hash and not security.verify_secret(payload.pin, member.pin_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "PIN salah")
    token = security.create_token(
        subject=member.id,
        family_id=family.id,
        role="child",
        member_id=member.id,
        expires_minutes=settings.child_token_expire_minutes,
    )
    return schemas.TokenOut(access_token=token, role="child", family_access_code=family.access_code)

