# دادهٔ ارسالی به LLM بیرونی

| مسیر | چه می‌رود | خاموش‌کردن |
|------|-----------|------------|
| بریف کمپین (`/perf/campaigns/{id}/brief/draft`) | عنوان، کد، برند، هدف، تاریخ، بودجه، کانال‌ها | `LLM_EXTERNAL_ENABLED=false` یا `LLM_PROVIDER=rules` |
| خواندن اینسایت (`read_insight_image`) | تصویر base64 اسکرین‌شات استوری | همان + بدون `LLM_API_KEY` |
| دستیار/RAG (`/agent`, hybrid) | متن پرسش + قطعات RAG از SQL/جستجو | `LLM_PROVIDER=rules` |
| embedding | متن ایندکس‌شده (خودرو، SOP) | `EMBEDDING_PROVIDER=hash` |

**نمی‌رود:** شبا، x-token میزیتو، رمز پنل SMS (فقط در DB رمزنگاری‌شده).

مرجع کلید: [adr/003-field-encryption.md](adr/003-field-encryption.md)
