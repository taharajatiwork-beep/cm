import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api";
import {
  Badge,
  Button,
  Card,
  Disclosure,
  ErrorMessage,
  LoadingState,
  Muted,
  Field,
  Input,
  PageHeader,
  SectionHeader,
  Segmented,
  StatCard,
} from "../components/ui";
import { DateText } from "../components/DateText";
import { SheetsSyncCard } from "../components/SheetsSyncCard";
import { useAuth } from "../auth";
import { faNum, tomanText } from "../fa";
import { Bi, useBi } from "../i18n";
import { canSeeNavPath } from "../lib/access";
import { requestsApi } from "../requests/api";
import { ConceptHint, StatusLabel } from "../ux";
import { WorkChainLegend, WorkListKindBadge } from "../lib/workContext";

type Kpis = Record<string, number | string>;

const KPI_LINKS: Record<string, string> = {
  open_tasks: "/my-work",
  vehicles: "/vehicles",
  cases: "/",
  work_items: "/projects",
};

const STAT_KEYS: Array<{
  key: string;
  icon: "check" | "car" | "message" | "layers";
  label: [string, string];
  tone?: "ok" | "warn" | "accent";
}> = [
  { key: "open_tasks", icon: "check", label: ["Open to-dos", "کارهای باز"], tone: "warn" },
  { key: "vehicles", icon: "car", label: ["Vehicles", "خودروها"] },
  { key: "cases", icon: "message", label: ["Follow-ups", "پیگیری‌ها"] },
  { key: "work_items", icon: "layers", label: ["Projects", "پروژه‌ها"], tone: "accent" },
];

