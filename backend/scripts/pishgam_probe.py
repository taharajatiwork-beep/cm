"""پروب زندهٔ پیشگامان: اعتبار و خطوط. فقط خواندن؛ توکن چاپ نمی‌شود."""

import json

import httpx

from app.core.config import get_settings


def main() -> None:
    s = get_settings()
    base = s.pishgam_sms_api_url.rstrip("/")
    token = s.pishgam_sms_token.strip()
    headers = {"Authorization": f"Bearer {token}"}

    r = httpx.get(f"{base}/Messages/GetCredit", headers=headers, timeout=20)
    print("credit status:", r.status_code)
    print("credit body:", r.text[:500])

    r2 = httpx.get(f"{base}/Messages/PrivateNumberList", headers=headers, timeout=20)
    print("lines status:", r2.status_code)
    print("lines body:", r2.text[:800])


main()