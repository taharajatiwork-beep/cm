# AI Lab — تحویل نتیجه از GitHub (polling)

## هدف

Grok نتیجه را در ریپوی خصوصی `results/{task_id}.json` می‌نویسد. CM به‌جای callback عمومی، فایل را از GitHub API می‌خواند. ارسال کار به automation (`AI_LAB_OUTBOUND_URL`) بدون تغییر می‌ماند.

## جریان

1. کاربر «تحلیل جدید» → snapshot + `POST /ai-lab/tasks`.
2. در `AI_LAB_MODE=webhook`، CM همان payload قبلی را به automation می‌فرستد (**بدون `callback_url`** وقتی `AI_LAB_RESULT_SOURCE=github`).
3. وضعیت: `pending` → `waiting` (پس از ارسال موفق).
4. Worker پس‌زمینه (همان `app.worker.Worker` در embedded mode) با leader lock `ai_lab_github_poll` کارهای `waiting` را poll می‌کند.
5. `GET .../repos/{repo}/contents/results/{task_id}.json` با `Accept: application/vnd.github.raw`.
6. اعتبارسنجی envelope → اعمال نتیجه (idempotent) → `done` یا `failed`.
7. Fallback: `POST /ai-lab/results` (callback) و `manual-result` (paste) بدون تغییر رفتار.

## زمان‌بندی poll

از `created_at` (یا `sent_at`):

| سن کار | فاصلهٔ poll بعدی |
|--------|------------------|
| ۰–۵ دقیقه | ۶۰ ثانیه |
| ۵–۳۰ دقیقه | ۵ دقیقه |
| ۳۰ دقیقه–۲ ساعت | ۱۵ دقیقه |
| بعد از ۲ ساعت | `failed` + `error=timeout`؛ UI paste دستی |

`last_polled_at` روی هر task ذخیره می‌شود. خطای ۵xx/شبکه: retry در دور بعد، task را fail نکن.

## اعتبارسنجی envelope

```json
{"task_id":"uuid","timestamp":"...","signature":"sha256=...","body":"{...}"}
```

- `signature` = `sha256=` + hex(HMAC-SHA256(`AI_LAB_INBOUND_SECRET`, `str(timestamp) + "." + body`))
- `body` رشتهٔ JSON است؛ بعد از امضا، `json.loads(body)` و validator `BotCallbackIn`.
- `task_id` داخل body باید با task یکی باشد.
- امضای بد → `failed` + `invalid signature`.

## تنظیمات (.env)

```env
AI_LAB_RESULT_SOURCE=github   # callback | github
AI_LAB_GITHUB_REPO=owner/repo
AI_LAB_GITHUB_TOKEN_RO=ghp_...   # فقط read contents — در git نگذار
```

## قدم‌های پیاده‌سازی

| # | کار | تست |
|---|-----|-----|
| 1 | این سند | — |
| 2 | config + migration `last_polled_at` | migration unit |
| 3 | `polling.py` + `github_results.py` + signing GitHub | unit |
| 4 | refactor service + routes + worker loop + `POST .../poll` | pytest mock GitHub |
| 5 | UI `/ai-lab` (waiting، last check، چک الان) | — |
| 6 | `docs/ai-lab-setup.md` + `.env.example` | — |

## تست

فقط pytest با DB تست (SQLite/Postgres تست) — **بدون دیتابیس production**.
