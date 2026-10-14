import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { DateText } from "../components/DateText";
import {
  Badge,
  Button,
  Card,
  Disclosure,
  EmptyState,
  ErrorMessage,
  ForbiddenState,
  LoadingState,
  Muted,
  PageHeader,
  SectionHeader,
  TitleCode,
} from "../components/ui";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { Bi, useBi } from "../i18n";
import { faNum } from "../fa";
import { requestsApi, type WorkProject } from "./api";
import { REQUEST_STATUS_LABEL } from "./labels";
import { DeliveryReviewCard } from "./DeliveryReview";
import { PROJECT_STATUS_LABEL } from "./ProjectsPage";
import { StatusLabel } from "../ux";

function spineStatusText(kind: string, status?: string) {
  if (!status) return "";
  if (kind === "task") return status;
  if (kind === "work_project" || kind === "project") return PROJECT_STATUS_LABEL[status] || status;
  return status;
}

function projectProgressLabel(project: WorkProject, bi: (en: string, fa: string) => string) {
  const total = project.task_total ?? 0;
  const done = project.task_done ?? 0;
  if (total === 0) return bi("Not planned yet", "هنوز برنامه‌ریزی نشده");
  return `${faNum(done)}/${faNum(total)}`;
}

export function RequestPage() {
  const { id = "" } = useParams();
  const bi = useBi();
  const qc = useQueryClient();
  const { user } = useAuth();
  const detail = useQuery({
    queryKey: ["request", id],
    queryFn: () => requestsApi.get(id),
    enabled: Boolean(id),
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["request", id] });
    void qc.invalidateQueries({ queryKey: ["requests"] });
    void qc.invalidateQueries({ queryKey: ["team-home"] });
  };

  if (detail.isLoading) return <LoadingState />;
  if (detail.error) {
    const err = detail.error;
    if (err instanceof ApiError && err.status === 403) {
      return <ForbiddenState />;
    }
    if (err instanceof ApiError && err.status === 404) {
      return (
        <EmptyState
          titleEn="Request not found"
          titleFa="درخواست پیدا نشد"
          bodyEn="It may have been removed or you do not have access."
          bodyFa="حذف شده یا دسترسی ندارید."
          action={<Button to="/requests"><Bi en="All requests" fa="همهٔ درخواست‌ها" /></Button>}
        />
      );
    }
    return <ErrorMessage error={err instanceof Error ? err.message : String(err)} />;
  }

  const payload = detail.data!;
  const row = payload.request;
  const projects = payload.projects ?? [];
  const tasks = payload.tasks ?? [];
  const spine = payload.spine ?? [];
  const pendingDelivery = projects.filter(
    (p) => p.status === "done" && !p.requester_acceptance && row.requested_by === user?.id,
  );
  const doneTasks = tasks.filter((t) => t.status === "COMPLETED").length;
  const nextStep =
    pendingDelivery.length > 0
      ? bi("Review delivered work and accept or return it.", "تحویل را ببینید و تأیید یا برگشت بزنید.")
      : row.status === "new"
        ? bi("Waiting for the team to review this request.", "منتظر رسیدگی تیم هستید.")
        : projects.length === 0
          ? bi("Team will turn this into projects or tasks.", "تیم این را به پروژه یا کار تبدیل می‌کند.")
          : bi("Open a project to see progress.", "برای پیشرفت، یک پروژه را باز کنید.");

  return (
    <>
      <PageHeader
        title={row.title}
        description={<TitleCode title={row.kind} code={row.code} />}
        actions={
          <Button variant="secondary" to="/requests">
            <Bi en="All requests" fa="همهٔ درخواست‌ها" />
          </Button>
        }
      />
      <Card className="stack">
        <SectionHeader title={<Bi en="Summary" fa="خلاصه" />} />
        <div className="meta-row">
          <span className="meta-chip">
            <Bi en="Stage" fa="مرحله" />: {REQUEST_STATUS_LABEL[row.status] || row.status}
          </span>
          {row.team_name ? <span className="meta-chip">{row.team_name}</span> : null}
          {row.requester_name ? (
            <span className="meta-chip">
              <Bi en="Requester" fa="درخواست‌دهنده" />: {row.requester_name}
            </span>
          ) : null}
          {row.due_date ? (
            <span className="meta-chip">
              <Bi en="Needed by" fa="لازم تا" /> <DateText value={row.due_date} />
            </span>
          ) : null}
        </div>
        <p className="banner banner-info">{nextStep}</p>
        {row.description ? <p>{row.description}</p> : <Muted><Bi en="No description." fa="توضیحی ثبت نشده." /></Muted>}
        <Muted as="p">
          {projects.length > 0
            ? bi(
                `${projects.length} project(s) · ${doneTasks} direct task(s) done`,
                `${faNum(projects.length)} پروژه · ${faNum(doneTasks)} کار مستقیم انجام‌شده`,
              )
            : bi(`${tasks.length} direct task(s)`, `${faNum(tasks.length)} کار مستقیم`)}
        </Muted>
      </Card>

      {pendingDelivery.map((project) => (
        <DeliveryReviewCard key={project.id} projectId={project.id} onSuccess={refresh} />
      ))}

      {projects.length > 0 ? (
        <Card className="stack">
          <SectionHeader title={<Bi en="Projects" fa="پروژه‌ها" />} count={projects.length} />
          <ul className="record-subs">
            {projects.map((project) => (
              <li key={project.id}>
                <Link className="record-sub" to={`/projects/${project.id}`}>
                  <strong><TitleCode title={project.title} code={project.code} /></strong>
                  <Badge tone={project.status === "done" ? "ok" : "warn"}>
                    {PROJECT_STATUS_LABEL[project.status] || project.status}
                  </Badge>
                </Link>
                <span className="row-meta">
                  {projectProgressLabel(project, bi)}
                  {project.requester_acceptance === "accepted" ? (
                    <Badge tone="ok"><Bi en="Accepted" fa="تأیید شده" /></Badge>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {tasks.length > 0 ? (
        <Card className="stack">
          <SectionHeader title={<Bi en="Direct tasks" fa="کارهای مستقیم" />} count={tasks.length} />
          <ul className="plain-list">
            {tasks.map((task) => (
              <li key={task.id}>
                <Link to={`/my-work?task=${task.id}`}>{task.title}</Link>
                <StatusLabel status={task.status} />
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {spine.length > 0 ? (
        <Card className="stack">
          <Disclosure label={<Bi en="Activity history" fa="تاریخچهٔ فعالیت" />}>
            <ul className="plain-list">
              {spine.slice(-16).map((item, index) => (
                <li key={`${item.kind}-${index}`}>
                  <Muted>{item.at ? <DateText value={item.at} withTime /> : "—"}</Muted>
                  {" · "}
                  <TitleCode title={item.label} code={item.code ? String(item.code) : null} />
                  {item.status ? ` (${spineStatusText(String(item.kind), String(item.status))})` : ""}
                </li>
              ))}
            </ul>
          </Disclosure>
        </Card>
      ) : null}
    </>
  );
}
