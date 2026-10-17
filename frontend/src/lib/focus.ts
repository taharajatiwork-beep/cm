import {
  canSeeCalendar,
  canSeeMarketingHome,
  canSeeNavPath,
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

const DAILY_LIMIT = 12;

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
    push("/pricing", pricing());
    push("/reports");
    push("/communication", has("conversation.read"));
    push("/calendar", calendar());
    return out;
  }

  if (code === "requester") {
    push("/requests", has("request.create"));
    push("/projects", projects());
    push("/vehicles", has("inventory.read"));
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

const PERF_TOOL_ORDER = [
  "/perf/campaigns",
  "/perf/sms",
  "/perf/social",
  "/perf/sheet",
  "/ai-lab",
  "/perf/money",
];

export function isPerfToolPath(to: string): boolean {
  return (to.startsWith("/perf/") && to !== "/perf/connections") || to === "/ai-lab";
}

/** مارکتینگ: اول خانهٔ بخش و پرفورمنس، بقیهٔ مسیرهای /perf در ابزارهای تو در تو. */
export function partitionMarketingNav<T extends { to: string; group?: string }>(
  items: T[],
  marketingHomeTo: string | null,
): { head: T[]; perfTools: T[] } {
  const seen = new Set<string>();
  for (const item of items) {
    if (item.group === "") seen.add(item.to);
  }
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

export type OnboardingStep = {
  labelEn: string;
  labelFa: string;
  to: string;
};

export type OnboardingCue = {
  titleEn: string;
  titleFa: string;
  bodyEn: string;
  bodyFa: string;
  steps: OnboardingStep[];
};

export function filterOnboardingCue(
  cue: OnboardingCue,
  user: FocusNavUser,
  has: (perm: string) => boolean,
): OnboardingCue {
  const access = {
    roleCode: user.roleCode,
    permissions: user.permissions,
    teamId: user.teamId,
    teamHomeTeamId: user.teamHomeTeamId,
  };
  const steps = cue.steps.filter((step) => canSeeNavPath(step.to, access, has));
  return { ...cue, steps };
}

export function onboardingCue(role: FocusRole, roleCode?: string | null): OnboardingCue {
  if (roleCode === "designer" || roleCode === "filmmaker") {
    return {
      titleEn: "Your design queue",
      titleFa: "صف کار طراحی و تولید",
      bodyEn: "Projects first, then tasks, then messages when someone needs you.",
      bodyFa: "اول پروژه‌ها، بعد کارهای شما، بعد پیام وقتی کسی منتظر شماست.",
      steps: [
        { labelEn: "Projects", labelFa: "پروژه‌ها", to: "/projects" },
        { labelEn: "My work", labelFa: "کارهای من", to: "/my-work" },
        { labelEn: "Messages", labelFa: "پیام‌ها", to: "/communication" },
      ],
    };
  }
  if (role === "admin" || role === "manager") {
    return {
      titleEn: "Three places to run the team",
      titleFa: "سه جا برای راه انداختن تیم",
      bodyEn: "Follow these in order — each step is one click away.",
      bodyFa: "به ترتیب پیش بروید — هر قدم یک کلیک فاصله دارد.",
      steps: [
        { labelEn: "Requests queue", labelFa: "صف درخواست‌ها", to: "/requests" },
        { labelEn: "Projects", labelFa: "پروژه‌ها", to: "/projects" },
        { labelEn: "Reports", labelFa: "گزارش‌ها", to: "/reports" },
      ],
    };
  }
  if (role === "marketing") {
    return {
      titleEn: "Your marketing rhythm",
      titleFa: "ریتم کار مارکتینگ",
      bodyEn: "Only steps you can open from the menu are shown.",
      bodyFa: "فقط مسیرهایی که در منوی شما هست نشان داده می‌شود.",
      steps: [
        { labelEn: "Performance", labelFa: "پرفورمنس", to: "/perf" },
        { labelEn: "Calendar", labelFa: "تقویم", to: "/calendar" },
        { labelEn: "Prices & posts", labelFa: "قیمت و پست‌ها", to: "/pricing" },
      ],
    };
  }
  if (role === "finance") {
    return {
      titleEn: "Where money shows up",
      titleFa: "پول کجا دیده می‌شود",
      bodyEn: "Costs, reports, then messages when something needs you.",
      bodyFa: "هزینه‌ها، گزارش، بعد پیام وقتی چیزی منتظر شماست.",
      steps: [
        { labelEn: "Costs", labelFa: "هزینه‌ها", to: "/perf/money" },
        { labelEn: "Reports", labelFa: "گزارش‌ها", to: "/reports" },
        { labelEn: "Messages", labelFa: "پیام‌ها", to: "/communication" },
      ],
    };
  }
  if (role === "seller") {
    return {
      titleEn: "Sell from stock",
      titleFa: "فروش از موجودی",
      bodyEn: "Vehicles first, then inquiries, then your tasks.",
      bodyFa: "اول خودروها، بعد استعلام، بعد کارهای شما.",
      steps: [
        { labelEn: "Vehicles", labelFa: "خودروها", to: "/vehicles" },
        { labelEn: "My work", labelFa: "کارهای من", to: "/my-work" },
        { labelEn: "Messages", labelFa: "پیام‌ها", to: "/communication" },
      ],
    };
  }
  return {
    titleEn: "Your daily trio",
    titleFa: "سه‌تایی روزانهٔ شما",
    bodyEn: "My Work first; other steps only if they appear in your menu.",
    bodyFa: "اول کارهای من؛ بقیه فقط اگر در منوی شما هست.",
    steps: [
      { labelEn: "My work", labelFa: "کارهای من", to: "/my-work" },
      { labelEn: "Calendar", labelFa: "تقویم", to: "/calendar" },
      { labelEn: "Colleagues", labelFa: "همکاران", to: "/people" },
    ],
  };
}

export const WORK_BUCKETS = ["overdue", "today", "later", "waiting", "projects_without_tasks"] as const;
export type WorkBucket = (typeof WORK_BUCKETS)[number];

export function filledWorkBuckets(counts: Partial<Record<WorkBucket, number>>): WorkBucket[] {
  return WORK_BUCKETS.filter((key) => (counts[key] ?? 0) > 0);
}

/** Tasks from /requests/my-work buckets (owner or assignee), deduped in bucket priority order. */
export function flattenMyWorkTasks(
  data: Partial<Record<WorkBucket, Array<Record<string, string>>>> | undefined,
): Array<Record<string, unknown>> {
  const seen = new Set<string>();
  const out: Array<Record<string, unknown>> = [];
  for (const key of WORK_BUCKETS) {
    if (key === "projects_without_tasks") continue;
    for (const row of data?.[key] ?? []) {
      if (row.kind === "project") continue;
      const id = String(row.id);
      if (seen.has(id)) continue;
      seen.add(id);
      out.push(row);
    }
  }
  return out;
}

export function myWorkProjectsWithoutTasks(
  data: Partial<Record<WorkBucket, Array<Record<string, string>>>> | undefined,
): Array<Record<string, string>> {
  return data?.projects_without_tasks ?? [];
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

export const DEFAULT_REQUEST_KIND = "عمومی";
export const DEFAULT_REQUEST_PRIORITY = "normal";
export const DEFAULT_PROJECT_KIND = "پرفورمنس";

export const PROJECT_TABS = ["tasks", "overview", "resources"] as const;
export type ProjectTab = (typeof PROJECT_TABS)[number];
