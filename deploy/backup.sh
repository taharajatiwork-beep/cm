#!/bin/sh
# پشتیبان‌گیری دیتابیس با رمزنگاری و تأیید خودکار.
#
# رمز دیتابیس از محیط می‌آید (DATABASE_URL) — هیچ رمزی در این فایل نیست.
# اگر BACKUP_PASSPHRASE تنظیم شده باشد dump با GPG رمزنگاری می‌شود؛
# بدون آن، اسکریپت عمداً خطا می‌دهد تا بی‌سروصدا بی‌رمز ذخیره نکند.
set -eu

dir="${BACKUP_DIR:-backups}"
mkdir -p "$dir"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is not set — refusing to guess credentials" >&2
  exit 1
fi

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  echo "BACKUP_PASSPHRASE is not set — refusing to write an unencrypted dump" >&2
  exit 1
fi

stamp=$(date +%Y%m%d-%H%M%S)
plain="${dir}/cm-${stamp}.dump"
out="${plain}.gpg"

# gpg فقط برای رمزنگاری symmetric لازم است (بدون کلید عمومی).
# --batch و --pinentry-mode لازم‌اند تا در محیط غیرتعاملی گیر نکند.
# اگر رمزنگاری شکست بخورد، فایل خام حتماً پاک می‌شود — نباید دادهٔ
# مشتری به‌صورت بی‌رمز روی دیسک بماند.
if ! gpg --batch --yes --pinentry-mode loopback --passphrase "$BACKUP_PASSPHRASE" \
         --symmetric --cipher-algo AES256 --output "$out" "$plain"; then
  rm -f "$plain"
  echo "encryption failed — plaintext dump removed" >&2
  exit 1
fi

# تأیید: فایل رمزنگاری‌شده باید واقعاً قابل باز کردن باشد.
# بدون این مرحله یک dump خراب یا ناقص ماه‌ها بی‌سروصدا باقی می‌ماند.
if ! gpg --batch --quiet --pinentry-mode loopback \
         --passphrase "$BACKUP_PASSPHRASE" \
         --decrypt "$out" > "${plain}.verify" 2>/dev/null; then
  rm -f "$plain" "$out" "${plain}.verify"
  echo "verification failed for ${out} — dump removed" >&2
  exit 1
fi

# dump بازیابی‌شده باید یک آرشیو pg_dump معتبر باشد.
if ! pg_restore --list "${plain}.verify" >/dev/null 2>&1; then
  rm -f "$plain" "$out" "${plain}.verify"
  echo "verification failed: ${plain}.verify is not a valid pg_dump archive" >&2
  exit 1
fi

# فایل موقت بازیابی‌شده شامل دادهٔ خام است و نباید باقی بماند.
rm -f "$plain"

# فایل‌های قدیمی را از روی فایل رمزنگاری‌شده پاک کن.
find "$dir" -name 'cm-*.dump.gpg' -mtime +"${BACKUP_RETENTION_DAYS:-30}" -delete

echo "wrote ${out} (verified)"
