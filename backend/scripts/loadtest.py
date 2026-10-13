"""بار تست سبک برای مسیرهای بحرانی.

هدف: قبل از هر استقرار واقعی بفهمیم کدام endpoint زیر بار واقعی کند می‌شود.
این جایگزین k6 یا locust نیست — کتابخانهٔ استاندارد است، بدون وابستگی
اضافه، و در CI قابل اجرا.

چطور کار می‌کند:
  1. اپلیکیشن واقعی بالا می‌آید (ASGI، بدون سرور و بدون شبکه).
  2. دادهٔ دمو seed می‌شود.
  3. چند کاربر با توکن واقعی وارد می‌شوند.
  4. چند coroutine هم‌زمان endpointهای پرکاربرد را صدا می‌زنند.
  5. صدک ۵۰/۹۵، کندترین درخواست و نرخ خطا گزارش می‌شود.

چرا coroutine و نه thread: هر thread یک event loop خودش می‌سازد و
اشیای loop-وابستهٔ anyio (مثل Queue داخلی Starlette) بین loopها قابل
استفاده نیستند — خطای «bound to a different event loop». یک loop
واحد با N coroutine هم‌زمان، همان هم‌زمانی واقعی را می‌دهد بدون آن
محدودیت.

نکته دربارهٔ مسیرها: FastAPI 0.141 روترها را lazy نگه می‌دارد، پس
``app.routes`` مسیرهای تخت نشان نمی‌دهد. مسیرها از OpenAPI خوانده می‌شوند
که همیشه درست است — و اگر مسیری که این فایل صدا می‌زند وجود نداشته
باشد، تست قبل از اجرا شکست می‌خورد.

اجرا:
    uv run python -m scripts.loadtest
    uv run python -m scripts.loadtest --users 40 --rounds 5
    uv run python -m scripts.loadtest --print-only     # فقط baseline بگیر
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# بودجهٔ هر endpoint بر حسب ms، بر پایهٔ baseline واقعی ۲۰ کاربر هم‌زمان روی
# SQLite فایلی (WAL روشن). login گران است چون bcrypt دارد: p50 حدود ۱.۵ ثانیه
# زیر بار. این اعداد پایدارند و در README هم آمده‌اند.
BUDGETS_MS: dict[str, int] = {
    "health": 400,
    "login": 9000,
    "cases": 2200,
    "case_timeline": 1800,
    "work_items": 1900,
    "conversations": 2400,
    "search": 2700,
}

# مسیرهایی که این ابزار صدا می‌زند. وجودشان در OpenAPI بررسی می‌شود.
REQUIRED_PATHS = (
    "/health",
    "/auth/login",
    "/cases",
    "/cases/{case_id}/timeline",
    "/work-items",
    "/conversations",
    "/search",
)

ORG_SLUG = "autoco"
DEMO_PASSWORD = "password"
# ایمیل‌هایی که seed_demo می‌سازد — نام کاربری نیست، ایمیل است.
DEMO_EMAILS = (
    "ali@autoco.example",
    "sara@autoco.example",
    "reza@autoco.example",
    "maryam@autoco.example",
)


@dataclass
class Stats:
    """زمان‌های پاسخ و خطاهای یک endpoint."""

    name: str
    times: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    statuses: dict[int, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, ms: float, status: int, error: str | None = None) -> None:
        with self.lock:
            self.times.append(ms)
            self.statuses[status] = self.statuses.get(status, 0) + 1
            if error:
                self.errors.append(error)

    def percentile(self, pct: float) -> float:
        if not self.times:
            return 0.0
        ordered = sorted(self.times)
        idx = min(len(ordered) - 1, int(len(ordered) * pct / 100))
        return ordered[idx]

    @property
    def p50(self) -> float:
        return self.percentile(50)

    @property
    def p95(self) -> float:
        return self.percentile(95)

    @property
    def slowest(self) -> float:
        return max(self.times) if self.times else 0.0


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- آماده‌سازی


def prepare_app() -> Any:
    """اپلیکیشن آماده با دادهٔ seedشده.

    محیط دقیقاً مثل conftest ست می‌شود، وگرنه تنظیمات توسعهٔ ماشین
    (مثل TELEGRAM_MODE) وارد تست می‌شود و نتیجه گمراه‌کننده می‌دهد.
    lifespan عمداً اجرا نمی‌شود: worker و outbox برای اندازه‌گیری مسیرها
    لازم نیستند و بالا آوردنشان چند ثانیه به هر اجرا اضافه می‌کند.
    """
    os.environ.setdefault("LLM_PROVIDER", "rules")
    os.environ.setdefault("DIVAR_MODE", "fake")
    os.environ.setdefault("REQUIRE_HUMAN_APPROVAL_FOR_SENSITIVE_AI", "false")
    os.environ["APP_ENV"] = "development"
    os.environ["TELEGRAM_MODE"] = "off"
    os.environ["TELEGRAM_BOT_TOKEN"] = ""
    os.environ["BALE_MODE"] = "off"
    db_url = os.environ.get("LOADTEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "postgresql+asyncpg://cm:cm@localhost:5432/cm"
    if db_url.startswith("sqlite"):
        raise SystemExit("loadtest requires PostgreSQL DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url

    from app.main import app

    # مسیرهایی که این ابزار صدا می‌زند باید واقعاً وجود داشته باشند.
    # مسیرها از OpenAPI خوانده می‌شوند چون app.routes در FastAPI 0.141
    # روترهای lazy را تخت نشان نمی‌دهد.
    spec = app.openapi()
    missing = [p for p in REQUIRED_PATHS if p not in spec["paths"]]
    if missing:
        raise SystemExit(
            f"این مسیرها در اپلیکیشن نیستند: {missing}\n"
            f"اگر عمدی حذف شده‌اند، REQUIRED_PATHS را به‌روز کنید."
        )

    from scripts.seed_demo import seed

    asyncio.run(seed())
    return app


async def login_all(app: Any, emails: tuple[str, ...]) -> list[str]:
    """توکن همهٔ کاربران، داخل همان loopی که درخواست‌ها اجرا می‌شوند.

    TestClient یک loop جدا می‌سازد، پس لاگین را هم باید داخل loop
    اصلی انجام داد — وگرنه همان خطای «different event loop» برمی‌گردد.
    """
    async with _make_client(app) as client:
        tokens: list[str] = []
        for email in emails:
            response = await client.post(
                "/auth/login",
                json={
                    "organization_slug": ORG_SLUG,
                    "email": email,
                    "password": DEMO_PASSWORD,
                },
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"login failed for {email}: {response.status_code} {response.text[:300]}"
                )
            tokens.append(response.json()["access_token"])
        return tokens


async def first_case_id(app: Any, token: str) -> str:
    """شناسهٔ یک پروندهٔ seedشده — یک بار برای کل اجرا کافی است."""
    async with _make_client(app) as client:
        response = await client.get("/cases", params={"limit": 1}, headers=_auth(token))
    body = response.json()
    items = body.get("items") if isinstance(body, dict) else body
    if not items:
        raise RuntimeError("هیچ پرونده‌ای seed نشده — seed_demo را بررسی کنید")
    return str(items[0]["id"])


# ------------------------------------------------------------------ اجرا


def build_endpoints(
    case_id: str,
) -> list[tuple[str, Callable[[Any, str], Any]]]:
    """(نام، تابع) — تابع یک (client, token) می‌گیرد و response برمی‌گرداند."""
    return [
        ("health", lambda c, t: c.get("/health")),
        ("login", lambda c, t: c.post(
            "/auth/login",
            json={
                "organization_slug": ORG_SLUG,
                "email": DEMO_EMAILS[0],
                "password": DEMO_PASSWORD,
            },
        )),
        ("cases", lambda c, t: c.get("/cases", params={"limit": 50}, headers=_auth(t))),
        ("case_timeline", lambda c, t: c.get(
            f"/cases/{case_id}/timeline", headers=_auth(t))),
        ("work_items", lambda c, t: c.get("/work-items", headers=_auth(t))),
        ("conversations", lambda c, t: c.get("/conversations", headers=_auth(t))),
        ("search", lambda c, t: c.get("/search", params={"q": "test"}, headers=_auth(t))),
    ]


def _make_client(app: Any) -> Any:
    """یک ASGI client که داخل همان event loop اجرا می‌شود.

    httpx.AsyncClient مستقیم به اپلیکیشن وصل می‌شود و ASGITransport آن
    را در همان loop اجرا می‌کند — بدون سرور، بدون شبکه، بدون lifespan.
    """
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://loadtest")


async def drive_async(
    app: Any,
    tokens: list[str],
    endpoints: list[tuple[str, Callable[..., Any]]],
    rounds: int,
    users: int,
    verbose: bool,
) -> list[Stats]:
    """همهٔ درخواست‌ها روی یک loop، با N coroutine هم‌زمان."""
    stats = {name: Stats(name) for name, _ in endpoints}

    async def one_user(token: str) -> None:
        async with _make_client(app) as client:
            for _ in range(rounds):
                for name, call in endpoints:
                    start = time.perf_counter()
                    try:
                        response = await call(client, token)
                        ms = (time.perf_counter() - start) * 1000
                        stats[name].record(ms, response.status_code)
                        # ۴xx یا ۵xx یعنی مسیر شکسته یا دسترسی غلط — هر دو خطا
                        if response.status_code >= 400:
                            snippet = response.text[:120].replace("\n", " ")
                            stats[name].errors.append(f"HTTP {response.status_code}: {snippet}")
                    except Exception as exc:  # noqa: BLE001 — هر استثنا یک یافته است
                        ms = (time.perf_counter() - start) * 1000
                        stats[name].record(ms, 0, f"{type(exc).__name__}: {exc}")
                        if verbose:
                            print(f"  {name}: {type(exc).__name__}: {exc}", file=sys.stderr)

    await asyncio.gather(*(one_user(tokens[i % len(tokens)]) for i in range(users)))
    return list(stats.values())


# ---------------------------------------------------------------- گزارش


def report(stats: list[Stats]) -> bool:
    header = (
        f"{'endpoint':<15}{'n':>5}{'p50':>9}{'p95':>9}{'max':>9}{'err':>6}{'budget':>9}   verdict"
    )
    print(header)
    print("-" * len(header))
    ok = True
    for row in stats:
        budget = BUDGETS_MS.get(row.name, 1000)
        slow = row.p95 > budget
        ok = ok and not slow and not row.errors
        if row.errors:
            verdict = f"{len(row.errors)} خطا — {row.errors[0][:58]}"
        elif slow:
            verdict = "SLOW"
        else:
            verdict = "ok"
        print(
            f"{row.name:<15}{len(row.times):>5}{row.p50:>8.0f}m{row.p95:>8.0f}m"
            f"{row.slowest:>8.0f}m{len(row.errors):>6}{budget:>8}m   {verdict}"
        )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="بار تست مسیرهای بحرانی")
    parser.add_argument("--users", type=int, default=8, help="تعداد کاربر هم‌زمان")
    parser.add_argument("--rounds", type=int, default=3, help="دور برای هر کاربر")
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="بودجه‌ها را enforce نکن — برای گرفتن baseline",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    print(f"load test: {args.users} users x {args.rounds} rounds")
    print(f"budgets (ms): {BUDGETS_MS}\n")

    app = prepare_app()

    async def run_all() -> list[Stats]:
        tokens = await login_all(app, DEMO_EMAILS)
        case_id = await first_case_id(app, tokens[0])
        print(f"seeded — {len(tokens)} tokens, case {case_id}\n")
        endpoints = build_endpoints(case_id)
        return await drive_async(app, tokens, endpoints, args.rounds, args.users, args.verbose)

    start = time.perf_counter()
    stats = asyncio.run(run_all())
    elapsed = time.perf_counter() - start

    total = sum(len(row.times) for row in stats)
    print()
    ok = report(stats)
    print(f"\ntotal {total} requests in {elapsed:.1f}s ({total / elapsed:.0f} req/s)")

    if args.print_only:
        print(
            "\n--print-only: بودجه‌ها enforce نشد. مقادیر p95 را مبنای سخت‌تر "
            "کردن بگذارید."
        )
        print(
            json.dumps(
                {r.name: round(r.p95) for r in stats}, ensure_ascii=False, indent=2
            )
        )
        return 0
    if not ok:
        print("\nFAILED: یک endpoint از بودجه‌اش رد شده یا خطا داشته", file=sys.stderr)
        return 1
    print("\nPASSED: همهٔ endpointها داخل بودجه")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
