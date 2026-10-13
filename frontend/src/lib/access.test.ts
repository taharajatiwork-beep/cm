import { describe, expect, it } from "vitest";
import { canSeeCalendar, canSeeNavPath, canSeePricing, canSeeProjects, marketingHomePath } from "./access";

const has = (perms: string[]) => (code: string) => perms.includes(code) || perms.includes("org.admin");

describe("access", () => {
  it("pricing for manager and marketing, not finance", () => {
    expect(canSeePricing({ roleCode: "requester", permissions: ["request.create", "campaign.read"] }, has([]))).toBe(true);
    expect(canSeePricing({ roleCode: "designer", permissions: ["task.read"] }, has([]))).toBe(true);
    expect(canSeePricing({ roleCode: "lead", permissions: ["price.write", "campaign.read"] }, has([]))).toBe(false);
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
