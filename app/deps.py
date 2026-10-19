import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    role: str
    family_id: uuid.UUID
    subject_id: uuid.UUID
    member_id: uuid.UUID | None


async def get_current_context(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> AuthContext:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token diperlukan")
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak valid")
    member_raw = payload.get("member_id")
    return AuthContext(
        role=payload["role"],
        family_id=uuid.UUID(payload["family_id"]),
        subject_id=uuid.UUID(payload["sub"]),
        member_id=uuid.UUID(member_raw) if member_raw else None,
    )


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
