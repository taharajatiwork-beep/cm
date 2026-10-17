import { useEffect, useState } from "react";
import { api } from "../api";
import type { CalendarEntry } from "../calendarApi";
import { Button, Dialog, Field, Input, Select } from "../components/ui";
import { PRODUCTION_STATUSES, STATUSES, TIERS } from "./constants";

type Props = {
  open: boolean;
  initial?: Partial<CalendarEntry> | null;
  defaultDate: string;
  onClose: () => void;
  onSave: (body: Record<string, unknown>) => void;
  busy?: boolean;
};

export function EntryDialog({ open, initial, defaultDate, onClose, onSave, busy }: Props) {
  const [entryType, setEntryType] = useState("content");
  const [onDate, setOnDate] = useState(defaultDate);
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [allDay, setAllDay] = useState(true);
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("10:00");
  const [tier, setTier] = useState("long");
  const [format, setFormat] = useState("");
  const [channel, setChannel] = useState("");
  const [productionStatus, setProductionStatus] = useState("idea");
  const [status, setStatus] = useState("todo");
  const [recurrence, setRecurrence] = useState("none");
  const [recurUntil, setRecurUntil] = useState("");
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [publishedUrl, setPublishedUrl] = useState("");
  const [attendeeIds, setAttendeeIds] = useState<string[]>([]);
  const [people, setPeople] = useState<Array<{ id: string; name: string }>>([]);
  const [scope, setScope] = useState<"this" | "all" | "">("");

  useEffect(() => {
    if (!open) return;
    void api.people.list().then((rows) => {
      setPeople(
        rows.map((row) => ({
          id: String(row.id),
          name: String(row.full_name || row.email || row.id),
        })),
      );
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setEntryType(initial?.entry_type || "content");
    setOnDate(initial?.on_date || defaultDate);
    setTitle(initial?.title || "");
    setTopic(initial?.topic || "");
    setAllDay(initial?.all_day ?? true);
    setStartTime(initial?.start_time?.slice(0, 5) || "09:00");
    setEndTime(initial?.end_time?.slice(0, 5) || "10:00");
    setTier(initial?.tier || "long");
    setFormat(initial?.format || "");
    setChannel(initial?.channel || "");
    setProductionStatus(initial?.production_status || "idea");
    setStatus(initial?.status || "todo");
    setRecurrence(initial?.recurrence || "none");
    setRecurUntil(initial?.recur_until || "");
    setLocation(initial?.location || "");
    setNotes(initial?.notes || "");
    setPublishedUrl(initial?.published_url || "");
    setAttendeeIds(initial?.attendee_ids || []);
    setScope("");
  }, [open, initial, defaultDate]);

  if (!open) return null;

  const isRecurringEdit = Boolean(
    initial?.recurrence && initial.recurrence !== "none" && initial.id && initial.id.includes(":"),
  );

  function submit() {
    const body: Record<string, unknown> = {
      on_date: onDate,
      entry_type: entryType,
      title,
      topic: topic || title,
      all_day: allDay,
      tier,
      format,
      channel,
      production_status: productionStatus,
      status,
      recurrence,
      recur_until: recurUntil || null,
      location,
      notes,
      published_url: publishedUrl,
      attendee_ids: attendeeIds,
    };
    if (!allDay && entryType === "event") {
      body.start_time = startTime;
      body.end_time = endTime;
    }
    if (isRecurringEdit && scope) {
      body.scope = scope;
      body.occurrence_date = initial?.on_date;
    }
    onSave(body);
  }

  return (
    <Dialog onClose={onClose} label={initial ? "ویرایش" : "ردیف تقویم"}>
      <div className="stack">
        <Field label="نوع">
          <Select value={entryType} onChange={(e) => setEntryType(e.target.value)}>
            <option value="content">محتوا</option>
            <option value="event">رویداد</option>
          </Select>
        </Field>
        <Field label="تاریخ"><Input type="date" value={onDate} onChange={(e) => setOnDate(e.target.value)} /></Field>
        {entryType === "event" ? (
          <>
            <Field label="عنوان"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
            <label className="row">
              <input type="checkbox" checked={allDay} onChange={(e) => setAllDay(e.target.checked)} />
              تمام‌روز
            </label>
            {!allDay ? (
              <div className="row">
                <Field label="شروع"><Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} /></Field>
                <Field label="پایان"><Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} /></Field>
              </div>
            ) : null}
            <Field label="مکان"><Input value={location} onChange={(e) => setLocation(e.target.value)} /></Field>
            <Field label="شرکت‌کنندگان">
              <Select
                multiple
                value={attendeeIds}
                onChange={(e) => {
                  const selected = [...e.target.selectedOptions].map((opt) => opt.value);
                  setAttendeeIds(selected);
                }}
              >
                {people.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </Select>
            </Field>
          </>
        ) : (
          <>
            <Field label="موضوع"><Input value={topic} onChange={(e) => setTopic(e.target.value)} /></Field>
            <Field label="کمپین">
              <Select value={tier} onChange={(e) => setTier(e.target.value)}>
                {TIERS.map((row) => <option key={row.value} value={row.value}>{row.label}</option>)}
              </Select>
            </Field>
            <Field label="فرمت"><Input value={format} onChange={(e) => setFormat(e.target.value)} /></Field>
            <Field label="کانال"><Input value={channel} onChange={(e) => setChannel(e.target.value)} /></Field>
            <Field label="وضعیت تولید">
              <Select value={productionStatus} onChange={(e) => setProductionStatus(e.target.value)}>
                {PRODUCTION_STATUSES.map((row) => <option key={row.value} value={row.value}>{row.label}</option>)}
              </Select>
            </Field>
            <Field label="لینک انتشار"><Input value={publishedUrl} onChange={(e) => setPublishedUrl(e.target.value)} /></Field>
          </>
        )}
        <Field label="تکرار">
          <Select value={recurrence} onChange={(e) => setRecurrence(e.target.value)}>
            <option value="none">بدون</option>
            <option value="daily">روزانه</option>
            <option value="weekly">هفتگی</option>
            <option value="monthly">ماهانه</option>
          </Select>
        </Field>
        {recurrence !== "none" ? (
          <Field label="تا تاریخ"><Input type="date" value={recurUntil} onChange={(e) => setRecurUntil(e.target.value)} /></Field>
        ) : null}
        <Field label="وضعیت">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((row) => <option key={row.value} value={row.value}>{row.label}</option>)}
          </Select>
        </Field>
        <Field label="یادداشت"><Input value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        {isRecurringEdit ? (
          <Field label="ویرایش تکرار">
            <Select value={scope} onChange={(e) => setScope(e.target.value as "this" | "all")}>
              <option value="">انتخاب کنید</option>
              <option value="this">فقط این بار</option>
              <option value="all">همه</option>
            </Select>
          </Field>
        ) : null}
        <div className="row">
          <Button type="button" disabled={busy || (isRecurringEdit && !scope)} onClick={submit}>ذخیره</Button>
          <Button type="button" variant="secondary" onClick={onClose}>انصراف</Button>
        </div>
      </div>
    </Dialog>
  );
}
