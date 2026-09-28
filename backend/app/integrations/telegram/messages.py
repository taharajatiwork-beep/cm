"""Plain bilingual bot copy — keep in sync with web UX vocabulary."""

from __future__ import annotations


def t(fa: str, en: str, *, lang: str = "fa") -> str:
    return fa if lang != "en" else en


BOT_COMMANDS = [
    {"command": "start", "description": "اتصال / خوش‌آمد"},
    {"command": "kar", "description": "کارهای باز من"},
    {"command": "payam", "description": "منتظر جواب من"},
    {"command": "khodro", "description": "جستجوی خودرو"},
    {"command": "unlink", "description": "قطع اتصال"},
    {"command": "help", "description": "راهنما"},
]


def welcome_unlinked(*, lang: str = "fa") -> str:
    return t(
        "سلام! برای اتصال حساب، از «تنظیمات» در سایت دکمهٔ «اتصال تلگرام» را بزنید.\n"
        "یا کد را اینجا بفرستید: /link کد",
        "Hi! Open Settings in the web app and tap “Connect Telegram”.\n"
        "Or send: /link <code>",
        lang=lang,
    )


def linked_ok(name: str, *, lang: str = "fa") -> str:
    return t(
        f"متصل شدید، سلام {name}.\nاز این به بعد اعلان‌های کار اینجا می‌آید. /help",
        f"Linked. Hello {name}.\nWork notifications will arrive here. /help",
        lang=lang,
    )


def already_linked(*, lang: str = "fa") -> str:
    return t(
        "حساب شما قبلاً متصل است. /kar برای دیدن کارها.",
        "Your account is already linked. /kar to see your to-dos.",
        lang=lang,
    )


def link_invalid(*, lang: str = "fa") -> str:
    return t(
        "کد نامعتبر یا منقضی است. از سایت یک کد تازه بگیرید.",
        "Invalid or expired code. Get a fresh one from the web app.",
        lang=lang,
    )


def link_usage(*, lang: str = "fa") -> str:
    return t("نحوه استفاده: /link کد", "Usage: /link <code>", lang=lang)


def not_linked(*, lang: str = "fa") -> str:
    return t(
        "تلگرام شما متصل نیست. از تنظیمات سایت «اتصال تلگرام» را بزنید.",
        "Telegram is not linked. Use “Connect Telegram” in Settings.",
        lang=lang,
    )


def help_text(*, lang: str = "fa") -> str:
    return t(
        "فرمان‌ها:\n"
        "/kar — کارهای باز من\n"
        "/payam — منتظر جواب من\n"
        "/khodro متن — جستجوی خودرو\n"
        "/unlink — قطع اتصال\n\n"
        "یا بنویسید چه کسی چه کند، مثلاً:\n"
        "برای این کمری، رضا مشتری را پیگیری کند و سارا تبلیغات را انجام بدهد.\n"
        "سؤال آزاد هم می‌توانید بپرسید.",
        "Commands:\n"
        "/kar — my open to-dos\n"
        "/payam — waiting for my reply\n"
        "/khodro <query> — find a car\n"
        "/unlink — disconnect\n\n"
        "Or write who should do what, e.g.:\n"
        "For this Camry, Reza follows up customers and Sara does marketing.\n"
        "You can also ask free questions.",
        lang=lang,
    )


def text_only(*, lang: str = "fa") -> str:
    return t(
        "فعلاً فقط پیام متنی پشتیبانی می‌شود.",
        "Only text messages are supported for now.",
        lang=lang,
    )


def unlinked_ok(*, lang: str = "fa") -> str:
    return t("اتصال قطع شد.", "Disconnected.", lang=lang)


def no_open_tasks(*, lang: str = "fa") -> str:
    return t("کار بازی ندارید. عالی!", "No open to-dos. Nice!", lang=lang)


def no_waiting_messages(*, lang: str = "fa") -> str:
    return t("کسی منتظر جواب شما نیست.", "No one is waiting for your reply.", lang=lang)


def task_done_ok(*, lang: str = "fa") -> str:
    return t("ثبت شد ✓ انجام شد", "Done ✓", lang=lang)


def task_done_fail(reason: str, *, lang: str = "fa") -> str:
    return t(f"نتوانست ثبت شود: {reason}", f"Could not complete: {reason}", lang=lang)


def no_permission(*, lang: str = "fa") -> str:
    return t("اجازه این کار را ندارید.", "You do not have permission for this.", lang=lang)


def project_created(title: str, lines: list[str], *, lang: str = "fa") -> str:
    head = t(f"پروژه ساخته شد\n{title}", f"Project created\n{title}", lang=lang)
    return head + "\n\n" + "\n".join(lines)


def confirm_create_preview(title: str, lines: list[str], *, lang: str = "fa") -> str:
    head = t(
        f"این پروژه را بسازم؟\n{title}",
        f"Create this project?\n{title}",
        lang=lang,
    )
    return head + "\n\n" + "\n".join(lines)


def confirm_cancelled(*, lang: str = "fa") -> str:
    return t("لغو شد.", "Cancelled.", lang=lang)


