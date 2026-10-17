import type { CalendarLoad } from "../calendarApi";

type Props = {
  load: CalendarLoad[];
  people: Map<string, string>;
  dates: string[];
};

export function WorkloadStrip({ load, people, dates }: Props) {
  if (!load.length) return null;
  const max = Math.max(...load.map((row) => row.count), 1);
  const byPerson = new Map<string, CalendarLoad[]>();
  for (const row of load) {
    byPerson.set(row.person_id, [...(byPerson.get(row.person_id) ?? []), row]);
  }
  return (
    <div className="cal2-load">
      {[...byPerson.entries()].slice(0, 6).map(([id, rows]) => (
        <div key={id} className="cal2-load-row">
          <span className="cal2-load-name">{people.get(id) || "—"}</span>
          <div className="cal2-load-bars">
            {dates.map((day) => {
              const hit = rows.find((row) => row.date === day);
              const count = hit?.count ?? 0;
              return (
                <span
                  key={day}
                  className="cal2-load-bar"
                  style={{ height: `${(count / max) * 100}%` }}
                  title={`${count}`}
                />
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