export function ReportsPage() {
  const bi = useBi();
  const { has, user } = useAuth();
  const isOrgAdmin = has("org.admin");
  const orgNumbers = isOrgAdmin && has("event.read");
  const scopes = isOrgAdmin
    ? [
        { value: "me", label: "خودم" },
        ...(user?.team_id ? [{ value: "team", label: "تیم" }] : []),
        ...(has("request.triage") || has("request.manage") ? [{ value: "team_tree", label: "زیرمجموعه" }] : []),
        { value: "org", label: "سازمان" },
      ]
    : has("report.read") && user?.team_id
      ? [{ value: "me", label: "خودم" }, { value: "team", label: "تیم" }]
      : [{ value: "me", label: "خودم" }];
  const q = useQuery<Kpis>({
    queryKey: ["kpis"],
    queryFn: () => api.reports.kpis(),
    enabled: orgNumbers,
  });
  const [params, setParams] = useSearchParams();
  const projectId = params.get("project") || "";
  const requestId = params.get("request") || "";
  const [scope, setScope] = useState(() =>
    scopes.some((item) => item.value === "org")
      ? "org"
      : scopes.some((item) => item.value === "team_tree")
        ? "team_tree"
        : scopes.some((item) => item.value === "team")
          ? "team"
          : "me",
  );
  const activeScope = scopes.some((item) => item.value === scope) ? scope : "me";
  const work = useQuery({
    queryKey: ["reports", "work", activeScope, projectId, requestId],
    queryFn: () => requestsApi.workReport(activeScope, projectId, requestId),
  });

  const error = q.error
    ? q.error instanceof ApiError
      ? q.error.message
      : String(q.error)
    : "";

  if (work.isLoading && !work.data) return <LoadingState />;
  if (orgNumbers && q.error && !(q.error instanceof ApiError && q.error.status === 403)) {
    return <ErrorMessage error={error} />;
  }

  const data = q.data ?? {};
  const stats = STAT_KEYS.filter((s) => s.key in data);

  const extraStats = stats.filter((item) => item.key === "vehicles" || item.key === "cases");

  return (
    <>
      <PageHeader
        title={<Bi en="Reports" fa="گزارش‌ها" />}
        description={<Bi en="Campaign numbers from the ledger, then the requests in this range." fa="عدد کمپین‌ها از دفتر هزینه، بعد درخواست‌های این محدوده." />}
      />
      {scopes.length > 1 ? (
        <Segmented
          ariaLabel={bi("Report range", "محدودهٔ گزارش")}
          value={activeScope}
          onChange={setScope}
          items={scopes.map((item) => ({ key: item.value, label: item.label }))}
        />
      ) : null}
      {work.error ? <ErrorMessage error={work.error instanceof Error ? work.error.message : String(work.error)} /> : null}
      {work.data ? (
        <div className="kpi-row kpi-row--4">
          <StatCard to="/requests" icon="message" label={<Bi en="Requests (asked)" fa="درخواست (خواسته)" />} value={faNum(Number(work.data.requests ?? 0))} />
          <StatCard to="/projects" icon="layers" tone="accent" label={<Bi en="Projects (work packages)" fa="پروژه (بستهٔ کار)" />} value={faNum(Number(work.data.projects ?? 0))} />
          <StatCard
            to={has("task.read") ? "/my-work" : undefined}
            icon="check"
            tone="warn"
            label={<Bi en="Open tasks (steps)" fa="کار باز (قدم‌ها)" />}
            value={faNum(Number(work.data.open_tasks ?? 0))}
          />
          <StatCard icon="car" label={<Bi en="Recorded cost" fa="هزینهٔ ثبت‌شده" />} value={tomanText(Number(work.data.recorded_cost ?? 0))} />
        </div>
      ) : null}
      <CampaignBoard scope={activeScope} projectId={projectId} requestId={requestId} />
      {work.data ? (
        <>
          <WorkChainLegend variant="reports" />
          <ConceptHint kind="followup" />
        </>
      ) : null}
      {work.data ? (
        <WorkDetail
          data={work.data}
          requestId={requestId}
          projectId={projectId}
          focused={Boolean(projectId || requestId)}
          onBack={() => {
            const next = new URLSearchParams(params);
            next.delete("project");
            next.delete("request");
            setParams(next);
          }}
        />
      ) : null}
      {orgNumbers ? (
        <Card>
          <Disclosure label={<Bi en="Organization numbers and export" fa="شاخص سازمان و خروجی" />}>
            <div className="stack">
              {extraStats.length > 0 ? (
                <div className="kpi-row">
                  {extraStats.map((item) => (
                    <StatCard
                      key={item.key}
                      to={KPI_LINKS[item.key]}
                      icon={item.icon}
                      tone={item.tone}
                      label={bi(item.label[0], item.label[1])}
                      value={faNum(Number(data[item.key]))}
                    />
                  ))}
                </div>
              ) : null}
              <Muted as="p">
                <Bi en="As of" fa="تا تاریخ" /> {String(data.as_of_jalali ?? "—")}
              </Muted>
              <div className="record-actions">
                {(["csv", "xlsx", "pdf"] as const).map((format) => (
                  <Button
                    key={format}
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => {
                      void api.reports.download(format).catch((err: unknown) => {
                        console.error("export failed", err);
                      });
                    }}
                  >
                    {format.toUpperCase()}
                  </Button>
                ))}
              </div>
            </div>
          </Disclosure>
        </Card>
      ) : null}
      {has("perf.write") ? (
        <Card>
          <Disclosure label={<Bi en="Google Sheets" fa="گوگل‌شیت" />}>
            <SheetsSyncCard embedded />
          </Disclosure>
        </Card>
      ) : null}
    </>
  );
}

type TaskLine = {
  id: string;
  title: string;
  status: string;
  deadline: string | null;
  person: string;
  overdue: boolean;
};

type ProjectLine = {
  id: string;
  code: string;
  title: string;
  status: string;
  done: number;
  total: number;
  overdue: number;
  tasks?: TaskLine[];
};

type RequestLine = {
  id: string;
  code: string;
  title: string;
  status: string;
  done: number;
  total: number;
  projects: ProjectLine[];
};

const REQUEST_STATUS: Record<string, string> = {
  new: "جدید",
  in_review: "در بررسی",
  converted: "تبدیل به پروژه",
  rejected: "رد شده",
  done: "انجام شد",
  in_progress: "در جریان",
};

const PROJECT_STATUS: Record<string, string> = {
  new: "تازه",
  in_progress: "در جریان",
  done: "تمام",
};

type CampaignLine = {
  id: string;
  code: string;
  title: string;
  brand: string;
  status: string;
  cost_toman: number;
  leads: number;
  views: number;
  cpl: number | null;
};

