"""تست امنیتی: هیچ رمز یا توکنی نباید در فایل‌های استقرار hardcode شده باشد.

این تست عمداً روی فایل‌های متنی ریپو اجرا می‌شود نه فقط کد اپلیکیشن،
چون نشتی اصلی در `docker-compose.prod.yml` بود: رمز دیتابیس، MinIO و
Grafana مستقیم در YAML نوشته شده بودند و `env_file: .env` بی‌اثر می‌شد.

اگر روزی کسی رمز واقعی را در YAML بگذارد، این تست fails می‌شود.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# فایل‌هایی که در استقرار واقعی به کار می‌روند و نباید رمز داشته باشند
DEPLOY_FILES = [
    "docker-compose.prod.yml",
    "deploy/nginx.conf",
    "deploy/backup.sh",
    "deploy/prometheus.yml",
    "deploy/alerts.yml",
]

# کلیدهایی که مقدارشان باید از محیط بیاید، نه از متن فایل
SECRET_KEYS = [
    "POSTGRES_PASSWORD",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "GF_SECURITY_ADMIN_PASSWORD",
]

# الگوی URL دیتابیس با رمز داخلش
DB_URL_WITH_PASSWORD = re.compile(r"postgresql(?:\+asyncpg)?://[^:$\s]+:[^:@$\s]+@")


def _read(name: str) -> str:
    path = REPO / name
    assert path.exists(), f"expected {name} to exist"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", DEPLOY_FILES)
def test_no_inline_database_password(name: str) -> None:
    """هیچ URL دیتابیسی نباید رمز داخلش داشته باشد."""
    offenders = DB_URL_WITH_PASSWORD.findall(_read(name))
    assert not offenders, (
        f"{name} has an inline database password: {offenders}. "
        "Read it from the environment instead (e.g. ${POSTGRES_PASSWORD})."
    )


@pytest.mark.parametrize("name", DEPLOY_FILES)
@pytest.mark.parametrize("key", SECRET_KEYS)
def test_secret_keys_come_from_environment(name: str, key: str) -> None:
    """مقدار رمزها باید از متغیر محیطی بیاید، نه مقدار ثابت."""
    for line in _read(name).splitlines():
        stripped = line.strip()
        if not stripped.startswith(f"{key}:"):
            continue
        _, _, value = stripped.partition(":")
        value = value.strip()
        # خالی یا ارجاع به محیط یا متغیر ترکیبی مجاز است
        if not value or value.startswith("${"):
            continue
        raise AssertionError(
            f"{name}: {key} has a hardcoded value {value!r}. "
            f"Use {key}: ${{{key}}} and declare it in .env instead."
        )


def test_env_example_marks_production_secrets_as_placeholders() -> None:
    """`.env.example` نباید رمز واقعی داشته باشد؛ فقط الگو."""
    text = _read(".env.example")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key not in SECRET_KEYS:
            continue
        assert not value.strip(), f".env.example sets {key} to a real value"


# ---------- هدرهای امنیتی در nginx ----------

# هر هدری که بدون آن برنامه در برابر یک کلاس حملهٔ مشخص آسیب‌پذیر است
REQUIRED_SECURITY_HEADERS = [
    "Strict-Transport-Security",  # downgrade به HTTP
    "X-Frame-Options",  # clickjacking
    "X-Content-Type-Options",  # MIME sniffing
    "Referrer-Policy",  # نشت URL در Referer
    "Content-Security-Policy",  # تزریق XSS
]


def _nginx_headers(name: str = "deploy/nginx.conf") -> dict[str, str]:
    """add_header ها را به dict تبدیل می‌کند: نام → مقدار."""
    found: dict[str, str] = {}
    for line in _read(name).splitlines():
        stripped = line.strip()
        if not stripped.startswith("add_header "):
            continue
        rest = stripped[len("add_header ") :]
        header, _, rest = rest.partition(" ")
        value = rest.strip().rstrip(";")
        # nginx مقدار را در کوتیشن می‌پذیرد
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        found[header.strip()] = value
    return found


@pytest.mark.parametrize("header", REQUIRED_SECURITY_HEADERS)
def test_security_headers_present(header: str) -> None:
    assert header in _nginx_headers(), f"nginx.conf is missing add_header {header}"


@pytest.mark.parametrize("header", REQUIRED_SECURITY_HEADERS)
def test_security_headers_always_applied(header: str) -> None:
    """بدون `always` هدر در پاسخ‌های خطا حذف می‌شود."""
    assert " always;" in _read("deploy/nginx.conf").split(f"add_header {header}", 1)[1].split(
        "\n", 1
    )[0], f"add_header {header} must end with `always;` to cover 4xx/5xx"


def test_server_tokens_off() -> None:
    assert "server_tokens off;" in _read("deploy/nginx.conf")


def test_http_redirects_to_https() -> None:
    """پورت ۸۰ نباید سرو کند — فقط redirect."""
    conf = _read("deploy/nginx.conf")
    assert "listen 80;" in conf
    assert "return 308 https://" in conf


def test_tls_12_or_newer_only() -> None:
    conf = _read("deploy/nginx.conf")
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in conf
    # TLSv1 و TLSv1.1 نباید فعال باشند
    assert "ssl_protocols TLSv1;" not in conf
    assert "ssl_protocols TLSv1.1" not in conf


def test_csp_allows_self_and_no_external_script() -> None:
    """CSP نباید به دامنهٔ بیرونی اجازهٔ اسکریپت بدهد."""
    csp = _nginx_headers()["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    # منبع بیرونی برای اسکریپت یعنی XSS از CDN
    assert "https://" not in csp, f"CSP allows an external origin: {csp}"
    assert "frame-ancestors 'none'" in csp


def test_csp_matches_reality_no_external_origins_needed() -> None:
    """برنامه نباید به منبع بیرونی نیاز داشته باشد که CSP نبیند."""
    frontend = REPO / "frontend" / "index.html"
    html = frontend.read_text(encoding="utf-8")
    # هیچ لینک CDN (مثل فونت گوگل) نباید بماند
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html
    assert "//cdn." not in html


# ---------- runbook باید با رفتار واقعی هم‌خوان باشد ----------

RUNBOOK = "docs/runbooks/backup.md"


def test_backup_script_refuses_to_run_without_a_passphrase() -> None:
    """بدون رمز نباید بی‌سروصدا dump بی‌رمز بنویسد."""
    script = _read("deploy/backup.sh")
    assert "BACKUP_PASSPHRASE" in script
    # باید صریحاً خطا بدهد، نه اینکه بدون رمز ادامه دهد
    assert "refusing to write an unencrypted dump" in script


def test_backup_script_verifies_before_reporting_success() -> None:
    """تأیید باید قبل از پیام موفقیت انجام شود."""
    script = _read("deploy/backup.sh")
    assert "pg_restore --list" in script
    assert script.index("pg_restore --list") < script.index("wrote ${out}")


def test_backup_script_deletes_plaintext_dump() -> None:
    """فایل بازیابی‌شدهٔ خام نباید باقی بماند."""
    script = _read("deploy/backup.sh")
    assert 'rm -f "$plain"' in script


def test_generated_secrets_are_never_committed() -> None:
    """فایل تولیدی نباید در git track شود.

    اگر این guard نبود، یک `git add .` ساده کل رمزهای تولید را می‌فرستاد
    و بعد از آن باید تاریخچهٔ git را بازنویسی کرد.
    """
    ignored = _read(".gitignore").lower()
    assert ".env.prod.local" in ignored

    # git در ویندوز شاید نباشد؛ آن‌وقت این guard قابل بررسی نیست
    try:
        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    # `.env.example` عمداً commit شده — قالب بدون رمز است. فقط فایل‌های
    # `.env` واقعی ممنوع‌اند.
    offenders = [
        line
        for line in tracked.splitlines()
        if Path(line).name.startswith(".env") and Path(line).name != ".env.example"
    ]
    assert not offenders, f"env files are tracked in git: {offenders}"


def test_readme_points_to_the_secret_generator() -> None:
    """راهنما باید راه درست ساختن رمز را بگوید، نه کپی‌کردن پیش‌فرض‌ها."""
    readme = _read("README.md")
    assert "make-secrets" in readme, "README does not mention deploy/make-secrets.sh"

    deploy_runbook = _read("docs/runbooks/deploy.md")
    assert "make-secrets" in deploy_runbook, "deploy runbook still tells you to hand-edit .env"


def test_env_example_has_no_values_that_look_real() -> None:
    """`.env.example` باید فقط جای‌خالی یا placeholder داشته باشد.

    یک placeholder که واضحاً غیرقابل استفاده است اشکالی ندارد — ولی
    اگر شبیه رمز واقعی باشد، کسی ممکن است همان را در production بگذارد.
    """
    example = _read(".env.example")
    suspicious = []
    for line in example.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not any(token in key.upper() for token in ("SECRET", "PASSWORD", "PASSPHRASE")):
            continue
        if not value:
            continue
        # هر مقدار غیربالنده باید صریحاً بگوید placeholder است
        if not re.search(r"(?i)change[-_ ]?me|placeholder|example|generate", value):
            suspicious.append(f"{key}={value}")
    assert not suspicious, f".env.example has values that look real: {suspicious}"


def test_backup_runbook_documents_encryption() -> None:
    """runbook باید رمزنگاری و نیاز به passphrase را توضیح دهد."""
    runbook = _read(RUNBOOK).lower()
    assert "backup_passphrase" in runbook
    assert "gpg" in runbook
    assert "verified" in runbook


def test_backup_runbook_never_shows_a_real_password() -> None:
    """مثال دستور نباید رمز واقعی داشته باشد."""
    runbook = _read(RUNBOOK)
    offenders = DB_URL_WITH_PASSWORD.findall(runbook)
    assert not offenders, f"runbook leaks a database password: {offenders}"


