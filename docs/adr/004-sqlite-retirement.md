# ADR 004: حذف SQLite به‌عنوان دیتابیس اپ

**وضعیت:** پذیرفته و اجرا شده  
**تاریخ:** ۱۴۰۵/۰۷/۲۱

## مسئله

CI و تولید روی Postgres بودند؛ dev و pytest هنوز `sqlite+aiosqlite` داشتند. قفل‌ها، Uuid، و seed دمو بین دو موتور فرق می‌کردند — مثلاً API لوکال روی `cm_dev.db` بالا می‌آمد در حالی که `seed_demo` به Postgres می‌نوشت.

## تصمیم

Postgres اجباری است برای API، pytest، e2e و loadtest.

- پیش‌فرض `DATABASE_URL`: `postgresql+asyncpg://cm:cm@localhost:5432/cm`
- تست‌ها: `cm_test` (دموی `autoco` روی `cm` پاک نمی‌شود)
- e2e: `cm_e2e`

خواندن فایل‌های dump قدیمی (مثل import تاریخچهٔ کمپین از `.db` خارجی) جدا است و دیتابیس اپ نیست.

## معیار

- بدون `aiosqlite` در وابستگی‌ها
- `assert_postgres_url` در boot
- `docker compose` برای Postgres لوکال
