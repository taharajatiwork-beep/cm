/** Client-side helpers for collaboration-first UX (no jargon). */
import { faDigits } from "../fa";
import { formatJalali } from "../jalali";

export type PersonMap = Map<string, string>;

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

export function buildPersonMap(people: Array<Record<string, unknown>>): PersonMap {
  const m = new Map<string, string>();
  for (const p of people) m.set(String(p.id), String(p.full_name));
  return m;
}

export function personName(map: PersonMap, id: unknown, fallback = "—"): string {
  if (id == null) return fallback;
  return map.get(String(id)) || String(id).slice(0, 8);
}

export function formatDeadline(
  value: unknown,
  bi: (en: string, fa: string) => string,
  _locale: "en" | "fa" = "en",
): string | null {
  if (!value) return null;
  const d = new Date(String(value));
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const time = faDigits(`${pad2(d.getHours())}:${pad2(d.getMinutes())}`);
  if (sameDay) return `${bi("Due", "مهلت")}: ${time}`;
  const date = formatJalali(d);
  return `${bi("Due", "مهلت")}: ${date ?? ""} ${time}`.trim();
}

export function isOverdue(value: unknown, status?: unknown): boolean {
  if (!value || status === "COMPLETED" || status === "CANCELLED") return false;
  return new Date(String(value)) < new Date();
}

export type StoryLine = {
  text: string;
  done?: boolean;
  waiting?: boolean;
};

export type AttentionStory = {
  id: string;
  title: string;
  href: string;
  lines: StoryLine[];
  deadline?: string | null;
  tone?: "warn" | "danger";
  kind: "shared" | "branch" | "campaign" | "task" | "alert";
  waitingOnMe?: boolean;
};

export function taskMark(status: string): "✓" | "◷" | "○" {
  if (status === "COMPLETED") return "✓";
  if (status === "BLOCKED" || status === "IN_PROGRESS" || status === "ASSIGNED") return "◷";
  return "○";
}

export function assigneeNames(
  assignees: unknown,
  map: PersonMap,
  bi: (en: string, fa: string) => string,
): string {
  if (!Array.isArray(assignees) || assignees.length === 0) {
    return bi("Unassigned", "بدون مسئول");
  }
  const names = assignees
    .filter((a: Record<string, unknown>) => a.role !== "OWNER")
    .map((a: Record<string, unknown>) => personName(map, a.user_id));
  return names.filter(Boolean).join("، ") || bi("Unassigned", "بدون مسئول");
}