const CAMPAIGN_STATUS: Record<string, string> = {
  active: "فعال",
  done: "تمام",
  draft: "پیش‌نویس",
};

function CampaignBoard({
  scope,
  projectId,
  requestId,
}: {
  scope: string;
  projectId: string;
  requestId: string;
}) {
  const { has } = useAuth();
  const canSee = has("campaign.read") || has("perf.read") || has("report.read") || has("org.admin");
  const [query, setQuery] = useState("");
  const report = useQuery({
    queryKey: ["reports", "campaigns", scope, projectId, requestId],
    queryFn: () => requestsApi.campaignReport(scope, projectId),
    enabled: canSee,
  });
  if (!canSee) return null;
  if (report.isLoading) return <LoadingState />;
  if (report.error) {
    return <ErrorMessage error={report.error instanceof Error ? report.error.message : String(report.error)} />;
  }
  const rows = report.data?.campaigns ?? [];
  const needle = query.trim();
  const shown = needle
    ? rows.filter((row) => `${row.code} ${row.title} ${row.brand}`.toLowerCase().includes(needle.toLowerCase()))
    : rows;
  return (
    <>
      <SectionHeader title={<Bi en="Campaigns" fa="کمپین‌ها" />} />
      <div className="kpi-row">
        <StatCard icon="layers" tone="accent" label={<Bi en="Campaigns" fa="کمپین" />} value={faNum(report.data?.count ?? 0)} />
        <StatCard icon="car" label={<Bi en="Recorded cost" fa="هزینهٔ ثبت‌شده" />} value={tomanText(report.data?.cost_toman ?? 0)} />
        <StatCard icon="message" label={<Bi en="Leads" fa="ورودی" />} value={faNum(report.data?.leads ?? 0)} />
      </div>
      <Field label={<Bi en="Find a campaign" fa="جستجوی کمپین" />}>
        <Input value={query} onChange={(event) => setQuery(event.target.value)} />
      </Field>
      {shown.length === 0 ? (
        <Muted as="p">
          {needle ? (
            <Bi en="No campaign matches." fa="کمپینی با این عبارت نیست." />
          ) : (
            <Bi en="No campaigns in this range." fa="کمپینی در این محدوده نیست." />
          )}
        </Muted>
      ) : (
        <div className="report-board">
          {shown.map((row: CampaignLine) => {
            const empty = !row.cost_toman && !row.leads && !row.views;
            return (
              <Card key={row.id} as="article" className="record-card report-tile" stack>
                <div className="record-head">
                  <div>
                    <div className="record-code" dir="ltr">{row.code}</div>
                    <h3 className="record-title"><Link to={`/perf/campaigns/${row.id}`}>{row.title || row.code}</Link></h3>
                  </div>
                  <Badge tone={row.status === "done" ? "ok" : row.status === "active" ? "warn" : ""}>
                    {CAMPAIGN_STATUS[row.status] || row.status}
                  </Badge>
                </div>
                <div className="meta-row">
                  {row.brand ? <span className="meta-chip">{row.brand}</span> : null}
                  <span className="meta-chip">هزینه {tomanText(row.cost_toman || 0)}</span>
                  <span className="meta-chip">ورودی {faNum(row.leads || 0)}</span>
                  <span className="meta-chip">بازدید {faNum(row.views || 0)}</span>
                  <span className="meta-chip">هر ورودی {row.cpl == null ? "—" : tomanText(row.cpl)}</span>
                </div>
                {empty ? <Muted as="p"><Bi en="No ledger row for this code." fa="برای این کد ردیفی در دفتر ثبت نشده." /></Muted> : null}
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}

function asRequests(data: Record<string, unknown>): RequestLine[] {
  const rows = data.request_rows;
  return Array.isArray(rows) ? (rows as RequestLine[]) : [];
}

function WorkDetail({
  data,
  focused,
  requestId,
  projectId,
  onBack,
}: {
  data: Record<string, unknown>;
  focused: boolean;
  requestId: string;
  projectId: string;
  onBack: () => void;
}) {
  const { user, has } = useAuth();
  const canOpenRequest = canSeeNavPath(
    "/requests",
    { roleCode: user?.roleCode, permissions: user?.permissions ?? [] },
    has,
  );
  let rows = asRequests(data);
  if (requestId) {
    rows = rows.filter((row) => row.id === requestId);
  }
  if (projectId) {
    rows = rows
      .map((row) => ({
        ...row,
        projects: row.projects.filter((project) => project.id === projectId),
      }))
      .filter((row) => row.projects.length > 0);
  }
  if (rows.length === 0) {
    return <Muted as="p"><Bi en="Nothing in this range." fa="در این محدوده درخواستی نیست." /></Muted>;
  }
  return (
    <div className="report-board">
      {focused ? (
        <div className="record-actions">
          <Button type="button" variant="ghost" className="btn-sm" onClick={onBack}>
            <Bi en="All reports" fa="همهٔ گزارش‌ها" />
          </Button>
        </div>
      ) : null}
      {rows.map((request) => (
        <Card key={request.id || request.title} as="article" className="record-card report-tile" stack>
          <div className="record-head">
            <div>
              {request.code ? <div className="record-code" dir="ltr">{request.code}</div> : null}
              <h3 className="record-title">{request.title}</h3>
              <span className="row-meta work-parent-context">
                <WorkListKindBadge kind="request" />
              </span>
            </div>
            <Badge tone={request.status === "done" || request.status === "converted" ? "ok" : request.status === "rejected" ? "danger" : "warn"}>
              {REQUEST_STATUS[request.status] || request.status}
            </Badge>
          </div>
          <Progress done={request.done} total={request.total} />
          {request.projects.length > 0 ? (
            <>
            <Muted as="p">
              <Bi en="Projects under this request" fa="پروژه‌های زیر این درخواست" />
            </Muted>
            <ul className="record-subs">
              {request.projects.map((project) => (
                <li key={project.id}>
                  <Link className="record-sub" to={`/projects/${project.id}`}>
                    <span className="record-code" dir="ltr">{project.code}</span>
                    <strong>{project.title}</strong>
                    <WorkListKindBadge kind="project" />
                    <Badge tone={project.overdue ? "danger" : project.status === "done" ? "ok" : "warn"}>
                      {project.overdue
                        ? `${faNum(project.overdue)} عقب`
                        : `${PROJECT_STATUS[project.status] || project.status} · ${faNum(project.done)}/${faNum(project.total)}`}
                    </Badge>
                  </Link>
                  {project.tasks && project.tasks.length > 0 ? (
                    <ul className="record-subs">
                      {project.tasks.map((task) => (
                        <li key={task.id} className="record-line">
                          <WorkListKindBadge kind="task" />
                          <strong>{task.title}</strong>
                          <span className="meta-row">
                            {task.person ? <span className="meta-chip">{task.person}</span> : null}
                            {task.deadline ? <span className="meta-chip"><DateText value={task.deadline} /></span> : null}
                            {task.overdue ? <span className="meta-chip">عقب‌افتاده</span> : null}
                            <StatusLabel status={task.status} />
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
            </>
          ) : (
            <Muted as="p">
              <Bi en="No projects yet — the team has not split this request into work packages." fa="هنوز پروژه‌ای نیست — تیم این درخواست را به بستهٔ کار تبدیل نکرده." />
            </Muted>
          )}
          {!focused && request.id ? (
            <div className="record-actions">
              <Button
                variant="ghost"
                className="btn-sm"
                to={canOpenRequest ? `/requests/${request.id}` : `/reports?request=${request.id}`}
              >
                <Bi en="How this request moved" fa="روند این درخواست" />
              </Button>
            </div>
          ) : null}
        </Card>
      ))}
    </div>
  );
}

function Progress({ done, total }: { done: number; total: number }) {
  const bi = useBi();
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="report-progress">
      <span>
        {total
          ? `${faNum(done)} از ${faNum(total)} ${bi("tasks done on all projects", "کار انجام‌شده روی همهٔ پروژه‌ها")}`
          : bi("No tasks on projects yet", "هنوز کار روی پروژه‌ها ثبت نشده")}
      </span>
      <div className="progress-bar" aria-hidden>
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
