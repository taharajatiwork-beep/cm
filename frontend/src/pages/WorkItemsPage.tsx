import { useState, type FormEvent } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Avatar,
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Icon,
  IconButton,
  Input,
  List,
  ListItem,
  LoadingState,
  Muted,
  PageHeader,
  SectionHeader,
  Select,
} from "../components/ui";
import { canFinishTask } from "../lib/collaboration";
import { Bi, useBi } from "../i18n";
import { nextCursor } from "../lib/pagination";
import { queryKeys } from "../lib/queryKeys";
import { DateText } from "../components/DateText";
import { StatusLabel } from "../ux";

const EVENT_LABELS: Record<string, [string, string]> = {
  "work_item.created": ["Project created", "پروژه ساخته شد"],
  "work_item.participant_added": ["Someone joined", "همکاری اضافه شد"],
  "task.created": ["To-do added", "کار جدید اضافه شد"],
  "task.assigned": ["To-do given to someone", "کاری به کسی سپرده شد"],
  "task.reassigned": ["To-do handed over", "کار به فرد دیگری سپرده شد"],
  "task.completed": ["To-do finished", "یک کار انجام شد"],
  "task.participant_added": ["Helper added to a to-do", "به یک کار کمک‌کننده اضافه شد"],
  "task.dependency_added": ["Order of to-dos set", "ترتیب کارها مشخص شد"],
  "conversation.created": ["Conversation started", "گفتگو شروع شد"],
  "message.sent": ["New message", "پیام جدید"],
  "case.created": ["Follow-up opened", "پیگیری باز شد"],
  "case.assigned": ["Follow-up given to someone", "پیگیری به کسی سپرده شد"],
  "case.escalated": ["Sent to manager", "به مدیر ارجاع شد"],
  "sla.warning": ["Deadline is close", "مهلت نزدیک است"],
  "sla.breached": ["Deadline passed", "مهلت گذشت"],
  "sla.escalated": ["Late — sent to manager", "دیر شد و به مدیر ارجاع شد"],
};

