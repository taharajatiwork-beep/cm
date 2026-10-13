import { describe, expect, it } from "vitest";
import { hasExpenseTeamApprove } from "./permissions";

describe("hasExpenseTeamApprove", () => {
  const has = (perm: string) => perm === "request.triage";

  it("allows triage", () => {
    expect(hasExpenseTeamApprove(has)).toBe(true);
  });

  it("denies bare perf.write", () => {
    expect(hasExpenseTeamApprove((p) => p === "perf.write")).toBe(false);
  });
});
