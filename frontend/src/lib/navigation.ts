/** مبدأ ریدایرکت بعد از ورود — state که Protected در React Router می‌گذارد. */
export type LoginFrom = {
  pathname?: string;
  search?: string;
  hash?: string;
} | null;

/**
 * مقصد بعد از ورود: صفحه‌ای که کاربر از آن به /login پرت شده (لینک مستقیم،
 * رفرش صفحه، انقضای نشست) وگرنه خانه. مبدأهای خودِ لاگین/خانه طرد می‌شوند تا
 * حلقهٔ ریدایرکت نسازیم.
 */
export function loginRedirectTarget(from: LoginFrom | undefined): string {
  if (!from || !from.pathname || from.pathname === "/" || from.pathname === "/login") {
    return "/";
  }
  return `${from.pathname}${from.search ?? ""}${from.hash ?? ""}`;
}

type PerfUserLike = { roleCode?: string; permissions: string[] } | null | undefined;

/**
 * کاربر پرفورمنس: نقش performance_marketing، یا کسی که دسترسی نوشتن پرفورمنس دارد
 * ولی مدیر/تأییدکنندهٔ پرفورمنس یا ادمین نیست (مثل کاربر نمایشی نادیا که نقشش «سرپرست»
 * در تیم پرفورمنس است و perf.write جداگانه گرفته). نقش و دیتابیس دست نمی‌خورد.
 */
export function isPerformanceUser(user: PerfUserLike): boolean {
  if (!user) return false;
  if (user.roleCode === "performance_marketing") return true;
  const perms = user.permissions ?? [];
  return perms.includes("perf.write") && !perms.includes("perf.approve") && !perms.includes("org.admin");
}

