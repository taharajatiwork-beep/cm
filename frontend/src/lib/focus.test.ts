import { describe, expect, it } from "vitest";

import {
  PROJECT_TABS,
  caughtUpTarget,
  dailyPaths,
  defaultWorkTab,
  filledWorkBuckets,
  flattenMyWorkTasks,
  groupDailyNav,
  partitionMarketingNav,
  PERF_HUB_PATH,
  filterOnboardingCue,
  onboardingCue,
  suggestTeamId,
  visibleHomeKpis,
} from "./focus";

const admin = {
  roleHint: "admin" as const,
  roleCode: "admin",
  permissions: ["org.admin"],
  teamId: "team-1",
};

describe("dailyPaths", () => {
  it("keeps an admin on core everyday destinations", () => {
    const paths = dailyPaths(admin);
    expect(paths.slice(0, 6)).toEqual(["/", "/my-work", "/requests", "/projects", "/communication", "/admin"]);
    expect(paths).toContain("/calendar");
    expect(paths).toContain("/reports");
  });

  it("gives performance users perf, campaigns, sms, and sheet", () => {
    const paths = dailyPaths({
      roleHint: "marketing",
      roleCode: "performance_marketing",
      permissions: ["perf.read", "perf.write", "campaign.read", "conversation.read"],
      teamId: "team-1",
      teamHomeTeamId: "team-parent",
    });
    expect(paths).toContain("/perf");
    expect(paths).toContain("/perf/campaigns");
    expect(paths).toContain("/perf/sheet");
    expect(paths.length).toBeLessThanOrEqual(12);
  });

  it("prioritizes requests and projects for a requester", () => {
    expect(
      dailyPaths({
        roleCode: "requester",
        permissions: ["request.create", "campaign.read", "conversation.read", "inventory.read"],
      }),
    ).toEqual(["/", "/my-work", "/requests", "/projects", "/vehicles", "/pricing", "/communication", "/reports"]);
  });

  it("starts a seller from vehicles and messages", () => {
    expect(
      dailyPaths({
        roleHint: "seller",
        roleCode: "seller",
        permissions: ["inventory.read", "conversation.read"],
      }),
    ).toEqual(["/", "/my-work", "/vehicles", "/communication", "/reports"]);
  });

  it("gives marketing members home and pricing, not perf or requests", () => {
    const paths = dailyPaths({
      roleHint: "marketing",
      roleCode: "marketing",
      permissions: ["task.read", "conversation.read", "campaign.read"],
      teamId: "team-1",
      teamHomeTeamId: "team-parent",
    });
    expect(paths).toContain("/teams/team-parent");
    expect(paths).toContain("/pricing");
    expect(paths).not.toContain("/perf");
    expect(paths).not.toContain("/requests");
    expect(paths.length).toBeLessThanOrEqual(6);
  });
});

describe("partitionMarketingNav", () => {
  it("puts team home and perf hub first, then ordered perf tools", () => {
    const items = [
      { to: "/teams/parent", group: "Marketing" },
      { to: PERF_HUB_PATH, group: "Marketing" },
      { to: "/perf/sms", group: "Marketing" },
      { to: "/perf/campaigns", group: "Marketing" },
    ];
    const { head, perfTools } = partitionMarketingNav(items, "/teams/parent");
    expect(head.map((row) => row.to)).toEqual(["/teams/parent", PERF_HUB_PATH]);
    expect(perfTools.map((row) => row.to)).toEqual(["/perf/campaigns", "/perf/sms"]);
  });

  it("drops perf tools already in the main nav (group empty)", () => {
    const items = [
      { to: PERF_HUB_PATH, group: "Marketing" },
      { to: "/perf/money", group: "" },
      { to: "/perf/campaigns", group: "Marketing" },
    ];
    const { perfTools } = partitionMarketingNav(items, null);
    expect(perfTools.map((row) => row.to)).toEqual(["/perf/campaigns"]);
  });
});

describe("groupDailyNav", () => {
  it("promotes a daily admin link out of More and keeps rare links there once", () => {
    const placed = groupDailyNav(
      [
        { to: "/", group: "" },
        { to: "/admin", group: "More" },
        { to: "/perf/sheet", group: "Marketing" },
        { to: "/teams/team-1", group: "" },
        { to: "/teams/team-1", group: "Marketing" },
      ],
      ["/", "/admin"],
    );
    expect(placed.main.map((item) => item.to)).toEqual(["/", "/admin"]);
    expect(placed.marketing).toEqual([]);
    expect(placed.more.map((item) => item.to)).toEqual(["/perf/sheet", "/teams/team-1"]);
  });
});

describe("home and work focus", () => {
  it("hides project and message counts from a seller who cannot see them", () => {
    expect(
      visibleHomeKpis({ roleHint: "seller", permissions: ["inventory.read"] }),
    ).toEqual(["waiting", "late"]);
  });

  it("offers a concrete next page when the inbox is clear", () => {
    expect(caughtUpTarget({ roleHint: "manager", permissions: ["request.create"] })).toBe("/requests");
    expect(caughtUpTarget({ roleHint: "seller", permissions: ["inventory.read"] })).toBe("/vehicles");
  });

  it("gives each role three onboarding steps", () => {
    expect(onboardingCue("manager").steps).toHaveLength(3);
    expect(onboardingCue("manager").steps[0].to).toBe("/requests");
    expect(onboardingCue("marketing").steps[0].to).toBe("/perf");
    expect(onboardingCue("viewer").steps[0].to).toBe("/my-work");
    expect(onboardingCue("marketing", "designer").steps[0].to).toBe("/projects");
  });

  it("filters onboarding steps by nav access", () => {
    const cue = onboardingCue("marketing");
    const filtered = filterOnboardingCue(
      cue,
      { roleCode: "marketing", permissions: ["task.read", "conversation.read"], teamId: "t1" },
      (perm) => perm === "task.read" || perm === "conversation.read",
    );
    expect(filtered.steps.some((step) => step.to === "/perf")).toBe(false);
  });

  it("drops empty work buckets and opens late work first", () => {
    expect(filledWorkBuckets({ overdue: 0, today: 2, later: 0, waiting: 1 })).toEqual(["today", "waiting"]);
    expect(defaultWorkTab(3)).toBe("overdue");
    expect(defaultWorkTab(0)).toBe("tasks");
  });
});

describe("request defaults", () => {
  it("preselects the user's own top-level team", () => {
    const teams = [
      { id: "parent", parent_team_id: null },
      { id: "child", parent_team_id: "parent" },
    ];
    expect(suggestTeamId(teams, "parent")).toBe("parent");
    expect(suggestTeamId(teams, "child")).toBe("");
    expect(suggestTeamId(teams, null)).toBe("");
  });
});

describe("project sections", () => {
  it("keeps three primary sections", () => {
    expect(PROJECT_TABS).toEqual(["tasks", "overview", "resources"]);
  });
});

describe("flattenMyWorkTasks", () => {
  it("dedupes tasks across buckets in priority order", () => {
    const rows = flattenMyWorkTasks({
      overdue: [{ kind: "task", id: "a", title: "late" }],
      later: [{ kind: "task", id: "a", title: "late" }, { kind: "task", id: "b", title: "soon" }],
      projects_without_tasks: [{ kind: "project", id: "p1", title: "empty project" }],
    });
    expect(rows.map((row) => row.id)).toEqual(["a", "b"]);
  });
});
