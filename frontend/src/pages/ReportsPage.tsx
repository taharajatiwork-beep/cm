import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api";
import {
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  LoadingState,
  Muted,
  PageHeader,
  SectionHeader,
  Select,
  StatCard,
} from "../components/ui";
import { SheetsSyncCard } from "../components/SheetsSyncCard";
import { useAuth } from "../auth";
import { faNum, toman } from "../fa";
import { Bi, useBi } from "../i18n";
import { queryKeys } from "../lib/queryKeys";
import { requestsApi } from "../requests/api";

type Kpis = Record<string, number | string>;

const KPI_LINKS: Record<string, string> = {
  open_tasks: "/my-work",
  vehicles: "/vehicles",
  cases: "/cases",
  work_items: "/work-items",
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
  const orgNumbers = has("event.read");
  const scopes = [
    { value: "me", label: "خودم" },
    ...(user?.team_id || has("org.admin") ? [{ value: "team", label: "تیم" }] : []),
    ...(has("request.triage") || has("request.manage") ? [{ value: "team_tree", label: "زیرمجموعه" }] : []),
    ...(has("org.admin") ? [{ value: "org", label: "سازمان" }] : []),
  ];
  const q = useQuery<Kpis>({
    queryKey: ["kpis"],
    queryFn: () => api.reports.kpis(),
    enabled: orgNumbers,
  });
  const [scope, setScope] = useState("me");
  const activeScope = scopes.some((item) => item.value === scope) ? scope : "me";
  const work = useQuery({
    queryKey: ["reports", "work", activeScope],
    queryFn: () => requestsApi.workReport(activeScope),
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
  const extras = Object.entries(data).filter(
    ([key]) => key !== "as_of_jalali" && !STAT_KEYS.some((s) => s.key === key),
  );

  return (
    <>
      <PageHeader
        title={<Bi en="Reports" fa="گزارش‌ها" />}
        description={
          orgNumbers ? (
            <Bi
              en="The numbers that matter, plus one-click exports."
              fa="عدد‌های مهم، به‌علاوه خروجی با یک کلیک."
            />
          ) : (
            <Bi en="Your own requests, projects, and tasks." fa="درخواست‌ها، پروژه‌ها و وظیفه‌های خودتان." />
          )
        }
      />
      {has("perf.write") ? <SheetsSyncCard /> : null}
      <Card>
        <SectionHeader
          title={<Bi en="Work" fa="کار" />}
          action={
            <Select aria-label="محدوده" value={activeScope} onChange={(event) => setScope(event.target.value)}>
              {scopes.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
          }
        />
        {work.error ? <ErrorMessage error={work.error instanceof Error ? work.error.message : String(work.error)} /> : null}
        {work.data ? (
          <>
            <div className="kpi-row kpi-row--4">
              <StatCard to="/requests" icon="message" label={<Bi en="Requests" fa="درخواست" />} value={faNum(Number(work.data.requests ?? 0))} />
              <StatCard to="/projects" icon="layers" label={<Bi en="Projects" fa="پروژه" />} value={faNum(Number(work.data.projects ?? 0))} />
              <StatCard
                to={has("task.read") ? "/my-work" : undefined}
                icon="check"
                label={<Bi en="Open tasks" fa="وظیفهٔ باز" />}
                value={faNum(Number(work.data.open_tasks ?? 0))}
              />
              <StatCard icon="car" label={<Bi en="Recorded cost" fa="هزینهٔ ثبت‌شده" />} value={toman(Number(work.data.recorded_cost ?? 0))} />
            </div>
            <SectionLinks data={work.data} canOpenSection={has("request.triage") || has("request.manage") || has("org.admin")} />
          </>
        ) : null}
      </Card>
      {orgNumbers ? <ErrorMessage error={error} /> : null}
      {!orgNumbers ? null : stats.length === 0 ? (
        <Card>
          <EmptyState
            titleEn="No numbers yet"
            titleFa="هنوز عددی نیست"
            bodyEn="Once there is work in the system, KPIs show up here."
            bodyFa="به‌محض اینکه کاری در سیستم باشد، شاخص‌ها اینجا می‌آیند."
          />
        </Card>
      ) : (
        <div className="kpi-row kpi-row--4">
          {stats.map((s) => (
            <StatCard
              key={s.key}
              to={KPI_LINKS[s.key]}
              icon={s.icon}
              tone={s.tone}
              label={bi(s.label[0], s.label[1])}
              value={faNum(Number(data[s.key]))}
            />
          ))}
        </div>
      )}

      {orgNumbers ? <Card>
        <SectionHeader
          title={<Bi en="Exports" fa="خروجی‌ها" />}
          action={
            <span className="chip-row">
              <Muted className="fine">
                <Bi en="As of" fa="تا تاریخ" /> {String(data.as_of_jalali ?? "—")}
              </Muted>
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
            </span>
          }
        />
        <Muted>
          <Bi
            en="CSV opens anywhere, XLSX in Excel, PDF for sharing."
            fa="CSV همه‌جا باز می‌شود، XLSX در اکسل، PDF برای ارسال."
          />
        </Muted>
      </Card> : null}

      {orgNumbers && extras.length > 0 ? (
        <Card>
          <SectionHeader title={<Bi en="More indicators" fa="شاخص‌های بیشتر" />} />
          <ul className="rows">
            {extras.map(([key, value]) => (
              <li key={key} className="row-item">
                <span className="row-title">{key}</span>
                <span className="row-meta">{String(value)}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}

function counts(value: unknown): Array<[string, number]> {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value as Record<string, unknown>)
    .map(([name, count]) => [name, Number(count) || 0] as [string, number])
    .filter(([, count]) => count > 0);
}

function SectionLinks({ data, canOpenSection }: { data: Record<string, unknown>; canOpenSection: boolean }) {
  const kinds = counts(data.projects_by_kind);
  const teams = useQuery({
    queryKey: queryKeys.teams,
    queryFn: () => api.teams.list(),
    enabled: canOpenSection && kinds.length > 0,
  });
  if (kinds.length === 0) return null;
  const byName = new Map((teams.data ?? []).map((team) => [String(team.name), String(team.id)]));
  return (
    <ul className="rows">
      {kinds.map(([name, count]) => {
        const teamId = byName.get(name);
        const href = canOpenSection && teamId ? `/teams/${teamId}` : "/projects";
        return (
          <li key={name} className="row-item">
            <Link to={href} className="row-title">{name}</Link>
            <span className="row-meta">{faNum(count)}</span>
          </li>
        );
      })}
    </ul>
  );
}
