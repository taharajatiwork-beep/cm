import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Icon,
  Input,
  LoadingState,
  PageHeader,
  SectionHeader,
  Select,
} from "../components/ui";
import { DateText } from "../components/DateText";
import { Bi, useBi } from "../i18n";
import {
  CASE_STATUS_LABELS,
  PRIORITY_LABELS,
  caseStatusLabel,
  caseTypeLabel,
  eventTypeLabel,
  priorityLabel,
  slaStateLabel,
} from "../labels";
import { ConceptHint } from "../ux";

/** ترتیب نمایش وضعیت‌ها — هر هشت مقدار CaseStatus در enums.py را پوشش می‌دهد. */
const STATUS_ORDER = [
  "OPEN",
  "ASSIGNED",
  "IN_PROGRESS",
  "WAITING_FOR_RESPONSE",
  "WAITING_FOR_USER",
  "ESCALATED",
  "COMPLETED",
  "CANCELLED",
] as const;

const PRIORITY_ORDER = ["LOW", "MEDIUM", "HIGH", "URGENT"] as const;

/** ترتیب نوع پرونده‌ها — هم‌خوان با CaseType در backend/app/models/enums.py */
const TYPE_ORDER = [
  "GENERAL_OPERATIONAL_REQUEST",
  "BRANCH_REQUEST",
  "BUYER_REQUEST",
  "SELLER_REQUEST",
  "FOLLOW_UP",
  "INVENTORY_OPPORTUNITY",
  "CUSTOMER_INTEREST",
  "TRANSFER",
  "ESCALATION",
] as const;

type CaseRow = Record<string, unknown>;

