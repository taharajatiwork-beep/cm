import { describe, expect, it } from "vitest";
import {
  formatDateForLocale,
  formatJalali,
  formatJalaliDateTime,
  formatJalaliLong,
  formatJalaliShort,
  formatJalaliText,
  gregorianToJalali,
  jalaliMonthGrid,
  jalaliMonthLength,
  parseJalaliText,
} from "./jalali";

describe("jalali", () => {
  it("maps 2026-03-21 into 1405", () => {
    expect(gregorianToJalali(2026, 3, 21)[0]).toBe(1405);
  });

  it("formats 2026-03-21 as the first day of Farvardin 1405", () => {
    expect(formatJalali("2026-03-21")).toBe("۱۴۰۵/۰۱/۰۱");
  });

  it("pads month and day", () => {
    expect(formatJalali("2026-06-08")).toBe("۱۴۰۵/۰۳/۱۸");
  });

  it("returns null for empty or invalid input", () => {
    expect(formatJalali("")).toBeNull();
    expect(formatJalali(null)).toBeNull();
    expect(formatJalali("not a date")).toBeNull();
  });

  it("renders the long Persian date with month names", () => {
    expect(formatJalaliLong("2026-03-21")).toBe("۱ فروردین ۱۴۰۵");
    expect(formatJalaliShort("2026-03-21")).toBe("۱ فروردین");
  });

  it("keeps the Shamsi date in both locales", () => {
    expect(formatDateForLocale("2026-03-21", "fa")).toBe("۱۴۰۵/۰۱/۰۱");
    expect(formatDateForLocale("2026-03-21", "en", "—")).toBe("۱۴۰۵/۰۱/۰۱");
    expect(formatDateForLocale("bad", "fa", "—")).toBe("—");
  });

  it("renders 24-hour Shamsi time with Persian digits and no AM/PM", () => {
    const local = new Date(2026, 2, 21, 14, 30);
    const text = formatJalaliDateTime(local);
    expect(text).toBe("۱۴۰۵/۰۱/۰۱ ۱۴:۳۰");
    expect(text).not.toMatch(/AM|PM/i);
  });

  it("reads sheet date text with or without a year", () => {
    expect(parseJalaliText("31 شهریور")).toEqual({ year: null, month: 6, day: 31 });
    expect(parseJalaliText("4فروردین")).toEqual({ year: null, month: 1, day: 4 });
    expect(parseJalaliText("20 اسفند 1404")).toEqual({ year: 1404, month: 12, day: 20 });
    expect(parseJalaliText("۱۳ مهر ۱۴۰۵")).toEqual({ year: 1405, month: 7, day: 13 });
    expect(parseJalaliText("1405/07/13")).toEqual({ year: 1405, month: 7, day: 13 });
    expect(parseJalaliText("12 ابان")).toEqual({ year: null, month: 8, day: 12 });
    expect(parseJalaliText("2 اذر")).toEqual({ year: null, month: 9, day: 2 });
  });

  it("rejects text that is not a Jalali date", () => {
    expect(parseJalaliText("")).toBeNull();
    expect(parseJalaliText("بعداً")).toBeNull();
    expect(parseJalaliText("31 مهر")).toBeNull();
    expect(parseJalaliText("2026-03-21")).toBeNull();
    expect(parseJalaliText(null)).toBeNull();
  });

  it("formats sheet date text one way, with Persian digits", () => {
    expect(formatJalaliText("31 شهریور")).toBe("۳۱ شهریور");
    expect(formatJalaliText("20 اسفند 1404")).toBe("۲۰ اسفند ۱۴۰۴");
    expect(formatJalaliText("1405/07/13")).toBe("۱۳ مهر ۱۴۰۵");
    expect(formatJalaliText("4 ادز")).toBe("۴ ادز");
    expect(formatJalaliText("")).toBe("");
  });

  it("builds Aban 1405 from Saturday, with day 1 on Friday", () => {
    expect(jalaliMonthLength(1405, 8)).toBe(30);
    const weeks = jalaliMonthGrid(1405, 8);
    expect(weeks[0]).toHaveLength(7);
    expect(weeks[0][6]).toMatchObject({ day: 1, inMonth: true, iso: "2026-10-23" });
    expect(weeks.flat().filter((cell) => cell.inMonth)).toHaveLength(30);
    expect(weeks.at(-1)?.find((cell) => cell.day === 30 && cell.inMonth)?.iso).toBe("2026-11-21");
  });

  it("pads the hour and returns null for empty input", () => {
    expect(formatJalaliDateTime(new Date(2026, 2, 21, 9, 5))).toBe("۱۴۰۵/۰۱/۰۱ ۰۹:۰۵");
    expect(formatJalaliDateTime("")).toBeNull();
    expect(formatJalaliDateTime("not a date")).toBeNull();
  });
});
