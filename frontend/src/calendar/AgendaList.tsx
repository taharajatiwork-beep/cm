import { Link } from "react-router-dom";
import { addDaysIso } from "../jalali";
import { formatJalaliLong } from "../jalali";
import type { CalendarEntry, CalendarEvent } from "../calendarApi";
import { lateDay } from "./helpers";

type Props = {
  anchor: string;
  entries: CalendarEntry[];
  events: CalendarEvent[];
  days?: number;
};

export function AgendaList({ anchor, entries, events, days = 14 }: Props) {
  const rows: Array<{ iso: string; entries: CalendarEntry[]; events: CalendarEvent[] }> = [];
  for (let i = 0; i < days; i += 1) {
    const iso = addDaysIso(anchor, i);
    rows.push({
      iso,
      entries: entries.filter((row) => row.on_date === iso),
      events: events.filter((row) => row.date === iso),
    });
  }
  return (
    <div className="cal2-agenda stack">
      {rows.map((day) => (
        <section key={day.iso} className="cal2-agenda-day">
          <h3>{formatJalaliLong(day.iso) ?? day.iso}</h3>
          {day.entries.length === 0 && day.events.length === 0 ? (
            <p className="muted">—</p>
          ) : (
            <ul>
              {day.entries.map((row) => (
                <li key={row.id}>{row.entry_type === "event" ? row.title : row.topic}</li>
              ))}
              {day.events.map((row) => (
                <li key={row.id} className={lateDay(row.date, row.status) ? "is-late" : ""}>
                  <Link to={row.link}>{row.title}</Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
