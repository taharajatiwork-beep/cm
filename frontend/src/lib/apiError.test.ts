import { describe, expect, it } from "vitest";
import { ApiError } from "../api";
import { isForbiddenError } from "./apiError";

describe("isForbiddenError", () => {
  it("detects ApiError 403", () => {
    expect(isForbiddenError(new ApiError(403, "nope"))).toBe(true);
  });

  it("detects missing one of permissions message", () => {
    expect(
      isForbiddenError("Missing one of permissions: perf.read, perf.write"),
    ).toBe(true);
  });
});
