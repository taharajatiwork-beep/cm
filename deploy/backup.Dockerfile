# image پشتیبان‌گیری: postgres:16-alpine به‌همراه gnupg
#
# `deploy/backup.sh` برای رمزنگاری symmetric به gpg نیاز دارد و ایمیج
# رسمی postgres آن را ندارد. بدون این لایه، سرویس backup در تولید
# با «gpg: not found» از کار می‌افتد.
FROM postgres:16-alpine

# gnupg  : رمزنگاری و تأیید dump
# postgresql-client : در پایهٔ ایمیج هست ولی صریح می‌آوریم تا به آن تکیه نکنیم
RUN apk add --no-cache gnupg postgresql-client \
 && gpg --version | head -1
