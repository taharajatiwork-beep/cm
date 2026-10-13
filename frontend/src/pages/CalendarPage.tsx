import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { canSeeCalendar } from "../lib/access";
import {
  calendarApi,
  type CalendarEntry,
  type CalendarEvent,
  type CalendarMonth,
  type DraftEntry,
} from "../calendarApi";
import {
  Badge,
  Button,
  Card,
  ForbiddenState,
  Field,
  Input,
  QueryState,
  SectionHeader,
  Segmented,
  Select,
  MoreMenu,
} from "../components/ui";
import { DELETE_CONFIRM_LABEL, useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { useBi } from "../i18n";
import { faDigits } from "../fa";
import { formatJalaliLong, gregorianToJalali, jalaliMonthGrid, PERSIAN_MONTHS, type JalaliCell } from "../jalali";

const WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];
const TIERS = [
  { value: "long", label: "بلندمدت", tone: "ok" as const },
  { value: "mid", label: "میان‌مدت", tone: "" as const },
  { value: "short", label: "کوتاه‌مدت", tone: "warn" as const },
  { value: "reactive", label: "واکنشی", tone: "danger" as const },
];
const STATUSES = [
  { value: "todo", label: "برنامه‌ریزی" },
  { value: "doing", label: "در جریان" },
  { value: "done", label: "انجام شد" },
];
const WORK_KINDS = new Set(["task", "work", "project", "request"]);
const MARKETING_KINDS = new Set(["campaign", "sms", "story"]);

const KINDS = [
  { value: "", label: "همه" },
  { value: "content", label: "محتوا" },
  { value: "work", label: "کار و پروژه" },
  { value: "marketing", label: "مارکتینگ" },
  { value: "shoot", label: "فیلم‌برداری" },
];

function eventMatchesKind(rowKind: string, filter: string) {
  if (!filter || filter === "content") return true;
  if (filter === "work") return WORK_KINDS.has(rowKind);
  if (filter === "marketing") return MARKETING_KINDS.has(rowKind);
  return rowKind === filter;
}
const DONE = new Set(["done", "COMPLETED", "CANCELLED", "sent"]);

function tierLabel(value: string) {
  return TIERS.find((row) => row.value === value)?.label ?? value;
}

function tierTone(value: string) {
  return TIERS.find((row) => row.value === value)?.tone ?? "";
}

function statusLabel(value: string) {
  return STATUSES.find((row) => row.value === value)?.label ?? value;
}

function todayIso() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function late(date: string, status: string) {
  return date < todayIso() && !DONE.has(status);
}

