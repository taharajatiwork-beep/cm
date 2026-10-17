export const WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];

export const TIERS = [
  { value: "long", label: "بلندمدت", tone: "ok" as const },
  { value: "mid", label: "میان‌مدت", tone: "" as const },
  { value: "short", label: "کوتاه‌مدت", tone: "warn" as const },
  { value: "reactive", label: "واکنشی", tone: "danger" as const },
];

export const STATUSES = [
  { value: "todo", label: "برنامه‌ریزی" },
  { value: "doing", label: "در جریان" },
  { value: "done", label: "انجام شد" },
];

export const PRODUCTION_STATUSES = [
  { value: "idea", label: "ایده" },
  { value: "draft", label: "پیش‌نویس" },
  { value: "design", label: "طراحی" },
  { value: "review", label: "بازبینی" },
  { value: "approved", label: "تأیید" },
  { value: "published", label: "منتشر" },
];

export const LAYER_OPTIONS = [
  { key: "content", label: "محتوا", color: "content" },
  { key: "event", label: "رویداد", color: "event" },
  { key: "work", label: "کار", color: "work" },
  { key: "mizito", label: "میزیتو", color: "mizito" },
  { key: "marketing", label: "مارکتینگ", color: "marketing" },
  { key: "holiday", label: "تعطیل", color: "holiday" },
];

export const VIEW_OPTIONS = [
  { key: "month", label: "ماه" },
  { key: "week", label: "هفته" },
  { key: "day", label: "روز" },
  { key: "agenda", label: "برنامه" },
  { key: "board", label: "بورد محتوا" },
  { key: "table", label: "جدول" },
] as const;

export type CalendarViewKey = (typeof VIEW_OPTIONS)[number]["key"];

export const WORK_KINDS = new Set(["task", "work", "project", "request", "mizito"]);
export const MARKETING_KINDS = new Set(["campaign", "sms", "story"]);
export const DONE = new Set(["done", "COMPLETED", "CANCELLED", "sent"]);
