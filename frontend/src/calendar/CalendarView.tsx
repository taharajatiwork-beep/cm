import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth";
import { canSeeCalendar } from "../lib/access";
import { calendarApi, type CalendarEntry, type DraftEntry } from "../calendarApi";
import { Button, Card, ForbiddenState, MoreMenu, QueryState, SectionHeader } from "../components/ui";
import { DELETE_CONFIRM_LABEL, useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { useBi } from "../i18n";
import { faDigits } from "../fa";
import { addDaysIso, gregorianToJalali, jalaliMonthGrid, jalaliWeekAround, PERSIAN_MONTHS, parseIsoDate } from "../jalali";
import { AgendaList } from "./AgendaList";
import { CalendarToolbar } from "./CalendarToolbar";
import { ContentBoard } from "./ContentBoard";
import { ContentTable } from "./ContentTable";
import { DayDrawer } from "./DayDrawer";
import { EntryDialog } from "./EntryDialog";
import { MonthGrid } from "./MonthGrid";
import { MonthHeaderCard } from "./MonthHeaderCard";
import { PrintSheet } from "./PrintSheet";
import { TimeGrid } from "./TimeGrid";
import { WorkloadStrip } from "./WorkloadStrip";
import type { CalendarViewKey } from "./constants";
import { entryMatchesLayers, entryPatchId, eventMatchesLayers, todayIso } from "./helpers";
import { useCalendarUrlState } from "./useCalendarUrlState";

export function CalendarView() {
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
  const readOnly =
    has("calendar.read") &&
    !has("org.admin") &&
    !has("request.triage") &&
    !has("request.manage") &&
    !has("perf.write");
  const defaultView: CalendarViewKey = readOnly ? "week" : "month";
  const { state, patch } = useCalendarUrlState(defaultView, { defaultMine: readOnly });
  const bi = useBi();
  const toast = useToast();
  const confirmDialog = useConfirm();
  const qc = useQueryClient();

  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState("");
  const [draft, setDraft] = useState<DraftEntry[] | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<CalendarEntry | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [gy, gm, gd] = parseIsoDate(state.date);
  const [jy, jm] = gregorianToJalali(gy, gm, gd);

  const range = useMemo(() => {
    if (state.view === "month" || state.view === "board" || state.view === "table") {
      const weeks = jalaliMonthGrid(jy, jm);
      return { from: weeks[0][0].iso, to: weeks[weeks.length - 1][6].iso, weeks };
    }
    if (state.view === "week") {
      const week = jalaliWeekAround(state.date);
      return { from: week[0].iso, to: week[6].iso, weeks: [week] };
    }
    if (state.view === "agenda") {
      return { from: state.date, to: addDaysIso(state.date, 13), weeks: jalaliMonthGrid(jy, jm) };
    }
    const week = jalaliWeekAround(state.date);
    return { from: state.date, to: state.date, weeks: [week] };
  }, [state.view, state.date, jy, jm]);

  const layerSet = useMemo(() => new Set(state.layers), [state.layers]);
  const layersParam = state.layers.length ? state.layers.join(",") : undefined;

  const query = useQuery({
    queryKey: ["calendar", range.from, range.to, jy, jm, layersParam, state.mine],
    queryFn: () => calendarApi.range(range.from, range.to, jy, jm, layersParam, state.mine),
    enabled: allowed,
  });

  const entries = query.data?.entries ?? [];
  const events = query.data?.events ?? [];
  const occasions = query.data?.occasions ?? [];
  const load = query.data?.load ?? [];
  const header = query.data?.month ?? null;

  useEffect(() => {
    setTitle(header?.title ?? "");
    setGoal(header?.goal ?? "");
  }, [header?.title, header?.goal, jy, jm]);

  const people = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of events) if (row.person_id && row.person) map.set(row.person_id, row.person);
    for (const row of entries) if (row.assignee_id && row.assignee_name) map.set(row.assignee_id, row.assignee_name);
    return [...map.entries()];
  }, [events, entries]);

  const visibleEntries = useMemo(() => {
    return entries.filter((row) => {
      if (!entryMatchesLayers(row, layerSet)) return false;
      if (state.person && row.assignee_id !== state.person) return false;
      return true;
    });
  }, [entries, layerSet, state.person]);

  const visibleEvents = useMemo(() => {
    return events.filter((row) => {
      if (!eventMatchesLayers(row, layerSet)) return false;
      if (state.person && row.person_id !== state.person) return false;
      return true;
    });
  }, [events, layerSet, state.person]);

  const layerCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const row of entries) {
      counts[row.entry_type] = (counts[row.entry_type] ?? 0) + 1;
    }
    for (const row of events) {
      const key = row.kind === "mizito" ? "mizito" : WORK_LAYER(row.kind);
      counts[key] = (counts[key] ?? 0) + 1;
    }
    counts.holiday = occasions.length;
    return counts;
  }, [entries, events, occasions]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["calendar"] });
  }

  const saveEntry = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      editing ? calendarApi.patch(entryPatchId(editing), body) : calendarApi.create(body),
    onSuccess: () => {
      toast(editing ? "ذخیره شد" : "ردیف اضافه شد");
      setDialogOpen(false);
      setEditing(null);
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
      calendarApi.saveMonth(jy, jm, {
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
    mutationFn: () => calendarApi.draft(jy, jm),
    onSuccess: (result) => {
      setDraft(result.entries);
      toast(result.source === "llm" ? "پیش‌نویس با هوش مصنوعی آماده است" : "پیش‌نویس با قالب آماده است");
    },
    onError: (error: Error) => toast(error.message),
  });

  const keepDraft = useMutation({
    mutationFn: () => calendarApi.bulk(draft ?? []),
    onSuccess: (result) => {
      toast(`${result.added} ردیف ثبت شد`);
      setDraft(null);
      refresh();
    },
    onError: (error: Error) => toast(error.message),
  });

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (event.key === "t") patch({ date: todayIso() });
      if (event.key === "n" && !readOnly) {
        setEditing(null);
        setDialogOpen(true);
      }
      if (event.key === "ArrowLeft") shiftNav(1);
      if (event.key === "ArrowRight") shiftNav(-1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [patch, readOnly, state.view, jy, jm, state.date]);

  function shiftNav(deltaMonth: number) {
    let nm = jm + deltaMonth;
    let ny = jy;
    while (nm < 1) {
      ny -= 1;
      nm += 12;
    }
    while (nm > 12) {
      ny += 1;
      nm -= 12;
    }
    const weeks = jalaliMonthGrid(ny, nm);
    patch({ date: weeks[0][0].iso });
  }

  function shiftDay(delta: number) {
    patch({ date: addDaysIso(state.date, delta) });
  }

  function onPrev() {
    if (state.view === "day" || state.view === "agenda") shiftDay(-1);
    else shiftNav(-1);
  }

  function onNext() {
    if (state.view === "day" || state.view === "agenda") shiftDay(1);
    else shiftNav(1);
  }

  function moveEntry(entryId: string, toDate: string, occurrenceDate?: string, start?: string, end?: string) {
    const body: Record<string, unknown> = { on_date: toDate };
    if (occurrenceDate) {
      body.scope = "this";
      body.occurrence_date = occurrenceDate;
    }
    if (start && end) {
      body.all_day = false;
      body.start_time = start;
      body.end_time = end;
    }
    patchEntry.mutate({ id: entryId, body });
  }

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

  const monthName = faDigits(`${PERSIAN_MONTHS[jm - 1]} ${jy}`);
  const dayEvents = visibleEvents.filter((row) => row.date === state.date);
  const dayEntries = visibleEntries.filter((row) => row.on_date === state.date);
  const weekDays = range.weeks[0]?.map((cell) => cell.iso) ?? [];

  return (
    <div className="stack">
      <div className="cal2-screen stack">
        <SectionHeader
          title={bi("Calendar", "تقویم")}
          hint={bi("Content plan plus everyone's work", "برنامهٔ محتوا و کار همه")}
          action={
            !readOnly ? (
              <MoreMenu label={bi("More", "بیشتر")}>
                <Button type="button" variant="ghost" className="btn-sm" disabled={makeDraft.isPending} onClick={() => makeDraft.mutate()}>
                  پیش‌نویس ماه
                </Button>
                <Button type="button" variant="ghost" className="btn-sm" onClick={() => window.print()}>چاپ</Button>
                <Button type="button" variant="ghost" className="btn-sm" onClick={() => void calendarApi.download(range.from, range.to).catch((e: Error) => toast(e.message))}>
                  اکسل
                </Button>
              </MoreMenu>
            ) : null
          }
        />
        <CalendarToolbar
          view={state.view}
          date={state.date}
          layers={state.layers}
          person={state.person}
          mine={state.mine}
          people={people}
          layerCounts={layerCounts}
          readOnly={readOnly}
          onView={(view) => patch({ view })}
          onDate={(date) => patch({ date })}
          onLayers={(layers) => patch({ layers })}
          onPerson={(person) => patch({ person })}
          onMine={(mine) => patch({ mine })}
          onToday={() => patch({ date: todayIso() })}
          onPrev={onPrev}
          onNext={onNext}
          onNew={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        />
        <QueryState isLoading={query.isLoading} error={query.error}>
          <MonthHeaderCard
            header={header}
            entries={visibleEntries}
            title={title}
            goal={goal}
            readOnly={readOnly}
            onTitle={setTitle}
            onGoal={setGoal}
            onSave={() => saveHeader.mutate()}
            busy={saveHeader.isPending}
          />
          {!readOnly && draft ? (
            <Card>
              <p>{draft.length} ردیف پیش‌نویس آماده است.</p>
              <div className="row">
                <Button type="button" className="btn-sm" disabled={keepDraft.isPending} onClick={() => keepDraft.mutate()}>ثبت پیش‌نویس</Button>
                <Button type="button" variant="ghost" className="btn-sm" onClick={() => setDraft(null)}>رد کردن</Button>
              </div>
            </Card>
          ) : null}
          {state.view === "month" ? (
            <MonthGrid
              weeks={range.weeks as ReturnType<typeof jalaliMonthGrid>}
              entries={visibleEntries}
              events={visibleEvents}
              occasions={occasions}
              selected={state.date}
              readOnly={readOnly}
              onSelect={(iso) => {
                patch({ date: iso });
                setDrawerOpen(true);
              }}
              onMoveEntry={moveEntry}
            />
          ) : null}
          {state.view === "week" ? (
            <>
              <WorkloadStrip load={load} people={new Map(people)} dates={weekDays} />
              <MonthGrid
                weeks={range.weeks as ReturnType<typeof jalaliMonthGrid>}
                entries={visibleEntries}
                events={visibleEvents}
                occasions={occasions}
                selected={state.date}
                readOnly={readOnly}
                onSelect={(iso) => {
                  patch({ date: iso });
                  setDrawerOpen(true);
                }}
                onMoveEntry={moveEntry}
              />
            </>
          ) : null}
          {state.view === "day" ? (
            <TimeGrid
              dayIso={state.date}
              entries={visibleEntries.filter((row) => row.on_date === state.date)}
              events={dayEvents}
              readOnly={readOnly}
              onMoveEntry={moveEntry}
            />
          ) : null}
          {state.view === "agenda" ? (
            <AgendaList anchor={state.date} entries={visibleEntries} events={visibleEvents} />
          ) : null}
          {state.view === "board" ? (
            <ContentBoard
              entries={visibleEntries}
              readOnly={readOnly}
              onStatus={(id, status) => patchEntry.mutate({ id, body: { production_status: status } })}
            />
          ) : null}
          {state.view === "table" ? (
            <ContentTable
              entries={visibleEntries}
              readOnly
              onPatch={(id, body) => patchEntry.mutate({ id, body })}
              onRemove={(id) => {
                void confirmDialog("حذف ردیف", "این ردیف از تقویم حذف شود؟", DELETE_CONFIRM_LABEL, { danger: true }).then((ok) => {
                  if (ok) removeEntry.mutate(id);
                });
              }}
              onOpen={(row) => {
                setEditing(row);
                setDialogOpen(true);
              }}
            />
          ) : null}
        </QueryState>
        <EntryDialog
          open={dialogOpen}
          initial={editing}
          defaultDate={state.date}
          onClose={() => {
            setDialogOpen(false);
            setEditing(null);
          }}
          onSave={(body) => saveEntry.mutate(body)}
          busy={saveEntry.isPending}
        />
        {drawerOpen ? (
          <DayDrawer
            iso={state.date}
            onClose={() => setDrawerOpen(false)}
            entries={dayEntries}
            events={dayEvents}
            occasions={occasions}
            readOnly={readOnly}
            onAdd={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
            onEdit={(row) => {
              setEditing(row);
              setDialogOpen(true);
            }}
          />
        ) : null}
      </div>
      <PrintSheet monthName={monthName} header={header} entries={visibleEntries} />
    </div>
  );
}

function WORK_LAYER(kind: string) {
  if (kind === "mizito") return "mizito";
  if (kind === "campaign" || kind === "sms" || kind === "story") return "marketing";
  return "work";
}
