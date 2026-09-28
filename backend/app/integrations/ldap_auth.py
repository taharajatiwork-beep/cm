"""Optional LDAP bind. Disabled unless LDAP_ENABLED=true and ldap3 is installed."""

from __future__ import annotations

from app.core.config import get_settings


def ldap_authenticate(email: str, password: str) -> bool:
    settings = get_settings()
    if not settings.ldap_enabled or not settings.ldap_url:
        return False
    try:
        import ldap3
    except ImportError as exc:
        raise RuntimeError("ldap3 is not installed") from exc
    server = ldap3.Server(settings.ldap_url)
    conn = ldap3.Connection(server, user=email, password=password, auto_bind=True)
    return bool(conn.bound)
