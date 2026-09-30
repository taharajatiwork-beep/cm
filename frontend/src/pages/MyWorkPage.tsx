import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Icon,
  Input,
  PageHeader,
  SectionHeader,
  Segmented,
} from "../components/ui";
import { Bi, useBi, useLocale } from "../i18n";
import { formatDeadline, isOverdue } from "../lib/collaboration";
import { StatusLabel } from "../ux";

type Tab = "tasks" | "overdue" | "shared";
type Row = Record<string, unknown>;

export function MyWorkPage() {
  const { user, roleHint, has } = useAuth();
  const bi = useBi();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("tasks");
  const [newTitle, setNewTitle] = useState("");
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
  const tasks = workQuery.data?.tasks ?? [];
  const overdue = workQuery.data?.overdue ?? [];
  const shared = workQuery.data?.shared ?? [];
  const error = workQuery.isError ? String((workQuery.error as Error).message) : "";

  async function complete(id: string) {
    await api.tasks.complete(id);
    await qc.invalidateQueries({ queryKey: ["my-work"] });
  }

  async function createShared(e: FormEvent) {
    e.preventDefault();
    const wi = await api.workItems.create({ title: newTitle, priority: "HIGH" });
    navigate(`/work-items/${wi.id}`);
  }

  const openTasks = tasks.filter((t) => t.status !== "COMPLETED");
  const doneTasks = tasks.length - openTasks.length;
  const activeShared = shared.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  const pct = tasks.length ? Math.round((doneTasks / tasks.length) * 100) : 0;

  const description = bi(
    "Everything you need to do, in one list. Finish one, tick the circle, move to the next.",
    "همه کارهایی که باید انجام دهید در یک فهرست. هر کار را که تمام کردید، دایره‌اش را بزنید و سراغ بعدی بروید.",
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
      <ErrorMessage error={error} />

      <div className="split">
        <section>
          <div className="section-head">
            <Segmented
              value={tab}
              onChange={setTab}
              items={[
                { key: "tasks", icon: "check", label: bi("To do", "باید انجام دهم"), count: openTasks.length },
                { key: "overdue", icon: "alert", label: bi("Late", "دیر شده"), count: overdue.length },
                {
                  key: "shared",
                  icon: "layers",
                  label: bi("Projects", "پروژه‌ها"),
                  count: shared.length,
                },
              ]}
            />
          </div>
          <p className="help-text">
            {tab === "shared"
              ? bi(
                  "A project is a bigger job several people do together, like selling one car. Open it to see who does what.",
                  "پروژه یعنی یک کار بزرگ‌تر که چند نفر با هم انجام می‌دهند؛ مثلاً فروش یک خودرو. بازش کنید تا ببینید چه کسی چه می‌کند.",
                )
              : bi(
                  "Tap the circle when a job is done. Late items are shown in red.",
                  "وقتی کاری تمام شد روی دایره بزنید. کارهای دیرشده قرمز نمایش داده می‌شوند.",
                )}
          </p>

          <Card padded={false}>
            {tab === "tasks" &&
              (openTasks.length === 0 ? (
                <EmptyState
                  titleEn="Nothing to do right now"
                  titleFa="فعلاً کاری ندارید"
                  bodyEn="When someone gives you a job, it shows up here."
                  bodyFa="وقتی کسی کاری به شما بسپارد، اینجا نمایش داده می‌شود."
                />
              ) : (
                <ul className="rows">
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
                  bodyEn="Start one from the box on the side when several people need to work on the same thing."
                  bodyFa="وقتی چند نفر باید روی یک موضوع کار کنند، از کادر کناری یک پروژه بسازید."
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
              <strong>{pct}%</strong>
              <span className="muted">
                {doneTasks}/{tasks.length} <Bi en="done" fa="انجام‌شده" />
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
                <strong>{openTasks.length}</strong>
              </div>
              <div className={`mini-stat${overdue.length ? " is-danger" : ""}`}>
                <span>
                  <Bi en="Late" fa="دیر شده" />
                </span>
                <strong>{overdue.length}</strong>
              </div>
              <div className="mini-stat">
                <span>
                  <Bi en="Projects" fa="پروژه‌ها" />
                </span>
                <strong>{activeShared.length}</strong>
              </div>
            </div>
          </Card>

          {has("work_item.write") && (
            <Card as="form" stack onSubmit={createShared}>
              <SectionHeader icon="plus" title={<Bi en="Start a project" fa="شروع یک پروژه" />} />
              <p className="help-text">
                <Bi
                  en="Give it a short name. Next you can add people and split the work."
                  fa="یک نام کوتاه بدهید. در قدم بعد همکاران را اضافه و کار را بینشان تقسیم می‌کنید."
                />
              </p>
              <Input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                required
                placeholder={bi("e.g. Sell Camry #124", "مثلاً فروش کمری ۱۲۴")}
              />
              <div className="compose-actions">
                <Button type="submit" disabled={!newTitle.trim()}>
                  <Bi en="Create" fa="ساختن" />
                </Button>
              </div>
            </Card>
          )}
        </aside>
      </div>
    </>
  );
}