export function WorkItemsPage() {
  const { has } = useAuth();
  const canRead = has("work_item.read");
  const navigate = useNavigate();

  const listQuery = useInfiniteQuery({
    queryKey: queryKeys.workItems(canRead),
    enabled: canRead,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => api.workItems.page(pageParam),
    getNextPageParam: (last) => nextCursor(last),
  });
  const people = useQuery({
    queryKey: ["people"],
    enabled: canRead,
    queryFn: () => api.people.list(),
  });
  const rows = listQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const loading = listQuery.isLoading;
  const error = listQuery.isError ? String((listQuery.error as Error).message) : "";

  return (
    <>
      <PageHeader
        title={<Bi en="Projects" fa="پروژه‌ها" />}
        description={
          <Bi
            en="A section manager creates a project, stays its creator, chooses the members, and assigns every task to one of them."
            fa="مدیر بخش پروژه را می‌سازد و سازندهٔ آن می‌ماند. اعضا را انتخاب می‌کند و هر وظیفه را به یکی از همان افراد می‌سپارد."
          />
        }
        actions={
          <Button variant="secondary" to="/my-work">
            <Bi en="Back to My Work" fa="بازگشت به کارهای من" />
          </Button>
        }
      />
      <ErrorMessage error={error} />
      {listQuery.hasNextPage ? (
        <Button variant="secondary" onClick={() => void listQuery.fetchNextPage()}>
          <Bi en="Load more" fa="بیشتر" />
        </Button>
      ) : null}
      <Card padded={false}>
        {loading ? (
          <LoadingState />
        ) : rows.length === 0 ? (
          <EmptyState
            titleEn="No project yet"
            titleFa="هنوز پروژه‌ای نیست"
            bodyEn="When several people need to work on the same thing, start a project from My Work."
            bodyFa="وقتی چند نفر باید روی یک موضوع کار کنند، از «کارهای من» یک پروژه بسازید."
            action={
              <Button onClick={() => navigate("/my-work")}>
                <Bi en="Go to My Work" fa="برو به کارهای من" />
              </Button>
            }
          />
        ) : (
          <ul className="rows">
            {rows.map((h) => (
              <li key={String(h.id)} className="row-item">
                <span className="row-lead">
                  <Icon name="layers" />
                </span>
                <div className="row-main">
                  <Link to={`/work-items/${String(h.id)}`} className="row-title">
                    {String(h.title)}
                  </Link>
                  <span className="row-meta">
                    <StatusLabel status={String(h.status)} />
                    {h.owner_id ? (
                      <span>
                        <Bi en="Creator" fa="سازنده" />:{" "}
                        {String(
                          people.data?.find((person) => String(person.id) === String(h.owner_id))?.full_name || "—",
                        )}
                      </span>
                    ) : null}
                  </span>
                </div>
                <Button variant="secondary" className="btn-sm" to={`/work-items/${String(h.id)}`}>
                  <Bi en="Open" fa="باز کردن" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

export function WorkItemDetailPage() {
  const { id = "" } = useParams();
  const { has, user } = useAuth();
  const bi = useBi();
  const [taskTitle, setTaskTitle] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [memberId, setMemberId] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState("");
  const qc = useQueryClient();

  const detailQuery = useQuery({
    queryKey: queryKeys.workItemDetail(id),
    enabled: Boolean(id),
    queryFn: async () => {
      const [progress, wi, timeline, conversations, people] = await Promise.all([
        api.workItems.progress(id),
        api.workItems.get(id),
        api.workItems.timeline(id),
        api.conversations.list({ workItemId: id }),
        api.people.list().catch(() => [] as Array<Record<string, unknown>>),
      ]);
      return { progress, wi, timeline, conversations, people };
    },
  });
  const progress = detailQuery.data?.progress ?? null;
  const wi = detailQuery.data?.wi ?? null;
  const timeline = detailQuery.data?.timeline ?? [];
  const conversations = detailQuery.data?.conversations ?? [];
  const people = detailQuery.data?.people ?? [];
  const queryError = detailQuery.isError ? String((detailQuery.error as Error).message) : "";

  const invalidateDetail = () =>
    qc.invalidateQueries({ queryKey: queryKeys.workItemsRoot });

  const completeMutation = useMutation({
    mutationFn: (taskId: string) => api.tasks.complete(taskId),
    onSuccess: () => invalidateDetail(),
    onError: (e) => setError(String((e as Error).message)),
  });

  function complete(taskId: string) {
    completeMutation.mutate(taskId);
  }

  const addTaskMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.tasks.create(body),
    onSuccess: () => {
      setTaskTitle("");
      setAssigneeId("");
      setShowAdd(false);
      invalidateDetail();
    },
    onError: (e) => setError(String((e as Error).message)),
  });

  function addTask(e: FormEvent) {
    e.preventDefault();
    if (!assigneeId) return;
    addTaskMutation.mutate({
      title: taskTitle,
      work_item_id: id,
      assignee_ids: [assigneeId],
      priority: "HIGH",
    });
  }

  const addMemberMutation = useMutation({
    mutationFn: (userId: string) => api.workItems.addParticipant(id, userId),
    onSuccess: () => {
      setMemberId("");
      invalidateDetail();
    },
    onError: (e) => setError(String((e as Error).message)),
  });

  function addMember(e: FormEvent) {
    e.preventDefault();
    if (memberId) addMemberMutation.mutate(memberId);
  }

  function personName(uid: unknown) {
    const p = people.find((x) => String(x.id) === String(uid));
    return p ? String(p.full_name) : String(uid).slice(0, 8);
  }

  if (error || queryError) return <ErrorMessage error={error || queryError} />;
  if (!progress || !wi) return <LoadingState />;

  const nextTask = progress.tasks.find((t) => t.status !== "COMPLETED");
  const nextAssignees = Array.isArray(nextTask?.assignees)
    ? (nextTask!.assignees as Array<Record<string, unknown>>)
        .filter((a) => a.role !== "OWNER")
        .map((a) => personName(a.user_id))
        .join("، ")
    : "";
  const openCount = progress.tasks.filter((t) => t.status !== "COMPLETED").length;

  return (
    <>
      <PageHeader
        title={progress.title}
        description={
          <span className="meta-line">
            <StatusLabel status={progress.status} />
            <span>
              <Bi en="Creator" fa="سازنده" />: {personName(wi.owner_id)}
            </span>
            <span>
              {openCount} <Bi en="to-dos left" fa="وظیفهٔ مانده" />
            </span>
            {(progress.overdue_tasks || 0) > 0 ? (
              <span className="danger-text">
                · {progress.overdue_tasks} <Bi en="late" fa="دیر شده" />
              </span>
            ) : null}
          </span>
        }
        actions={
          <>
            {wi.vehicle_id ? (
              <Button variant="secondary" to={`/vehicles/${String(wi.vehicle_id)}`}>
                <Icon name="car" size={14} />
                <Bi en="See the car" fa="دیدن خودرو" />
              </Button>
            ) : null}
            <Button variant="secondary" to="/communication">
              <Icon name="message" size={14} />
              <Bi en="Messages" fa="پیام‌ها" />
            </Button>
          </>
        }
      />

      <div className="split">
        <div className="stack stack--roomy">
          <div className="grid grid-2">
            <Card className="progress-card">
              <div className="progress-nums">
                <strong>{progress.progress_pct}%</strong>
                <span className="muted">
                  {progress.completed_tasks}/{progress.total_tasks} <Bi en="done" fa="انجام‌شده" />
                </span>
              </div>
              <div className="progress-bar" aria-hidden>
                <span style={{ width: `${progress.progress_pct}%` }} />
              </div>
            </Card>
            <div className="next-card">
              <span className="row-lead">
                <Icon
                  name={nextTask ? "arrow" : "circleCheck"}
                  className={nextTask ? "icon-arrow" : undefined}
                />
              </span>
              <div className="row-main">
                <span className="next-label">
                  <Bi en="Next step" fa="قدم بعدی" />
                </span>
                {nextTask ? (
                  <span className="row-title row-title--wrap">
                    {nextAssignees ? <strong>{nextAssignees}: </strong> : null}
                    {String(nextTask.title)}
                  </span>
                ) : (
                  <span>
                    <Bi en="Everything is done." fa="همه کارها انجام شده." />
                  </span>
                )}
              </div>
            </div>
          </div>

          <Card padded={false}>
            <div className="card-bar">
              <SectionHeader
                icon="check"
                title={<Bi en="Tasks" fa="وظایف" />}
                hint={
                  <Bi
                    en="Every task has one person, and that person is a member of this project."
                    fa="هر وظیفه یک مسئول دارد و آن مسئول یکی از اعضای همین پروژه است."
                  />
                }
                count={progress.tasks.length}
              />
              {has("task.write") && !showAdd && (
                <Button variant="secondary" className="btn-sm" onClick={() => setShowAdd(true)}>
                  <Icon name="plus" size={13} />
                  <Bi en="Add a task" fa="افزودن وظیفه" />
                </Button>
              )}
            </div>
            {showAdd && (
              <form className="inline-form compose-pop" onSubmit={addTask}>
                <Input
                  autoFocus
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                  placeholder={bi("What exactly should be done?", "دقیقاً چه کاری باید انجام شود؟")}
                  required
                />
                <Select value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)} required>
                  <option value="">{bi("Who does it?", "مسئول این وظیفه")}</option>
                  {(progress?.participants || []).map((p) => (
                    <option key={`${p.user_id}-${p.role}`} value={String(p.user_id)}>
                      {personName(p.user_id)}
                      {p.role === "OWNER" ? bi(" (creator)", " (سازنده)") : ""}
                    </option>
                  ))}
                </Select>
                <Button type="submit" className="btn-sm" disabled={!taskTitle.trim() || !assigneeId}>
                  <Bi en="Add" fa="افزودن" />
                </Button>
                <IconButton icon="x" label={bi("Cancel", "انصراف")} onClick={() => setShowAdd(false)} />
              </form>
            )}
            {progress.tasks.length === 0 ? (
              <EmptyState
                titleEn="No tasks yet"
                titleFa="هنوز وظیفه‌ای نیست"
                bodyEn="Add a task and choose which member does it. A task without a person is not allowed."
                bodyFa="یک وظیفه اضافه کنید و مشخص کنید کدام عضو انجامش می‌دهد. وظیفه بدون مسئول ثبت نمی‌شود."
              />
            ) : (
              <ul className="rows">
                {progress.tasks.map((t) => {
                  const done = t.status === "COMPLETED";
                  const people = Array.isArray(t.assignees) ? (t.assignees as Array<Record<string, unknown>>) : [];
                  const names = people
                    .filter((a) => a.role !== "OWNER")
                    .map((a) => personName(a.user_id))
                    .join("، ");
                  const mine = canFinishTask(
                    {
                      owner_id: t.owner_id,
                      assignee_ids: people.filter((a) => a.role !== "OWNER").map((a) => a.user_id),
                    },
                    user?.id,
                  );
                  return (
                    <li key={String(t.id)} className="row-item">
                      {done ? (
                        <span className="check-mark check-mark--ok">
                          ✓
                        </span>
                      ) : mine ? (
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
                        <span
                          className="row-title"
                          style={done ? { color: "var(--faint)", textDecoration: "line-through" } : undefined}
                        >
                          {String(t.title)}
                        </span>
                        <span className="row-meta">
                          <Icon name="user" size={11} />
                          <Bi en="Owner" fa="مسئول" />: {names || bi("Unassigned", "بدون مسئول")}
                          {!done && t.status !== "OPEN" ? <StatusLabel status={String(t.status)} /> : null}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>

        <aside className="side-stack">
          <Card>
            <SectionHeader
              icon="users"
              title={<Bi en="Members" fa="اعضا" />}
              hint={
                <Bi
                  en="The creator is always a member. Others join only when someone adds them."
                  fa="سازنده همیشه عضو است. بقیه فقط وقتی عضو می‌شوند که اضافه شوند."
                />
              }
              count={(progress.participants || []).length}
            />
            {(progress.participants || []).length === 0 ? (
              <Muted>
                <Bi en="No one linked yet." fa="هنوز کسی وصل نشده." />
              </Muted>
            ) : (
              <ul className="people-involved">
                {[...(progress.participants || [])]
                  .sort((a, b) => Number(b.role === "OWNER") - Number(a.role === "OWNER"))
                  .map((p) => (
                  <li key={`${p.user_id}-${p.role}`}>
                    <Avatar name={personName(p.user_id)} size={26} />
                    <strong>{personName(p.user_id)}</strong>
                    <span className="badge">
                      {p.role === "OWNER" ? bi("Creator", "سازنده") : bi("Member", "عضو")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {has("work_item.write") ? (
              <form className="inline-form member-add" onSubmit={addMember}>
                <Select
                  value={memberId}
                  onChange={(e) => setMemberId(e.target.value)}
                  aria-label={bi("Add a member", "افزودن عضو")}
                >
                  <option value="">{bi("Add a member", "افزودن عضو")}</option>
                  {people
                    .filter(
                      (person) =>
                        !(progress.participants || []).some((p) => String(p.user_id) === String(person.id)),
                    )
                    .map((person) => (
                      <option key={String(person.id)} value={String(person.id)}>
                        {String(person.full_name)}
                      </option>
                    ))}
                </Select>
                <Button type="submit" className="btn-sm" disabled={!memberId || addMemberMutation.isPending}>
                  <Bi en="Add" fa="افزودن" />
                </Button>
              </form>
            ) : null}
          </Card>

          <Card>
            <SectionHeader
              icon="message"
              title={<Bi en="Conversations" fa="گفتگوها" />}
              count={conversations.length}
            />
            {conversations.length === 0 ? (
              <Muted>
                <Bi
                  en="No messages yet. In Messages, start a new one and attach it to this project."
                  fa="هنوز پیامی نیست. در «پیام‌ها» گفتگوی جدید بسازید و به این پروژه وصلش کنید."
                />
              </Muted>
            ) : (
              <ul className="work-threads">
                {conversations.map((c) => (
                  <li key={String(c.id)}>
                    <Button variant="ghost" to="/communication">
                      <Icon name="message" size={12} />
                      {String(c.topic || bi("Thread", "گفتگو"))}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {timeline.length > 0 && (
            <details className="advanced">
              <summary>
                <Bi en="What happened so far" fa="چه اتفاقاتی افتاده" />
                <span className="muted">({timeline.length})</span>
              </summary>
              <div className="advanced-body">
                <List variant="timeline">
                  {timeline.slice(0, 8).map((e) => {
                    const label = EVENT_LABELS[String(e.event_type)];
                    return (
                      <ListItem key={String(e.id)}>
                        <span>{label ? bi(label[0], label[1]) : bi("Updated", "به‌روزرسانی شد")}</span>
                        <div className="muted fine">
                          <DateText value={e.created_at} withTime />
                        </div>
                      </ListItem>
                    );
                  })}
                </List>
              </div>
            </details>
          )}
        </aside>
      </div>
    </>
  );
}

