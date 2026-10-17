import { describe, expect, it } from "vitest";
import { notificationHref } from "./notificationLinks";

describe("notificationHref", () => {
  it("links cases and tasks", () => {
    expect(notificationHref("case", "abc")).toBe("/cases?c=abc");
    expect(notificationHref("task", "t1")).toBe("/my-work?task=t1");
  });

  it("sends members without case.read to my-work", () => {
    const has = (code: string) => code !== "case.read";
    expect(notificationHref("case", "abc", has)).toBe("/my-work");
    expect(notificationHref("follow_up", "x", has)).toBe("/my-work");
    const canCase = (code: string) => code === "case.read";
    expect(notificationHref("case", "abc", canCase)).toBe("/cases?c=abc");
  });
});
