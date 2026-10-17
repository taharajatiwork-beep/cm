import { Link } from "react-router-dom";
import type { CalendarEntry, CalendarEvent, CalendarOccasion } from "../calendarApi";
import type { JalaliCell } from "../jalali";
import { faDigits } from "../fa";
import { MARKETING_KINDS, WEEKDAYS } from "./constants";
import { lateDay, tierLabel, todayIso } from "./helpers";

type Props = {
  weeks: JalaliCell[][];
  entries: CalendarEntry[];
  events: CalendarEvent[];
  occasions: CalendarOccasion[];
  selected: string;
  readOnly: boolean;
  onSelect: (iso: string) => void;
  onMoveEntry: (entryId: string, toDate: string, occurrenceDate?: string) => void;
};

const MAX_CHIPS = 4;

type DayChip =
  | { type: "entry"; key: string; entry: CalendarEntry }
  | { type: "event"; key: string; event: CalendarEvent };

function occasionForDay(rows: CalendarOccasion[], iso: string) {
  return rows.filter((row) => row.on_date === iso);
}

function chipsForDay(entries: CalendarEntry[], events: CalendarEvent[], iso: string): DayChip[] {
  const out: DayChip[] = [];
  for (const entry of entries) {
    if (entry.on_date !== iso) continue;
    out.push({ type: "entry", key: `e-${entry.id}`, entry });
  }
  for (const event of events) {
    if (event.date !== iso) continue;
    out.push({ type: "event", key: `w-${event.id}`, event });
  }
  out.sort((a, b) => {
    const lateA =
      a.type === "entry"
        ? Boolean(a.entry.late)
        : lateDay(a.event.date, a.event.status);
    const lateB =
      b.type === "entry"
        ? Boolean(b.entry.late)
        : lateDay(b.event.date, b.event.status);
    if (lateA !== lateB) return lateA ? -1 : 1;
    return 0;
  });
  return out;
}

function eventChipClass(event: CalendarEvent) {
  if (event.kind === "mizito") return "cal2-chip--mizito";
  if (MARKETING_KINDS.has(event.kind)) return "cal2-chip--marketing";
  return "cal2-chip--work";
}

function entryLabel(entry: CalendarEntry) {
  if (entry.entry_type === "event") return entry.title;
  const topic = entry.topic || entry.format || entry.title || "محتوا";
  return `${tierLabel(entry.tier)} · ${topic}`;
}

export function MonthGrid({ weeks, entries, events, occasions, selected, readOnly, onSelect, onMoveEntry }: Props) {
  const today = todayIso();
  return (
    <div className="cal2-month cal2-month-card">
      <div className="cal2-grid cal2-head-row">
        {WEEKDAYS.map((name) => (
          <div className="cal2-head" key={name}>{name}</div>
        ))}
      </div>
      {weeks.map((row) => (
        <div className="cal2-grid cal2-week-row" key={row[0].iso}>
          {row.map((cell) => {
            const dayOcc = occasionForDay(occasions, cell.iso);
            const isFriday = row.indexOf(cell) === 6;
            const isHoliday = dayOcc.some((o) => o.is_off);
            const allChips = chipsForDay(entries, events, cell.iso);
            const visible = allChips.slice(0, MAX_CHIPS);
            const extra = allChips.length - visible.length;
            return (
              <div
                key={cell.iso}
                className={`cal2-day${cell.inMonth ? "" : " is-out"}${cell.iso === today ? " is-today" : ""}${cell.iso === selected ? " is-selected" : ""}${isFriday || isHoliday ? " is-off" : ""}`}
                onDragOver={(event) => {
                  if (!readOnly) event.preventDefault();
                }}
                onDrop={(event) => {
                  if (readOnly) return;
                  event.preventDefault();
                  const entryId = event.dataTransfer.getData("entry_id");
                  const occ = event.dataTransfer.getData("occurrence_date");
                  if (entryId) onMoveEntry(entryId, cell.iso, occ || undefined);
                }}
              >
                <button
                  type="button"
                  className="cal2-day-btn"
                  onClick={() => onSelect(cell.iso)}
                  aria-pressed={selected === cell.iso}
                  aria-label={cell.iso}
                >
                  <span className="cal2-day-num">{faDigits(String(cell.day))}</span>
                  {dayOcc[0] ? <span className="cal2-occasion">{dayOcc[0].title}</span> : null}
                </button>
                <div className="cal2-chips">
                  {visible.map((chip) => {
                    if (chip.type === "entry") {
                      const item = chip.entry;
                      return (
                        <span
                          key={chip.key}
                          className={`cal2-chip cal2-chip--${item.entry_type}${item.late ? " is-late" : ""}`}
                          draggable={!readOnly}
                          title={entryLabel(item)}
                          onDragStart={(event) => {
                            event.dataTransfer.setData("entry_id", item.entry_id);
                            if (item.id.includes(":")) event.dataTransfer.setData("occurrence_date", item.on_date);
                          }}
                        >
                          {entryLabel(item)}
                        </span>
                      );
                    }
                    const item = chip.event;
                    const late = lateDay(item.date, item.status);
                    return (
                      <Link
                        key={chip.key}
                        to={item.link}
                        className={`cal2-chip cal2-chip-link ${eventChipClass(item)}${late ? " is-late" : ""}`}
                        title={item.title}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {item.title}
                      </Link>
                    );
                  })}
                  {extra > 0 ? (
                    <button type="button" className="cal2-more" onClick={() => onSelect(cell.iso)}>
                      +{faDigits(String(extra))} دیگر
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
