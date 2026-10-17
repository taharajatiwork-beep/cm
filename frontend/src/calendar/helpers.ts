import type { CalendarEntry, CalendarEvent } from "../calendarApi";
import { DONE, MARKETING_KINDS, TIERS, WORK_KINDS } from "./constants";

export function todayIso() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export function tierLabel(value: string) {
  return TIERS.find((row) => row.value === value)?.label ?? value;
}

export function tierTone(value: string) {
  return TIERS.find((row) => row.value === value)?.tone ?? "";
}

export function lateDay(date: string, status: string) {
  return date < todayIso() && !DONE.has(status);
}

export function eventMatchesLayers(row: CalendarEvent, layers: Set<string>) {
  if (layers.size === 0) return true;
  if (row.kind === "mizito") return layers.has("mizito") || layers.has("work");
  if (WORK_KINDS.has(row.kind)) return layers.has("work") || layers.has(row.kind);
  if (MARKETING_KINDS.has(row.kind)) return layers.has("marketing");
  if (row.kind === "shoot") return layers.has("marketing") || layers.has("work");
  return layers.has(row.kind);
}

export function entryMatchesLayers(row: CalendarEntry, layers: Set<string>) {
  if (layers.size === 0) return true;
  return layers.has(row.entry_type) || layers.has("content");
}

export function parseTimeMinutes(value: string | null | undefined): number {
  if (!value) return 0;
  const [h, m] = value.split(":").map(Number);
  return h * 60 + (m || 0);
}

export type TimedBlock = {
  id: string;
  startMin: number;
  endMin: number;
  column: number;
};

/** Assign overlap columns for timed events on one day. */
export function layoutTimedEvents(
  rows: Array<{ id: string; start_time: string | null; end_time: string | null }>,
  dayStart = 8 * 60,
  dayEnd = 21 * 60,
): TimedBlock[] {
  const items = rows
    .map((row) => {
      const startMin = Math.max(dayStart, parseTimeMinutes(row.start_time));
      const endMin = Math.min(dayEnd, parseTimeMinutes(row.end_time) || startMin + 60);
      return { id: row.id, startMin, endMin, column: 0 };
    })
    .sort((a, b) => a.startMin - b.startMin);
  const columns: TimedBlock[][] = [];
  for (const item of items) {
    let placed = false;
    for (const col of columns) {
      const last = col[col.length - 1];
      if (last.endMin <= item.startMin) {
        item.column = columns.indexOf(col);
        col.push(item);
        placed = true;
        break;
      }
    }
    if (!placed) {
      item.column = columns.length;
      columns.push([item]);
    }
  }
  return items;
}

export function entryPatchId(row: CalendarEntry) {
  return row.entry_id || row.id.split(":")[0];
}
