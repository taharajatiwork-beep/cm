import { faDigits } from "./fa";

export function gregorianToJalali(gy: number, gm: number, gd: number): [number, number, number] {
  const gDays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  const jDays = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29];
  gy -= 1600;
  gm -= 1;
  gd -= 1;
  let gDayNo = 365 * gy + Math.floor((gy + 3) / 4) - Math.floor((gy + 99) / 100) + Math.floor((gy + 399) / 400);
  for (let i = 0; i < gm; i++) gDayNo += gDays[i];
  if (gm > 1 && (gy + 1600) % 4 === 0 && ((gy + 1600) % 100 !== 0 || (gy + 1600) % 400 === 0)) gDayNo += 1;
  gDayNo += gd;
  let jDayNo = gDayNo - 79;
  const jNp = Math.floor(jDayNo / 12053);
  jDayNo %= 12053;
  let jy = 979 + 33 * jNp + 4 * Math.floor(jDayNo / 1461);
  jDayNo %= 1461;
  if (jDayNo >= 366) {
    jy += Math.floor((jDayNo - 1) / 365);
    jDayNo = (jDayNo - 1) % 365;
  }
  let jm = 12;
  for (let i = 0; i < 11; i++) {
    if (jDayNo < jDays[i]) {
      jm = i + 1;
      break;
    }
    jDayNo -= jDays[i];
  }
  return [jy, jm, jDayNo + 1];
}

const PERSIAN_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
];

/** نام ماه در شیت‌ها گاهی بی‌مد یا با غلط تایپی نوشته شده؛ این‌ها هم شناخته می‌شوند. */
const MONTH_ALIASES: Record<string, number> = {
  ابان: 8,
  اذر: 9,
  شهرویر: 6,
  اردیبهست: 2,
};

function monthNumber(name: string): number | null {
  const clean = name.replace(/ي/g, "ی").replace(/ك/g, "ک").replace(/\u200c/g, "").trim();
  const exact = PERSIAN_MONTHS.indexOf(clean);
  if (exact >= 0) return exact + 1;
  return MONTH_ALIASES[clean] ?? null;
}

function enDigits(text: string): string {
  return text
    .replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)));
}

function validDay(month: number, day: number): boolean {
  if (month < 1 || month > 12 || day < 1) return false;
  return day <= (month <= 6 ? 31 : 30);
}

/**
 * تاریخ متنی شیت‌ها: «31 شهریور»، «4فروردین»، «20 اسفند 1404»، «1405/07/13».
 * سال اگر در متن نباشد `null` است — حدس زده نمی‌شود تا سال اشتباه نشان داده نشود.
 */
export function parseJalaliText(text: unknown): { year: number | null; month: number; day: number } | null {
  if (typeof text !== "string") return null;
  const value = enDigits(text).replace(/\s+/g, " ").trim();
  if (!value) return null;
  const numeric = /^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$/.exec(value);
  if (numeric) {
    const [year, month, day] = numeric.slice(1).map(Number);
    if (year < 1300 || year > 1500 || !validDay(month, day)) return null;
    return { year, month, day };
  }
  const named = /^(\d{1,2}) ?([^\d\s]+)(?: (\d{4}))?$/.exec(value);
  if (!named) return null;
  const day = Number(named[1]);
  const month = monthNumber(named[2]);
  const year = named[3] ? Number(named[3]) : null;
  if (!month || !validDay(month, day)) return null;
  if (year !== null && (year < 1300 || year > 1500)) return null;
  return { year, month, day };
}

/**
 * نمایش یکدست تاریخ متنی شیت به شکل «۳۱ شهریور ۱۴۰۴» (بی‌سال: «۳۱ شهریور»).
 * متنی که خوانده نشود همان‌طور ولی با رقم فارسی برمی‌گردد.
 */
export function formatJalaliText(text: unknown): string {
  if (typeof text !== "string" || !text.trim()) return "";
  const parts = parseJalaliText(text);
  if (!parts) return faDigits(text.trim());
  const base = `${parts.day} ${PERSIAN_MONTHS[parts.month - 1]}`;
  return faDigits(parts.year ? `${base} ${parts.year}` : base);
}

/** Accepts Date | ISO string | epoch ms; returns null for empty/invalid input. */
function toDate(value: unknown): Date | null {
  if (value == null || value === "") return null;
  const d = value instanceof Date ? value : new Date(String(value));
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

/**
 * Some sheet dates are already Jalali, stored as `1405-06-10`.
 * `new Date` reads that year as Gregorian and the conversion goes negative.
 * Years 1200–1600 in this shape are Jalali; real Gregorian rows in this app are 1900+.
 */
function alreadyJalali(value: unknown): { year: number; month: number; day: number } | null {
  if (typeof value !== "string") return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value.trim());
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (year < 1200 || year > 1600 || month < 1 || month > 12 || day < 1 || day > 31) return null;
  return { year, month, day };
}

function jalaliParts(value: unknown): [number, number, number] | null {
  const ready = alreadyJalali(value);
  if (ready) return [ready.year, ready.month, ready.day];
  const d = toDate(value);
  if (!d) return null;
  return gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate());
}

/** «۱۴۰۵/۰۳/۲۱» — تاریخ شمسی با رقم فارسی. */
export function formatJalali(value: unknown): string | null {
  const parts = jalaliParts(value);
  if (!parts) return null;
  const [y, m, day] = parts;
  return faDigits(`${String(y).padStart(4, "0")}/${String(m).padStart(2, "0")}/${String(day).padStart(2, "0")}`);
}

/** "21 خرداد 1405" — long Persian date, used where space allows. */
export function formatJalaliLong(value: unknown): string | null {
  const parts = jalaliParts(value);
  if (!parts) return null;
  const [y, m, day] = parts;
  return faDigits(`${day} ${PERSIAN_MONTHS[m - 1]} ${y}`);
}

/** "21 خرداد" — short Persian date (day + month, no year), for tight rows. */
export function formatJalaliShort(value: unknown): string | null {
  const parts = jalaliParts(value);
  if (!parts) return null;
  const [, m, day] = parts;
  return faDigits(`${day} ${PERSIAN_MONTHS[m - 1]}`);
}

/** «۱۴۰۵/۰۳/۲۱ ۱۴:۳۰» — تاریخ شمسی به‌علاوهٔ ساعت ۲۴ساعته، هر دو با رقم فارسی.
 *
 * ساعت دستی ساخته می‌شود تا نشانگر AM/PM در متن راست‌به‌چپ جابه‌جا نشود. */
export function formatJalaliDateTime(value: unknown): string | null {
  const d = toDate(value);
  if (!d) return null;
  const date = formatJalali(d);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return faDigits(`${date} ${hh}:${mm}`);
}

/** تاریخ همیشه شمسی است. زبان رابط تقویم را عوض نمی‌کند. */
export function formatDateForLocale(
  value: unknown,
  _locale?: string,
  fallback: string = "",
): string {
  return formatJalali(value) ?? fallback;
}
