import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth";
import { Badge } from "../components/ui";
import { Bi, useBi } from "../i18n";
import { canSeeProjects } from "./access";
import { requestsApi, type WorkProject, type WorkRequest } from "../requests/api";

export type WorkListKind = "task" | "project" | "request" | "price" | "ai" | "legacy_work";

const KIND_LABEL: Record<WorkListKind, [string, string]> = {
  task: ["Task", "کار"],
  project: ["Project", "پروژه"],
  request: ["Request", "درخواست"],
  price: ["Price / post", "قیمت / پست"],
  ai: ["Assistant", "دستیار"],
  legacy_work: ["Shared project", "پروژه مشترک"],
};

export function WorkListKindBadge({ kind }: { kind: WorkListKind }) {
  const bi = useBi();
  const [en, fa] = KIND_LABEL[kind];
  return (
    <Badge className="work-kind-badge">
      {bi(en, fa)}
    </Badge>
  );
}

export type WorkParentFields = {
  kind?: WorkListKind | "project" | "task" | null;
  origin?: string | null;
  projectId?: string | null;
  requestId?: string | null;
  projectCode?: string | null;
  projectTitle?: string | null;
  requestCode?: string | null;
  requestTitle?: string | null;
};

export function resolveTaskParents(
  task: { project_id?: string | null; request_id?: string | null },
  projects: WorkProject[],
  requests: WorkRequest[],
): Omit<WorkParentFields, "kind"> {
  const project = task.project_id ? projects.find((p) => p.id === String(task.project_id)) : undefined;
  const requestFromProject =
    project?.request_id ? requests.find((r) => r.id === project.request_id) : undefined;
  const requestDirect = task.request_id ? requests.find((r) => r.id === String(task.request_id)) : undefined;
  const request = requestFromProject ?? requestDirect;
  return {
    origin: project ? "project" : requestDirect ? "request" : "work",
    projectId: project?.id ?? (task.project_id ? String(task.project_id) : null),
    requestId: request?.id ?? (task.request_id ? String(task.request_id) : null),
    projectCode: project?.code ?? null,
    projectTitle: project?.title ?? null,
    requestCode: request?.code ?? project?.request_code ?? null,
    requestTitle: request?.title ?? project?.request_title ?? null,
  };
}

export function mergeTaskParentFields(
  task: Record<string, unknown>,
  resolved: Omit<WorkParentFields, "kind">,
): WorkParentFields {
  const pick = (key: string, fallback: string | null | undefined) => {
    const raw = task[key];
    if (raw != null && String(raw).trim()) return String(raw);
    return fallback ?? null;
  };
  return {
    kind: "task",
    origin: pick("origin", resolved.origin ?? undefined),
    projectId: pick("project_id", resolved.projectId ?? undefined),
    requestId: pick("request_id", resolved.requestId ?? undefined),
    projectCode: pick("project_code", resolved.projectCode ?? undefined),
    projectTitle: pick("project_title", resolved.projectTitle ?? undefined),
    requestCode: pick("request_code", resolved.requestCode ?? undefined),
    requestTitle: pick("request_title", resolved.requestTitle ?? undefined),
  };
}