export function CalendarPage() {
  const { has, user } = useAuth();
  const accessUser = useMemo(
    () => ({
      roleCode: user?.roleCode,
      permissions: user?.permissions ?? [],
      teamId: user?.team_id,
      teamHomeTeamId: user?.team_home_team_id,
    }),
    [user?.roleCode, user?.permissions, user?.team_id, user?.team_home_team_id],
  );
  const allowed = canSeeCalendar(accessUser, has);
  const bi = useBi();
  const toast = useToast();
  const confirmDialog = useConfirm();
  const qc = useQueryClient();
  const now = gregorianToJalali(new Date().getFullYear(), new Date().getMonth() + 1, new Date().getDate());
  const [year, setYear] = useState(now[0]);
  const [month, setMonth] = useState(now[1]);
  const [view, setView] = useState<"month" | "week" | "table">("month");
  const [week, setWeek] = useState(0);
  const [kind, setKind] = useState("");
  const [person, setPerson] = useState("");
  const [selected, setSelected] = useState("");
  const [draft, setDraft] = useState<DraftEntry[] | null>(null);
  const [goal, setGoal] = useState("");
  const [title, setTitle] = useState("");
  const [fresh, setFresh] = useState({ topic: "", tier: "long", format: "", channel: "", on_date: "" });

  const weeks = useMemo(() => jalaliMonthGrid(year, month), [year, month]);
  const from = weeks[0][0].iso;
  const to = weeks[weeks.length - 1][6].iso;
  const query = useQuery({
    queryKey: ["calendar", from, to, year, month],
    queryFn: () => calendarApi.range(from, to, year, month),
    enabled: allowed,
  });

  const entries = query.data?.entries ?? [];
  const events = query.data?.events ?? [];
  const header = query.data?.month ?? null;
  useEffect(() => {
    setTitle(header?.title ?? "");
    setGoal(header?.goal ?? "");
  }, [header?.title, header?.goal, year, month]);
  const people = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of events) if (row.person_id && row.person) map.set(row.person_id, row.person);
    for (const row of entries) if (row.assignee_id && row.assignee_name) map.set(row.assignee_id, row.assignee_name);
    return [...map.entries()];
  }, [events, entries]);

  function showEvent(row: CalendarEvent) {
    if (kind === "content") return false;
    if (kind && !eventMatchesKind(row.kind, kind)) return false;
    if (person && row.person_id !== person) return false;
    return true;
  }
  function showEntry(row: CalendarEntry) {
    if (kind && kind !== "content") return false;
    if (person && row.assignee_id !== person) return false;
    return true;
  }
  const visibleEvents = kind === "content" ? [] : events.filter(showEvent);
  const visibleEntries = kind && kind !== "content" ? [] : entries.filter(showEntry);

  function shift(delta: number) {
    const next = month + delta;
    if (next < 1) {
      setYear((value) => value - 1);
      setMonth(12);
    } else if (next > 12) {
      setYear((value) => value + 1);
      setMonth(1);
    } else setMonth(next);
    setWeek(0);
    setSelected("");
    setDraft(null);
  }

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["calendar"] });
  }

  const saveEntry = useMutation({
    mutationFn: (body: Record<string, unknown>) => calendarApi.create(body),
    onSuccess: () => {
      toast("ردیف اضافه شد");
      setFresh({ topic: "", tier: "long", format: "", channel: "", on_date: "" });
      refresh();
    },
    onError: (error: Error) => toast(error.message),
  });
  const patchEntry = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => calendarApi.patch(id, body),
    onSuccess: () => refresh(),
    onError: (error: Error) => toast(error.message),
  });
  const removeEntry = useMutation({
    mutationFn: (id: string) => calendarApi.remove(id),
    onSuccess: () => {
      toast("ردیف حذف شد");
      refresh();
    },
  });
  const saveHeader = useMutation({
    mutationFn: () =>
      calendarApi.saveMonth(year, month, {
        title: title || header?.title || "",
        goal: goal || header?.goal || "",
        logic: header?.logic ?? [],
        weeks: header?.weeks ?? [],
        mix: header?.mix ?? [],
        kpis: header?.kpis ?? [],
        rules: header?.rules ?? [],
      }),
    onSuccess: () => {
      toast("سربرگ ماه ذخیره شد");
      refresh();
    },
    onError: (error: Error) => toast(error.message),
  });
  const makeDraft = useMutation({
    mutationFn: () => calendarApi.draft(year, month),
    onSuccess: (result) => {
      setDraft(result.entries);
      toast(result.source === "llm" ? "پیش‌نویس با هوش مصنوعی آماده است" : "پیش‌نویس با قالب آماده است");
    },
    onError: (error: Error) => toast(error.message),
  });
  const keepDraft = useMutation({
    mutationFn: () => calendarApi.bulk(draft ?? []),
    onSuccess: (result) => {
      toast(`${result.added} روز تازه ثبت شد`);
      setDraft(null);
      refresh();
    },
    onError: (error: Error) => toast(error.message),
  });

  if (!allowed) {
    return (
      <ForbiddenState
        titleEn="Calendar isn’t available for your role"
        titleFa="تقویم برای نقش شما فعال نیست"
        bodyEn="Content planning is for managers and marketing leads. Your own tasks stay on My Work."
        bodyFa="برنامهٔ محتوا برای مدیر و سرپرست مارکتینگ است. کارهای خودتان در «کارهای من» می‌ماند."
      />
    );
  }

  const monthName = faDigits(`${PERSIAN_MONTHS[month - 1]} ${year}`);
  const dayEntries = visibleEntries.filter((row) => row.on_date === selected);
  const dayEvents = visibleEvents.filter((row) => row.date === selected);

  return (
    <div className="stack">
      <div className="cal-screen stack">
        <SectionHeader
          title={bi("Calendar", "تقویم")}
          hint={bi("Content plan plus everyone's work", "برنامهٔ محتوا و کار همه")}
          action={
            <div className="row no-print">
              <Button type="button" variant="ghost" className="btn-sm" onClick={() => shift(-1)}>ماه قبل</Button>
              <strong>{monthName}</strong>
              <Button type="button" variant="ghost" className="btn-sm" onClick={() => shift(1)}>ماه بعد</Button>
              <Button
                type="button"
                variant="secondary"
                className="btn-sm"
                onClick={() => {
                  setView("table");
                  if (!fresh.on_date) setFresh((row) => ({ ...row, on_date: todayIso() }));
                }}
              >
                افزودن محتوا
              </Button>
              <MoreMenu label={bi("More", "بیشتر")}>
                <Button type="button" variant="ghost" className="btn-sm" disabled={makeDraft.isPending} onClick={() => makeDraft.mutate()}>
                  پیش‌نویس ماه
                </Button>
                <Button type="button" variant="ghost" className="btn-sm" onClick={() => window.print()}>چاپ</Button>
                <Button type="button" variant="ghost" className="btn-sm" onClick={() => void calendarApi.download(from, to).catch((error: Error) => toast(error.message))}>
                  اکسل
                </Button>
              </MoreMenu>
            </div>
          }
        />
        <QueryState isLoading={query.isLoading} error={query.error}>
          <MonthCard
            header={header}
            title={title}
            goal={goal}
            onTitle={setTitle}
            onGoal={setGoal}
            onSave={() => saveHeader.mutate()}
            busy={saveHeader.isPending}
          />
          {draft ? (
            <Card>
              <p>{draft.length} ردیف پیش‌نویس آماده است و هنوز ذخیره نشده. روزهایی که ردیف دارند عوض نمی‌شوند.</p>
              <div className="row">
                <Button type="button" className="btn-sm" disabled={keepDraft.isPending} onClick={() => keepDraft.mutate()}>ثبت پیش‌نویس</Button>
                <Button type="button" variant="ghost" className="btn-sm" onClick={() => setDraft(null)}>رد کردن</Button>
              </div>
            </Card>
          ) : null}
          <div className="row">
            <Segmented
              value={view}
              onChange={setView}
              ariaLabel="نمای تقویم"
              items={[
                { key: "month", label: "ماه" },
                { key: "week", label: "هفته" },
                { key: "table", label: "جدول محتوا" },
              ]}
            />
            <Field label="نوع">
              <Select value={kind} onChange={(event) => setKind(event.target.value)}>
                {KINDS.map((row) => (
                  <option key={row.value} value={row.value}>{row.label}</option>
                ))}
              </Select>
            </Field>
            <Field label="شخص">
              <Select value={person} onChange={(event) => setPerson(event.target.value)}>
                <option value="">همه</option>
                {people.map(([id, name]) => (
                  <option key={id} value={id}>{name}</option>
                ))}
              </Select>
            </Field>
          </div>
          {view === "month" ? (
            <MonthGrid
              weeks={weeks}
              entries={visibleEntries}
              events={visibleEvents}
              selected={selected}
              onSelect={setSelected}
            />
          ) : null}
          {view === "week" ? (
            <WeekBoard
              weeks={weeks}
              week={Math.min(week, weeks.length - 1)}
              onWeek={setWeek}
              entries={visibleEntries}
              events={visibleEvents}
              onSelect={setSelected}
            />
          ) : null}
          {view === "table" ? (
            <ContentTable
              entries={visibleEntries}
              fresh={fresh}
              onFresh={setFresh}
              onCreate={() => {
                if (!fresh.topic.trim() || !fresh.on_date) {
                  toast("تاریخ و موضوع لازم است");
                  return;
                }
                saveEntry.mutate(fresh);
              }}
              onPatch={(id, body) => patchEntry.mutate({ id, body })}
              onRemove={(id) => {
                void confirmDialog("حذف ردیف", "این ردیف از تقویم حذف شود؟", DELETE_CONFIRM_LABEL, { danger: true }).then((ok) => {
                  if (ok) removeEntry.mutate(id);
                });
              }}
            />
          ) : null}
          {selected ? (
            <Card>
              <SectionHeader title={formatJalaliLong(selected) ?? selected} />
              {dayEntries.length === 0 && dayEvents.length === 0 ? <p className="muted">برای این روز موردی نیست.</p> : null}
              {dayEntries.map((row) => (
                <p key={row.id}>
                  <Badge tone={tierTone(row.tier)}>{tierLabel(row.tier)}</Badge> {row.format} · {row.channel} — {row.topic}
                  {row.cta ? ` · ${row.cta}` : ""} {row.assignee_name ? ` · ${row.assignee_name}` : ""}
                </p>
              ))}
              {groupByPerson(dayEvents).map(([name, rows]) => (
                <div key={name}>
                  <h4>{name}</h4>
                  {rows.map((row) => (
                    <p key={row.id} className={late(row.date, row.status) ? "cal-chip is-late" : ""}>
                      <Link to={row.link}>{row.title}</Link>
                    </p>
                  ))}
                </div>
              ))}
            </Card>
          ) : null}
        </QueryState>
      </div>
      <PrintSheet monthName={monthName} header={header} entries={entries} />
    </div>
  );
}