export function CasesPage() {
  const { user, has } = useAuth();
  const bi = useBi();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const [status, setStatus] = useState("");
  const [subject, setSubject] = useState("");
  const [type, setType] = useState<string>("GENERAL_OPERATIONAL_REQUEST");
  const [priority, setPriority] = useState<string>("MEDIUM");
  const [actionError, setActionError] = useState("");

  // انتخاب پرونده در URL می‌ماند تا رفرش و اشتراک لینک کار کند
  const selected = params.get("c") ?? "";
  const setSelected = (id: string) => {
    const next = new URLSearchParams(params);
    if (id) next.set("c", id);
    else next.delete("c");
    setParams(next, { replace: true });
  };

  const list = useQuery({
    queryKey: ["cases", status],
    queryFn: () => api.cases.list(status ? { status } : undefined),
  });
  const timeline = useQuery({
    queryKey: ["cases", selected, "timeline"],
    enabled: Boolean(selected),
    queryFn: () => api.cases.timeline(selected),
  });

  const create = useMutation({
    mutationFn: () => api.cases.create({ subject: subject.trim(), type, priority }),
    onSuccess: (created) => {
      setSubject("");
      void qc.invalidateQueries({ queryKey: ["cases"] });
      const id = (created as { id?: unknown }).id;
      if (id != null) setSelected(String(id));
    },
  });

  // تغییر وضعیت/مسئول پرونده — PATCH /cases/{id}
  const people = useQuery({
    queryKey: ["people"],
    queryFn: () => api.people.list(),
  });
  const update = useMutation({
    mutationFn: (body: { status?: string; owner_id?: string | null }) =>
      api.cases.update(activeId, body),
    onSuccess: () => {
      setActionError("");
      void qc.invalidateQueries({ queryKey: ["cases"] });
    },
    onError: (err) => setActionError(String((err as Error).message)),
  });
  // شروع گفتگو با اتصال به همین پرونده
  const startConv = useMutation({
    mutationFn: () =>
      api.conversations.create({
        topic: String(current?.subject ?? bi("Case follow-up", "پیگیری پرونده")),
        participant_ids: user?.id ? [user.id] : [],
        channel: "WEB",
        case_id: activeId,
      }),
    onSuccess: (created) => {
      setActionError("");
      navigate(`/communication?c=${String(created.id)}`);
    },
    onError: (err) => setActionError(String((err as Error).message)),
  });

  const rows: CaseRow[] = list.data ?? [];
  const events = timeline.data ?? [];
  // پروندهٔ انتخاب‌شده از خود ردیف لیست می‌آید؛ endpoint جداگانه‌ای برای جزئیات نیست.
  // اگر چیزی انتخاب نشده باشد اولین پرونده مشتق‌شده انتخاب می‌شود تا ستون جزئیات خالی نماند.
  const activeId = selected || (rows[0] ? String(rows[0].id) : "");
  const current = rows.find((r) => String(r.id) === activeId) ?? null;

  function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!has("case.write")) return;
    if (!subject.trim() || create.isPending) return;
    create.mutate();
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Cases" fa="پرونده‌ها" />}
        description={
          <Bi
            en="One subject to track in your section: a customer, a branch request, or a deadline. Not the project, and not an ad."
            fa="یک موضوع برای پیگیری در بخش شما: مشتری، درخواست شعبه، یا یک مهلت. پروژه نیست و آگهی هم نیست."
          />
        }
      />
      <ConceptHint kind="followup" />

      <ErrorMessage
        error={
          list.isError
            ? String((list.error as Error).message)
            : create.isError
              ? String((create.error as Error).message)
              : actionError
        }
      />

      <div className="split split--side">
        <Card padded={false}>
          <div className="card-bar">
            <SectionHeader
              icon="briefcase"
              title={<Bi en="All cases" fa="همه پرونده‌ها" />}
              count={list.isLoading ? undefined : rows.length}
            />
            <Select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              aria-label={bi("Status", "وضعیت")}
            >
              <option value="">{bi("All statuses", "همهٔ وضعیت‌ها")}</option>
              {STATUS_ORDER.map((value) => (
                <option key={value} value={value}>
                  {CASE_STATUS_LABELS[value]}
                </option>
              ))}
            </Select>
          </div>
          {list.isLoading ? (
            <div className="flush-foot">
              <LoadingState labelEn="Loading cases…" labelFa="در حال بارگذاری پرونده‌ها…" />
            </div>
          ) : rows.length === 0 ? (
            <div className="flush-foot">
              <EmptyState
                titleEn="No cases"
                titleFa="پرونده‌ای نیست"
                bodyEn={
                  status
                    ? "No case has this status yet."
                    : "Create a follow-up when work needs a record."
                }
                bodyFa={
                  status
                    ? "هیچ پرونده‌ای با این وضعیت وجود ندارد."
                    : "وقتی کاری باید ثبت شود، یک پرونده بسازید."
                }
              />
            </div>
          ) : (
            <ul className="rows">
              {rows.map((row) => {
                const id = String(row.id);
                const statusInfo = caseStatusLabel(row.status);
                const slaInfo = slaStateLabel(row.sla_state);
                const priorityInfo = priorityLabel(row.priority);
                return (
                  <li key={id}>
                    <button
                      type="button"
                      className={`row-item row-button${activeId === id ? " is-active" : ""}`}
                      onClick={() => setSelected(id)}
                    >
                      <span className="row-main">
                        <span className="row-title">{String(row.subject ?? "—")}</span>
                        <span className="row-meta">
                          <Badge tone={statusInfo.tone}>{statusInfo.label}</Badge>
                          <Badge tone={priorityInfo.tone}>{priorityInfo.label}</Badge>
                          {slaInfo.label ? <Badge tone={slaInfo.tone}>{slaInfo.label}</Badge> : null}
                        </span>
                      </span>
                      <DateText value={row.created_at} className="row-meta" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {has("case.write") ? (
            <form onSubmit={onCreate} className="case-create">
              <Input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder={bi("New case subject…", "موضوع پروندهٔ جدید…")}
                required
                disabled={create.isPending}
              />
              <Select
                value={type}
                onChange={(e) => setType(e.target.value)}
                aria-label={bi("Type", "نوع")}
                disabled={create.isPending}
              >
                {TYPE_ORDER.map((value) => (
                  <option key={value} value={value}>
                    {caseTypeLabel(value)}
                  </option>
                ))}
              </Select>
              <Select
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                aria-label={bi("Priority", "اولویت")}
                disabled={create.isPending}
              >
                {PRIORITY_ORDER.map((value) => (
                  <option key={value} value={value}>
                    {PRIORITY_LABELS[value]}
                  </option>
                ))}
              </Select>
              <Button type="submit" disabled={create.isPending || !subject.trim()}>
                {create.isPending ? (
                  <Bi en="Creating…" fa="در حال ساخت…" />
                ) : (
                  <Bi en="Create" fa="ساخت" />
                )}
              </Button>
            </form>
          ) : null}
        </Card>

        <Card>
          {!current ? (
            <EmptyState
              titleEn="Pick a case"
              titleFa="یک پرونده انتخاب کنید"
              bodyEn="The timeline and details of the selected case appear here."
              bodyFa="تایم‌لاین و جزئیات پروندهٔ انتخاب‌شده اینجا نمایش داده می‌شود."
            />
          ) : (
            <div className="stack stack--roomy">
              <SectionHeader
                icon="briefcase"
                title={<span className="row-title">{String(current?.subject ?? "…")}</span>}
              />
              {current ? (
                <div className="row-meta">
                  <span>
                    <Bi en="Status" fa="وضعیت" />:{" "}
                    <Badge tone={caseStatusLabel(current.status).tone}>
                      {caseStatusLabel(current.status).label}
                    </Badge>
                  </span>
                  <span>
                    <Bi en="Priority" fa="اولویت" />:{" "}
                    <Badge tone={priorityLabel(current.priority).tone}>
                      {priorityLabel(current.priority).label}
                    </Badge>
                  </span>
                  <span>
                    <Bi en="Type" fa="نوع" />: {caseTypeLabel(current.type)}
                  </span>
                  <span>
                    <Bi en="SLA" fa="مهلت" />:{" "}
                    <Badge tone={slaStateLabel(current.sla_state).tone}>
                      {slaStateLabel(current.sla_state).label}
                    </Badge>
                  </span>
                  {current.deadline ? (
                    <span>
                      <Bi en="Due" fa="مهلت" />: <DateText value={current.deadline} withTime />
                    </span>
                  ) : null}
                </div>
              ) : null}

              {has("case.write") && current ? (
                <div className="case-actions">
                  <Select
                    value={String(current.status ?? "")}
                    onChange={(e) => update.mutate({ status: e.target.value })}
                    aria-label={bi("Change status", "تغییر وضعیت")}
                    disabled={update.isPending}
                  >
                    {STATUS_ORDER.map((value) => (
                      <option key={value} value={value}>
                        {CASE_STATUS_LABELS[value]}
                      </option>
                    ))}
                  </Select>
                  <Select
                    value={current.owner_id ? String(current.owner_id) : ""}
                    onChange={(e) => update.mutate({ owner_id: e.target.value || null })}
                    aria-label={bi("Owner", "مسئول")}
                    disabled={update.isPending}
                  >
                    <option value="">{bi("No owner", "بدون مسئول")}</option>
                    {(people.data ?? []).map((p) => (
                      <option key={String(p.id)} value={String(p.id)}>
                        {String(p.full_name)}
                      </option>
                    ))}
                  </Select>
                  <Button
                    variant="secondary"
                    disabled={startConv.isPending}
                    onClick={() => startConv.mutate()}
                  >
                    <Icon name="message" size={14} />
                    <Bi en="Open conversation" fa="شروع گفتگو" />
                  </Button>
                </div>
              ) : null}

              <SectionHeader title={<Bi en="Timeline" fa="تایم‌لاین" />} />
              {timeline.isLoading ? (
                <LoadingState labelEn="Loading timeline…" labelFa="در حال بارگذاری تایم‌لاین…" />
              ) : timeline.isError ? (
                <ErrorMessage error={String((timeline.error as Error).message)} />
              ) : events.length === 0 ? (
                <p className="muted case-timeline-empty">
                  <Bi
                    en="No events yet — changes to this case will show up here."
                    fa="هنوز رویدادی نیست — تغییرات این پرونده اینجا ثبت می‌شود."
                  />
                </p>
              ) : (
                <ul className="rows">
                  {events.map((event) => (
                    <li key={String(event.id)}>
                      <div className="row-item">
                        <span className="row-main">
                          <span className="row-title">{eventTypeLabel(event.event_type)}</span>
                        </span>
                        <DateText value={event.created_at} withTime className="row-meta" />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
