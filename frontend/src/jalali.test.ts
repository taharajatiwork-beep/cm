import { describe, expect, it } from "vitest";
import {
  formatDateForLocale,
  formatJalali,
  formatJalaliLong,
  formatJalaliShort,
  gregorianToJalali,
} from "./jalali";

describe("jalali", () => {
  it("maps 2026-03-21 into 1405", () => {
    expect(gregorianToJalali(2026, 3, 21)[0]).toBe(1405);
  });

  it("formats 2026-03-21 as the first day of Farvardin 1405", () => {
    expect(formatJalali("2026-03-21")).toBe("1405/01/01");
  });

  it("pads month and day", () => {
    expect(formatJalali("2026-06-08")).toBe("1405/03/18");
  });

  it("returns null for empty or invalid input", () => {
    expect(formatJalali("")).toBeNull();
    expect(formatJalali(null)).toBeNull();
    expect(formatJalali("not a date")).toBeNull();
  });

  it("renders the long Persian date with month names", () => {
    expect(formatJalaliLong("2026-03-21")).toBe("1 فروردین 1405");
    expect(formatJalaliShort("2026-03-21")).toBe("1 فروردین");
  });

  it("keeps Gregorian under the English locale, Jalali under Persian", () => {
    expect(formatDateForLocale("2026-03-21", "fa")).toBe("1405/01/01");
    expect(formatDateForLocale("2026-03-21", "en", "—")).toContain("2026");
    expect(formatDateForLocale("bad", "fa", "—")).toBe("—");
  });
});
