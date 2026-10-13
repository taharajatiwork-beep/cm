# Synthetic users — اهداف و معیارها

جزئیات فنی: [`frontend/synthetic/README.md`](../frontend/synthetic/README.md).

## هدف

قبل از تست با انسان واقعی، نقش‌های دمو مسیرهای روزمره را در UI طی کنند و گزارش فارسی (اصطکاک، SUS کوتاه، پیشنهاد) تولید شود.

## پرسوناها (۱۳ سناریو)

| پرسونا | ایمیل | سناریوها |
|--------|-------|----------|
| علی (requester) | ali@autoco.example | `requester-home-requests` |
| رضا (seller) | reza@autoco.example | `seller-my-work`, `seller-vehicles` |
| مینا (marketing_manager) | mina@autoco.example | `marketing-manager-projects`, `marketing-manager-triage-queue`, `marketing-manager-calendar` |
| سارا (marketing) | sara@autoco.example | `marketing-pricing` |
| نادیا (performance) | nadia@autoco.example | `performance-campaigns`, `performance-sheet` |
| مالی | finance@autoco.example | `finance-money` |
| گزارش‌گیر | reporter@autoco.example | `reporter-reports` |
| مریم (مشهد) | maryam@autoco.example | `mashhad-requester-requests` |
| ادمین | admin@autoco.example | `admin-organization` |

رمز: `password` — سازمان: `autoco` (`uv run python -m scripts.seed_demo`).

## معیار فیدبک

- **mission_result:** completed / partial / failed
- **severity:** blocker / major / minor (با URL یا نام منو)
- **sus_short:** وضوح، سهولت، اطمینان (۱–۵)

## LLM (اختیاری)

| متغیر | کار |
|--------|-----|
| `SYNTHETIC_AGENT=1` | کاوش بعد از گام‌های ثابت |
| `SYNTHETIC_INTERVIEW=1` | سه سؤال follow-up در گزارش |
| `OPENAI_API_KEY` | debrief + agent + interview |

بدون کلید: فقط scripted + گزارش rule-based.

## محدودیت داده

طبق [llm-data-audit.md](llm-data-audit.md): فقط متن UI و لاگ مسیر به LLM.

## ریتم تیم

1. `npm run synthetic -- --all` قبل از release UI بزرگ
2. خواندن `synthesis.md` در همان پوشه run
3. هر **blocker** → یک کاربر واقعی همان سناریو را تأیید کند
4. CI: `npm run synthetic:ci` روی هر PR (scripted، mock LLM)
