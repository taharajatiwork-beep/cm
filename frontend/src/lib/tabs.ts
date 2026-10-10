/**
 * تب‌هایی که در URL می‌مانند (?tab=). مقدار نامعتبر یا خالی یعنی تب پیش‌فرض،
 * و تب پیش‌فرض اصلاً در URL نوشته نمی‌شود تا لینک ساده بماند.
 */
export function tabFromParam<K extends string>(value: string | null | undefined, keys: readonly K[], fallback: K): K {
  return value && (keys as readonly string[]).includes(value) ? (value as K) : fallback;
}

/** پارامترهای دیگر URL دست نمی‌خورند؛ فقط tab عوض یا برای تب پیش‌فرض حذف می‌شود. */
export function withTabParam(params: URLSearchParams, tab: string, fallback: string): URLSearchParams {
  const next = new URLSearchParams(params);
  if (tab === fallback) next.delete("tab");
  else next.set("tab", tab);
  return next;
}

/**
 * جابه‌جایی با کیبورد در فهرست تب‌ها (الگوی WAI-ARIA): Home/End و فلش‌ها، چرخشی.
 * در راست‌به‌چپ فلش چپ یعنی تب بعدی. کلید دیگر null برمی‌گرداند.
 */
export function nextTabIndex(current: number, count: number, key: string, rtl: boolean): number | null {
  if (count <= 0) return null;
  let next: number;
  if (key === "Home") next = 0;
  else if (key === "End") next = count - 1;
  else if (key === "ArrowRight") next = current + (rtl ? -1 : 1);
  else if (key === "ArrowLeft") next = current + (rtl ? 1 : -1);
  else return null;
  return ((next % count) + count) % count;
}
