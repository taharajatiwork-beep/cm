import { describe, expect, it } from "vitest";
import { layoutTimedEvents } from "./helpers";

describe("layoutTimedEvents", () => {
  it("places non-overlapping events in one column", () => {
    const out = layoutTimedEvents([
      { id: "a", start_time: "09:00", end_time: "10:00" },
      { id: "b", start_time: "10:00", end_time: "11:00" },
    ]);
    expect(out.every((row) => row.column === 0)).toBe(true);
  });

  it("splits overlapping events into columns", () => {
    const out = layoutTimedEvents([
      { id: "a", start_time: "09:00", end_time: "10:30" },
      { id: "b", start_time: "09:30", end_time: "10:00" },
    ]);
    expect(new Set(out.map((row) => row.column)).size).toBe(2);
  });
});
