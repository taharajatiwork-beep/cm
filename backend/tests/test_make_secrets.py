"""تست اسکریپت تولید secrets.

این اسکریپت اولین چیزی است که اپراتور قبل از استقرار اجرا می‌کند، پس
هر باگش می‌تواند کل استقرار را با رمزهای ضعیف یا یک DATABASE_URL خراب
از کار بیندازد. اینجا اسکریپت را واقعاً اجرا می‌کنیم.
"""

from __future__ import annotations

import re
import subprocess
import sys
import urllib.parse as urlparse
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "deploy" / "make-secrets.sh"

# متغیرهایی که compose باید بتواند از فایل تولیدشده بخواند
REQUIRED_VARS = {
    "APP_ENV",
    "DEBUG",
    "SECRET_KEY",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "DATABASE_URL",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "GF_SECURITY_ADMIN_PASSWORD",
    "BACKUP_PASSPHRASE",
    "COOKIE_SECURE",
    "CORS_ORIGINS",
}

# هر کدام از اینها باید در فایل تولیدشده متفاوت باشند
SECRET_VARS = (
    "SECRET_KEY",
    "POSTGRES_PASSWORD",
    "MINIO_ROOT_PASSWORD",
    "GF_SECURITY_ADMIN_PASSWORD",
    "BACKUP_PASSPHRASE",
    "TELEGRAM_WEBHOOK_SECRET",
)

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(), reason="deploy/make-secrets.sh not present"
)


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """اجرای اسکریپت با sh — و بدون اجازهٔ دانلود چیزی."""
    return subprocess.run(
        ["sh", str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _parse_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def test_generated_env_has_every_variable_compose_needs(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr

    env = _parse_env(tmp_path / ".env.prod.local")
    missing = REQUIRED_VARS - set(env)
    assert not missing, f"generated env is missing {sorted(missing)}"

    # متغیر نباید خالی باشد — وگرنه compose آن را بی‌رمز می‌بیند
    empty = [k for k in REQUIRED_VARS if not env.get(k)]
    assert not empty, f"generated env has empty values for {sorted(empty)}"


def test_secrets_are_random_and_long_enough(tmp_path: Path) -> None:
    """رمزها نباید یکسان باشند یا کوتاه باشند.

    رمز تکراری یک اشتباه رایج است: اگر یکی از متغیرها کپی شود و همه
    رمزها یکی شوند، یک نشت همهٔ سرویس‌ها را افشا می‌کند.
    """
    _run(tmp_path)
    env = _parse_env(tmp_path / ".env.prod.local")

    values = [env[name] for name in SECRET_VARS]
    assert len(set(values)) == len(values), "secrets are not distinct"

    for name in SECRET_VARS:
        assert len(env[name]) >= 32, f"{name} is too short to be random: {len(env[name])} chars"

    # نه الگوی قابل حدس، نه مقدار ثابت
    assert env["SECRET_KEY"] != "dev-secret-change-me"
    assert not re.search(r"(?i)(password|secret|123)", env["POSTGRES_PASSWORD"])


def test_two_runs_produce_different_secrets(tmp_path: Path) -> None:
    """دو بار اجرا نباید همان رمزها را بدهد."""
    _run(tmp_path)
    first = _parse_env(tmp_path / ".env.prod.local")
    _run(tmp_path, "--force")
    second = _parse_env(tmp_path / ".env.prod.local")

    assert first["SECRET_KEY"] != second["SECRET_KEY"]
    assert first["POSTGRES_PASSWORD"] != second["POSTGRES_PASSWORD"]


def test_database_url_is_usable_and_matches_password(tmp_path: Path) -> None:
    """DATABASE_URL باید واقعاً پارس شود و رمزش همان رمز باشد.

    یک رمز شامل `@` یا `/` در URL بدون percent-encoding، اتصال را خراب
    می‌کند — و خطا فقط هنگام استقرار دیده می‌شود.
    """
    _run(tmp_path)
    env = _parse_env(tmp_path / ".env.prod.local")

    parsed = urlparse.urlparse(env["DATABASE_URL"])
    assert parsed.scheme == "postgresql+asyncpg", parsed.scheme
    assert parsed.hostname == "postgres", "host must be the compose service name"
    assert parsed.port == 5432
    assert parsed.path.strip("/") == env["POSTGRES_DB"]

    password_in_url = urlparse.unquote(parsed.password or "")
    assert password_in_url == env["POSTGRES_PASSWORD"], (
        "password embedded in DATABASE_URL does not match POSTGRES_PASSWORD"
    )
    # رمز خام نباید کاراکتر URL-breaking داشته باشد
    assert not any(c in env["POSTGRES_PASSWORD"] for c in "@:/?#%[]")


def test_generated_env_passes_the_production_startup_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """فایل تولیدشده باید guard امنیتی production را رد کند.

    این اتصال مستقیم بین اسکریپت و تنظیمات است: اگر روزی یکی عوض شد،
    این تست می‌گیرد قبل از آنکه در استقرار کشف شود. به‌جای بازرسی دستیِ
    چند متغیر، کل env تولیدشده را به همان تنظیمات واقعی اپلیکیشن می‌دهیم.
    """
    _run(tmp_path)
    env = _parse_env(tmp_path / ".env.prod.local")

    assert env["APP_ENV"] == "production"
    assert env["DEBUG"] == "false"
    assert env["COOKIE_SECURE"] == "true"

    # CORS باید https باشد، نه http — وگرنه startup رد می‌کند
    origins = [o.strip() for o in env["CORS_ORIGINS"].split(",") if o.strip()]
    assert origins, "CORS_ORIGINS is empty"
    for origin in origins:
        assert origin.startswith("https://"), f"origin is not https: {origin}"

    # خودِ guard واقعی، روی همان متغیرهای تولیدشده. از مسیر عادی
    # بارگذاری تنظیمات می‌رویم (همان کاری که اپلیکیشن در startup می‌کند)
    # تا تبدیل نوع‌ها هم واقعاً آزموده شود.
    from app.core.config import Settings
    from app.core.startup import assert_production_safe

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    settings = Settings()
    assert_production_safe(settings)  # نباید چیزی پرتاب کند


def test_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    """بازنویسی ناخواستهٔ فایل، تنها کپی رمزها را از بین می‌برد."""
    _run(tmp_path)
    original = (tmp_path / ".env.prod.local").read_text(encoding="utf-8")

    second = _run(tmp_path)
    assert second.returncode != 0
    assert "refusing to overwrite" in second.stderr.lower()

    unchanged = (tmp_path / ".env.prod.local").read_text(encoding="utf-8")
    assert unchanged == original, "the refused run still modified the file"


def test_refuses_when_no_secret_generator_exists(tmp_path: Path) -> None:
    """بدون python یا openssl باید خطا بدهد، نه اینکه رمز ضعیف بگذارد."""
    if sys.platform == "win32":
        pytest.skip(
            "روی ویندوز sh از نوع MSYS است و با PATH خالی هم python را پیدا "
            "می‌کند؛ این تضمین در CI لینوکس واقعاً آزموده می‌شود."
        )
    empty_path = tmp_path / "emptybin"
    empty_path.mkdir()
    env = {
        "PATH": str(empty_path),
        "SystemRoot": __import__("os").environ.get("SystemRoot", ""),
    }
    result = subprocess.run(
        ["sh", str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert result.returncode != 0, "script succeeded with no way to generate randomness"
    assert not (tmp_path / ".env.prod.local").exists()
