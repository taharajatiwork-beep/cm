import type { CalendarEntry, CalendarMonth } from "../calendarApi";
import { Badge, Button, Card, Field, Input } from "../components/ui";

type Props = {
  header: CalendarMonth | null;
  entries: CalendarEntry[];
  title: string;
  goal: string;
  readOnly: boolean;
  onTitle: (v: string) => void;
  onGoal: (v: string) => void;
  onSave: () => void;
  busy: boolean;
};

export function MonthHeaderCard({ header, entries, title, goal, readOnly, onTitle, onGoal, onSave, busy }: Props) {
  const content = entries.filter((row) => row.entry_type === "content");
  const byFormat = new Map<string, number>();
  const byTier = new Map<string, number>();
  for (const row of content) {
    const f = row.format || "—";
    byFormat.set(f, (byFormat.get(f) ?? 0) + 1);
    byTier.set(row.tier, (byTier.get(row.tier) ?? 0) + 1);
  }
  if (readOnly && !header) return null;
  return (
    <Card className="cal2-header-card">
      <h3>{header?.title || title || "تقویم ماه"}</h3>
      {(header?.goal || goal) ? <p>{header?.goal || goal}</p> : null}
      {header?.mix?.length ? (
        <div className="cal2-mix">
          <span className="muted">برنامه:</span>
          {header.mix.map((row) => (
            <Badge key={row.label}>{row.label} {row.share}٪</Badge>
          ))}
        </div>
      ) : null}
      {content.length ? (
        <div className="cal2-mix">
          <span className="muted">واقعی:</span>
          {[...byFormat.entries()].map(([label, count]) => (
            <Badge key={label}>{label} ×{count}</Badge>
          ))}
          {[...byTier.entries()].map(([label, count]) => (
            <Badge key={`t-${label}`}>{label} ×{count}</Badge>
          ))}
        </div>
      ) : null}
      {!readOnly ? (
        <div className="row">
          <Field label="عنوان"><Input value={title || header?.title || ""} onChange={(e) => onTitle(e.target.value)} /></Field>
          <Field label="هدف"><Input value={goal || header?.goal || ""} onChange={(e) => onGoal(e.target.value)} /></Field>
          <Button type="button" className="btn-sm" disabled={busy} onClick={onSave}>ذخیرهٔ سربرگ</Button>
        </div>
      ) : null}
    </Card>
  );
}
