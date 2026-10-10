import { useId, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { requestsApi } from "../requests/api";
import { useAuth } from "../auth";
import {
  Avatar,
  Button,
  Card,
  Dialog,
  EmptyState,
  ErrorMessage,
  Field,
  Icon,
  IconButton,
  Input,
  PageHeader,
  SectionHeader,
  Segmented,
  Select,
} from "../components/ui";
import { Bi, useBi, useLocale } from "../i18n";
import { formatDeadline, isOverdue } from "../lib/collaboration";
import { DateText } from "../components/DateText";
import { faNum } from "../fa";
import { StatusLabel } from "../ux";

type Tab = "tasks" | "overdue" | "shared";
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

function ProjectStartPop({
  userId,
  userName,
  colleagues,
  onClose,
}: {
  userId: string;
  userName: string;
  colleagues: Array<Record<string, unknown>>;
  onClose: () => void;
}) {
  const bi = useBi();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [members, setMembers] = useState<string[]>([]);
  const [draftTasks, setDraftTasks] = useState<Array<{ title: string; assigneeId: string }>>([
    { title: "", assigneeId: "" },
  ]);
  const [formError, setFormError] = useState("");
  const [creating, setCreating] = useState(false);

  const titleId = useId();

  function personName(id: string) {
    if (id === userId) return userName;
    const person = colleagues.find((row) => String(row.id) === id);
    return person ? String(person.full_name || person.email) : "";
  }

  function toggleMember(id: string) {
    setMembers((current) => {
      const next = current.includes(id) ? current.filter((item) => item !== id) : [...current, id];
      const allowed = new Set([userId, ...next]);
      setDraftTasks((rows) =>
        rows.map((row) => (row.assigneeId && !allowed.has(row.assigneeId) ? { ...row, assigneeId: "" } : row)),
      );
      return next;
    });
  }

  async function createShared(e: FormEvent) {
    e.preventDefault();
    const ready = draftTasks
      .map((row) => ({ title: row.title.trim(), assigneeId: row.assigneeId }))
      .filter((row) => row.title);
    if (!title.trim() || ready.length === 0 || ready.some((row) => !row.assigneeId)) {
      setFormError(
        bi(
          "Each task needs a title and a person who is the creator or a member.",
          "هر وظیفه باید عنوان داشته باشد و مسئولش سازنده یا یکی از اعضا باشد.",
        ),
      );
      return;
    }
    setCreating(true);
    setFormError("");
    try {
      const wi = await api.workItems.create({
        title: title.trim(),
        priority: "HIGH",
        participant_ids: members,
      });
      for (const task of ready) {
        await api.tasks.create({
          title: task.title,
          work_item_id: wi.id,
          assignee_ids: [task.assigneeId],
          priority: "HIGH",
        });
      }
      navigate(`/work-items/${String(wi.id)}`);
    } catch (err) {
      setFormError(String((err as Error).message));
      setCreating(false);
    }
  }

  return (
    <Dialog
      onClose={onClose}
      className="project-pop"
      labelledBy={titleId}
      closeLabel={bi("Close", "بستن")}
      busy={creating}
      as="form"
      onSubmit={createShared}
    >
        <SectionHeader
          icon="plus"
          title={<span id={titleId}><Bi en="Start a project" fa="شروع یک پروژه" /></span>}
          action={
            <button type="button" className="kpi-more" onClick={onClose}>
              <Bi en="Close" fa="بستن" />
            </button>
          }
        />
        <p className="help-text">
          <Bi
            en="Only someone allowed to create projects can open this. You stay the creator and a member. Choose who else joins, then give every task to the creator or one of those members."
            fa="این پنجره فقط برای کسی است که اجازهٔ ساخت پروژه دارد. سازنده خودتان می‌مانید و همیشه عضو هستید. بقیهٔ اعضا را انتخاب کنید و هر وظیفه را به خودتان یا یکی از آن‌ها بسپارید."
          />
        </p>
        <div className="project-pop-body">
          <Field label={<Bi en="Project name" fa="نام پروژه" />}>
            <Input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              placeholder={bi("e.g. Sell Camry #124", "مثلاً فروش کمری ۱۲۴")}
            />
          </Field>
          <Field label={<Bi en="Creator" fa="سازنده" />}>
            <div className="project-creator">
              <Avatar name={userName} size={32} />
              <div>
                <strong>{userName}</strong>
                <span className="muted">
                  <Bi en="Always a member. This does not change." fa="همیشه عضو است و عوض نمی‌شود." />
                </span>
              </div>
            </div>
          </Field>
          <Field
            label={
              <>
                <Bi en="Other members" fa="اعضای دیگر" />
                {members.length > 0 ? <span className="muted"> · {members.length.toLocaleString("fa-IR")}</span> : null}
              </>
            }
          >
            {colleagues.length === 0 ? (
              <p className="help-text">
                <Bi
                  en="No other colleague is in your section. The project will only include you."
                  fa="همکار دیگری در بخش شما نیست. پروژه فقط خودتان را عضو دارد."
                />
              </p>
            ) : (
              <ul className="member-picks">
                {[...colleagues]
                  .sort((a, b) =>
                    String(a.full_name || a.email).localeCompare(String(b.full_name || b.email), "fa"),
                  )
                  .map((person) => {
                    const id = String(person.id);
                    const name = String(person.full_name || person.email);
                    const picked = members.includes(id);
                    return (
                      <li key={id}>
                        <label className={`member-pick${picked ? " is-on" : ""}`}>
                          <input
                            className="member-pick-input"
                            type="checkbox"
                            checked={picked}
                            onChange={() => toggleMember(id)}
                          />
                          <span className="member-pick-box" aria-hidden />
                          <Avatar name={name} size={28} />
                          <span className="member-pick-name">{name}</span>
                        </label>
                      </li>
                    );
                  })}
              </ul>
            )}
          </Field>
          <Field label={<Bi en="Tasks" fa="وظایف" />}>
            <div className="draft-tasks">
              {draftTasks.map((row, index) => (
                <div className="draft-task" key={index}>
                  <Input
                    value={row.title}
                    onChange={(e) =>
                      setDraftTasks((rows) =>
                        rows.map((item, i) => (i === index ? { ...item, title: e.target.value } : item)),
                      )
                    }
                    placeholder={bi("What exactly should be done?", "دقیقاً چه کاری باید انجام شود؟")}
                    aria-label={bi("Task", "وظیفه")}
                    required={index === 0}
                  />
                  <Select
                    value={row.assigneeId}
                    onChange={(e) =>
                      setDraftTasks((rows) =>
                        rows.map((item, i) => (i === index ? { ...item, assigneeId: e.target.value } : item)),
                      )
                    }
                    aria-label={bi("Who does it?", "مسئول این وظیفه")}
                    required={Boolean(row.title.trim()) || index === 0}
                  >
                    <option value="">{bi("Who does it?", "مسئول این وظیفه")}</option>
                    <option value={userId}>
                      {userName} ({bi("creator", "سازنده")})
                    </option>
                    {members.map((id) => (
                      <option key={id} value={id}>
                        {personName(id)}
                      </option>
                    ))}
                  </Select>
                  {draftTasks.length > 1 ? (
                    <IconButton
                      icon="x"
                      label={bi("Remove task", "حذف وظیفه")}
                      onClick={() => setDraftTasks((rows) => rows.filter((_, i) => i !== index))}
                    />
                  ) : (
                    <span />
                  )}
                </div>
              ))}
            </div>
            <Button
              type="button"
              variant="ghost"
              className="btn-sm"
              onClick={() => setDraftTasks((rows) => [...rows, { title: "", assigneeId: "" }])}
            >
              <Icon name="plus" size={13} />
              <Bi en="Another task" fa="وظیفهٔ دیگر" />
            </Button>
          </Field>
          <ErrorMessage error={formError} />
        </div>
        <div className="compose-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            <Bi en="Cancel" fa="انصراف" />
          </Button>
          <Button type="submit" disabled={!title.trim() || creating}>
            {creating ? <Bi en="Creating…" fa="در حال ساخت…" /> : <Bi en="Create" fa="ساختن" />}
          </Button>
        </div>
    </Dialog>
  );
}

function WorkBuckets() {
  const buckets = useQuery({ queryKey: ["requests", "my-work"], queryFn: () => requestsApi.myWork() });
  if (!buckets.data) return null;
  const labels: Array<[string, string, string]> = [
    ["overdue", "Late", "عقب‌افتاده"],
    ["today", "Today", "امروز"],
    ["later", "Later", "آینده"],
    ["waiting", "Waiting on others", "منتظر دیگران"],
    ["projects_without_tasks", "Team projects with no task", "پروژه بدون وظیفه"],
  ];
  return (
    <div className="kpi-row kpi-row--4">
      {labels.map(([key, en, fa]) => (
        <Card key={key}>
          <SectionHeader title={<Bi en={en} fa={fa} />} count={(buckets.data?.[key] ?? []).length} />
          <ul className="plain-list">
            {(buckets.data?.[key] ?? []).slice(0, 5).map((row) => (
              <li key={row.id}>{row.title}</li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

export function MyWorkPage() {
  const { user, roleHint, has } = useAuth();
  const bi = useBi();
  const canProjects = has("work_item.read");
  const canPrice = has("price.write");
  const canPost = has("campaign.write");
  const [tab, setTab] = useState<Tab>("tasks");
  const [projectOpen, setProjectOpen] = useState(false);
  const qc = useQueryClient();
  const workQuery = useQuery({
    queryKey: ["my-work", user?.id, roleHint],
    enabled: Boolean(user?.id),
    queryFn: async () => {
      const tasks = has("task.read") && user?.id ? await api.tasks.list({ assignee_id: user.id }) : [];
      const overdue =
        has("task.read") && (roleHint === "manager" || roleHint === "admin")
          ? await api.tasks.list({ overdue_only: true })
          : tasks.filter((t) => isOverdue(t.deadline, t.status));
      const shared = has("work_item.read") ? await api.workItems.list() : [];
      return { tasks, overdue, shared };
    },
  });
  const people = useQuery({
    queryKey: ["people"],
    enabled: canProjects,
    queryFn: () => api.people.list(),
  });
  const colleagues = (people.data ?? []).filter((person) => String(person.id) !== user?.id);
  const pricing = useQuery({
    queryKey: ["pricing-board", "my-work", user?.id],
    enabled: Boolean(user?.id) && (canPrice || canPost),
    queryFn: () => api.pricing.board(),
  });
  const tasks = workQuery.data?.tasks ?? [];
  const overdue = workQuery.data?.overdue ?? [];
  const shared = canProjects ? (workQuery.data?.shared ?? []) : [];
  const priceJobs = ((pricing.data?.slots ?? []) as Slot[]).filter((slot) => {
    if (canPrice && (slot.status === "requested" || slot.status === "needs_recheck")) return true;
    if (canPost && slot.status === "confirmed") return true;
    return false;
  });
  const error = workQuery.isError ? String((workQuery.error as Error).message) : "";

  async function complete(id: string) {
    await api.tasks.complete(id);
    await qc.invalidateQueries({ queryKey: ["my-work"] });
  }

  function personName(id: unknown) {
    const person = (people.data ?? []).find((row) => String(row.id) === String(id));
    if (person) return String(person.full_name || person.email);
    if (String(id) === user?.id) return user?.full_name || "";
    return "";
  }

  const openTasks = tasks.filter((t) => t.status !== "COMPLETED");
  const doneTasks = tasks.length - openTasks.length;
  const activeShared = shared.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  const pct = tasks.length ? Math.round((doneTasks / tasks.length) * 100) : 0;

  const description = canProjects
    ? bi(
        "Your own jobs, and the projects of your section. Price checks and posts that need you are in the same list.",
        "کارهای خودتان و پروژه‌های بخش شما. تأیید قیمت و پست‌هایی که به شما مربوط است همین‌جا هستند.",
      )
    : bi(
        "Jobs that need you, including a price to confirm or a post to publish.",
        "کارهایی که باید انجام دهید، از جمله تأیید قیمت یا انتشار پست.",
      );

  function TaskRow({ t, late }: { t: Row; late?: boolean }) {
    const { locale } = useLocale();
    const deadline = formatDeadline(t.deadline, bi, locale);
    return (
      <li className={`row-item${late ? " is-danger" : ""}`}>
        <button
          type="button"
          className="done-btn"
          title={bi("Mark done", "انجام شد")}
          aria-label={bi("Mark done", "انجام شد")}
          onClick={() => void complete(String(t.id))}
        >
          <Icon name="check" size={12} />
        </button>
        <div className="row-main">
          <span className="row-title">{String(t.title)}</span>
          <span className="row-meta">
            {t.status !== "ASSIGNED" && t.status !== "OPEN" ? <StatusLabel status={String(t.status)} /> : null}
            {deadline ? (
              <span className={late ? "danger-text" : undefined}>
                <Icon name="clock" size={11} /> {deadline}
              </span>
            ) : null}
          </span>
        </div>
        {t.work_item_id ? (
          <div className="row-end">
            <Button variant="ghost" to={`/work-items/${String(t.work_item_id)}`}>
              <Icon name="layers" size={13} />
              <Bi en="View project" fa="دیدن پروژه" />
            </Button>
          </div>
        ) : null}
      </li>
    );
  }

  return (
    <>
      <PageHeader title={<Bi en="My Work" fa="کارهای من" />} description={description} />
      <WorkBuckets />
      <ErrorMessage error={error} />

      <div className="split">
        <section>
          <div className="section-head">
            <Segmented
              value={tab}
              onChange={setTab}
              items={[
                {
                  key: "tasks",
                  icon: "check",
                  label: bi("To do", "باید انجام دهم"),
                  count: openTasks.length + priceJobs.length,
                },
                { key: "overdue", icon: "alert", label: bi("Late", "دیر شده"), count: overdue.length },
                ...(canProjects
                  ? [
                      {
                        key: "shared" as const,
                        icon: "layers" as const,
                        label: bi("Projects", "پروژه‌ها"),
                        count: shared.length,
                      },
                    ]
                  : []),
              ]}
            />
          </div>
          <p className="help-text">
            {tab === "shared"
              ? has("work_item.write")
                ? bi(
                    "Only someone allowed to create projects can start one. You are the creator. Add the members, then give each task to the creator or a member.",
                    "فقط کسی که اجازهٔ ساخت پروژه دارد می‌تواند پروژه بسازد. سازنده خود شما هستید. اعضا را انتخاب کنید و هر وظیفه را به سازنده یا یکی از اعضا بسپارید.",
                  )
                : bi(
                    "You can see projects in your section, and any project you are a member of. Starting a project needs the create-project permission; in this company that is the section manager.",
                    "پروژه‌های بخش خودتان و هر پروژه‌ای که عضوش هستید را می‌بینید. ساختن پروژه اجازهٔ جدا می‌خواهد؛ در این شرکت آن اجازه با مدیر بخش است.",
                  )
              : bi(
                  "Tap the circle when a job is done. Late items are shown in red.",
                  "وقتی کاری تمام شد روی دایره بزنید. کارهای دیرشده قرمز نمایش داده می‌شوند.",
                )}
          </p>

          <Card padded={false}>
            {tab === "tasks" &&
              (openTasks.length + priceJobs.length === 0 ? (
                <EmptyState
                  titleEn="Nothing to do right now"
                  titleFa="فعلاً کاری ندارید"
                  bodyEn="When someone gives you a job, or a post needs a price, it shows up here."
                  bodyFa="وقتی کاری به شما سپرده شود، یا پستی به قیمت نیاز داشته باشد، اینجا نمایش داده می‌شود."
                />
              ) : (
                <ul className="rows">
                  {priceJobs.map((slot) => {
                    const confirm = slot.status === "requested" || slot.status === "needs_recheck";
                    return (
                      <li key={slot.id} className="row-item">
                        <span className="row-lead">
                          <Icon name="megaphone" />
                        </span>
                        <div className="row-main">
                          <Link to="/pricing" className="row-title">
                            {confirm ? (
                              <Bi en={`Confirm the price of ${carName(slot)}`} fa={`تأیید قیمت ${carName(slot)}`} />
                            ) : (
                              <Bi en={`Publish ${carName(slot)}`} fa={`انتشار پست ${carName(slot)}`} />
                            )}
                          </Link>
                          <span className="row-meta">
                            {slot.slot_type === "price_change" ? (
                              <Bi en="Stock price" fa="قیمت موجودی" />
                            ) : (
                              <Bi en="Post" fa="پست" />
                            )}
                            {slot.post_at ? <DateText value={slot.post_at} withTime /> : null}
                          </span>
                        </div>
                        <div className="row-end">
                          <Button variant="secondary" className="btn-sm" to="/pricing">
                            <Bi en="Open" fa="باز کردن" />
                          </Button>
                        </div>
                      </li>
                    );
                  })}
                  {openTasks.map((t) => (
                    <TaskRow key={String(t.id)} t={t} late={isOverdue(t.deadline, t.status)} />
                  ))}
                </ul>
              ))}

            {tab === "overdue" &&
              (overdue.length === 0 ? (
                <EmptyState
                  titleEn="Nothing is late"
                  titleFa="هیچ کاری دیر نشده"
                  bodyEn="Great — everything is on time."
                  bodyFa="عالی — همه‌چیز سر وقت است."
                />
              ) : (
                <ul className="rows">
                  {overdue.map((t) => (
                    <TaskRow key={String(t.id)} t={t} late />
                  ))}
                </ul>
              ))}

            {tab === "shared" &&
              (shared.length === 0 ? (
                <EmptyState
                  titleEn="No project yet"
                  titleFa="هنوز پروژه‌ای نیست"
                  bodyEn={
                    has("work_item.write")
                      ? "Open Start a project. You become the creator, then choose members and a task for each person."
                      : "A section manager starts a project, names the members, and assigns each task."
                  }
                  bodyFa={
                    has("work_item.write")
                      ? "«شروع یک پروژه» را بزنید. شما سازنده می‌شوید، بعد اعضا و وظیفهٔ هر کدام را مشخص می‌کنید."
                      : "مدیر بخش پروژه را می‌سازد، اعضا را انتخاب می‌کند و برای هر وظیفه یک مسئول می‌گذارد."
                  }
                />
              ) : (
                <ul className="rows">
                  {shared.map((w) => (
                    <li key={String(w.id)} className="row-item">
                      <span className="row-lead">
                        <Icon name="layers" />
                      </span>
                      <div className="row-main">
                        <Link to={`/work-items/${String(w.id)}`} className="row-title">
                          {String(w.title)}
                        </Link>
                        <span className="row-meta">
                          <StatusLabel status={String(w.status)} />
                          {w.owner_id ? (
                            <span>
                              <Bi en="Creator" fa="سازنده" />: {personName(w.owner_id) || "—"}
                            </span>
                          ) : null}
                        </span>
                      </div>
                      <div className="row-end">
                        <Button variant="secondary" className="btn-sm" to={`/work-items/${String(w.id)}`}>
                          <Bi en="Open" fa="باز کردن" />
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              ))}
          </Card>
        </section>

        <aside className="side-stack">
          <Card className="progress-card">
            <SectionHeader icon="activity" title={<Bi en="Your progress" fa="پیشرفت شما" />} />
            <div className="progress-nums">
              <strong>{faNum(pct)}٪</strong>
              <span className="muted">
                {faNum(doneTasks)}/{faNum(tasks.length)} <Bi en="done" fa="انجام‌شده" />
              </span>
            </div>
            <div className="progress-bar" aria-hidden>
              <span style={{ width: `${pct}%` }} />
            </div>
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
              {canProjects ? (
                <div className="mini-stat">
                  <span>
                    <Bi en="Projects" fa="پروژه‌ها" />
                  </span>
                  <strong>{faNum(activeShared.length)}</strong>
                </div>
              ) : null}
            </div>
          </Card>

          {has("work_item.write") && (
            <Card stack>
              <SectionHeader icon="plus" title={<Bi en="Start a project" fa="شروع یک پروژه" />} />
              <p className="help-text">
                <Bi
                  en="You can create a project. The window asks for the name, the members, and who does each task."
                  fa="شما اجازهٔ ساخت پروژه را دارید. پنجره نام، اعضا و مسئول هر وظیفه را می‌پرسد."
                />
              </p>
              <Button onClick={() => setProjectOpen(true)}>
                <Bi en="Start a project" fa="شروع یک پروژه" />
              </Button>
            </Card>
          )}
          {projectOpen && user ? (
            <ProjectStartPop
              userId={user.id}
              userName={user.full_name}
              colleagues={colleagues}
              onClose={() => setProjectOpen(false)}
            />
          ) : null}
        </aside>
      </div>
    </>
  );
}
