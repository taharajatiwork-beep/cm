/**
 * برچسب فارسی enumهای بک‌اند — برای اینکه هیچ رشتهٔ خام انگلیسی در UI دیده نشود.
 * کلیدها با مقادیر واقعی `backend/app/models/enums.py` هم‌خوان‌اند.
 */

export const CASE_STATUS_LABELS: Record<string, string> = {
  OPEN: "باز",
  ASSIGNED: "ارجاع‌شده",
  IN_PROGRESS: "در حال انجام",
  WAITING_FOR_RESPONSE: "در انتظار پاسخ",
  WAITING_FOR_USER: "در انتظار کاربر",
  COMPLETED: "انجام‌شده",
  CANCELLED: "لغو‌شده",
  ESCALATED: "ارجاع‌شده به بالا",
};

export const PRIORITY_LABELS: Record<string, string> = {
  LOW: "کم",
  MEDIUM: "متوسط",
  HIGH: "زیاد",
  URGENT: "فوری",
};

export const SLA_STATE_LABELS: Record<string, string> = {
  NONE: "بدون SLA",
  ACTIVE: "فعال",
  WARNING: "هشدار",
  BREACHED: "نقض‌شده",
  ESCALATED: "ارجاع به سطح بالا",
};

export const CASE_TYPE_LABELS: Record<string, string> = {
  GENERAL_OPERATIONAL_REQUEST: "درخواست عملیاتی",
  BRANCH_REQUEST: "درخواست شعبه",
  BUYER_REQUEST: "درخواست خریدار",
  SELLER_REQUEST: "درخواست فروشنده",
  FOLLOW_UP: "پیگیری",
  INVENTORY_OPPORTUNITY: "فرصت موجودی",
  CUSTOMER_INTEREST: "علاقهٔ مشتری",
  TRANSFER: "انتقال",
  ESCALATION: "ارجاع به بالا",
};

/** رویدادهای تایم‌لاین پرونده — کلید کامل «<object>.<action>» و بخش object. */
const EVENT_TYPE_LABELS: Record<string, string> = {
  "case.created": "پرونده ساخته شد",
  "case.assigned": "پرونده ارجاع شد",
  "case.status_changed": "وضعیت پرونده تغییر کرد",
  "case.priority_changed": "اولویت پرونده تغییر کرد",
  "case.note_added": "یادداشت ثبت شد",
  "case.completed": "پرونده انجام شد",
  "case.cancelled": "پرونده لغو شد",
  "case.escalated": "پرونده به سطح بالا ارجاع شد",
  "case.sla_warning": "هشدار مهلت پرونده",
  "case.sla_breached": "مهلت پرونده نقض شد",
  "comment.added": "دیدگاه ثبت شد",
  "approval.created": "درخواست تأیید ساخته شد",
  "approval.approved": "تأیید شد",
  "approval.rejected": "رد شد",
};

function eventLabel(eventType: string): string {
  if (EVENT_TYPE_LABELS[eventType]) return EVENT_TYPE_LABELS[eventType];
  // پشتیبانی از کلیدهای ناشناخته: بخش‌ها را با نقطه جدا کن و زیرخط‌ها را فاصله بگذار
  const [object, action] = eventType.split(".");
  if (object && action) {
    return `${object} · ${action.replace(/_/g, " ")}`;
  }
  return eventType;
}

export type Tone = "" | "ok" | "warn" | "danger";

/** برچسب وضعیت پرونده + رنگ Badge. */
export function caseStatusLabel(status: unknown): { label: string; tone: Tone } {
  const key = String(status ?? "").toUpperCase();
  const label = CASE_STATUS_LABELS[key] ?? (key ? humanize(key) : "—");
  const tone: Tone =
    key === "COMPLETED" ? "ok"
    : key === "CANCELLED" ? ""
    : key === "ESCALATED" || key === "WAITING_FOR_USER" ? "danger"
    : key === "WAITING_FOR_RESPONSE" ? "warn"
    : "";
  return { label, tone };
}

export function priorityLabel(priority: unknown): { label: string; tone: Tone } {
  const key = String(priority ?? "").toUpperCase();
  const label = PRIORITY_LABELS[key] ?? (key ? humanize(key) : "—");
  const tone: Tone =
    key === "URGENT" ? "danger" : key === "HIGH" ? "warn" : "";
  return { label, tone };
}

export function slaStateLabel(state: unknown): { label: string; tone: Tone } {
  const key = String(state ?? "").toUpperCase();
  const label = SLA_STATE_LABELS[key] ?? (key ? humanize(key) : "—");
  const tone: Tone =
    key === "BREACHED" || key === "ESCALATED" ? "danger"
    : key === "WARNING" ? "warn"
    : key === "ACTIVE" ? "ok"
    : "";
  return { label, tone };
}

export function caseTypeLabel(type: unknown): string {
  const key = String(type ?? "").toUpperCase();
  return CASE_TYPE_LABELS[key] ?? (key ? humanize(key) : "—");
}

export function eventTypeLabel(eventType: unknown): string {
  const key = String(eventType ?? "");
  return key ? eventLabel(key) : "رویداد";
}

/** تبدیل CONSTANT_CASE به متن قابل‌خواندن وقتی ترجمه‌ای موجود نیست. */
function humanize(key: string): string {
  return key.toLowerCase().replace(/_/g, " ");
}
