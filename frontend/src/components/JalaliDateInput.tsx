import { useState } from "react";
import { Input } from "./ui";
import { jalaliToGregorian, parseJalaliText } from "../jalali";

/** ورودی تاریخ شمسی. مقدار خروجی برای API میلادی `YYYY-MM-DD` است. */
export function JalaliDateInput({ onChange }: { value?: string; onChange: (isoDate: string) => void }) {
  const [text, setText] = useState("");
  return (
    <Input
      value={text}
      placeholder="۱۴۰۵/۰۷/۱۹"
      inputMode="numeric"
      onChange={(event) => {
        const next = event.target.value;
        setText(next);
        onChange(jalaliTextToIso(next) || "");
      }}
    />
  );
}

export function jalaliTextToIso(text: string): string | null {
  const parsed = parseJalaliText(text);
  if (!parsed?.year) return null;
  const [gy, gm, gd] = jalaliToGregorian(parsed.year, parsed.month, parsed.day);
  return `${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`;
}
