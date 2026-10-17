import { formatJalaliLong } from "../jalali";
import type { CalendarEntry } from "../calendarApi";
import { STATUSES as STATUS_OPTS } from "./constants";
import { tierLabel } from "./helpers";

function statusLabelLocal(value: string) {
  return STATUS_OPTS.find((row) => row.value === value)?.label ?? value;
}

type Props = {
  entries: CalendarEntry[];
  readOnly: boolean;
  onPatch: (id: string, body: Record<string, unknown>) => void;
  onRemove: (id: string) => void;
  onOpen?: (row: CalendarEntry) => void;
};

export function ContentTable({ entries, readOnly, onOpen }: Props) {
  const rows = entries.filter((row) => row.entry_type === "content");
  return (
    <div className="cal2-table-wrap">
      <table className="cal2-table">
        <thead>
          <tr>
            <th>تاریخ</th><th>کمپین</th><th>فرمت</th><th>کانال</th><th>موضوع</th><th>تولید</th><th>وضعیت</th><th>لینک</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={readOnly && onOpen ? "cal2-table-row-hit" : undefined}
              onClick={readOnly && onOpen ? () => onOpen(row) : undefined}
              onKeyDown={
                readOnly && onOpen
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onOpen(row);
                      }
                    }
                  : undefined
              }
              tabIndex={readOnly && onOpen ? 0 : undefined}
              role={readOnly && onOpen ? "button" : undefined}
            >
              <td>{formatJalaliLong(row.on_date)}</td>
              <td>{tierLabel(row.tier)}</td>
              <td>{row.format}</td>
              <td>{row.channel}</td>
              <td>{row.topic}</td>
              <td>{row.production_status}</td>
              <td>{statusLabelLocal(row.status)}</td>
              <td>{row.published_url || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
