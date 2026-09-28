import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Icon,
  type IconName,
  Input,
  LoadingState,
  PageHeader,
  SectionHeader,
  StatCard,
} from "../components/ui";
import { Bi, useBi, useLocale } from "../i18n";
import { formatJalaliLong } from "../jalali";
import {
  type AttentionStory,
  assigneeNames,
  buildPersonMap,
  formatDeadline,
  isOverdue,
  personName,
  taskMark,
} from "../lib/collaboration";
import { OnboardingBanner, dismissOnboarding, shouldShowOnboarding } from "../ux";

export function HomePage() {
  const { user, roleHint, has } = useAuth();
  const bi = useBi();
  const { locale } = useLocale();
  const [showOnboard, setShowOnboard] = useState(shouldShowOnboarding);
  const [askText, setAskText] = useState("");
  const navigate = useNavigate();

  const inbox = useQuery({
    queryKey: ["home-inbox", user?.id, roleHint, locale],
    queryFn: async () => {
      const out: AttentionStory[] = [];
      let roleHintLine = "";
        const people = await api.people.list().catch(() => []);
        const map = buildPersonMap(people);

        if (roleHint === "manager" || roleHint === "admin") {
          roleHintLine = bi(
            "Who’s waiting on you — and where work is slipping.",
            "چه کسی منتظر شماست — و کجا کار عقب افتاده.",
          );
        } else if (roleHint === "seller") {
          roleHintLine = bi(
            "What’s assigned to you — and who is waiting for your next step.",
            "چه چیزی به شما سپرده شده — و چه کسی منتظر قدم بعدی شماست.",
          );
        } else if (roleHint === "marketing") {
          roleHintLine = bi(
            "Which listings and campaigns need you today.",
            "کدام آگهی‌ها و کمپین‌ها امروز به شما نیاز دارند.",
          );
        } else {
          roleHintLine = bi("What’s happening around you.", "الان اطراف شما چه خبر است.");
        }

        const myTasks =
          user?.id && has("task.read")
            ? await api.tasks.list({ assignee_id: user.id })
            : [];
        const openMine = myTasks.filter((t) => t.status !== "COMPLETED");

        const overdue =
          has("task.read") && (roleHint === "manager" || roleHint === "admin")
            ? await api.tasks.list({ overdue_only: true })
            : openMine.filter((t) => isOverdue(t.deadline, t.status));

        const wiIds = new Set<string>();
        for (const t of [...openMine, ...overdue]) {
          if (t.work_item_id) wiIds.add(String(t.work_item_id));
        }

        for (const wiId of [...wiIds].slice(0, 8)) {
          try {
            const prog = await api.workItems.progress(wiId);
            const openTasks = prog.tasks.filter((t) => t.status !== "COMPLETED");
            const lines = openTasks.slice(0, 4).map((t) => ({
              text: `${assigneeNames(t.assignees, map, bi)} → ${String(t.title)}`,
              done: false,
              waiting: isOverdue(t.deadline, t.status),
            }));
            const nearest = openTasks
              .map((t) => t.deadline)
              .filter(Boolean)
              .sort()[0];
            const tone =
              (prog.overdue_tasks || 0) > 0 || openTasks.some((t) => isOverdue(t.deadline, t.status))
                ? "danger"
                : openTasks.length
                  ? "warn"
                  : undefined;
            out.push({
              id: `wi-${wiId}`,
              title: prog.title,
              href: `/work-items/${wiId}`,
              lines:
                lines.length > 0
                  ? lines
                  : [{ text: bi("All to-dos done", "همه کارها انجام شده"), done: true }],
              deadline: formatDeadline(nearest, bi, locale),
              tone,
              kind: "shared",
              waitingOnMe: openTasks.some((t) =>
                Array.isArray(t.assignees)
                  ? (t.assignees as Array<Record<string, unknown>>).some(
                      (a) => String(a.user_id) === String(user?.id),
                    )
                  : false,
              ),
            });
          } catch {
            /* skip */
          }
        }

        if (has("case.read") && (roleHint === "manager" || roleHint === "admin")) {
          const branchCases = await api.cases
            .list({ type: "BRANCH_REQUEST" })
            .catch(() => []);
          for (const c of branchCases
            .filter((x) => x.status !== "COMPLETED" && x.status !== "CANCELLED")
            .slice(0, 4)) {
            out.push({
              id: `case-${c.id}`,
              title: String(c.subject),
              href: c.work_item_id ? `/work-items/${c.work_item_id}` : "/cases",
              lines: [
                {
                  text: bi("Waiting for your response", "منتظر پاسخ شما"),
                  waiting: true,
                },
                {
                  text: `${bi("Owner", "مسئول")}: ${personName(map, c.owner_id)}`,
                },
              ],
              deadline: formatDeadline(c.deadline, bi, locale),
              tone: c.sla_state === "BREACHED" || c.sla_state === "ESCALATED" ? "danger" : "warn",
              kind: "branch",
              waitingOnMe: true,
            });
          }
        }

        if (has("campaign.read")) {
          const camps = await api.campaigns.list().catch(() => []);
          for (const camp of camps.filter((c) => c.status === "ACTIVE").slice(0, 3)) {
            let overdueCount = 0;
            if (camp.work_item_id) {
              try {
                const prog = await api.workItems.progress(String(camp.work_item_id));
                overdueCount = prog.overdue_tasks || 0;
              } catch {
                /* ignore */
              }
            }
            if (overdueCount > 0 || camp.status === "ACTIVE") {
              out.push({
                id: `camp-${camp.id}`,
                title: String(camp.title),
                href: "/communication",
                lines: [
                  {
                    text:
                      overdueCount > 0
                        ? bi(
                            `${overdueCount} late to-dos`,
                            `${overdueCount} کار عقب‌افتاده`,
                          )
                        : bi("Campaign in progress", "کمپین در جریان"),
                    waiting: overdueCount > 0,
                  },
                ],
                tone: overdueCount > 0 ? "danger" : undefined,
                kind: "campaign",
              });
            }
          }
        }

        for (const t of openMine.filter((x) => !x.work_item_id).slice(0, 3)) {
          out.push({
            id: `task-${t.id}`,
            title: String(t.title),
            href: "/my-work",
            lines: [{ text: bi("Assigned to you", "به شما سپرده شده") }],
            deadline: formatDeadline(t.deadline, bi, locale),
            tone: isOverdue(t.deadline, t.status) ? "danger" : undefined,
            kind: "task",
            waitingOnMe: true,
          });
        }

        const seen = new Set<string>();
        const ranked = out
          .sort((a, b) => {
            const score = (s: AttentionStory) =>
              (s.tone === "danger" ? 0 : s.tone === "warn" ? 1 : 2) +
              (s.waitingOnMe ? 0 : 1);
            return score(a) - score(b);
          })
          .filter((s) => {
            if (seen.has(s.title)) return false;
            seen.add(s.title);
            return true;
          });
        return { stories: ranked.slice(0, 8), roleHintLine };
    },
  });
  const stories = inbox.data?.stories ?? [];
  const roleHintLine = inbox.data?.roleHintLine ?? "";
  const loading = inbox.isLoading;
  const error = inbox.isError ? String((inbox.error as Error).message) : "";

  const hour = new Date().getHours();
  const greet =
    hour < 12
      ? bi("Good morning", "صبح بخیر")
      : hour < 18
        ? bi("Good afternoon", "ظهر بخیر")
        : bi("Good evening", "عصر بخیر");

  const todayLabel =
    locale === "fa"
      ? formatJalaliLong(new Date())
      : new Date().toLocaleDateString(undefined, {
          weekday: "long",
          month: "long",
          day: "numeric",
        });

  const waiting = stories.filter((s) => s.waitingOnMe).length;
  const atRisk = stories.filter((s) => s.tone === "danger").length;
  const sharedCount = stories.filter((s) => s.kind === "shared").length;
  const next = stories[0];

  function askAi(e: FormEvent) {
    e.preventDefault();
    const q = askText.trim();
    navigate(q ? `/agent?q=${encodeURIComponent(q)}` : "/agent");
  }

  return (
    <>
      <PageHeader
        title={
          <>
            {greet}
            {user?.full_name ? `، ${user.full_name}` : ""}
          </>
        }
        description={
          <>
            <div className="home-today">{todayLabel}</div>
            {roleHintLine}
          </>
        }
        actions={
          <>
            <Button variant="secondary" to="/communication">
              <Icon name="message" size={14} />
              <Bi en="Messages" fa="پیام‌ها" />
            </Button>
          </>
        }
      />

      {showOnboard && (
        <OnboardingBanner
          onDismiss={() => {
            dismissOnboarding();
            setShowOnboard(false);
          }}
        />
      )}

      <p>
        <Link to="/approvals">
          <Bi en="Open approvals" fa="تأییدهای منتظر" />
        </Link>
      </p>
      <ErrorMessage error={error} />

      {!loading && (
        <Card className={`next-step${next ? "" : " is-clear"}`}>
          <span className="next-step-icon">
            <Icon name={next ? "flag" : "circleCheck"} size={18} />
          </span>
          <div className="next-step-body">
            <span className="next-step-label">
              <Bi en="Your next step" fa="قدم بعدی شما" />
            </span>
            <strong>
              {next ? next.title : bi("Nothing urgent — you’re all caught up.", "کار فوری ندارید — همه‌چیز مرتب است.")}
            </strong>
            <span className="muted">
              {next
                ? next.tone === "danger"
                  ? bi("This is late. Start here.", "این کار دیر شده؛ از همین شروع کنید.")
                  : bi("This is the most important item right now.", "مهم‌ترین مورد همین الان.")
                : bi("You can check your list or ask the assistant.", "می‌توانید فهرست کارهایتان را ببینید یا از دستیار بپرسید.")}
            </span>
          </div>
          <Button to={next ? next.href : "/my-work"}>
            {next ? <Bi en="Start" fa="شروع کن" /> : <Bi en="See my work" fa="دیدن کارهای من" />}
            <Icon name="arrow" size={14} className="icon-arrow" />
          </Button>
        </Card>
      )}

      <div className="kpi-row kpi-row--3">
        <StatCard
          icon="user"
          tone="accent"
          label={<Bi en="Waiting for you" fa="منتظر شما" />}
          value={loading ? "–" : waiting}
          hint={<Bi en="people need your action" fa="مواردی که کسی منتظر شماست" />}
          to="/my-work"
        />
        <StatCard
          icon="alert"
          tone={atRisk > 0 ? "danger" : "neutral"}
          label={<Bi en="Late" fa="دیر شده" />}
          value={loading ? "–" : atRisk}
          hint={<Bi en="past their deadline" fa="از مهلتشان گذشته" />}
        />
        <StatCard
          icon="layers"
          tone="ok"
          label={<Bi en="Active projects" fa="پروژه‌های در جریان" />}
          value={loading ? "–" : sharedCount}
          hint={<Bi en="team work you’re part of" fa="کارهای تیمی که در آن هستید" />}
          to="/work-items"
        />
      </div>

      <div className="home-layout">
        <section className="home-main">
          <SectionHeader
            icon="flag"
            title={<Bi en="Needs your attention" fa="نیاز به رسیدگی شما" />}
            count={loading ? undefined : stories.length}
            action={
              <Button variant="ghost" to="/work-items">
                <Bi en="All projects" fa="همه پروژه‌ها" />
              </Button>
            }
          />

          {loading ? (
            <Card>
              <LoadingState />
            </Card>
          ) : stories.length === 0 ? (
            <Card>
              <EmptyState
                titleEn="You’re all caught up"
                titleFa="همه‌چیز مرتب است"
                bodyEn="When work is assigned or something slips, it shows up here first."
                bodyFa="وقتی کاری سپرده شود یا چیزی عقب بیفتد، اول اینجا دیده می‌شود."
              />
            </Card>
          ) : (
            <ul className="story-grid">
              {stories.map((story) => {
                const kind = KIND_META[story.kind];
                return (
                  <li
                    key={story.id}
                    className={`story-card${story.tone === "danger" ? " is-danger" : story.tone === "warn" ? " is-warn" : ""}`}
                  >
                    <div className="story-body">
                      <div className="story-top">
                        <span className="story-kind">
                          <Icon name={kind.icon} size={12} />
                          {bi(kind.en, kind.fa)}
                        </span>
                        {story.waitingOnMe ? (
                          <Badge tone="warn">
                            <Bi en="Waiting for you" fa="منتظر شما" />
                          </Badge>
                        ) : null}
                      </div>
                      <Link to={story.href} className="story-title">
                        {story.title}
                      </Link>
                      <ul className="story-lines">
                        {story.lines.map((line, i) => (
                          <li
                            key={i}
                            className={line.waiting ? "is-waiting" : line.done ? "is-done" : ""}
                          >
                            <span className="story-mark">
                              {line.done ? "✓" : line.waiting ? "!" : taskMark("OPEN")}
                            </span>
                            {line.text}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="story-foot">
                      {story.deadline ? (
                        <span className="deadline">
                          <Icon name="clock" size={12} />
                          {story.deadline}
                        </span>
                      ) : (
                        <span />
                      )}
                      <Link to={story.href} className="story-open">
                        <Bi en="Handle" fa="رسیدگی" />
                        <Icon name="arrow" size={13} />
                      </Link>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <aside className="home-side">
          <Card className="ask-card">
            <SectionHeader icon="sparkles" title={<Bi en="Ask anything" fa="هر سؤالی بپرسید" />} />
            <form onSubmit={askAi}>
              <Input
                value={askText}
                onChange={(e) => setAskText(e.target.value)}
                placeholder={bi("Is Elantra 2021 in stock?", "النترا ۲۰۲۱ موجود است؟")}
              />
              <Button type="submit">
                <Icon name="send" size={14} />
              </Button>
            </form>
          </Card>

          <Card>
            <SectionHeader title={<Bi en="Jump to" fa="دسترسی سریع" />} />
            <div className="quick-grid">
              {QUICK.map((q) => (
                <Link key={q.to} to={q.to} className="quick-tile">
                  <Icon name={q.icon} />
                  {bi(q.en, q.fa)}
                </Link>
              ))}
            </div>
          </Card>
        </aside>
      </div>
    </>
  );
}

const KIND_META: Record<AttentionStory["kind"], { icon: IconName; en: string; fa: string }> = {
  shared: { icon: "layers", en: "Project", fa: "پروژه" },
  branch: { icon: "branch", en: "Branch request", fa: "درخواست شعبه" },
  campaign: { icon: "megaphone", en: "Campaign", fa: "کمپین" },
  task: { icon: "check", en: "To-do", fa: "کار" },
  alert: { icon: "bell", en: "Alert", fa: "هشدار" },
};

const QUICK: Array<{ to: string; icon: IconName; en: string; fa: string }> = [
  { to: "/vehicles", icon: "car", en: "Vehicles", fa: "خودروها" },
  { to: "/customers", icon: "user", en: "Customers", fa: "مشتریان" },
  { to: "/communication", icon: "message", en: "Messages", fa: "پیام‌ها" },
  { to: "/knowledge", icon: "book", en: "Rules & guides", fa: "قوانین و راهنماها" },
];

