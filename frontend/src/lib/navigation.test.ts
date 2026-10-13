import { describe, expect, it } from "vitest";

import { isPerformanceUser, loginRedirectTarget } from "./navigation";

describe("loginRedirectTarget", () => {
  it("keeps the deep link the user was bounced from", () => {
    expect(loginRedirectTarget({ pathname: "/communication", search: "?c=abc" })).toBe(
      "/communication?c=abc",
    );
    expect(loginRedirectTarget({ pathname: "/requests", search: "", hash: "" })).toBe("/requests");
    expect(loginRedirectTarget({ pathname: "/search", search: "?q=camry", hash: "#top" })).toBe(
      "/search?q=camry#top",
    );
  });

  it("falls back to home when there is no origin", () => {
    expect(loginRedirectTarget(undefined)).toBe("/");
    expect(loginRedirectTarget(null)).toBe("/");
    expect(loginRedirectTarget({})).toBe("/");
  });

  it("never redirects back to /login or / (no loops)", () => {
    expect(loginRedirectTarget({ pathname: "/login" })).toBe("/");
    expect(loginRedirectTarget({ pathname: "/" })).toBe("/");
  });
});

describe("isPerformanceUser", () => {
  it("matches the performance role", () => {
    expect(isPerformanceUser({ roleCode: "performance_marketing", permissions: [] })).toBe(true);
  });

  it("matches a lead with performance write access but no approve/admin", () => {
    expect(isPerformanceUser({ roleCode: "lead", permissions: ["task.read", "perf.read", "perf.write"] })).toBe(true);
  });

  it("does not match managers, admins, readers or nobody", () => {
    expect(isPerformanceUser({ roleCode: "marketing_manager", permissions: ["perf.read", "perf.write", "perf.approve"] })).toBe(false);
    expect(isPerformanceUser({ roleCode: "admin", permissions: ["org.admin", "perf.write"] })).toBe(false);
    expect(isPerformanceUser({ roleCode: "finance", permissions: ["perf.read"] })).toBe(false);
    expect(isPerformanceUser({ roleCode: "lead", permissions: ["task.read"] })).toBe(false);
    expect(isPerformanceUser(null)).toBe(false);
  });
});
