# ADR 005: حذف alias `price.write`

## وضعیت

پذیرفته — حذف در **۱ تیر ۱۴۰۵ (۲۰۲۶-۰۶-۲۱)**

## زمینه

`price.write` هر دو توانایی **تأیید قیمت** (`price.approve`) و **پرداخت هزینه** (`expense.pay`) را می‌داد و جداسازی وظایف مالی را دور می‌زد. از migration `0032_finance_split` نقش `finance` و seed فقط `price.approve` + `expense.pay` می‌گیرند.

## تصمیم

1. تا تاریخ بالا، کد `finance_perms` و مسیرهای legacy هنوز `price.write` را به‌عنوان fallback می‌پذیرند (سازگاری با دادهٔ قدیمی).
2. seed دمو، قالب نقش‌ها و نقش `admin` (bootstrap) **هرگز** `price.write` نمی‌گیرند — `admin_role_permission_codes()` (`tests/test_price_write_sunset.py`).
3. بعد از تاریخ sunset، fallback از `has_price_approve` / `has_expense_pay` و `require_*` حذف می‌شود؛ اعلان‌ها و pricing فقط `price.approve` / `expense.pay` را می‌بینند.

## پیامد

تست CI هر بار seed را چک می‌کند. نقش‌های سفارشی تولید که هنوز `price.write` دارند باید قبل از sunset به دو مجوز جدا مهاجرت کنند.