function groupByPerson(rows: CalendarEvent[]) {
  const map = new Map<string, CalendarEvent[]>();
  for (const row of rows) {
    const name = row.person || "بدون نام";
    map.set(name, [...(map.get(name) ?? []), row]);
  }
  return [...map.entries()];
}

function MonthCard({
  header,
  title,
  goal,
  onTitle,
  onGoal,
  onSave,
  busy,
}: {
  header: CalendarMonth | null;
  title: string;
  goal: string;
  onTitle: (value: string) => void;
  onGoal: (value: string) => void;
  onSave: () => void;
  busy: boolean;
}) {
  if (!header) {
    return (
      <Card>
        <p className="muted">برای این ماه هنوز سربرگی ثبت نشده.</p>
        <div className="row">
          <Field label="عنوان"><Input value={title} onChange={(event) => onTitle(event.target.value)} /></Field>
          <Field label="هدف"><Input value={goal} onChange={(event) => onGoal(event.target.value)} /></Field>
          <Button type="button" className="btn-sm" disabled={busy} onClick={onSave}>ذخیرهٔ سربرگ</Button>
        </div>
      </Card>
    );
  }
  const shown = header;
  return (
    <Card>
      <h3>{shown?.title || title || "تقویم ماه"}</h3>
      {shown?.goal ? <p>{shown.goal}</p> : null}
      {shown?.logic?.length ? (
        <ul>{shown.logic.map((line) => <li key={line}>{line}</li>)}</ul>
      ) : null}
      {shown?.mix?.length ? (
        <div className="cal-mix">
          {shown.mix.map((row) => (
            <Badge key={row.label}>{row.label} {row.share}٪</Badge>
          ))}
        </div>
      ) : null}
      {shown?.weeks?.length ? (
        <div className="stack">
          {shown.weeks.map((row) => (
            <p key={row.title}><strong>{row.title}</strong> — {row.body}</p>
          ))}
        </div>
      ) : null}
      <div className="row">
        <Field label="عنوان"><Input value={title || shown?.title || ""} onChange={(event) => onTitle(event.target.value)} /></Field>
        <Field label="هدف"><Input value={goal || shown?.goal || ""} onChange={(event) => onGoal(event.target.value)} /></Field>
        <Button type="button" variant="secondary" className="btn-sm" disabled={busy} onClick={onSave}>ذخیرهٔ سربرگ</Button>
      </div>
    </Card>
  );
}

