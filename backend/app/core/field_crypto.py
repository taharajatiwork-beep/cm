"""رمزنگاری فیلدهای حساس در rest — پیشوند enc1: برای تشخیص از متن ساده."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_PREFIX = "enc1:"


def _fernet() -> Fernet | None:
    settings = get_settings()
    raw = (settings.field_encryption_key or "").strip()
    if not raw:
        if settings.app_env == "production":
            return None
        digest = hashlib.sha256(settings.secret_key.encode()).digest()
        raw = base64.urlsafe_b64encode(digest).decode()
    try:
        return Fernet(raw.encode() if not raw.startswith("gAAAA") else raw)
    except (ValueError, TypeError):
        key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
        return Fernet(key)


def encrypt_secret(plain: str) -> str:
    text = (plain or "").strip()
    if not text or text.startswith(_PREFIX):
        return plain or ""
    fernet = _fernet()
    if fernet is None:
        return text
    token = fernet.encrypt(text.encode()).decode()
    return f"{_PREFIX}{token}"


def decrypt_secret(stored: str) -> str:
    text = stored or ""
    if not text.startswith(_PREFIX):
        return text
    fernet = _fernet()
    if fernet is None:
        return ""
    try:
        return fernet.decrypt(text[len(_PREFIX) :].encode()).decode()
    except InvalidToken:
        return ""


def mask_iban(iban: str) -> str:
    clean = (iban or "").replace(" ", "")
    if len(clean) < 8:
        return "***" if clean else ""
    return f"{clean[:4]}…{clean[-4:]}"