export function WorkParentContext({
  kind,
  origin,
  projectId,
  requestId,
  projectCode,
  projectTitle,
  requestCode,
  requestTitle,
  showKindBadge = true,
}: WorkParentFields & { showKindBadge?: boolean }) {
  const bi = useBi();
  const { user, has } = useAuth();
  const showProjectLink = canSeeProjects(
    { roleCode: user?.roleCode, permissions: user?.permissions ?? [] },
    has,
  );
  const listKind: WorkListKind | null =
    kind === "project"
      ? "project"
      : kind === "task"
        ? "task"
        : kind && kind in KIND_LABEL
          ? (kind as WorkListKind)
          : origin === "project"
            ? "task"
            : origin === "request"
              ? "task"
              : null;

  const parts: ReactNode[] = [];
  if (requestId && (requestCode || requestTitle)) {
    parts.push(
      <span key="req">
        <Bi en="Under request" fa="زیر درخواست" />{" "}
        <Link to={`/requests/${requestId}`} className="work-parent-link">
          {requestTitle ? <span>{requestTitle}</span> : null}
          {requestCode ? <span className="mono muted ltr-value"> {requestCode}</span> : null}
        </Link>
      </span>,
    );
  }
  if (projectId && (projectCode || projectTitle)) {
    parts.push(
      <span key="prj">
        <Bi en="In project" fa="در پروژه" />{" "}
        {showProjectLink ? (
          <Link to={`/projects/${projectId}`} className="work-parent-link">
            {projectTitle ? <span>{projectTitle}</span> : null}
            {projectCode ? <span className="mono muted ltr-value"> {projectCode}</span> : null}
          </Link>
        ) : (
          <span className="work-parent-link">
            {projectTitle ? <span>{projectTitle}</span> : null}
            {projectCode ? <span className="mono muted ltr-value"> {projectCode}</span> : null}
          </span>
        )}
      </span>,
    );
  }
  if (!parts.length && origin === "work") {
    parts.push(<span key="solo">{bi("Not linked to a request or project yet", "هنوز به درخواست یا پروژه وصل نیست")}</span>);
  }
  if (!parts.length && listKind === "project") {
    parts.push(<span key="gap">{bi("Project with no tasks yet — add work on the project page", "پروژه بدون کار — از صفحهٔ پروژه کار اضافه کنید")}</span>);
  }
  if (!parts.length) return null;

  return (
    <div className="work-parent-context">
      {showKindBadge && listKind ? <WorkListKindBadge kind={listKind} /> : null}
      <div className="work-parent-body">
        {parts.map((node, i) => (
          <span key={i} className="work-parent-sep">
            {node}
          </span>
        ))}
      </div>
    </div>
  );
}

/** راهنمای کوتاه بالای فهرست پروژه / درخواست / گزارش */
export function WorkChainLegend({ variant }: { variant: "projects" | "requests" | "reports" }) {
  const copy = {
    projects: {
      en: "Each card is a project — work the team does. The parent request is what you (or a manager) asked for; one request can spawn several projects (e.g. film, design, performance).",
      fa: "هر کارت یک پروژه است — جایی که تیم کار را انجام می‌دهد. درخواست والد همان چیزی است که شما (یا مدیر) خواسته‌اید؛ یک درخواست می‌تواند چند پروژه بسازد (مثلاً فیلم، طراحی، پرفورمنس).",
    },
    requests: {
      en: "Each card is a request. After triage, the team adds projects under it; tasks live on those projects.",
      fa: "هر کارت یک درخواست است. بعد از رسیدگی، تیم پروژه زیر آن می‌سازد؛ کارها روی همان پروژه‌ها ثبت می‌شوند.",
    },
    reports: {
      en: "Request → projects → tasks. Progress counts tasks across all projects of that request.",
      fa: "درخواست → پروژه‌ها → کارها. پیشرفت، کارهای انجام‌شده روی همهٔ پروژه‌های آن درخواست را می‌شمارد.",
    },
  }[variant];
  return (
    <p className="help-text">
      <Bi en={copy.en} fa={copy.fa} />
    </p>
  );
}

/** روی کارت پروژه: این ردیف پروژه است و زیر کدام درخواست است */
export function ProjectParentRequestLine({
  requestId,
  requestCode,
  requestTitle,
}: {
  requestId?: string | null;
  requestCode?: string | null;
  requestTitle?: string | null;
}) {
  const bi = useBi();
  return (
    <span className="row-meta work-parent-context">
      <WorkListKindBadge kind="project" />
      {requestCode || requestTitle ? (
        <span>
          <Bi en="Part of request" fa="زیرمجموعهٔ درخواست" />{" "}
          <Link to={requestId ? `/requests/${requestId}` : "/requests"} className="work-parent-link">
            <span dir="ltr">{requestCode}</span>
            {requestTitle ? <> — {requestTitle}</> : null}
          </Link>
        </span>
      ) : (
        <span>{bi("Standalone project (no parent request)", "پروژه مستقل (بدون درخواست والد)")}</span>
      )}
    </span>
  );
}

/** Lookups for task rows (My Work, People, Home). */
export function useWorkParentLookups(enabled = true) {
  const projects = useQuery({
    queryKey: ["requests", "work-projects"],
    queryFn: () => requestsApi.projects(),
    enabled,
  });
  const requests = useQuery({
    queryKey: ["requests", "work-requests", "picker"],
    queryFn: () => requestsApi.list(),
    enabled,
  });
  const resolve = useMemo(() => {
    const plist = projects.data ?? [];
    const rlist = requests.data ?? [];
    return (task: { project_id?: string | null; request_id?: string | null }) =>
      resolveTaskParents(task, plist, rlist);
  }, [projects.data, requests.data]);
  return { resolve, loading: projects.isLoading || requests.isLoading };
}
