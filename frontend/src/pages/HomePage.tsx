import { useMemo, useState } from "react";
import { InquiryDialog } from "../components/InquiryDialog";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { requestsApi } from "../requests/api";
import { useAuth } from "../auth";
import {
  Badge,
  Button,
  Card,
  ErrorMessage,
  Icon,
  type IconName,
  LoadingState,
  PageHeader,
  SectionHeader,
  StatCard,
} from "../components/ui";
import { Bi, useBi, useLocale } from "../i18n";
import { formatJalaliLong } from "../jalali";
import { faNum } from "../fa";
import {
  type AttentionStory,
  formatDeadline,
  isOverdue,
  taskMark,
} from "../lib/collaboration";
import { caughtUpTarget, filterOnboardingCue, onboardingCue, visibleHomeKpis, type HomeKpi } from "../lib/focus";
import { useVehicleLabel } from "../lib/vehicleLabels";
import { OnboardingBanner, dismissOnboarding, recallOnboarding, shouldShowOnboarding } from "../ux";

export function HomePage() {
  const { user, roleHint, has } = useAuth();
  const bi = useBi();
  const vehicleLabel = useVehicleLabel();
  const { locale } = useLocale();
  const [showOnboard, setShowOnboard] = useState(() => shouldShowOnboarding(user?.id));
  const [inquiryOpen, setInquiryOpen] = useState(false);
  const sellerVehicles = useQuery({
    queryKey: ["seller-vehicles"],
    queryFn: () => api.vehicles.list(),
    enabled: has("inquiry.create"),
  });
  const inquiryVehicles = useMemo(
    () =>
      (sellerVehicles.data ?? []).map((row) => ({
        id: String(row.id),
        label: `${vehicleLabel(String(row.brand ?? ""))} ${vehicleLabel(String(row.model ?? ""))} ${String(row.year ?? "")}`.trim(),
      })),
    [sellerVehicles.data, vehicleLabel],
  );

  const inbox = useQuery({
    queryKey: ["home-inbox", user?.id, roleHint, locale],
    queryFn: async () => {
      const out: AttentionStory[] = [];
      let roleHintLine = "";

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

        const isRequester =
          has("request.create") && !has("request.triage") && !has("request.manage") && !has("task.read");
        const canSeeProjects =
          has("request.create") || has("request.triage") || has("request.manage") || has("task.read");
        let loadPartial = false;
        const fail = () => {
          loadPartial = true;
          return [] as never[];
        };
        const [myTasks, projects, camps, conversations] = await Promise.all([
          user?.id && has("task.read")
            ? api.tasks.list({ assignee_id: user.id }).catch(fail)
            : Promise.resolve([]),
          canSeeProjects ? requestsApi.projects().catch(fail) : Promise.resolve([]),
          !isRequester && has("campaign.read") ? api.campaigns.list().catch(fail) : Promise.resolve([]),
          has("conversation.read") ? api.conversations.list().catch(fail) : Promise.resolve([]),
        ]);
        const openMine = myTasks.filter((t) => t.status !== "COMPLETED");
        const projectById = new Map(projects.map((p) => [String(p.id), p]));
        for (const project of projects.filter((p) => p.status !== "done").slice(0, 8)) {
          const subline = project.request_title
            ? bi(`Under request ${project.request_title}`, `زیر درخواست ${project.request_title}`)
            : project.request_code
              ? bi(`Under request ${project.request_code}`, `زیر درخواست ${project.request_code}`)
              : project.team_name || project.kind;
          out.push({
            id: `prj-${project.id}`,
            title: project.title,
            href: `/projects/${project.id}`,
            lines: [
              {
                text: subline,
                waiting: project.status === "new",
              },
            ],
            tone: project.status === "new" ? "warn" : undefined,
            kind: "shared",
            waitingOnMe: false,
          });
        }

        const activeCamps = camps.filter((c) => c.status === "ACTIVE").slice(0, 3);
        const campProgress = await Promise.all(
          activeCamps.map(async (camp) => {
            if (!camp.work_item_id) return { camp, overdueCount: 0 };
            try {
              const prog = await api.workItems.progress(String(camp.work_item_id));
              return { camp, overdueCount: prog.overdue_tasks || 0 };
            } catch {
              return { camp, overdueCount: 0 };
            }
          }),
        );
        for (const { camp, overdueCount } of campProgress) {
          if (overdueCount > 0 || camp.status === "ACTIVE") {
            out.push({
              id: `camp-${camp.id}`,
              title: String(camp.title),
              href: `/perf/campaigns/${camp.id}`,
              lines: [
                {
                  text:
                    overdueCount > 0
                      ? bi(`${overdueCount} late tasks`, `${faNum(overdueCount)} کار عقب‌افتاده`)
                      : bi("Campaign in progress", "کمپین در جریان"),
                  waiting: overdueCount > 0,
                },
              ],
              tone: overdueCount > 0 ? "danger" : undefined,
              kind: "campaign",
            });
          }
        }

        for (const t of openMine.filter((x) => !x.work_item_id).slice(0, 3)) {
          const proj = t.project_id ? projectById.get(String(t.project_id)) : undefined;
          const lines = [{ text: bi("Task assigned to you", "کار — به شما سپرده شده") }];
          if (proj?.request_title || proj?.request_code) {
            const reqLabel = proj.request_title || proj.request_code;
            lines.push({
              text: bi(`Under request ${reqLabel}`, `زیر درخواست ${reqLabel}`),
            });
          }
          if (proj?.title) {
            lines.push({
              text: bi(`In project ${proj.title}`, `در پروژه ${proj.title}`),
            });
          }
          out.push({
            id: `task-${t.id}`,
            title: String(t.title),
            href: "/my-work",
            lines,
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

        const waitingReply = conversations.filter((c) => Boolean(c.needs_reply)).length;

        return { stories: ranked.slice(0, 8), roleHintLine, waitingReply, loadPartial };
    },
  });
  const stories = inbox.data?.stories ?? [];
  const roleHintLine = inbox.data?.roleHintLine ?? "";
  const waitingReply = inbox.data?.waitingReply ?? 0;
  const loadPartial = inbox.data?.loadPartial ?? false;
  const pricing = useQuery({
    queryKey: ["pricing-board", "home"],
    queryFn: () => api.pricing.board(),
    enabled: has("price.approve") || has("price.write") || has("campaign.read"),
  });
  const loading = inbox.isLoading;
  const error = inbox.isError ? String((inbox.error as Error).message) : "";

  const hour = new Date().getHours();
  const greet =
    hour < 12
      ? bi("Good morning", "صبح بخیر")
      : hour < 18
        ? bi("Good afternoon", "ظهر بخیر")
        : bi("Good evening", "عصر بخیر");

  const todayLabel = formatJalaliLong(new Date());

  const waiting = stories.filter((s) => s.waitingOnMe).length;
  const atRisk = stories.filter((s) => s.tone === "danger").length;
  const sharedCount = stories.filter((s) => s.kind === "shared").length;
  const next = stories[0];
  const accessUser = {
    roleCode: user?.roleCode,
    permissions: user?.permissions ?? [],
    teamId: user?.team_id,
    teamHomeTeamId: user?.team_home_team_id,
  };
  const cue = filterOnboardingCue(onboardingCue(roleHint, user?.roleCode), accessUser, has);
  const kpis = visibleHomeKpis({
    roleHint,
    roleCode: user?.roleCode,
    permissions: user?.permissions ?? [],
    teamId: user?.team_id,
  });
  const clearTarget = caughtUpTarget({
    roleHint,
    roleCode: user?.roleCode,
    permissions: user?.permissions ?? [],
    teamId: user?.team_id,
  });
  const isRequester =
    has("request.create") && !has("request.triage") && !has("request.manage") && !has("task.read");

  return (
    <>
      <PageHeader
        title={
          <span className="bidi-mixed">
            {greet}
            {user?.full_name ? `، ${user.full_name}` : ""}
          </span>
        }
        description={
          <>
            <div className="home-today">{todayLabel}</div>
            {roleHintLine}
          </>
        }
        actions={
          <>
            {!showOnboard ? (
              <Button
                variant="ghost"
                onClick={() => {
                  recallOnboarding(user?.id);
                  setShowOnboard(true);
                }}
              >
                <Bi en="Guide" fa="راهنما" />
              </Button>
            ) : null}
            {kpis.includes("replies") ? (
              <Button variant="secondary" to="/communication">
                <Icon name="message" size={14} />
                <Bi en="Messages" fa="پیام‌ها" />
              </Button>
            ) : null}
            {isRequester ? (
              <Button variant="secondary" to="/requests">
                <Bi en="My request status" fa="وضعیت درخواست‌های من" />
              </Button>
            ) : null}
            {has("inquiry.create") ? (
              <Button type="button" onClick={() => setInquiryOpen(true)}>
                <Bi en="New inquiry" fa="استعلام جدید" />
              </Button>
            ) : null}
          </>
        }
      />

      <InquiryDialog open={inquiryOpen} onClose={() => setInquiryOpen(false)} vehicles={inquiryVehicles} />

      {showOnboard && cue.steps.length > 0 ? (
        <OnboardingBanner
          {...cue}
          onDismiss={() => {
            dismissOnboarding(user?.id);
            setShowOnboard(false);
          }}
        />
      ) : null}

      <ErrorMessage error={error} />
      {!loading && loadPartial ? (
        <p className="banner banner-warn">
          <Bi en="Some data could not be loaded." fa="بخشی از داده بارگذاری نشد." />
          <Button type="button" variant="ghost" className="btn-sm" onClick={() => void inbox.refetch()}>
            <Bi en="Try again" fa="تلاش دوباره" />
          </Button>
        </p>
      ) : null}

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
              {next
                ? next.title
                : loadPartial
                  ? bi("We could not confirm your full queue.", "نمی‌توانیم همهٔ صف را تأیید کنیم.")
                  : bi("Nothing urgent — you’re all caught up.", "کار فوری ندارید — همه‌چیز مرتب است.")}
            </strong>
            <span className="muted">
              {next
                ? next.tone === "danger"
                  ? bi("This is late. Start here.", "این کار دیر شده؛ از همین شروع کنید.")
                  : bi("This is the most important item right now.", "مهم‌ترین مورد همین الان.")
                : loadPartial
                  ? bi("Retry loading or open My Work directly.", "دوباره بارگذاری کنید یا مستقیم به کارهای من بروید.")
                  : bi("The next useful page is ready. Nothing else is waiting.", "صفحهٔ بعدی آماده است. چیز دیگری منتظر شما نیست.")}
            </span>
          </div>
          <Button to={next ? next.href : clearTarget}>
            {next ? <Bi en="Start" fa="شروع کن" /> : <Bi en="Continue" fa="ادامه" />}
            <Icon name="arrow" size={14} className="icon-arrow" />
          </Button>
        </Card>
      )}

      <div className="kpi-row">
        {kpis.map((key) => (
          <HomeKpiCard
            key={key}
            kpi={key}
            loading={loading}
            pricingLoading={pricing.isLoading}
            waiting={waiting}
            atRisk={atRisk}
            sharedCount={sharedCount}
            waitingReply={waitingReply}
            pricesWaiting={pricing.data?.waiting ?? 0}
            postsToday={pricing.data?.today_total ?? 0}
            allPriced={Boolean(pricing.data?.all_priced)}
          />
        ))}
      </div>

      {stories.length === 0 && !loading ? null : (
        <section className="home-main">
          <SectionHeader
            icon="flag"
            title={<Bi en="Needs your attention" fa="نیاز به رسیدگی شما" />}
            count={loading ? undefined : stories.length}
            action={
              <Button variant="ghost" to="/projects">
                <Bi en="All projects" fa="همه پروژه‌ها" />
              </Button>
            }
          />

          {loading ? (
            <Card>
              <LoadingState />
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
      )}
    </>
  );
}

function HomeKpiCard({
  kpi,
  loading,
  pricingLoading,
  waiting,
  atRisk,
  sharedCount,
  waitingReply,
  pricesWaiting,
  postsToday,
  allPriced,
}: {
  kpi: HomeKpi;
  loading: boolean;
  pricingLoading: boolean;
  waiting: number;
  atRisk: number;
  sharedCount: number;
  waitingReply: number;
  pricesWaiting: number;
  postsToday: number;
  allPriced: boolean;
}) {
  if (kpi === "waiting") {
    return (
      <StatCard
        icon="user"
        tone="accent"
        label={<Bi en="Waiting for you" fa="منتظر شما" />}
        value={loading ? "–" : waiting}
        hint={<Bi en="people need your action" fa="مواردی که کسی منتظر شماست" />}
        to="/my-work"
      />
    );
  }
  if (kpi === "late") {
    return (
      <StatCard
        icon="alert"
        tone={atRisk > 0 ? "danger" : "neutral"}
        label={<Bi en="Late" fa="دیر شده" />}
        value={loading ? "–" : atRisk}
        hint={<Bi en="past their deadline" fa="از مهلتشان گذشته" />}
      />
    );
  }
  if (kpi === "projects") {
    return (
      <StatCard
        icon="layers"
        tone="ok"
        label={<Bi en="Active projects" fa="پروژه‌های در جریان" />}
        value={loading ? "–" : sharedCount}
        hint={<Bi en="projects you can see" fa="پروژه‌هایی که می‌بینید" />}
        to="/projects"
      />
    );
  }
  if (kpi === "replies") {
    return (
      <StatCard
        icon="message"
        tone={waitingReply > 0 ? "warn" : "neutral"}
        label={<Bi en="Waiting for your reply" fa="منتظر پاسخ شما" />}
        value={loading ? "–" : waitingReply}
        hint={<Bi en="conversations you owe an answer" fa="گفتگوهایی که جوابتان را می‌خواهند" />}
        to="/communication"
      />
    );
  }
  if (kpi === "prices") {
    return (
      <StatCard
        icon="megaphone"
        tone={pricesWaiting > 0 ? "warn" : "ok"}
        label={<Bi en="Prices waiting for you" fa="قیمت منتظر شماست" />}
        value={pricingLoading ? "–" : pricesWaiting}
        hint={<Bi en="posts that still need a confirmed price" fa="پست‌هایی که قیمت تأییدشده ندارند" />}
        to="/pricing"
      />
    );
  }
  return (
    <StatCard
      icon="car"
      tone="accent"
      label={<Bi en="Today’s posts" fa="پست‌های امروز" />}
      value={pricingLoading ? "–" : postsToday}
      hint={
        allPriced ? (
          <Bi en="every post has a price" fa="همه قیمت دارند" />
        ) : (
          <Bi en="some posts still need a price" fa="بعضی پست‌ها هنوز قیمت ندارند" />
        )
      }
      to="/pricing"
    />
  );
}

const KIND_META: Record<AttentionStory["kind"], { icon: IconName; en: string; fa: string }> = {
  shared: { icon: "layers", en: "Project", fa: "پروژه" },
  branch: { icon: "branch", en: "Branch request", fa: "درخواست شعبه" },
  campaign: { icon: "megaphone", en: "Campaign", fa: "کمپین" },
  task: { icon: "check", en: "Task", fa: "کار" },
  alert: { icon: "bell", en: "Alert", fa: "هشدار" },
};

