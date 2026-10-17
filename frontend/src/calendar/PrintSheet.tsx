import { formatJalaliLong } from "../jalali";
import type { CalendarEntry, CalendarMonth } from "../calendarApi";
import { tierLabel } from "./helpers";
import { STATUSES } from "./constants";

function statusLabel(value: string) {
  return STATUSES.find((row) => row.value === value)?.label ?? value;
}

type Props = {
  monthName: string;
  header: CalendarMonth | null;
  entries: CalendarEntry[];
};

export function PrintSheet({ monthName, header, entries }: Props) {
  const content = entries.filter((row) => row.entry_type === "content");
  return (
    <div className="cal2-print">
      <h1>{header?.title || `تقویم محتوا — ${monthName}`}</h1>
      {header?.goal ? <p>{header.goal}</p> : null}
      <table className="cal2-table">
        <thead>
          <tr>
            <th>تاریخ</th><th>کمپین</th><th>فرمت</th><th>کانال</th><th>موضوع</th><th>وضعیت</th>
          </tr>
        </thead>
        <tbody>
          {content.map((row) => (
            <tr key={row.id}>
              <td>{formatJalaliLong(row.on_date)}</td>
              <td>{tierLabel(row.tier)}</td>
              <td>{row.format}</td>
              <td>{row.channel}</td>
              <td>{row.topic}</td>
              <td>{statusLabel(row.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
