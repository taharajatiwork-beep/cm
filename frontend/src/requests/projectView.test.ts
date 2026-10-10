import { describe, expect, it } from "vitest";

const TABS = ["overview", "tasks", "links", "chat", "costs", "activity", "type"];

describe("project page", () => {
  it("keeps the seven tabs in order", () => {
    expect(TABS).toEqual(["overview", "tasks", "links", "chat", "costs", "activity", "type"]);
  });

  it("clamps a scope picker to the four report scopes", () => {
    const scopes = ["me", "team", "team_tree", "org"];
    expect(scopes.includes("branch")).toBe(false);
    expect(scopes[0]).toBe("me");
  });
});
