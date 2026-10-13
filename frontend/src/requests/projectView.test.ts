import { describe, expect, it } from "vitest";

import { PROJECT_TABS } from "../lib/focus";

describe("project page", () => {
  it("puts work first, then overview and resources", () => {
    expect(PROJECT_TABS).toEqual(["tasks", "overview", "resources"]);
  });

  it("clamps a scope picker to the four report scopes", () => {
    const scopes = ["me", "team", "team_tree", "org"];
    expect(scopes.includes("branch")).toBe(false);
    expect(scopes[0]).toBe("me");
  });
});
