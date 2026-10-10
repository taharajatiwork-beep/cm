import { describe, expect, it } from "vitest";
import { faDigits, faNum, faText, splitLatin, toman, tomanText } from "./fa";

describe("fa", () => {
  it("prints prices in toman with Persian digits", () => {
    expect(toman(12500000)).toBe("۱۲٬۵۰۰٬۰۰۰");
    expect(tomanText(12500000)).toBe("۱۲٬۵۰۰٬۰۰۰ تومان");
    expect(toman(null)).toBe("—");
    expect(tomanText(undefined)).toBe("—");
  });

  it("keeps Persian digits and groups thousands", () => {
    expect(faNum(1500)).toBe("۱٬۵۰۰");
    expect(faDigits("1405/01/01")).toBe("۱۴۰۵/۰۱/۰۱");
    expect(faDigits("۱۴۰۵")).toBe("۱۴۰۵");
  });

  it("turns loose digits Persian but keeps codes and ids readable", () => {
    expect(faText("S84: 2 انتشار بدون عدد اینسایت")).toBe("S84: ۲ انتشار بدون عدد اینسایت");
    expect(faText("3 پرداخت منتظر تأیید")).toBe("۳ پرداخت منتظر تأیید");
    expect(faText("کد K1-1 و U85")).toBe("کد K1-1 و U85");
    expect(faText("تماس 021-47677777")).toBe("تماس ۰۲۱-۴۷۶۷۷۷۷۷");
    expect(faText("")).toBe("");
    expect(faText(null)).toBe("");
  });

  it("splits Latin tokens out of Persian text", () => {
    expect(splitLatin("کد S84: 2 مورد")).toEqual([
      { latin: false, text: "کد " },
      { latin: true, text: "S84" },
      { latin: false, text: ": 2 مورد" },
    ]);
  });
});
