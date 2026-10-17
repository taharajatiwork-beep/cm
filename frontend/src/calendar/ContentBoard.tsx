import type { CalendarEntry } from "../calendarApi";
import { PRODUCTION_STATUSES } from "./constants";

type Props = {
  entries: CalendarEntry[];
  readOnly: boolean;
  onStatus: (entryId: string, status: string) => void;
};

export function ContentBoard({ entries, readOnly, onStatus }: Props) {
  const content = entries.filter((row) => row.entry_type === "content");
  return (
    <div className="cal2-board">
      {PRODUCTION_STATUSES.map((col) => {
        const cards = content.filter((row) => row.production_status === col.value);
        return (
          <div
            key={col.value}
            className="cal2-board-col"
            onDragOver={(e) => {
              if (!readOnly) e.preventDefault();
            }}
            onDrop={(e) => {
              if (readOnly) return;
              e.preventDefault();
              const entryId = e.dataTransfer.getData("entry_id");
              if (entryId) onStatus(entryId, col.value);
            }}
          >
            <h4>{col.label} ({cards.length})</h4>
            {cards.map((row) => (
              <div
                key={row.id}
                className="cal2-board-card"
                draggable={!readOnly}
                onDragStart={(e) => e.dataTransfer.setData("entry_id", row.entry_id)}
              >
                <strong>{row.topic}</strong>
                <span className="muted">{row.format} · {row.channel}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
