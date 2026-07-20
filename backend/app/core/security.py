from datetime import timedelta

import bcrypt
from jose import jwt, JWTError

from app.core.config import settings
from app.db.base import utcnow

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    # bcrypt has a 72-byte limit; truncate defensively.
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except ValueError:
        return False


def _create_token(sub: str, kind: str, expires: timedelta, extra: dict | None = None) -> str:
    now = utcnow()
    payload = {"sub": sub, "type": kind, "iat": now, "exp": now + expires}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int, org_id: int, role: str) -> str:
    return _create_token(
        str(user_id),
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        {"org_id": org_id, "role": role},
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        str(user_id), "refresh", timedelta(days=settings.refresh_token_expire_days)
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
