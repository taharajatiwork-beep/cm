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
  StatCard,
} from "../components/ui";
import { Bi, useBi } from "../i18n";

type Kpis = Record<string, number | string>;

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
  const q = useQuery<Kpis>({
    queryKey: ["kpis"],
    queryFn: () => api.reports.kpis(),
  });

  const error = q.error
    ? q.error instanceof ApiError
      ? q.error.message
      : String(q.error)
    : "";

  if (q.isLoading) return <LoadingState />;
  if (q.error) return <ErrorMessage error={error} />;

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
          <Bi
            en="The numbers that matter, plus one-click exports."
            fa="عدد‌های مهم، به‌علاوه خروجی با یک کلیک."
          />
        }
      />
      <ErrorMessage error={error} />
      {stats.length === 0 ? (
        <Card>
          <EmptyState
            titleEn="No numbers yet"
            titleFa="هنوز عددی نیست"
            bodyEn="Once there is work in the system, KPIs show up here."
            bodyFa="به‌محض اینکه کاری در سیستم باشد، شاخص‌ها اینجا می‌آیند."
          />
        </Card>
      ) : (
        <div className="kpi-row">
          {stats.map((s) => (
            <StatCard
              key={s.key}
              icon={s.icon}
              tone={s.tone}
              label={bi(s.label[0], s.label[1])}
              value={String(data[s.key])}
            />
          ))}
        </div>
      )}

      <Card>
        <SectionHeader
          title={<Bi en="Exports" fa="خروجی‌ها" />}
          action={
            <Muted>
              <Bi en="As of" fa="تا تاریخ" /> {String(data.as_of_jalali ?? "—")}
            </Muted>
          }
        />
        <div className="toolbar">
          {(["csv", "xlsx", "pdf"] as const).map((format) => (
            <Button
              key={format}
              variant="secondary"
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
        <Muted>
          <Bi
            en="CSV opens anywhere, XLSX in Excel, PDF for sharing."
            fa="CSV همه‌جا باز می‌شود، XLSX در اکسل، PDF برای ارسال."
          />
        </Muted>
      </Card>

      {extras.length > 0 ? (
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
