/**
 * قالب ثابت نمایش در CM:
 * قیمت همیشه تومان است (نه ریال)، تاریخ همیشه شمسی است، رقم همیشه فارسی است.
 * زبان رابط (فارسی/انگلیسی) این سه را عوض نمی‌کند.
 */

const DIGITS = "۰۱۲۳۴۵۶۷۸۹";

/** رقم‌های انگلیسی داخل متن را فارسی می‌کند. رقم فارسی دست‌نخورده می‌ماند. */
export function faDigits(text: string): string {
  return text.replace(/\d/g, (digit) => DIGITS[Number(digit)] ?? digit);
}

/**
 * تکه‌های لاتین داخل متن فارسی: کد کمپین (S84، K1-1)، شناسه، آدرس و هر چیزی که حرف لاتین دارد.
 * رقم‌های این تکه‌ها دست‌نخورده می‌مانند تا کد خوانا بماند.
 */
const LATIN_TOKEN = /[A-Za-z0-9_.\-/@]*[A-Za-z][A-Za-z0-9_.\-/@]*/g;

/** متن را به تکه‌های «لاتین» و «فارسی» می‌شکند؛ برای `FaText` و `faText`. */
export function splitLatin(text: string): Array<{ latin: boolean; text: string }> {
  const parts: Array<{ latin: boolean; text: string }> = [];
  let last = 0;
  for (const match of text.matchAll(LATIN_TOKEN)) {
    const at = match.index ?? 0;
    if (at > last) parts.push({ latin: false, text: text.slice(last, at) });
    parts.push({ latin: true, text: match[0] });
    last = at + match[0].length;
  }
  if (last < text.length) parts.push({ latin: false, text: text.slice(last) });
  return parts;
}

/**
 * متن آمادهٔ نمایش از سرور («S84: 2 انتشار…»): رقم‌های جدا فارسی می‌شوند،
 * ولی رقم‌های داخل کد و شناسهٔ لاتین (S84) همان‌طور می‌مانند.
 */
export function faText(text: string | null | undefined): string {
  if (!text) return "";
  return splitLatin(text)
    .map((part) => (part.latin ? part.text : faDigits(part.text)))
    .join("");
}

/** عدد با جداکنندهٔ هزارگان و رقم فارسی. */
export function faNum(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("fa-IR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  }).format(Number(value));
}

/** مبلغ به تومان، بدون واحد. واحد را با `tomanText` بچسبانید. */
export function toman(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return faNum(Math.round(Number(value)));
}

/** «۱۲٬۵۰۰٬۰۰۰ تومان». ورودی خالی خط تیره است. */
export function tomanText(value: number | null | undefined): string {
  const amount = toman(value);
  return amount === "—" ? amount : `${amount} تومان`;
}
