import { describe, expect, it } from "vitest";
import { formatDeadline, isOverdue } from "./collaboration";

const bi = (en: string, fa: string) => fa;

describe("formatDeadline", () => {
  it("renders a 24-hour clock with no AM/PM in either locale", () => {
    // 2026-09-29T15:04:00Z — اگر ساعت ۱۵ باشد، AM/PM یعنی ۳ بعدازظهر
    const at = "2026-09-29T15:04:00";
    for (const locale of ["en", "fa"] as const) {
      const out = formatDeadline(at, bi, locale) ?? "";
      expect(out, `locale=${locale}`).not.toMatch(/AM|PM/i);
      expect(out, `locale=${locale}`).toMatch(/\d{2}:\d{2}/);
    }
  });

  it("zero-pads hours below 10", () => {
    const out = formatDeadline("2026-09-29T05:07:00", bi, "fa") ?? "";
    expect(out).toMatch(/05:07/);
  });

  it("uses the Jalali date under the Persian locale", () => {
    // نه برای «امروز» — شاخهٔ sameDay تاریخ ندارد و فقط ساعت را نشان می‌دهد
    const out = formatDeadline("2999-12-30T15:04:00", bi, "fa") ?? "";
    expect(out).toMatch(/\d{4}\/\d{2}\/\d{2}/);
  });

  it("shows only the time for something due today", () => {
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}T15:04:00`;
    const out = formatDeadline(today, bi, "fa") ?? "";
    expect(out).not.toMatch(/\d{4}\/\d{2}\/\d{2}/);
    expect(out).toMatch(/15:04/);
  });

  it("returns null for missing or unparsable values", () => {
    expect(formatDeadline(null, bi, "fa")).toBeNull();
    expect(formatDeadline("not-a-date", bi, "fa")).toBeNull();
  });
});

describe("isOverdue", () => {
  it("ignores finished work", () => {
    expect(isOverdue("2020-01-01", "COMPLETED")).toBe(false);
    expect(isOverdue("2020-01-01", "CANCELLED")).toBe(false);
  });

  it("flags a past deadline on open work", () => {
    expect(isOverdue("2020-01-01", "OPEN")).toBe(true);
  });

  it("leaves a future deadline alone", () => {
    expect(isOverdue("2999-01-01", "OPEN")).toBe(false);
  });
});