function dayItems(cell: JalaliCell, entries: CalendarEntry[], events: CalendarEvent[]) {
  return {
    content: entries.filter((row) => row.on_date === cell.iso),
    work: events.filter((row) => row.date === cell.iso),
  };
}

function MonthGrid({
  weeks,
  entries,
  events,
  selected,
  onSelect,
}: {
  weeks: JalaliCell[][];
  entries: CalendarEntry[];
  events: CalendarEvent[];
  selected: string;
  onSelect: (iso: string) => void;
}) {
  const today = todayIso();
  return (
    <div>
      <div className="cal-grid">
        {WEEKDAYS.map((name) => <div className="cal-head" key={name}>{name}</div>)}
      </div>
      {weeks.map((row) => (
        <div className="cal-grid" key={row[0].iso}>
          {row.map((cell) => {
            const items = dayItems(cell, entries, events);
            const lateCount = items.work.filter((item) => late(item.date, item.status)).length;
            return (
              <button
                type="button"
                key={cell.iso}
                className={`cal-day${cell.inMonth ? "" : " is-out"}${cell.iso === today ? " is-today" : ""}`}
                onClick={() => onSelect(cell.iso)}
                aria-pressed={selected === cell.iso}
              >
                <span className="cal-day-num">{cell.day}</span>
                {items.content.slice(0, 1).map((item) => (
                  <span className="cal-chip" key={item.id}>{tierLabel(item.tier)} · {item.format}</span>
                ))}
                {items.work.length ? (
                  <span className={`cal-chip${lateCount ? " is-late" : ""}`}>{items.work.length} کار{lateCount ? ` · ${lateCount} دیر` : ""}</span>
                ) : null}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function WeekBoard({
  weeks,
  week,
  onWeek,
  entries,
  events,
  onSelect,
}: {
  weeks: JalaliCell[][];
  week: number;
  onWeek: (value: number) => void;
  entries: CalendarEntry[];
  events: CalendarEvent[];
  onSelect: (iso: string) => void;
}) {
  const row = weeks[week] ?? weeks[0];
  return (
    <div className="stack">
      <div className="row">
        {weeks.map((item, index) => (
          <Button key={item[0].iso} type="button" variant={index === week ? "primary" : "ghost"} className="btn-sm" onClick={() => onWeek(index)}>
            هفته {index + 1}
          </Button>
        ))}
      </div>
      <div className="cal-week">
        {row.map((cell) => {
          const items = dayItems(cell, entries, events);
          return (
            <div key={cell.iso} className={`cal-col${cell.iso === todayIso() ? " is-today" : ""}`}>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => onSelect(cell.iso)}>{WEEKDAYS[row.indexOf(cell)]} {cell.day}</button>
              {items.content.map((item) => <span className="cal-chip" key={item.id}>{item.topic}</span>)}
              {items.work.map((item) => (
                <Link key={item.id} to={item.link} className={late(item.date, item.status) ? "cal-chip is-late" : "cal-chip"}>{item.person ? `${item.person}: ` : ""}{item.title}</Link>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ContentTable({
  entries,
  fresh,
  onFresh,
  onCreate,
  onPatch,
  onRemove,
}: {
  entries: CalendarEntry[];
  fresh: { topic: string; tier: string; format: string; channel: string; on_date: string };
  onFresh: (value: { topic: string; tier: string; format: string; channel: string; on_date: string }) => void;
  onCreate: () => void;
  onPatch: (id: string, body: Record<string, unknown>) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <div className="stack">
      <div className="row">
        <Field label="تاریخ"><Input type="date" value={fresh.on_date} onChange={(event) => onFresh({ ...fresh, on_date: event.target.value })} /></Field>
        <Field label="موضوع"><Input value={fresh.topic} onChange={(event) => onFresh({ ...fresh, topic: event.target.value })} /></Field>
        <Field label="کمپین">
          <Select value={fresh.tier} onChange={(event) => onFresh({ ...fresh, tier: event.target.value })}>
            {TIERS.map((row) => <option key={row.value} value={row.value}>{row.label}</option>)}
          </Select>
        </Field>
        <Field label="فرمت"><Input value={fresh.format} onChange={(event) => onFresh({ ...fresh, format: event.target.value })} /></Field>
        <Field label="کانال"><Input value={fresh.channel} onChange={(event) => onFresh({ ...fresh, channel: event.target.value })} /></Field>
        <Button type="button" className="btn-sm" onClick={onCreate}>افزودن</Button>
      </div>
      <div className="cal-table-wrap">
        <table className="cal-table">
          <thead>
            <tr>
              <th>تاریخ</th><th>کمپین</th><th>فرمت</th><th>کانال</th><th>موضوع</th><th>CTA</th><th>KPI</th><th>وضعیت</th><th></th>
            </tr>
          </thead>
          <tbody>
            {entries.map((row) => (
              <EntryRow key={row.id} row={row} onPatch={onPatch} onRemove={onRemove} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EntryRow({
  row,
  onPatch,
  onRemove,
}: {
  row: CalendarEntry;
  onPatch: (id: string, body: Record<string, unknown>) => void;
  onRemove: (id: string) => void;
}) {
  const [topic, setTopic] = useState(row.topic);
  const [format, setFormat] = useState(row.format);
  const [channel, setChannel] = useState(row.channel);
  const [cta, setCta] = useState(row.cta);
  const [kpi, setKpi] = useState(row.kpi);
  return (
    <tr>
      <td>{formatJalaliLong(row.on_date)}</td>
      <td>
        <Select value={row.tier} onChange={(event) => onPatch(row.id, { tier: event.target.value })}>
          {TIERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </Select>
      </td>
      <td><Input value={format} onChange={(event) => setFormat(event.target.value)} /></td>
      <td><Input value={channel} onChange={(event) => setChannel(event.target.value)} /></td>
      <td><Input className="topic" value={topic} onChange={(event) => setTopic(event.target.value)} /></td>
      <td><Input value={cta} onChange={(event) => setCta(event.target.value)} /></td>
      <td><Input value={kpi} onChange={(event) => setKpi(event.target.value)} /></td>
      <td>
        <Select value={row.status} onChange={(event) => onPatch(row.id, { status: event.target.value })}>
          {STATUSES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </Select>
      </td>
      <td>
        <div className="row">
          <Button type="button" variant="secondary" className="btn-sm" onClick={() => onPatch(row.id, { topic, format, channel, cta, kpi })}>ذخیره</Button>
          <Button type="button" variant="danger-quiet" className="btn-sm" onClick={() => onRemove(row.id)}>حذف</Button>
        </div>
      </td>
    </tr>
  );
}

function PrintSheet({
  monthName,
  header,
  entries,
}: {
  monthName: string;
  header: CalendarMonth | null;
  entries: CalendarEntry[];
}) {
  return (
    <div className="cal-print">
      <h1>{header?.title || `تقویم محتوا — ${monthName}`}</h1>
      {header?.goal ? <p>{header.goal}</p> : null}
      {header?.weeks?.map((row) => <p key={row.title}><strong>{row.title}</strong> — {row.body}</p>)}
      <table className="cal-table">
        <thead>
          <tr>
            <th>تاریخ</th><th>کمپین</th><th>فرمت</th><th>کانال</th><th>موضوع</th><th>CTA</th><th>KPI</th><th>وضعیت</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((row) => (
            <tr key={row.id}>
              <td>{formatJalaliLong(row.on_date)}</td>
              <td>{tierLabel(row.tier)}</td>
              <td>{row.format}</td>
              <td>{row.channel}</td>
              <td>{row.topic}</td>
              <td>{row.cta}</td>
              <td>{row.kpi}</td>
              <td>{statusLabel(row.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
