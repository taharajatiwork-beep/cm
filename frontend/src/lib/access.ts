import { isPerformanceUser } from "./navigation";
import { hasExpensePay, hasPriceApprove } from "./permissions";

export type AccessUser = {
  roleCode?: string;
  permissions: string[];
  teamId?: string | null;
  teamHomeTeamId?: string | null;
};

const MARKETING_ROLE_CODES = new Set([
  "marketing_manager",
  "performance_marketing",
  "marketing",
  "designer",
  "filmmaker",
]);

export function isSiteAdmin(user: AccessUser | null | undefined, has: (perm: string) => boolean): boolean {
  return has("org.admin") || user?.roleCode === "admin";
}

export function canSeeCustomers(user: AccessUser | null | undefined, has: (perm: string) => boolean): boolean {
  return isSiteAdmin(user, has);
}

export function canSeeCalendar(user: AccessUser | null | undefined, has: (perm: string) => boolean): boolean {
  if (isSiteAdmin(user, has)) return true;
  if (has("request.triage") || has("request.manage") || has("perf.write")) return true;
  return false;
}

export function canSeeProjects(user: AccessUser | null | undefined, has: (perm: string) => boolean): boolean {
  if (!user) return false;
  if (isSiteAdmin(user, has)) return true;
  if (isPerformanceUser(user) || user.roleCode === "performance_marketing") return false;
  if (isMarketingMemberReadOnly(user)) return false;
  if (has("request.create") || has("request.triage") || has("request.manage")) return true;
  if (has("task.read")) return true;
  return false;
}

export function canSeePricing(user: AccessUser | null | undefined, has: (perm: string) => boolean): boolean {
  if (!user) return false;
  if (isSiteAdmin(user, has)) return true;
  const code = user.roleCode ?? "";
  if (code === "finance") return false;
  if (code === "lead" && hasPriceApprove(has) && !MARKETING_ROLE_CODES.has(code)) return false;
  if (code === "requester" || code === "manager") return true;
  if (MARKETING_ROLE_CODES.has(code)) return true;
  return false;
}

export function isMarketingManager(user: AccessUser | null | undefined): boolean {
  return user?.roleCode === "marketing_manager";
}

export function isMarketingMemberReadOnly(user: AccessUser | null | undefined): boolean {
  if (!user?.roleCode) return false;
  return ["marketing", "designer", "filmmaker"].includes(user.roleCode);
}

export function marketingHomePath(user: AccessUser | null | undefined): string | null {
  const teamId = user?.teamHomeTeamId ?? user?.teamId;
  return teamId ? `/teams/${teamId}` : null;
}

export function canSeeMarketingHome(user: AccessUser | null | undefined): boolean {
  if (!user) return false;
  if (isMarketingManager(user) || isPerformanceUser(user) || isMarketingMemberReadOnly(user)) {
    return Boolean(marketingHomePath(user));
  }
  return false;
}

/** منوی پرفورمنس: مسیر مشخص برای هر نقش. */
export function canSeeNavPath(
  path: string,
  user: AccessUser | null | undefined,
  has: (perm: string) => boolean,
): boolean {
  if (path === "/calendar") return canSeeCalendar(user, has);
  if (path === "/reports") return true;
  if (path === "/people") return has("user.read") || isSiteAdmin(user, has);
  if (path === "/knowledge") return has("kb.read") || isSiteAdmin(user, has);
  if (path === "/customers") return canSeeCustomers(user, has);
  if (path === "/pricing") return canSeePricing(user, has);

  const marketingHome = marketingHomePath(user);
  if (marketingHome && path === marketingHome) {
    return canSeeMarketingHome(user);
  }

  if (path === "/requests") {
    return has("request.triage") || has("request.manage") || has("request.create") || isSiteAdmin(user, has);
  }
  if (path === "/projects") return canSeeProjects(user, has);

  if (!path.startsWith("/perf")) {
    if (path === "/vehicles") return has("inventory.read");
    if (path === "/communication") return has("conversation.read");
    if (path === "/admin") return has("org.admin");
    if (path === "/" || path === "/my-work") return true;
    return true;
  }

  if (isSiteAdmin(user, has)) {
    return has("perf.read") || has("perf.write") || has("perf.approve") || hasPriceApprove(has);
  }

  if (isMarketingManager(user)) {
    return (
      path === "/calendar" ||
      path === "/perf/campaigns" ||
      path.startsWith("/perf/campaigns/") ||
      path === "/perf/sheet"
    );
  }

  if (isMarketingMemberReadOnly(user)) {
    return false;
  }

  if (user?.roleCode === "finance" || (user?.roleCode === "lead" && hasExpensePay(has) && !has("request.triage"))) {
    return path === "/perf/money";
  }

  if (isPerformanceUser(user) || user?.roleCode === "performance_marketing") {
    if (path === "/perf/money" && !has("perf.write") && !has("expense.request")) return false;
    return (
      path === "/perf" ||
      path === "/perf/campaigns" ||
      path.startsWith("/perf/campaigns/") ||
      path === "/perf/sms" ||
      path === "/perf/social" ||
      path === "/perf/sheet" ||
      path === "/perf/money"
    );
  }

  if (has("perf.read") || has("perf.write") || has("perf.approve")) {
    return path === "/perf/campaigns" || path.startsWith("/perf/campaigns/");
  }

  return false;
}
