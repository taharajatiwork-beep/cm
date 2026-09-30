"""تکرار bootstrap+login بدون Playwright برای جدا کردن ریشهٔ خطای
«Organization not found»: آیا مشکل از سمت سرور/DB است یا از لایهٔ تست؟

مسیرها عمداً بدون پیشوند `/api` هستند چون این اسکریپت مستقیم بک‌اند را
هدف می‌گیرد و پراکسی Vite (که `/api` را حذف می‌کند) در مسیر نیست.

اجرا: python -m scripts.probe_e2e_login
"""
import asyncio
import sqlite3
import time

import httpx

BASE = "http://127.0.0.1:8011"
DB = "e2e.db"
N = 50


async def main() -> None:
    fails = 0
    conn = sqlite3.connect(DB)
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as c:
        for i in range(N):
            slug = f"probe{time.time_ns()}{i}"
            email = f"boss-{slug}@example.com"
            payload = {
                "organization_name": "E2E",
                "organization_slug": slug,
                "admin_email": email,
                "admin_name": "Boss",
                "admin_password": "password",
            }
            boot = await c.post("/auth/bootstrap", json=payload)
            if not boot.is_success:
                print(f"[{i}] bootstrap {boot.status_code}: {boot.text[:200]}")
                fails += 1
                continue
            login = await c.post(
                "/auth/login",
                json={
                    "organization_slug": slug,
                    "email": email,
                    "password": "password",
                },
            )
            if not login.is_success:
                fails += 1
                # WAL: دادهٔ commit‌شده ممکن است هنوز در فایل `-wal` باشد و
                # اتصال دوم آن را نبیند. checkpoint می‌زنیم تا واقعیت را ببینیم.
                conn.commit()
                found = conn.execute(
                    "select count(*) from organizations where slug = ?", (slug,)
                ).fetchone()[0]
                print(f"[{i}] login {login.status_code}  sent={slug!r}  org_rows={found}")
                if fails >= 4:
                    break
    print(f"probe done: {N - fails} ok, {fails} failed")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    asyncio.run(main())
