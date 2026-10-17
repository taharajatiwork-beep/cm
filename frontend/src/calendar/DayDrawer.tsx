import { Link } from "react-router-dom";
import { Badge, Sheet } from "../components/ui";
import { formatJalaliLong } from "../jalali";
import type { CalendarEntry, CalendarEvent, CalendarOccasion } from "../calendarApi";
import { lateDay, tierLabel, tierTone } from "./helpers";

type Props = {
  iso: string;
  onClose: () => void;
  entries: CalendarEntry[];
  events: CalendarEvent[];
  occasions: CalendarOccasion[];
  readOnly: boolean;
  onAdd: () => void;
  onEdit: (row: CalendarEntry) => void;
};

export function DayDrawer({ iso, onClose, entries, events, occasions, readOnly, onAdd, onEdit }: Props) {
  const dayOcc = occasions.filter((row) => row.on_date === iso);
  const content = entries.filter((row) => row.entry_type === "content");
  const meetings = entries.filter((row) => row.entry_type === "event");
  return (
    <Sheet open onClose={onClose} title={formatJalaliLong(iso) ?? iso}>
      <div className="stack cal2-drawer">
        {dayOcc.length ? (
          <section>
            <h4>مناسبت</h4>
            {dayOcc.map((row) => (
              <p key={row.id}>{row.title}</p>
            ))}
          </section>
        ) : null}
        <section>
          <div className="row">
            <h4>محتوا و رویداد</h4>
            {!readOnly ? (
              <button type="button" className="btn btn-ghost btn-sm" onClick={onAdd}>افزودن</button>
            ) : null}
          </div>
          {content.map((row) => (
            <button key={row.id} type="button" className="cal2-drawer-item" onClick={() => onEdit(row)}>
              <Badge tone={tierTone(row.tier)}>{tierLabel(row.tier)}</Badge> {row.topic}
            </button>
          ))}
          {meetings.map((row) => (
            <button key={row.id} type="button" className="cal2-drawer-item" onClick={() => onEdit(row)}>
              {row.title} {row.start_time ? `· ${row.start_time}` : ""}
            </button>
          ))}
        </section>
        <section>
          <h4>کار و مارکتینگ</h4>
          {events.length === 0 ? <p className="muted">موردی نیست</p> : null}
          {events.map((row) => (
            <p key={row.id} className={lateDay(row.date, row.status) ? "is-late" : ""}>
              <Link to={row.link}>{row.title}</Link>
            </p>
          ))}
        </section>
      </div>
    </Sheet>
  );
}
