import { describe, expect, it } from "vitest";
import { needsClamp } from "./text";

describe("needsClamp", () => {
  it("leaves short text alone", () => {
    expect(needsClamp("کوتاه")).toBe(false);
    expect(needsClamp("")).toBe(false);
    expect(needsClamp(null)).toBe(false);
    expect(needsClamp("a\nb\nc")).toBe(false);
  });

  it("clamps long or many-line text", () => {
    expect(needsClamp("x".repeat(181))).toBe(true);
    expect(needsClamp("a\nb\nc\nd")).toBe(true);
    expect(needsClamp("a\r\nb\r\nc\r\nd")).toBe(true);
  });
});
