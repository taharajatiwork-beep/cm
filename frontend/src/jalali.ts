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

/** Accepts Date | ISO string | epoch ms; returns null for empty/invalid input. */
function toDate(value: unknown): Date | null {
  if (value == null || value === "") return null;
  const d = value instanceof Date ? value : new Date(String(value));
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

/** "1405/03/21" — Persian (Jalali) calendar date. */
export function formatJalali(value: unknown): string | null {
  const d = toDate(value);
  if (!d) return null;
  const [y, m, day] = gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate());
  return `${String(y).padStart(4, "0")}/${String(m).padStart(2, "0")}/${String(day).padStart(2, "0")}`;
}

/** "21 خرداد 1405" — long Persian date, used where space allows. */
export function formatJalaliLong(value: unknown): string | null {
  const d = toDate(value);
  if (!d) return null;
  const [y, m, day] = gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate());
  return `${day} ${PERSIAN_MONTHS[m - 1]} ${y}`;
}

/** "21 خرداد" — short Persian date (day + month, no year), for tight rows. */
export function formatJalaliShort(value: unknown): string | null {
  const d = toDate(value);
  if (!d) return null;
  const [y, m, day] = gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate());
  void y;
  return `${day} ${PERSIAN_MONTHS[m - 1]}`;
}

/** "1405/03/21 14:30" — Persian date plus local time. */
export function formatJalaliDateTime(value: unknown): string | null {
  const d = toDate(value);
  if (!d) return null;
  const date = formatJalali(d);
  const time = d.toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit" });
  return `${date} ${time}`;
}

/**
 * Locale-aware date string: Persian calendar under `fa`, Gregorian under `en`.
 * `fallback` keeps the original Gregorian rendering for empty/invalid input.
 */
export function formatDateForLocale(
  value: unknown,
  locale: string,
  fallback: string = "",
): string {
  if (locale !== "fa") {
    const d = toDate(value);
    return d ? d.toLocaleDateString() : fallback;
  }
  return formatJalali(value) ?? fallback;
}
