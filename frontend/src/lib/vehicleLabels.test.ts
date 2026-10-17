import { describe, expect, it } from "vitest";
import { formatEngine } from "./vehicleLabels";

describe("formatEngine", () => {
  it("formats liters in Persian", () => {
    expect(formatEngine("2.5L")).toBe("۲٫۵ لیتر");
    expect(formatEngine("2.5l")).toBe("۲٫۵ لیتر");
  });

  it("returns raw value when not a liter pattern", () => {
    expect(formatEngine("Turbo")).toBe("Turbo");
  });
});
