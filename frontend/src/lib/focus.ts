import {
  canSeeCalendar,
  canSeeMarketingHome,
  canSeePricing,
  canSeeProjects,
  isMarketingManager,
  isMarketingMemberReadOnly,
  marketingHomePath,
} from "./access";
import { isPerformanceUser } from "./navigation";
import { focusRoleFromCode, type FocusRole } from "./roles";

export type { FocusRole };

export type FocusNavUser = {
  roleHint?: FocusRole;
  roleCode?: string;
  permissions: string[];
  teamId?: string | null;
  teamHomeTeamId?: string | null;
};

function navFocus(user: FocusNavUser): FocusRole {
  return user.roleHint ?? focusRoleFromCode(user.roleCode);
}

const DAILY_LIMIT = 6;

export function focusCan(user: FocusNavUser, perm: string): boolean {
  const focus = navFocus(user);
  return user.permissions.includes("org.admin") || focus === "admin" || user.permissions.includes(perm);
}

function teamPath(user: FocusNavUser): string | null {
  return marketingHomePath(user);
}

/** Up to six everyday destinations. Everything else stays available under More. */
export function dailyPaths(user: FocusNavUser): string[] {
  const out: string[] = ["/", "/my-work"];
  const push = (path: string | null | undefined, ok = true) => {
    if (!path || !ok || out.includes(path) || out.length >= DAILY_LIMIT) return;
    out.push(path);
  };
  const has = (perm: string) => focusCan(user, perm);
  const access = {
    roleCode: user.roleCode,
    permissions: user.permissions,
    teamId: user.teamId,
    teamHomeTeamId: user.teamHomeTeamId,
  };
  const pricing = () => canSeePricing(access, has);
  const projects = () => canSeeProjects(access, has);
  const calendar = () => canSeeCalendar(access, has);
  const perf = isPerformanceUser(access);
  const code = user.roleCode ?? "";

  if (isMarketingManager(access)) {
    push("/requests", has("request.triage") || has("request.manage"));
    push("/projects", projects());
    push(teamPath(user), canSeeMarketingHome(access));
    push("/perf/campaigns");
    push("/perf/sheet");
    push("/pricing", pricing());
    push("/communication", has("conversation.read"));
    push("/calendar", calendar());
    push("/reports");
    push("/people", has("user.read"));
    push("/knowledge", has("kb.read"));
    return out;
  }

  if (perf) {
    push("/perf");
    push("/perf/campaigns");
    push("/perf/sheet");
    push(teamPath(user), canSeeMarketingHome(access));
    push("/perf/sms");
    push("/pricing", pricing());
    push("/communication", has("conversation.read"));
    push("/calendar", calendar());
    push("/reports");
    push("/people", has("user.read"));
    push("/knowledge", has("kb.read"));
    return out;
  }

  if (isMarketingMemberReadOnly(access)) {
    push(teamPath(user), canSeeMarketingHome(access));
    push("/pricing", pricing());
    push("/communication", has("conversation.read"));
    push("/calendar", calendar());
    push("/reports");
    push("/people", has("user.read"));
    push("/knowledge", has("kb.read"));
    return out;
  }

  if (code === "seller") {
    push("/vehicles", has("inventory.read"));
    push("/communication", has("conversation.read"));
    push("/requests", has("request.create") || has("request.triage") || has("request.manage"));
    push("/calendar", calendar());
    push("/reports");
    push("/people", has("user.read"));
    push("/knowledge", has("kb.read"));
    return out;
  }

  if (code === "finance") {
    push("/perf/money", has("campaign.read") || has("expense.request") || has("perf.read"));
    push("/reports");
    push("/communication", has("conversation.read"));
    push("/calendar", calendar());
    return out;
  }

  if (code === "requester") {
    push("/requests", has("request.create"));
    push("/projects", projects());
    push("/pricing", pricing());
    push("/communication", has("conversation.read"));
    push("/reports");
    push("/people", has("user.read"));
    push("/knowledge", has("kb.read"));
    return out;
  }

  push("/requests", has("request.create") || has("request.triage") || has("request.manage"));
  push("/projects", projects());
  push("/communication", has("conversation.read"));
  const focus = navFocus(user);
  if (focus === "admin" || code === "admin") {
    push("/admin", has("org.admin"));
  } else {
    push("/pricing", pricing());
    if (code === "lead" || code === "marketing_manager") {
      push(teamPath(user), canSeeMarketingHome(access));
    }
  }
  push("/calendar", calendar());
  push("/reports");
  push("/people", has("user.read"));
  push("/knowledge", has("kb.read"));
  return out;
}

export const PERF_HUB_PATH = "/perf";

const PERF_TOOL_ORDER = ["/perf/campaigns", "/perf/sms", "/perf/social", "/perf/sheet", "/perf/money"];

export function isPerfToolPath(to: string): boolean {
  return to.startsWith("/perf/") && to !== "/perf/connections";
}

/** مارکتینگ: اول خانهٔ بخش و پرفورمنس، بقیهٔ مسیرهای /perf در ابزارهای تو در تو. */
export function partitionMarketingNav<T extends { to: string }>(
  items: T[],
  marketingHomeTo: string | null,
): { head: T[]; perfTools: T[] } {
  const seen = new Set<string>();
  const head: T[] = [];
  const push = (item: T | undefined) => {
    if (!item || seen.has(item.to)) return;
    seen.add(item.to);
    head.push(item);
  };
  if (marketingHomeTo) push(items.find((row) => row.to === marketingHomeTo));
  push(items.find((row) => row.to === PERF_HUB_PATH));
  const order = new Map(PERF_TOOL_ORDER.map((path, index) => [path, index]));
  const perfTools = items
    .filter((row) => isPerfToolPath(row.to))
    .filter((row) => {
      if (seen.has(row.to)) return false;
      seen.add(row.to);
      return true;
    })
    .sort((a, b) => (order.get(a.to) ?? 99) - (order.get(b.to) ?? 99));
  return { head, perfTools };
}

