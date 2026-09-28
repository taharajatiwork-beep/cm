import { describe, expect, it } from "vitest";
import { nextCursor } from "./pagination";

describe("nextCursor", () => {
  it("returns the next page cursor", () => {
    expect(nextCursor({ next_cursor: "20" })).toBe("20");
  });

  it("stops when the envelope has no cursor", () => {
    expect(nextCursor({ next_cursor: null })).toBeUndefined();
    expect(nextCursor(undefined)).toBeUndefined();
  });
});
