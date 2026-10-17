import type { CalendarEntry, CalendarEvent, CalendarOccasion } from "../calendarApi";
import type { JalaliCell } from "../jalali";
import { faDigits } from "../fa";
import { WEEKDAYS } from "./constants";
import { tierLabel, todayIso } from "./helpers";

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

function occasionForDay(rows: CalendarOccasion[], iso: string) {
  return rows.filter((row) => row.on_date === iso);
}

export function MonthGrid({ weeks, entries, events, occasions, selected, readOnly, onSelect, onMoveEntry }: Props) {
  const today = todayIso();
  return (
    <div className="cal2-month">
      <div className="cal2-grid cal2-head-row">
        {WEEKDAYS.map((name) => (
          <div className="cal2-head" key={name}>{name}</div>
        ))}
      </div>
      {weeks.map((row) => (
        <div className="cal2-grid" key={row[0].iso}>
          {row.map((cell) => {
            const dayEntries = entries.filter((item) => item.on_date === cell.iso);
            const dayEvents = events.filter((item) => item.date === cell.iso);
            const dayOcc = occasionForDay(occasions, cell.iso);
            const isFriday = row.indexOf(cell) === 6;
            const isHoliday = dayOcc.some((o) => o.is_off);
            const chips = dayEntries.slice(0, 3);
            const extra = dayEntries.length - chips.length;
            return (
              <div
                key={cell.iso}
                className={`cal2-day${cell.inMonth ? "" : " is-out"}${cell.iso === today ? " is-today" : ""}${isFriday || isHoliday ? " is-off" : ""}`}
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
                <button type="button" className="cal2-day-btn" onClick={() => onSelect(cell.iso)} aria-pressed={selected === cell.iso}>
                  <span className="cal2-day-num">{faDigits(String(cell.day))}</span>
                  {dayOcc[0] ? <span className="cal2-occasion">{dayOcc[0].title}</span> : null}
                </button>
                <div className="cal2-chips">
                  {chips.map((item) => (
                    <span
                      key={item.id}
                      className={`cal2-chip cal2-chip--${item.entry_type}${item.late ? " is-late" : ""}`}
                      draggable={!readOnly}
                      onDragStart={(event) => {
                        event.dataTransfer.setData("entry_id", item.entry_id);
                        if (item.id.includes(":")) event.dataTransfer.setData("occurrence_date", item.on_date);
                      }}
                    >
                      {item.entry_type === "event" ? item.title : `${tierLabel(item.tier)} · ${item.format || item.topic}`}
                    </span>
                  ))}
                  {extra > 0 ? <span className="cal2-more">+{extra}</span> : null}
                  {dayEvents.length ? (
                    <span className="cal2-chip cal2-chip--work">{dayEvents.length} کار</span>
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
