# آزمایشگاه AI (Grok / Cursor Automation)

## فعال‌سازی سریع

1. Migration: `alembic upgrade head` (جدول `ai_tasks`).
2. در `.env` ریشهٔ پروژه (یا `secrets/ai-lab.env` را در سرور merge کن):

```env
AI_LAB_ENABLED=true
AI_LAB_MODE=webhook
LLM_EXTERNAL_ENABLED=true
AI_LAB_OUTBOUND_URL=https://api2.cursor.sh/automations/webhook/<your-webhook-id>
AI_LAB_OUTBOUND_BEARER=<Cursor automation bearer — secrets/ai-lab.env>
AI_LAB_OUTBOUND_SECRET=<shared with automation if verifying CM signature>
AI_LAB_INBOUND_SECRET=<same in Cursor secret AI_LAB_INBOUND_SECRET>
# Production HTTPS API (nginx strips /api prefix):
AI_LAB_CALLBACK_BASE=https://YOUR_PUBLIC_HOST/api
```

3. در **Cursor Automation → Secrets**: `AI_LAB_INBOUND_SECRET` = همان مقدار CM.

4. Instruction اتوماسیون: تحلیل مارکتینگ فارسی + POST نتیجه به `callback_url` با `X-Grok-Timestamp` / `X-Grok-Signature` (HMAC روی `timestamp + "." + body`).

## سرور داخلی (مثلاً `192.168.17.4`)

Cursor از اینترنت به `http://192.168.x.x` **نمی‌رسد**. برای webhook کامل یکی لازم است:

- دامنهٔ عمومی + HTTPS روی nginx (`docker-compose.prod.yml`) و `AI_LAB_CALLBACK_BASE=https://host/api`, یا
- موقت: Cloudflare Tunnel / ngrok به پورت API و همان URL در `AI_LAB_CALLBACK_BASE`.

تا callback عمومی نباشد، CM کار را به Cursor می‌فرستد (`sent`) ولی جواب خودکار نمی‌آید — از **manual paste** در `/ai-lab` استفاده کن.

## تست

```bash
docker compose run --rm -v $(pwd)/backend:/app api pytest tests/test_ai_lab.py -q
```

پنل: `/ai-lab` → تحلیل جدید → بعد از webhook باید وضعیت `sent` سپس `done` شود.

## قرارداد JSON

ورودی CM به automation: `task_id`, `kind`, `input`, `snapshot`, `callback_url`, `created_at`.

خروجی automation به CM: `task_id`, `status` (`done`|`failed`), `result` با `summary`, `findings[]` (هر کدام `evidence` اجباری), `recommendations[]` با `id` یکتا.

جزئیات: [`backend/app/ai_lab/schemas.py`](../backend/app/ai_lab/schemas.py).
