/** گروه فوکوس UI — از کد نقش در دیتابیس، نه از مجوز. */
export type FocusRole = "admin" | "manager" | "seller" | "marketing" | "finance" | "viewer";

export function focusRoleFromCode(roleCode?: string | null): FocusRole {
  if (!roleCode) return "viewer";
  if (roleCode === "admin") return "admin";
  if (roleCode === "finance") return "finance";
  if (roleCode === "seller") return "seller";
  if (
    roleCode === "marketing" ||
    roleCode === "marketing_manager" ||
    roleCode === "performance_marketing" ||
    roleCode === "designer" ||
    roleCode === "filmmaker"
  ) {
    return "marketing";
  }
  if (roleCode === "manager" || roleCode === "requester" || roleCode === "lead") return "manager";
  return "viewer";
}

/** برچسب نقش، هم‌نام با حساب‌های نمایشی autoco. */
const ROLE_TITLES: Record<string, string> = {
  admin: "ادمین سایت",
  requester: "مدیر",
  lead: "سرپرست",
  member: "عضو",
  marketing_manager: "سرپرست مارکتینگ",
  performance_marketing: "پرفورمنس مارکتینگ",
  viewer: "بازدیدکننده",
  manager: "مدیر شعبه",
  seller: "فروشنده",
  marketing: "مارکتینگ",
  finance: "مالی",
  designer: "طراح",
  filmmaker: "فیلم‌بردار",
};

export function roleTitle(roleCode: string | undefined, branchName?: string | null): string {
  if (roleCode === "requester" && branchName?.includes("مشهد")) return "مدیر شعبه مشهد";
  if (roleCode && ROLE_TITLES[roleCode]) return ROLE_TITLES[roleCode];
  return roleCode || "";
}
