import { useEffect, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { requestsApi } from "../requests/api";
import { useAuth } from "../auth";
import {
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Icon,
  LoadingState,
  PageHeader,
  SectionHeader,
  Segmented,
  Sheet,
  type IconName,
} from "../components/ui";
import { canSeeProjects } from "../lib/access";
import { useToast } from "../components/ui/Toast";
import {
  filledWorkBuckets,
  flattenMyWorkTasks,
  myWorkProjectsWithoutTasks,
  workEmptyTarget,
  WORK_BUCKETS,
  type WorkBucket,
} from "../lib/focus";
import { Bi, useBi, useLocale } from "../i18n";
import { canFinishTask, formatDeadline, isOverdue } from "../lib/collaboration";
import { DateText } from "../components/DateText";
import { faNum } from "../fa";
import { StatusLabel } from "../ux";
import { useWorkParentLookups, WorkListKindBadge, WorkParentContext } from "../lib/workContext";
import { TaskDetailSheet } from "./TaskDetailSheet";

type QueueFilter = "all" | WorkBucket;
type Row = Record<string, unknown>;
type Slot = {
  id: string;
  brand?: string | null;
  model?: string | null;
  post_at?: string | null;
  status?: string;
  slot_type?: string;
};

function carName(slot: Slot): string {
  return [slot.brand, slot.model].filter(Boolean).join(" ") || "خودرو";
}

function isDueToday(deadline: string | null | undefined): boolean {
  if (!deadline) return false;
  const day = deadline.slice(0, 10);
  const today = new Date().toISOString().slice(0, 10);
  return day === today;
}

function taskUrgencyRank(t: { deadline?: string | null; status?: string }) {
  if (isOverdue(t.deadline, t.status)) return 0;
  if (isDueToday(t.deadline)) return 1;
  if (t.deadline) return 2;
  return 3;
}

const BUCKET_LABEL: Record<WorkBucket, [string, string]> = {
  overdue: ["Late", "عقب‌افتاده"],
  today: ["Today", "امروز"],
  later: ["Later", "آینده"],
  waiting: ["Waiting on others", "منتظر دیگران"],
  projects_without_tasks: ["Team projects with no work yet", "پروژه بدون کار"],
};

const BUCKET_HELP: Record<WorkBucket, [string, string]> = {
  overdue: [
    "Tasks you own or are assigned — past deadline. Each row shows which request and project it belongs to.",
    "کارهایی که مالک یا محول‌شده‌اید و از مهلت گذشته‌اند. هر ردیف نشان می‌دهد زیر کدام درخواست و پروژه است.",
  ],
  today: [
    "Tasks due today. Request → project → task: the line under the title shows the chain.",
    "کارهایی که مهلتشان امروز است. درخواست → پروژه → کار؛ خط زیر عنوان زنجیره را نشان می‌دهد.",
  ],
  later: [
    "Tasks with a later deadline or no deadline yet.",
    "کارهایی با مهلت بعداً یا بدون مهلت.",
  ],
  waiting: [
    "You created the task but someone else is assigned to finish it.",
    "شما کار را ساخته‌اید اما نفر دیگری باید انجام دهد.",
  ],
  projects_without_tasks: [
    "A project exists but no tasks yet — open it and add steps or apply a template.",
    "پروژه ساخته شده اما هنوز کار ندارد — باز کنید و قدم اضافه کنید یا قالب بزنید.",
  ],
};

function emptyWorkAction(to: string) {
  if (to === "/requests") return { en: "Open requests", fa: "دیدن درخواست‌ها" };
  if (to === "/pricing") return { en: "Review prices", fa: "دیدن قیمت‌ها" };
  if (to === "/perf") return { en: "Open performance", fa: "رفتن به پرفورمنس" };
  if (to === "/vehicles") return { en: "Open vehicles", fa: "دیدن خودروها" };
  return { en: "Back home", fa: "بازگشت به خانه" };
}

function WorkBucketFilters({
  value,
  onChange,
  counts,
  loading,
}: {
  value: QueueFilter;
  onChange: (next: QueueFilter) => void;
  counts: Partial<Record<WorkBucket, number>>;
  loading: boolean;
}) {
  const bi = useBi();
  const filled = filledWorkBuckets(counts);
  const total = WORK_BUCKETS.reduce((sum, key) => sum + (counts[key] ?? 0), 0);
  if (!loading && filled.length === 0) return null;
  const items: Array<{ key: QueueFilter; label: ReactNode; count?: number; icon?: IconName }> = [
    { key: "all", icon: "layers", label: bi("All", "همه"), count: loading ? undefined : total },
    ...filled.map((key) => ({
      key,
      icon: (key === "overdue" ? "alert" : "clock") as IconName,
      label: bi(BUCKET_LABEL[key][0], BUCKET_LABEL[key][1]),
      count: counts[key],
    })),
  ];
  return (
    <Segmented<QueueFilter>
      idBase="my-work-buckets"
      ariaLabel={bi("Filter queue", "فیلتر فهرست")}
      value={value}
      onChange={onChange}
      items={items}
    />
  );
}

export function MyWorkPage() {
  const { user, roleHint, has } = useAuth();
  const bi = useBi();
  const qc = useQueryClient();
  const toast = useToast();
  const [justDone, setJustDone] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [detailTaskId, setDetailTaskId] = useState<string | null>(searchParams.get("task"));
  useEffect(() => {
    const id = searchParams.get("task");
    setDetailTaskId(id);
  }, [searchParams]);
  const showProjectLink = canSeeProjects(
    { roleCode: user?.roleCode, permissions: user?.permissions ?? [] },
    has,
  );
  const taskDetail = useQuery({
    queryKey: ["task", detailTaskId],
    enabled: Boolean(detailTaskId),
    queryFn: () => api.tasks.get(detailTaskId!),
  });
  const canPrice = has("price.approve") || has("price.write");
  const canPost = has("campaign.write");
  const canUseWorkBuckets = true;
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("all");
  const buckets = useQuery({
    queryKey: ["requests", "my-work"],
    queryFn: () => requestsApi.myWork(),
    enabled: canUseWorkBuckets,
  });
  const parentLookups = useWorkParentLookups(has("task.read"));
  const workQuery = useQuery({
    queryKey: ["my-work", user?.id, roleHint],
    enabled: Boolean(user?.id),
    queryFn: async () => {
      const tasks = has("task.read") && user?.id ? await api.tasks.list({ assignee_id: user.id }) : [];
      const overdue =
        has("task.read") && (roleHint === "manager" || roleHint === "admin")
          ? await api.tasks.list({ overdue_only: true })
          : tasks.filter((t) => isOverdue(t.deadline, t.status));
      return { tasks, overdue };
    },
  });
  const aiApprovals = useQuery({
    queryKey: ["approvals", "ai"],
    queryFn: () => api.approvals.list(),
  });
  const pricing = useQuery({
    queryKey: ["pricing-board", "my-work", user?.id],
    enabled: Boolean(user?.id) && (canPrice || canPost),
    queryFn: () => api.pricing.board(),
  });
  const tasks = workQuery.data?.tasks ?? [];
  const overdue = workQuery.data?.overdue ?? [];
  const priceJobs = ((pricing.data?.slots ?? []) as Slot[]).filter((slot) => {
    if (canPrice && (slot.status === "requested" || slot.status === "needs_recheck")) return true;
    if (canPost && slot.status === "confirmed") return true;
    return false;
  });
  const error = workQuery.isError ? String((workQuery.error as Error).message) : "";

  async function complete(id: string) {
    await api.tasks.complete(id);
    setJustDone(id);
    toast(bi("Nice — one less on your list.", "آفرین — یکی از فهرست کم شد."), {
      labelEn: "Undo",
      labelFa: "برگرداندن",
      onClick: () => {
        void api.tasks.reopen(id).then(async () => {
          setJustDone((current) => (current === id ? null : current));
          await qc.invalidateQueries({ queryKey: ["my-work"] });
          await qc.invalidateQueries({ queryKey: ["requests", "my-work"] });
          await qc.invalidateQueries({ queryKey: ["project"] });
        });
      },
    });
    window.setTimeout(() => setJustDone((current) => (current === id ? null : current)), 1200);
    await qc.invalidateQueries({ queryKey: ["my-work"] });
    await qc.invalidateQueries({ queryKey: ["requests", "my-work"] });
    await qc.invalidateQueries({ queryKey: ["project"] });
    await qc.invalidateQueries({ queryKey: ["requests", "work-projects"] });
    await qc.invalidateQueries({ queryKey: ["requests", "work-requests"] });
    await qc.invalidateQueries({ queryKey: ["team-home"] });
  }

  const openTasks = tasks.filter((t) => t.status !== "COMPLETED");
  const openSorted = [...openTasks].sort((a, b) => {
    const ra = taskUrgencyRank(a);
    const rb = taskUrgencyRank(b);
    if (ra !== rb) return ra - rb;
    if (a.deadline && b.deadline) return String(a.deadline).localeCompare(String(b.deadline));
    if (a.deadline) return -1;
    if (b.deadline) return 1;
    return String(a.title ?? "").localeCompare(String(b.title ?? ""), "fa");
  });
  const bucketCounts = Object.fromEntries(
    WORK_BUCKETS.map((key) => [key, (buckets.data?.[key] ?? []).length]),
  ) as Partial<Record<WorkBucket, number>>;
  const listLoading =
    workQuery.isLoading ||
    buckets.isLoading ||
    ((canPrice || canPost) && pricing.isLoading);
  const nextPlace = workEmptyTarget({
    roleHint,
    roleCode: user?.roleCode,
    permissions: user?.permissions ?? [],
    teamId: user?.team_id,
  });
  const nextPlaceLabel = emptyWorkAction(nextPlace);
  const doneTasks = tasks.length - openTasks.length;
  const pct = tasks.length ? Math.round((doneTasks / tasks.length) * 100) : 0;
  const pendingAi = (aiApprovals.data ?? []).filter(
    (row) => String(row.status || "pending") === "pending" && String(row.kind || "").startsWith("ai."),
  );

  const description = bi("Tasks by deadline, plus prices and assistant items in their own groups.", "کارها بر اساس مهلت؛ قیمت و دستیار در گروه جدا.");
  function openTask(id: string) {
    setDetailTaskId(id);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("task", id);
      return next;
    });
  }
  function closeTask() {
    setDetailTaskId(null);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("task");
      return next;
    });
  }

  function TaskRow({ t, late }: { t: Row; late?: boolean }) {
    const { locale } = useLocale();
    const deadline = formatDeadline(t.deadline, bi, locale);
    const parents = parentLookups.resolve({
      project_id: t.project_id as string | null | undefined,
      request_id: t.request_id as string | null | undefined,
    });
    return (
      <li className={`row-item${late ? " is-danger" : ""}${justDone === String(t.id) ? " is-celebrate" : ""}`}>
        {canFinishTask(t, user?.id) ? (
          <button
            type="button"
            className="done-btn"
            title={bi("Mark done", "انجام شد")}
            aria-label={bi("Mark done", "انجام شد")}
            onClick={() => void complete(String(t.id))}
          >
            <Icon name="check" size={12} />
          </button>
        ) : (
          <span className="check-mark" aria-hidden>○</span>
        )}
        <div className="row-main">
          <button type="button" className="row-title row-title-btn" onClick={() => openTask(String(t.id))}>
            {String(t.title)}
          </button>
          <span className="row-meta">
            {t.status !== "ASSIGNED" && t.status !== "OPEN" ? <StatusLabel status={String(t.status)} /> : null}
            {deadline ? (
              <span className={late ? "danger-text" : undefined}>
                <Icon name="clock" size={11} /> {deadline}
              </span>
            ) : null}
          </span>
          <WorkParentContext kind="task" {...parents} />
        </div>
      </li>
    );
  }

  const bucketTasks = flattenMyWorkTasks(buckets.data);
  const bucketProjects = myWorkProjectsWithoutTasks(buckets.data);
  const unifiedTasks = (() => {
    const seen = new Set<string>();
    const merged: Row[] = [];
    for (const row of bucketTasks) {
      const id = String(row.id);
      if (seen.has(id)) continue;
      seen.add(id);
      merged.push(row as Row);
    }
    for (const row of openSorted) {
      const id = String(row.id);
      if (seen.has(id)) continue;
      seen.add(id);
      merged.push(row);
    }
    return merged.sort((a, b) => {
      const ra = taskUrgencyRank(a);
      const rb = taskUrgencyRank(b);
      if (ra !== rb) return ra - rb;
      if (a.deadline && b.deadline) return String(a.deadline).localeCompare(String(b.deadline));
      if (a.deadline) return -1;
      if (b.deadline) return 1;
      return String(a.title ?? "").localeCompare(String(b.title ?? ""), "fa");
    });
  })();

  const allQueueCount =
    priceJobs.length + pendingAi.length + unifiedTasks.length + bucketProjects.length;

  const bucketRows =
    queueFilter === "all" ? [] : (buckets.data?.[queueFilter] ?? []) as Array<Record<string, string>>;
  const showUnified = queueFilter === "all";
  const unifiedEmpty = showUnified && allQueueCount === 0;
  const bucketEmpty = !showUnified && bucketRows.length === 0;

  return (
    <>
      <PageHeader title={<Bi en="My Work" fa="کارهای من" />} description={description} />
      <ErrorMessage error={error} />
      <ErrorMessage error={canUseWorkBuckets && buckets.isError ? buckets.error : null} />

      <div className="split">
        <section>
          <div className="section-head">
            <WorkBucketFilters
              value={queueFilter}
              onChange={setQueueFilter}
              counts={bucketCounts}
              loading={buckets.isLoading}
            />
          </div>
          {queueFilter !== "all" ? (
            <p className="help-text">{bi(BUCKET_HELP[queueFilter][0], BUCKET_HELP[queueFilter][1])}</p>
          ) : null}

          <Card padded={false}>
            {listLoading ? <LoadingState /> : null}
            {!listLoading && unifiedEmpty && filledWorkBuckets(bucketCounts).length === 0 ? (
              <EmptyState
                titleEn="You're clear"
                titleFa="صف شما خالی است"
                bodyEn="Nothing is late, due today, or waiting on someone else."
                bodyFa="نه کار عقب‌افتاده دارید، نه کار امروز، نه چیزی که منتظر دیگران باشد."
                action={
                  <Button to={nextPlace}>
                    <Bi en={nextPlaceLabel.en} fa={nextPlaceLabel.fa} />
                  </Button>
                }
              />
            ) : null}
            {!listLoading && bucketEmpty ? (
              <EmptyState
                titleEn="Nothing in this bucket"
                titleFa="در این دسته چیزی نیست"
                bodyEn="Pick another filter or switch back to All."
                bodyFa="فیلتر دیگری انتخاب کنید یا به «همه» برگردید."
              />
            ) : null}
            {!listLoading && showUnified && !unifiedEmpty ? (
              <ul className="rows">
                {priceJobs.length > 0 ? (
                  <li className="row-section-head" aria-hidden>
                    <SectionHeader icon="megaphone" title={<Bi en="Prices & posts" fa="قیمت و پست‌ها" />} />
                  </li>
                ) : null}
                {priceJobs.map((slot) => {
                  const confirm = slot.status === "requested" || slot.status === "needs_recheck";
                  return (
                    <li key={`price-${slot.id}`} className="row-item">
                      <span className="row-lead">
                        <Icon name="megaphone" />
                      </span>
                      <div className="row-main">
                        <span className="row-title">
                          {confirm ? (
                            <Bi en={`Confirm the price of ${carName(slot)}`} fa={`تأیید قیمت ${carName(slot)}`} />
                          ) : (
                            <Bi en={`Publish ${carName(slot)}`} fa={`انتشار پست ${carName(slot)}`} />
                          )}
                        </span>
                        <span className="row-meta">
                          <WorkListKindBadge kind="price" />
                          {slot.slot_type === "price_change" ? (
                            <Bi en="Stock price" fa="قیمت موجودی" />
                          ) : (
                            <Bi en="Post" fa="پست" />
                          )}
                          {slot.post_at ? <DateText value={slot.post_at} withTime /> : null}
                        </span>
                        <span className="row-meta work-parent-context">
                          <Bi
                            en="Vehicle pricing — not tied to a work request"
                            fa="قیمت خودرو — به درخواست/پروژهٔ کار وصل نیست"
                          />
                        </span>
                      </div>
                      <div className="row-end">
                        <Button className="btn-sm" to="/pricing">
                          <Bi en="Open" fa="باز کردن" />
                        </Button>
                      </div>
                    </li>
                  );
                })}
                {pendingAi.length > 0 ? (
                  <li className="row-section-head" aria-hidden>
                    <SectionHeader icon="sparkles" title={<Bi en="Assistant" fa="دستیار" />} />
                  </li>
                ) : null}
                {pendingAi.map((row) => (
                  <li key={`ai-${String(row.id)}`} className="row-item">
                    <span className="row-lead">
                      <Icon name="sparkles" />
                    </span>
                    <div className="row-main">
                      <span className="row-title">{String(row.title || row.kind || "تأیید")}</span>
                      <span className="row-meta">
                        <WorkListKindBadge kind="ai" />
                        <Bi en="Assistant approval" fa="تأیید دستیار" />
                      </span>
                      <span className="row-meta work-parent-context">
                        <Bi en="System check — open from admin if you need context" fa="بررسی سیستمی — در صورت نیاز از مدیریت جزئیات را ببینید" />
                      </span>
                    </div>
                    <div className="row-end">
                      <Button
                        variant="secondary"
                        className="btn-sm"
                        onClick={() =>
                          void api.approvals.decide(String(row.id), "approved").then(() =>
                            qc.invalidateQueries({ queryKey: ["approvals", "ai"] }),
                          )
                        }
                      >
                        <Bi en="Approve" fa="تأیید" />
                      </Button>
                      <Button
                        variant="ghost"
                        className="btn-sm"
                        onClick={() =>
                          void api.approvals.decide(String(row.id), "rejected").then(() =>
                            qc.invalidateQueries({ queryKey: ["approvals", "ai"] }),
                          )
                        }
                      >
                        <Bi en="Reject" fa="رد" />
                      </Button>
                    </div>
                  </li>
                ))}
                {unifiedTasks.length > 0 ? (
                  <li className="row-section-head" aria-hidden>
                    <SectionHeader icon="check" title={<Bi en="Tasks" fa="کارها" />} />
                  </li>
                ) : null}
                {unifiedTasks.map((t) => (
                  <TaskRow
                    key={String(t.id)}
                    t={t}
                    late={isOverdue(t.deadline as string | null | undefined, String(t.status))}
                  />
                ))}
                {bucketProjects.length > 0 ? (
                  <li className="row-section-head" aria-hidden>
                    <SectionHeader
                      icon="layers"
                      title={<Bi en="Projects without tasks yet" fa="پروژه بدون کار" />}
                    />
                  </li>
                ) : null}
                {bucketProjects.map((row) => {
                  const projectId = row.project_id ?? row.id;
                  const title = row.title ?? row.project_title ?? "";
                  return (
                    <li key={`project-${row.id}`} className="row-item">
                      <div className="row-main">
                        <span className="row-title">
                          {projectId && showProjectLink ? (
                            <Link to={`/projects/${projectId}`}>{title}</Link>
                          ) : (
                            title
                          )}
                        </span>
                        <WorkParentContext
                          kind="project"
                          origin={row.origin}
                          projectId={projectId}
                          requestId={row.request_id}
                          projectCode={row.project_code ?? row.code}
                          projectTitle={row.project_title ?? row.title}
                          requestCode={row.request_code}
                          requestTitle={row.request_title}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : null}
            {!listLoading && !showUnified && !bucketEmpty ? (
              <ul className="rows">
                {bucketRows.map((row) => {
                  const isProject = queueFilter === "projects_without_tasks" || row.kind === "project";
                  const title = row.title ?? row.project_title ?? "";
                  const projectId = row.project_id ?? row.id;
                  return (
                    <li key={row.id} className="row-item">
                      <div className="row-main">
                        <span className="row-title">
                          {projectId && showProjectLink ? <Link to={`/projects/${projectId}`}>{title}</Link> : title}
                        </span>
                        <WorkParentContext
                          kind={isProject ? "project" : "task"}
                          origin={row.origin}
                          projectId={projectId}
                          requestId={row.request_id}
                          projectCode={row.project_code ?? row.code}
                          projectTitle={row.project_title ?? row.title}
                          requestCode={row.request_code}
                          requestTitle={row.request_title}
                        />
                        {!isProject && row.deadline ? (
                          <span className="row-meta">
                            <DateText value={row.deadline} withTime />
                          </span>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </Card>
        </section>

        <aside className="side-stack">
          <Card className="progress-card">
            <SectionHeader icon="activity" title={<Bi en="Your progress" fa="پیشرفت شما" />} />
            {workQuery.isLoading ? (
              <LoadingState block={false} />
            ) : tasks.length === 0 ? (
              <p className="muted">
                <Bi en="No job has been assigned yet." fa="هنوز کاری به شما سپرده نشده." />
              </p>
            ) : (
              <>
                <div className="progress-nums">
                  <strong>{faNum(pct)}٪</strong>
                  <span className="muted">
                    {faNum(doneTasks)}/{faNum(tasks.length)} <Bi en="done" fa="انجام‌شده" />
                  </span>
                </div>
                <div className="progress-bar" aria-hidden>
                  <span style={{ width: `${pct}%` }} />
                </div>
              </>
            )}
            {tasks.length > 0 ? (
            <div className="mini-stats">
              <div className="mini-stat">
                <span>
                  <Bi en="To do" fa="مانده" />
                </span>
                <strong>{faNum(openTasks.length + priceJobs.length)}</strong>
              </div>
              <div className={`mini-stat${overdue.length ? " is-danger" : ""}`}>
                <span>
                  <Bi en="Late" fa="دیر شده" />
                </span>
                <strong>{faNum(overdue.length)}</strong>
              </div>
            </div>
            ) : null}
          </Card>
        </aside>
      </div>

      <Sheet
        open={Boolean(detailTaskId)}
        onClose={closeTask}
        title={taskDetail.data?.title ? String(taskDetail.data.title) : bi("Task details", "جزئیات کار")}
      >
        {taskDetail.isLoading ? (
          <LoadingState block={false} />
        ) : taskDetail.error ? (
          <ErrorMessage error={taskDetail.error} />
        ) : taskDetail.data && detailTaskId ? (
          <TaskDetailSheet
            taskId={detailTaskId}
            data={taskDetail.data}
            parentLookups={parentLookups}
            canFinish={canFinishTask(taskDetail.data, user?.id)}
            onComplete={async () => {
              await complete(detailTaskId);
              closeTask();
            }}
          />
        ) : null}
      </Sheet>
    </>
  );
}
