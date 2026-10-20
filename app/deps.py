import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.database import get_db
from app.security import decode_token, password_fingerprint

bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    role: str
    family_id: uuid.UUID
    subject_id: uuid.UUID
    member_id: uuid.UUID | None


async def get_current_context(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token diperlukan")
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak valid")
    try:
        role = payload["role"]
        family_id = uuid.UUID(payload["family_id"])
        subject_id = uuid.UUID(payload["sub"])
        member_raw = payload.get("member_id")
        member_id = uuid.UUID(member_raw) if member_raw else None
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak valid")

    # Token harus masih cocok dengan akun: sandi diganti atau akun/anak dihapus -> token mati.
    if role == "parent":
        parent = await db.get(models.ParentUser, subject_id)
        if (
            not parent
            or parent.family_id != family_id
            or payload.get("pwv") != password_fingerprint(parent.hashed_password)
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesi berakhir, silakan masuk kembali")
    elif role == "child":
        member = await db.get(models.Member, subject_id)
        if not member or member.family_id != family_id or member_id != member.id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesi berakhir, silakan masuk kembali")
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak valid")
    return AuthContext(role=role, family_id=family_id, subject_id=subject_id, member_id=member_id)


async def require_parent(ctx: AuthContext = Depends(get_current_context)) -> AuthContext:
    if ctx.role != "parent":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya orang tua")
    return ctx


async def require_member_id(ctx: AuthContext = Depends(get_current_context)) -> uuid.UUID:
    if ctx.role == "child" and ctx.member_id:
        return ctx.member_id
    if ctx.role == "parent" and ctx.member_id:
        return ctx.member_id
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pilih profil anak terlebih dahulu")


async def optional_member_id(ctx: AuthContext = Depends(get_current_context)) -> uuid.UUID | None:
    if ctx.role == "child":
        if not ctx.member_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Profil anak tidak valid")
        return ctx.member_id
    return ctx.member_id
