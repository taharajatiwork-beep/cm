"""کشف مسیرهای رسمی API پیشگامان از روی swagger. فقط خواندن؛ توکن چاپ نمی‌شود."""

import re

import httpx

from app.core.config import get_settings


def main() -> None:
    s = get_settings()
    base = s.pishgam_sms_api_url.rstrip("/")
    r = httpx.get(f"{base}/swagger/index.html", timeout=15)
    m = re.search(r"""url:\s*['"]([^'"]+)['"]""", r.text)
    spec = m.group(1) if m else "not-found"
    print("spec url:", spec)
    if not spec.startswith("http"):
        spec = f"{base}/{spec.lstrip('/')}"
    r2 = httpx.get(spec, timeout=15)
    print("spec status:", r2.status_code)
    try:
        data = r2.json()
    except ValueError:
        yaml_like = r2.text[:600]
        print("spec not json; head:", yaml_like)
        return
    for path, methods in sorted((data.get("paths") or {}).items()):
        verbs = [v for v in (methods or {}) if v in ("get", "post", "put", "delete", "patch")]
        print(path, verbs)


main()