def stored_only(*, lang: str = "fa") -> str:
    return t(
        "پیام ذخیره شد. برای تقسیم کار، نام افراد و خودرو را بنویسید، یا سؤال بپرسید.",
        "Message stored. To split work, name people and a vehicle, or ask a question.",
        lang=lang,
    )


def need_vehicle(*, lang: str = "fa") -> str:
    return t(
        "افراد را فهمیدم، ولی خودرو مشخص نیست. مدل یا شماره انبار را بنویسید (مثلاً کمری #124).",
        "I understood the people, but not the vehicle. Include model or stock # (e.g. Camry #124).",
        lang=lang,
    )


def notify_task_assigned(title: str, *, lang: str = "fa") -> str:
    return t(f"کار جدید برای شما:\n{title}", f"New to-do for you:\n{title}", lang=lang)


def notify_task_done(title: str, *, lang: str = "fa") -> str:
    return t(f"کار انجام شد:\n{title}", f"To-do finished:\n{title}", lang=lang)


def notify_message(topic: str, preview: str, sender: str, *, lang: str = "fa") -> str:
    return t(
        f"پیام جدید در «{topic}»\n{sender}: {preview}",
        f"New message in “{topic}”\n{sender}: {preview}",
        lang=lang,
    )


def notify_sla(title: str, late: bool, *, lang: str = "fa") -> str:
    if late:
        return t(f"مهلت گذشت:\n{title}", f"Deadline passed:\n{title}", lang=lang)
    return t(f"مهلت نزدیک است:\n{title}", f"Deadline is close:\n{title}", lang=lang)


def notify_branch(subject: str, *, lang: str = "fa") -> str:
    return t(
        f"درخواست شعبه منتظر شماست:\n{subject}",
        f"Branch request waiting for you:\n{subject}",
        lang=lang,
    )


def digest_text(open_n: int, late_n: int, waiting_n: int, *, lang: str = "fa") -> str:
    return t(
        f"صبح بخیر.\nامروز {open_n} کار دارید، {late_n} دیر شده، {waiting_n} نفر منتظر جواب شما هستند.",
        f"Good morning.\nToday: {open_n} to-dos, {late_n} late, {waiting_n} waiting for your reply.",
        lang=lang,
    )


def btn_done(*, lang: str = "fa") -> str:
    return t("انجام شد", "Done", lang=lang)


def btn_open(*, lang: str = "fa") -> str:
    return t("باز کردن", "Open", lang=lang)


def btn_hand_over(*, lang: str = "fa") -> str:
    return t("نمی‌توانم", "Can't do it", lang=lang)


def btn_reply(*, lang: str = "fa") -> str:
    return t("جواب بده", "Reply", lang=lang)


def btn_confirm(*, lang: str = "fa") -> str:
    return t("بساز", "Create", lang=lang)


def btn_cancel(*, lang: str = "fa") -> str:
    return t("لغو", "Cancel", lang=lang)


def btn_show(*, lang: str = "fa") -> str:
    return t("نشان بده", "Show", lang=lang)


def btn_approve(*, lang: str = "fa") -> str:
    return t("تأیید", "Approve", lang=lang)


def btn_reject(*, lang: str = "fa") -> str:
    return t("رد", "Reject", lang=lang)


def notify_approval(title: str, *, lang: str = "fa") -> str:
    return t(
        f"درخواست تأیید جدید:\n{title}\nبا دکمه‌های زیر پاسخ دهید.",
        f"New approval request:\n{title}\nRespond with the buttons below.",
        lang=lang,
    )


def approval_not_approver(*, lang: str = "fa") -> str:
    return t(
        "شما تأییدکنندهٔ این مرحله نیستید",
        "You are not the approver of this step.",
        lang=lang,
    )


def approval_not_found(*, lang: str = "fa") -> str:
    return t("درخواست تأیید پیدا نشد.", "Approval request not found.", lang=lang)


def approval_already_decided(*, lang: str = "fa") -> str:
    return t("این درخواست قبلاً تصمیم گرفته شده است.", "This request was already decided.", lang=lang)


def approval_step_recorded(final: bool, *, lang: str = "fa") -> str:
    if final:
        return t("تأیید نهایی شد ✓", "Approved ✓", lang=lang)
    return t("تأیید ثبت شد — مرحلهٔ بعدی منتظر تأیید است.", "Recorded — next step is waiting for approval.", lang=lang)


def approval_rejected(*, lang: str = "fa") -> str:
    return t("رد شد ✗", "Rejected ✗", lang=lang)


def rate_limited(*, lang: str = "fa") -> str:
    return t(
        "کمی صبر کنید و دوباره بپرسید.",
        "Please wait a moment and try again.",
        lang=lang,
    )


def hand_over_hint(*, lang: str = "fa") -> str:
    return t(
        "برای ارجاع، در سایت پروژه را باز کنید و کار را به فرد دیگری بسپارید.",
        "To hand over, open the project on the web and reassign the to-do.",
        lang=lang,
    )
