/** یک پیام یا درخواست را به ورودی ساخت کمپین پرفورمنس تبدیل می‌کند. */

const BRANDS: Array<[RegExp, string]> = [
  [/فونیکس|تیگو|ام\s?وی\s?ام|mvm/i, "فونیکس"],
  [/ماموت|فولکس|تیگوان/i, "ماموت"],
  [/لاماری/i, "لاماری"],
  [/کرمان/i, "کرمان موتور"],
  [/هیوندای|توسان/i, "هیوندای"],
];

export function campaignFromText(text: string) {
  const raw = text.replace(/\s+/g, " ").trim();
  const sms = /پیامک|اس ام اس|sms/i.test(raw);
  const social = /استوری|پست|بنر|سوشال|اینستا/.test(raw);
  let channels = ["sms", "ig_story"];
  if (sms && !social) channels = ["sms"];
  if (social && !sms) channels = ["ig_story"];
  const brand = BRANDS.find(([pattern]) => pattern.test(raw))?.[1] ?? "";
  return {
    title: raw.slice(0, 80) || "کمپین از پیام",
    brand,
    goal: raw,
    channels,
    status: "active",
  };
}
