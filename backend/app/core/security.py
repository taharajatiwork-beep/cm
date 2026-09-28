import hashlib
import hmac
import secrets
import struct
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str | UUID, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {"sub": str(subject), "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def validate_password(password: str) -> str | None:
    """Return an error message, or None when the password is acceptable.

    Complexity rules apply in production only so demo seed passwords stay valid.
    """
    settings = get_settings()
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if settings.app_env == "production":
        if not any(c.isupper() for c in password) or not any(c.islower() for c in password):
            return "Password must mix upper and lower case"
        if not any(c.isdigit() for c in password):
            return "Password must include a digit"
    return None


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def totp_key(secret: str) -> bytes:
    """Base32 secrets (authenticator apps) or raw strings (tests)."""
    import base64

    compact = secret.strip().replace(" ", "")
    alphabet = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
    if compact and set(compact.upper()) <= alphabet:
        padded = compact.upper() + ("=" * ((8 - len(compact) % 8) % 8))
        try:
            return base64.b32decode(padded, casefold=True)
        except Exception:
            pass
    return secret.encode("utf-8")


def new_totp_secret() -> str:
    import base64

    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_now(secret: str, step: int = 30, digits: int = 6, for_time: int | None = None) -> str:
    counter = int((for_time if for_time is not None else time.time()) // step)
    key = totp_key(secret)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10**digits)).zfill(digits)


def verify_totp(secret: str, code: str) -> bool:
    if not code or not secret:
        return False
    now = int(time.time())
    return any(hmac.compare_digest(totp_now(secret, for_time=now + drift), code.strip()) for drift in (-30, 0, 30))


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
