import { describe, expect, it } from "vitest";
import { notificationHref } from "./notificationLinks";

describe("notificationHref", () => {
  it("links cases and tasks", () => {
    expect(notificationHref("case", "abc")).toBe("/cases?c=abc");
    expect(notificationHref("task", "t1")).toBe("/my-work?task=t1");
  });
});
