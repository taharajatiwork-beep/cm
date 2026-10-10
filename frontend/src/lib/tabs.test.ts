import { describe, expect, it } from "vitest";
import { nextTabIndex, tabFromParam, withTabParam } from "./tabs";

const KEYS = ["campaigns", "requests", "missing", "triage"] as const;

describe("tabFromParam", () => {
  it("accepts a known tab and falls back otherwise", () => {
    expect(tabFromParam("requests", KEYS, "campaigns")).toBe("requests");
    expect(tabFromParam("triage", KEYS, "campaigns")).toBe("triage");
    expect(tabFromParam(null, KEYS, "campaigns")).toBe("campaigns");
    expect(tabFromParam("", KEYS, "campaigns")).toBe("campaigns");
    expect(tabFromParam("nope", KEYS, "campaigns")).toBe("campaigns");
  });
});

describe("withTabParam", () => {
  it("sets the tab and keeps other params", () => {
    const next = withTabParam(new URLSearchParams("q=abc"), "missing", "campaigns");
    expect(next.get("tab")).toBe("missing");
    expect(next.get("q")).toBe("abc");
  });

  it("drops the param for the default tab and does not mutate the input", () => {
    const start = new URLSearchParams("tab=triage&q=x");
    const next = withTabParam(start, "campaigns", "campaigns");
    expect(next.has("tab")).toBe(false);
    expect(next.toString()).toBe("q=x");
    expect(start.get("tab")).toBe("triage");
  });
});

describe("nextTabIndex", () => {
  it("moves with arrows, mirrored in RTL, and wraps", () => {
    expect(nextTabIndex(0, 4, "ArrowLeft", true)).toBe(1);
    expect(nextTabIndex(0, 4, "ArrowRight", true)).toBe(3);
    expect(nextTabIndex(3, 4, "ArrowRight", false)).toBe(0);
    expect(nextTabIndex(1, 4, "ArrowLeft", false)).toBe(0);
  });

  it("handles Home/End and ignores other keys", () => {
    expect(nextTabIndex(2, 4, "Home", true)).toBe(0);
    expect(nextTabIndex(0, 4, "End", true)).toBe(3);
    expect(nextTabIndex(1, 4, "Enter", true)).toBeNull();
    expect(nextTabIndex(0, 0, "Home", true)).toBeNull();
  });
});
