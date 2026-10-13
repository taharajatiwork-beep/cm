# Synthetic users (CM)

شبیه‌سازی کاربر با Playwright + (اختیاری) LLM برای **فیدبک UX**.

## پیش‌نیاز

`npm run synthetic` به **همان API پشت `npm run dev`** وصل می‌شود (Postgres). `npm run synthetic:ci` دیتابیس جدا (`cm_synthetic`) می‌سازد.

```bash
cd backend
uv run alembic upgrade head
uv run python -m scripts.seed_demo

cd ../frontend
npm run dev
```

## اجرا

```bash
npm run synthetic -- --list          # ۱۳ سناریو
npm run synthetic -- --scenario requester-home-requests
npm run synthetic -- --all           # + synthesis.md خودکار
npm run synthetic:aggregate -- synthetic/reports/<run-folder>
```

| Env | معنی |
|-----|------|
| `SYNTHETIC_BASE_URL` | پیش‌فرض `http://127.0.0.1:5173` |
| `SYNTHETIC_HEADED=1` | مرورگر با UI |
| `SYNTHETIC_MOCK_LLM=1` | بدون API (پیش‌فرض بدون کلید) |
| `SYNTHETIC_AGENT=1` | عامل LLM بعد از scripted |
| `SYNTHETIC_INTERVIEW=1` | مصاحبهٔ ۳ سؤالی در گزارش |
| `OPENAI_API_KEY` / `SYNTHETIC_LLM_API_KEY` | debrief و agent |

## CI

```bash
npm run synthetic:ci
```

در GitHub Actions بعد از e2e اجرا می‌شود (DB جدا + seed_demo).

## خروجی

`reports/<timestamp>/<scenario>/report.md` · `report.json` · اسکرین‌شات‌ها

مستند اهداف: [`docs/synthetic-users-goals.md`](../../docs/synthetic-users-goals.md).
