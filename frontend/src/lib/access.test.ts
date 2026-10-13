import { describe, expect, it } from "vitest";
import { canSeeCalendar, canSeeNavPath, canSeePricing, canSeeProjects, marketingHomePath } from "./access";

const has = (perms: string[]) => (code: string) => perms.includes(code) || perms.includes("org.admin");

describe("access", () => {
  it("pricing only when board API permissions match", () => {
    const requester = { roleCode: "requester", permissions: ["request.create", "campaign.read"] };
    expect(canSeePricing(requester, has(requester.permissions))).toBe(true);
    const designer = { roleCode: "designer", permissions: ["task.read"] };
    expect(canSeePricing(designer, has(designer.permissions))).toBe(false);
    const lead = { roleCode: "lead", permissions: ["price.write", "campaign.read"] };
    expect(canSeePricing(lead, has(lead.permissions))).toBe(true);
    const finance = { roleCode: "finance", permissions: ["price.approve"] };
    expect(canSeePricing(finance, has(finance.permissions))).toBe(true);
  });

  it("my-work only for task.read, request.create, or org.admin", () => {
    const reporter = { roleCode: "reporter", permissions: ["report.read"] };
    expect(canSeeNavPath("/my-work", reporter, has(reporter.permissions))).toBe(false);
    const member = { roleCode: "member", permissions: ["task.read"] };
    expect(canSeeNavPath("/my-work", member, has(member.permissions))).toBe(true);
    const requester = { roleCode: "requester", permissions: ["request.create"] };
    expect(canSeeNavPath("/my-work", requester, has(requester.permissions))).toBe(true);
  });

  it("calendar for perf.write; projects hidden from performance", () => {
    const user = { roleCode: "performance_marketing", permissions: ["perf.read", "perf.write", "task.read"] };
    const h = has(user.permissions);
    expect(canSeeCalendar(user, h)).toBe(true);
    expect(canSeeNavPath("/calendar", user, h)).toBe(true);
    expect(canSeeProjects(user, h)).toBe(false);
    expect(canSeeNavPath("/projects", user, h)).toBe(false);
  });

  it("marketing manager sees campaigns and sheet, not sms", () => {
    const user = { roleCode: "marketing_manager", permissions: ["request.triage", "perf.read", "perf.write"] };
    const h = has(user.permissions);
    expect(canSeeCalendar(user, h)).toBe(true);
    expect(canSeeNavPath("/calendar", user, h)).toBe(true);
    expect(canSeeNavPath("/perf/sms", user, h)).toBe(false);
    expect(canSeeNavPath("/perf/sheet", user, h)).toBe(true);
    expect(canSeeNavPath("/perf/campaigns", user, h)).toBe(true);
    expect(canSeeNavPath("/perf", user, h)).toBe(false);
  });

  it("uses parent team for marketing home link", () => {
    expect(
      marketingHomePath({ roleCode: "performance_marketing", permissions: [], teamId: "child", teamHomeTeamId: "parent" }),
    ).toBe("/teams/parent");
  });
});