export function groupDailyNav<T extends { to: string; group: string }>(
  items: T[],
  daily: string[],
): { main: T[]; marketing: T[]; more: T[] } {
  const wanted = new Set(daily);
  const seen = new Set<string>();
  const main: T[] = [];
  const marketing: T[] = [];
  const more: T[] = [];
  for (const item of items) {
    if (seen.has(item.to)) continue;
    seen.add(item.to);
    if (!wanted.has(item.to)) more.push(item);
    else if (item.group === "Marketing") marketing.push(item);
    else main.push(item);
  }
  return { main, marketing, more };
}

export type HomeKpi = "waiting" | "late" | "projects" | "replies" | "prices" | "posts";

export function visibleHomeKpis(user: FocusNavUser): HomeKpi[] {
  const has = (perm: string) => focusCan(user, perm);
  const kpis: HomeKpi[] = ["waiting", "late"];
  if (has("request.create") || has("request.triage") || has("request.manage") || has("task.read")) kpis.push("projects");
  if (has("conversation.read")) kpis.push("replies");
  if (has("price.approve") || has("price.write")) kpis.push("prices");
  if (has("campaign.read")) kpis.push("posts");
  return kpis;
}

export function caughtUpTarget(user: FocusNavUser): string {
  const has = (perm: string) => focusCan(user, perm);
  if (has("request.create")) return "/requests";
  if (has("price.approve") || has("price.write")) return "/pricing";
  if (has("perf.read") || has("perf.write") || has("campaign.read")) return "/perf";
  if (has("inventory.read")) return "/vehicles";
  return "/my-work";
}

export type OnboardingCue = {
  titleEn: string;
  titleFa: string;
  bodyEn: string;
  bodyFa: string;
  to: string;
  actionEn: string;
  actionFa: string;
};

export function onboardingCue(role: FocusRole): OnboardingCue {
  if (role === "admin" || role === "manager") {
    return {
      titleEn: "Start with one request",
      titleFa: "از یک درخواست شروع کنید",
      bodyEn: "The queue already shows what the team is waiting on. Open the first one.",
      bodyFa: "صف درخواست‌ها نشان می‌دهد تیم منتظر چیست. اولین مورد را باز کنید.",
      to: "/requests",
      actionEn: "Open requests",
      actionFa: "دیدن درخواست‌ها",
    };
  }
  if (role === "marketing") {
    return {
      titleEn: "Your campaigns are ready to review",
      titleFa: "کمپین‌ها آماده‌اند",
      bodyEn: "Performance shows the one campaign that needs you. The rest can wait.",
      bodyFa: "پرفورمنس همان کمپینی را نشان می‌دهد که به شما نیاز دارد. بقیه می‌توانند بمانند.",
      to: "/perf",
      actionEn: "Open performance",
      actionFa: "رفتن به پرفورمنس",
    };
  }
  if (role === "finance") {
    return {
      titleEn: "Costs that need a decision",
      titleFa: "هزینه‌هایی که تصمیم می‌خواهند",
      bodyEn: "The report shows what is waiting. You do not need to set anything up first.",
      bodyFa: "گزارش نشان می‌دهد چه چیزی منتظر تصمیم است. لازم نیست اول چیزی را تنظیم کنید.",
      to: "/reports",
      actionEn: "Open reports",
      actionFa: "دیدن گزارش",
    };
  }
  if (role === "seller") {
    return {
      titleEn: "Your next job is already listed",
      titleFa: "کار بعدی‌تان در فهرست است",
      bodyEn: "Open My Work and finish the first item. Vehicles stay one step away.",
      bodyFa: "کارهای من را باز کنید و اولین مورد را تمام کنید. خودروها یک قدم آن‌طرف‌ترند.",
      to: "/my-work",
      actionEn: "Open my work",
      actionFa: "کارهای من",
    };
  }
  return {
    titleEn: "One list, already filled in",
    titleFa: "یک فهرست، از قبل آماده",
    bodyEn: "My Work shows what is yours. Start with the first item.",
    bodyFa: "کارهای من نشان می‌دهد چه چیزی مال شماست. از اولین مورد شروع کنید.",
    to: "/my-work",
    actionEn: "Open my work",
    actionFa: "کارهای من",
  };
}

export const WORK_BUCKETS = ["overdue", "today", "later", "waiting", "projects_without_tasks"] as const;
export type WorkBucket = (typeof WORK_BUCKETS)[number];

export function filledWorkBuckets(counts: Partial<Record<WorkBucket, number>>): WorkBucket[] {
  return WORK_BUCKETS.filter((key) => (counts[key] ?? 0) > 0);
}

export function defaultWorkTab(overdueCount: number): "tasks" | "overdue" {
  return overdueCount > 0 ? "overdue" : "tasks";
}

export function workEmptyTarget(user: FocusNavUser): string {
  return caughtUpTarget(user);
}

export type TeamChoice = { id: string; parent_team_id?: string | null };

export function suggestTeamId(teams: TeamChoice[], userTeamId: string | null | undefined): string {
  if (!userTeamId) return "";
  const mine = teams.find((team) => team.id === userTeamId);
  if (!mine || mine.parent_team_id) return "";
  return mine.id;
}

export const DEFAULT_REQUEST_KIND = "تبلیغات";
export const DEFAULT_REQUEST_PRIORITY = "normal";
export const DEFAULT_PROJECT_KIND = "پرفورمنس";

export const PROJECT_TABS = ["tasks", "overview", "resources"] as const;
export type ProjectTab = (typeof PROJECT_TABS)[number];
