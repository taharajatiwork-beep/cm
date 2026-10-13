import { describe, expect, it } from "vitest";
import { gregorianToJalali, jalaliToGregorian } from "../jalali";
import { jalaliTextToIso } from "./JalaliDateInput";

describe("JalaliDateInput", () => {
  it("round-trips a known day", () => {
    const [jy, jm, jd] = gregorianToJalali(2026, 10, 11);
    const [gy, gm, gd] = jalaliToGregorian(jy, jm, jd);
    expect([gy, gm, gd]).toEqual([2026, 10, 11]);
  });

  it("turns a slash date into an ISO day", () => {
    const [jy, jm, jd] = gregorianToJalali(2026, 10, 11);
    const iso = jalaliTextToIso(`${jy}/${jm}/${jd}`);
    expect(iso).toBe("2026-10-11");
  });
});
