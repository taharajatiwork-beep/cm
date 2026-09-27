/** Map API / runtime errors to user-facing copy */
export function friendlyError(raw: string): { en: string; fa: string } {
  const s = raw.toLowerCase();
  if (s.includes("403") || s.includes("not authorized") || s.includes("missing permission")) {
    return {
      en: "You don’t have permission for this action. Ask your manager if you need access.",
      fa: "شما اجازه انجام این کار را ندارید. در صورت نیاز با مدیر سیستم تماس بگیرید.",
    };
  }
  if (s.includes("401") || s.includes("invalid credentials")) {
    return {
      en: "Email or password is incorrect.",
      fa: "ایمیل یا رمز عبور نادرست است.",
    };
  }
  if (s.includes("not found")) {
    return {
      en: "We couldn’t find that item. It may have been removed.",
      fa: "این مورد پیدا نشد. ممکن است حذف شده باشد.",
    };
  }
  if (s.includes("network") || s.includes("failed to fetch")) {
    return {
      en: "Couldn’t reach the server. Check your connection and try again.",
      fa: "به سرور وصل نشدیم. اتصال اینترنت را بررسی کنید و دوباره تلاش کنید.",
    };
  }
  return { en: raw, fa: raw };
}
