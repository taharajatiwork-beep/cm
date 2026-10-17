import { useState } from "react";
import { formatJalaliLong } from "../jalali";
import type { CalendarEntry } from "../calendarApi";
import { Button, Input, Select } from "../components/ui";
import { PRODUCTION_STATUSES, STATUSES, TIERS } from "./constants";
import { tierLabel } from "./helpers";
import { STATUSES as STATUS_OPTS } from "./constants";

function statusLabelLocal(value: string) {
  return STATUS_OPTS.find((row) => row.value === value)?.label ?? value;
}

type Props = {
  entries: CalendarEntry[];
  readOnly: boolean;
  onPatch: (id: string, body: Record<string, unknown>) => void;
  onRemove: (id: string) => void;
};

export function ContentTable({ entries, readOnly, onPatch, onRemove }: Props) {
  const rows = entries.filter((row) => row.entry_type === "content");
  return (
    <div className="cal2-table-wrap">
      <table className="cal2-table">
        <thead>
          <tr>
            <th>تاریخ</th><th>کمپین</th><th>فرمت</th><th>کانال</th><th>موضوع</th><th>تولید</th><th>وضعیت</th><th>لینک</th><th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <EntryRow key={row.id} row={row} readOnly={readOnly} onPatch={onPatch} onRemove={onRemove} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EntryRow({
  row,
  readOnly,
  onPatch,
  onRemove,
}: {
  row: CalendarEntry;
  readOnly: boolean;
  onPatch: (id: string, body: Record<string, unknown>) => void;
  onRemove: (id: string) => void;
}) {
  const [topic, setTopic] = useState(row.topic);
  const [format, setFormat] = useState(row.format);
  const [channel, setChannel] = useState(row.channel);
  const [publishedUrl, setPublishedUrl] = useState(row.published_url);
  const id = row.entry_id;
  if (readOnly) {
    return (
      <tr>
        <td>{formatJalaliLong(row.on_date)}</td>
        <td>{tierLabel(row.tier)}</td>
        <td>{row.format}</td>
        <td>{row.channel}</td>
        <td>{row.topic}</td>
        <td>{row.production_status}</td>
        <td>{statusLabelLocal(row.status)}</td>
        <td>{row.published_url}</td>
        <td />
      </tr>
    );
  }
  return (
    <tr>
      <td>{formatJalaliLong(row.on_date)}</td>
      <td>
        <Select value={row.tier} onChange={(e) => onPatch(id, { tier: e.target.value })}>
          {TIERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </Select>
      </td>
      <td><Input value={format} onChange={(e) => setFormat(e.target.value)} /></td>
      <td><Input value={channel} onChange={(e) => setChannel(e.target.value)} /></td>
      <td><Input className="topic" value={topic} onChange={(e) => setTopic(e.target.value)} /></td>
      <td>
        <Select value={row.production_status} onChange={(e) => onPatch(id, { production_status: e.target.value })}>
          {PRODUCTION_STATUSES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </Select>
      </td>
      <td>
        <Select value={row.status} onChange={(e) => onPatch(id, { status: e.target.value })}>
          {STATUSES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </Select>
      </td>
      <td><Input value={publishedUrl} onChange={(e) => setPublishedUrl(e.target.value)} /></td>
      <td>
        <div className="row">
          <Button type="button" variant="secondary" className="btn-sm" onClick={() => onPatch(id, { topic, format, channel, published_url: publishedUrl })}>ذخیره</Button>
          <Button type="button" variant="danger-quiet" className="btn-sm" onClick={() => onRemove(id)}>حذف</Button>
        </div>
      </td>
    </tr>
  );
}
