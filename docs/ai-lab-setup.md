# آزمایشگاه AI (Grok / Cursor Automation)

## فعال‌سازی سریع

1. Migration: `alembic upgrade head` (جدول `ai_tasks` + ستون `last_polled_at`).
2. در `.env` ریشهٔ پروژه (یا `secrets/ai-lab.env` را در سرور merge کن):

```env
AI_LAB_ENABLED=true
AI_LAB_MODE=webhook
LLM_EXTERNAL_ENABLED=true
AI_LAB_OUTBOUND_URL=https://api2.cursor.sh/automations/webhook/<your-webhook-id>
AI_LAB_OUTBOUND_BEARER=<Cursor automation bearer — secrets/ai-lab.env>
AI_LAB_OUTBOUND_SECRET=<shared with automation if verifying CM signature>
AI_LAB_INBOUND_SECRET=<same in Cursor secret AI_LAB_INBOUND_SECRET>
```

3. در **Cursor Automation → Secrets**: `AI_LAB_INBOUND_SECRET` = همان مقدار CM.

## تحویل نتیجه: GitHub (پیشنهادی)

Grok نتیجه را در ریپوی خصوصی می‌نویسد؛ CM با polling می‌خواند — **بدون** نیاز به `callback_url` یا tunnel عمومی.

```env
AI_LAB_RESULT_SOURCE=github
AI_LAB_GITHUB_REPO=taharajatiwork-beep/cm-ai-lab-results
AI_LAB_GITHUB_TOKEN_RO=<read-only PAT — فقط در .env سرور، commit نکن>
```

- مسیر فایل: `results/{task_id}.json`
- فرمت: `{"task_id","timestamp","signature","body"}` — `body` رشتهٔ JSON همان قرارداد callback است.
- امضا: `sha256=` + hex(HMAC-SHA256(`AI_LAB_INBOUND_SECRET`, `str(timestamp) + "." + body`))
- Worker تعبیه‌شده هر ~۶۰ ثانیه کارهای `waiting` را با backoff چک می‌کند (۱/۵/۱۵ دقیقه؛ بعد از ۲ ساعت `timeout`).
- UI: وضعیت `waiting`، زمان آخرین چک، دکمه **چک الان**؛ در `failed`/`timeout` paste دستی.

Instruction اتوماسیون: تحلیل مارکتینگ فارسی + commit/push فایل نتیجه در ریپو (نه POST به CM).

### Fallback: callback HTTPS

اگر `AI_LAB_RESULT_SOURCE=callback` (پیش‌فرض):

```env
AI_LAB_CALLBACK_BASE=https://YOUR_PUBLIC_HOST/api
```

Instruction: POST نتیجه به `callback_url` با `X-Grok-Timestamp` / `X-Grok-Signature`.

Endpoint `POST /ai-lab/results` و paste دستی در `/ai-lab` همیشه به‌عنوان پشتیبان می‌مانند.

## سرور داخلی (مثلاً `192.168.17.4`)

با **GitHub polling** نیازی به expose کردن API به اینترنت برای نتیجه نیست.

برای حالت callback، `AI_LAB_CALLBACK_BASE` باید **HTTPS عمومی** باشد — Quick Tunnel یا Cloudflare Tunnel؛ جزئیات قبلی در [`deploy/cloudflared/config.example.yml`](../deploy/cloudflared/config.example.yml).

## تست

```bash
cd backend
pytest tests/test_ai_lab.py tests/test_ai_lab_github.py -q
```

پنل: `/ai-lab` → تحلیل جدید → با GitHub: `waiting` سپس `done`؛ با callback: `sent` سپس `done`.

## قابلیت‌های بعدی (پیش‌فرض خاموش)

```env
AI_LAB_FOLLOWUP_DAYS=14
AI_LAB_WEEKLY_ENABLED=false
AI_LAB_WEEKLY_WEEKDAY=5
AI_LAB_SCHEDULE_USER_EMAIL=you@company.com
AI_LAB_ANOMALY_ENABLED=false
AI_LAB_ANOMALY_CPL_RATIO=1.5
```

- **حافظه:** فیلد `history` در `snapshot` — آخرین تحلیل‌ها و تصمیم‌ها.
- **پیشنهاد → کار:** `POST .../recommendations/{id}/to-task` و دکمه در UI.
- **سنجش نتیجه:** baseline هنگام قبول؛ worker روزانه followup.
- **sms_copy_review:** نوع تحلیل جدید برای متن پیامک‌ها.
- **هفتگی / هشدار:** worker روزانه؛ نیاز به `AI_LAB_SCHEDULE_USER_EMAIL`.

## قرارداد JSON

ورودی CM به automation: `task_id`, `kind`, `input`, `snapshot`, `created_at` (+ `callback_url` فقط در حالت callback). `snapshot.history` اختیاری است.

خروجی automation (داخل `body` یا callback): `task_id`, `status` (`done`|`failed`), `result` با `summary`, `findings[]` (هر کدام `evidence` اجباری), `recommendations[]` با `id` یکتا.

جزئیات: [`backend/app/ai_lab/schemas.py`](../backend/app/ai_lab/schemas.py). طرح polling: [`docs/ai-lab-github-polling.md`](ai-lab-github-polling.md).

## Worker (polling و زمان‌بندی)

- **Development:** با `WORKER_MODE=embedded` (پیش‌فرض)، همان پروسهٔ API حلقه‌های پس‌زمینه را اجرا می‌کند (شامل `ai_lab_github_poll` وقتی `AI_LAB_RESULT_SOURCE=github`).
- **Production:** `assert_production_safe` انتظار `WORKER_MODE=external` دارد — یک پروسهٔ جدا با `uv run python -m app.worker` (یا اسکریپت deploy شما) باید worker را نگه دارد؛ API فقط HTTP.
- سرور داخلی (`192.168.17.4`) اگر `APP_ENV` production نیست، embedded معمولاً OK است؛ اگر production است، worker جدا را مستند کنید و فقط یک نمونه leader (Redis یا DB lock) داشته باشید.

## پاک‌سازی ریپوی نتایج

توکن `AI_LAB_GITHUB_TOKEN_RO` فقط خواندن دارد. برای حذف فایل‌های قدیمی `results/*.json` نمونه workflow: [`docs/ai-lab-results-cleanup.example.yml`](ai-lab-results-cleanup.example.yml).
