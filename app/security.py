import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def hash_secret(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_secret(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def password_fingerprint(hashed_password: str) -> str:
    """Sidik jari hash sandi; berubah saat sandi diganti sehingga token lama otomatis tidak berlaku."""
    return hashlib.sha256(f"{hashed_password}:{settings.jwt_secret}".encode("utf-8")).hexdigest()[:24]


def create_token(
    *,
    subject: uuid.UUID,
    family_id: uuid.UUID,
    role: str,
    member_id: uuid.UUID | None,
    expires_minutes: int,
    pwv: str | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "family_id": str(family_id),
        "role": role,
        "member_id": str(member_id) if member_id else None,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    if pwv:
        payload["pwv"] = pwv
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
