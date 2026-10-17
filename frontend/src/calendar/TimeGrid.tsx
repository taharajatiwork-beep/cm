import { Link } from "react-router-dom";
import type { CalendarEntry, CalendarEvent } from "../calendarApi";
import { layoutTimedEvents, lateDay, todayIso } from "./helpers";

const HOURS = Array.from({ length: 14 }, (_, i) => 8 + i);

type Props = {
  dayIso: string;
  entries: CalendarEntry[];
  events: CalendarEvent[];
  readOnly: boolean;
  onMoveEntry: (entryId: string, toDate: string, occurrenceDate?: string, start?: string, end?: string) => void;
};

export function TimeGrid({ dayIso, entries, events, readOnly, onMoveEntry }: Props) {
  const allDayEntries = entries.filter((row) => row.all_day || row.entry_type === "content");
  const timed = entries.filter((row) => row.entry_type === "event" && !row.all_day && row.start_time);
  const layout = layoutTimedEvents(timed);
  const now = new Date();
  const nowLine =
    dayIso === todayIso() ? ((now.getHours() * 60 + now.getMinutes() - 8 * 60) / (13 * 60)) * 100 : null;

  return (
    <div className="cal2-time">
      <div className="cal2-allday">
        <span className="cal2-allday-label">تمام‌روز</span>
        <div className="cal2-allday-items">
          {allDayEntries.map((row) => (
            <span key={row.id} className="cal2-chip cal2-chip--content">{row.title || row.topic}</span>
          ))}
          {events.map((row) => (
            <Link key={row.id} to={row.link} className={`cal2-chip cal2-chip--work${lateDay(row.date, row.status) ? " is-late" : ""}`}>
              {row.title}
            </Link>
          ))}
        </div>
      </div>
      <div className="cal2-time-body">
        {nowLine !== null && nowLine >= 0 && nowLine <= 100 ? (
          <div className="cal2-now" style={{ top: `${nowLine}%` }} />
        ) : null}
        <div className="cal2-hours">
          {HOURS.map((h) => (
            <div key={h} className="cal2-hour">
              <span>{h}:00</span>
            </div>
          ))}
        </div>
        <div
          className="cal2-slots"
          onDragOver={(e) => {
            if (!readOnly) e.preventDefault();
          }}
          onDrop={(e) => {
            if (readOnly) return;
            e.preventDefault();
            const entryId = e.dataTransfer.getData("entry_id");
            const occ = e.dataTransfer.getData("occurrence_date");
            const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
            const ratio = (e.clientY - rect.top) / rect.height;
            const minutes = Math.round(8 * 60 + ratio * 13 * 60);
            const h = Math.floor(minutes / 60);
            const m = minutes % 60;
            const start = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
            const endH = Math.min(21, h + 1);
            const end = `${String(endH).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
            if (entryId) onMoveEntry(entryId, dayIso, occ || undefined, start, end);
          }}
        >
          {layout.map((block) => {
            const row = timed.find((item) => item.id === block.id);
            if (!row) return null;
            const top = ((block.startMin - 8 * 60) / (13 * 60)) * 100;
            const height = ((block.endMin - block.startMin) / (13 * 60)) * 100;
            const width = 100 / (layout.filter((b) => b.column === block.column).length || 1);
            return (
              <div
                key={row.id}
                className="cal2-event-block"
                style={{
                  top: `${top}%`,
                  height: `${Math.max(height, 4)}%`,
                  left: `${block.column * width}%`,
                  width: `${width}%`,
                }}
                draggable={!readOnly}
                onDragStart={(e) => {
                  e.dataTransfer.setData("entry_id", row.entry_id);
                  if (row.id.includes(":")) e.dataTransfer.setData("occurrence_date", row.on_date);
                }}
              >
                {row.title}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
