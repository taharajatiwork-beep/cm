import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import "../perf/perf.css"; // conn-tile / perf-actions استایل‌های مشترک
import { Badge, Button, Card, ErrorMessage, Field, LoadingState, Muted, PageHeader, SectionHeader, Select } from "../components/ui";
import { DELETE_CONFIRM_LABEL, useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { DateText } from "../components/DateText";
import { Bi } from "../i18n";
import { useAuth } from "../auth";
import { requestsApi, type WorkProject } from "./api";

export const PROJECT_STATUS_LABEL: Record<string, string> = {
  new: "تازه",
  in_progress: "در جریان",
  done: "تمام",
};

const STATUS_TONE: Record<string, "ok" | "warn" | "danger"> = {
  new: "warn",
  in_progress: "warn",
  done: "ok",
};

export function ProjectsPage() {
  const { has } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const triage = has("request.triage") || has("request.manage") || has("org.admin");
  const [statusFilter, setStatusFilter] = useState("");
  const projects = useQuery({
    queryKey: ["requests", "work-projects", statusFilter],
    queryFn: () => requestsApi.projects("", statusFilter),
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => requestsApi.patchProject(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["requests", "work-projects"] });
      toast("پروژه به‌روز شد");
    },
    onError: (error: Error) => toast(error.message),
  });
  const confirm = useConfirm();
  const remove = useMutation({
    mutationFn: (id: string) => requestsApi.deleteProject(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["requests", "work-projects"] });
      toast("پروژه حذف شد");
    },
    onError: (error: Error) => toast(error.message),
  });

  return (
    <>
      <PageHeader
        title={<Bi en="Projects" fa="پروژه‌ها" />}
        description={
          <Bi
            en="Each project was born from a request. Campaigns of the team attach to their project."
            fa="هر پروژه از دل یک درخواست ساخته شده است. کمپین‌های تیم به پروژهٔ خودشان وصل می‌شوند."
          />
        }
      />
      <Card>
        <SectionHeader
          icon="layers"
          title={<Bi en="All projects" fa="همهٔ پروژه‌ها" />}
          count={projects.data?.length}
          action={
            triage ? (
              <Select aria-label="وضعیت" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="">همهٔ وضعیت‌ها</option>
                {Object.entries(PROJECT_STATUS_LABEL).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </Select>
            ) : null
          }
        />
        {projects.isLoading ? <LoadingState /> : null}
        {projects.error ? <ErrorMessage error={projects.error instanceof Error ? projects.error.message : String(projects.error)} /> : null}
        {projects.data && projects.data.length === 0 ? <Muted as="p">پروژه‌ای با این فیلتر نیست. پروژه از کارت درخواست در صفحهٔ درخواست‌ها ساخته می‌شود.</Muted> : null}
        {projects.data && projects.data.length > 0 ? (
          <div className="conn-grid">
            {projects.data.map((row) => (
              <ProjectCard
                key={row.id}
                row={row}
                triage={triage}
                onPatch={(body) => patch.mutate({ id: row.id, body })}
                onDelete={() => {
                  void confirm("حذف پروژه", `پروژهٔ «${row.title}» حذف شود؟`, DELETE_CONFIRM_LABEL, { danger: true }).then((ok) => {
                    if (ok) remove.mutate(row.id);
                  });
                }}
              />
            ))}
          </div>
        ) : null}
      </Card>
    </>
  );
}

function ProjectCard({
  row,
  triage,
  onPatch,
  onDelete,
}: {
  row: WorkProject;
  triage: boolean;
  onPatch: (body: Record<string, unknown>) => void;
  onDelete: () => void;
}) {
  return (
    <article className="conn-tile" data-tone={STATUS_TONE[row.status] || "warn"}>
      <div className="conn-tile-head">
        <h3><span dir="ltr">{row.code}</span> — {row.title}</h3>
        <Badge tone={STATUS_TONE[row.status] || "warn"}>{PROJECT_STATUS_LABEL[row.status] || row.status}</Badge>
      </div>
      <p className="conn-help">{row.description || "بدون توضیح."}</p>
      <Muted>
        {row.kind}
        {row.request_code ? <> · از درخواست <span dir="ltr">{row.request_code}</span></> : " · بدون درخواست"}
        {row.team_id && row.team_name ? (
          <>
            {" · "}
            {triage ? <Link to={`/teams/${row.team_id}`}>{row.team_name}</Link> : row.team_name}
          </>
        ) : ""}
        {" · "}
        <DateText value={row.created_at} withTime />
      </Muted>
      <div className="row perf-actions">
        <Link to={`/projects/${row.id}`}><Bi en="Open" fa="باز کردن" /></Link>
      </div>
      {triage ? (
        <div className="row perf-actions">
          <Field label="وضعیت">
            <Select value={row.status} onChange={(event) => onPatch({ status: event.target.value })}>
              {Object.entries(PROJECT_STATUS_LABEL).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </Select>
          </Field>
          <Button type="button" variant="danger-quiet" className="btn-sm" onClick={onDelete}>
            <Bi en="Delete" fa="حذف" />
          </Button>
        </div>
      ) : null}
    </article>
  );
}