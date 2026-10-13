import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import "../perf/perf.css";
import { Badge, Button, Card, Dialog, Disclosure, EmptyState, Field, Input, Muted, PageHeader, QueryState, SectionHeader, Segmented, Select } from "../components/ui";
import { DELETE_CONFIRM_LABEL, useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { DateText } from "../components/DateText";
import { Bi, useBi } from "../i18n";
import { useAuth } from "../auth";
import { canSeeProjects } from "../lib/access";
import { ConceptHint } from "../ux";
import { ProjectParentRequestLine, WorkChainLegend } from "../lib/workContext";
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
  const { has, user } = useAuth();
  const accessUser = {
    roleCode: user?.roleCode,
    permissions: user?.permissions ?? [],
    teamId: user?.team_id,
    teamHomeTeamId: user?.team_home_team_id,
  };
  const allowed = canSeeProjects(accessUser, has);
  const qc = useQueryClient();
  const toast = useToast();
  const triage = has("request.triage") || has("request.manage") || has("org.admin");
  const requester = has("request.create") && !triage;
  const [statusFilter, setStatusFilter] = useState("");
  const [view, setView] = useState<"list" | "board">("list");
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [requestId, setRequestId] = useState("");
  const projects = useQuery({
    queryKey: ["requests", "work-projects", view === "board" ? "" : statusFilter],
    queryFn: () => requestsApi.projects("", view === "board" ? "" : statusFilter),
    enabled: allowed,
  });
  const requests = useQuery({
    queryKey: ["requests", "work-requests", "picker"],
    queryFn: () => requestsApi.list(),
    enabled: allowed && triage,
  });
  const create = useMutation({
    mutationFn: () => requestsApi.createStandaloneProject({ title: title.trim(), kind: "عمومی", status: "new" }, requestId),
    onSuccess: () => {
      setTitle("");
      setRequestId("");
      setCreating(false);
      void qc.invalidateQueries({ queryKey: ["requests", "work-projects"] });
      toast("پروژه ساخته شد");
    },
    onError: (error: Error) => toast(error.message),
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
  const bi = useBi();
  const createTitleId = useId();
  const remove = useMutation({
    mutationFn: (id: string) => requestsApi.deleteProject(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["requests", "work-projects"] });
      toast("پروژه حذف شد");
    },
    onError: (error: Error) => toast(error.message),
  });

  if (!allowed) {
    return (
      <EmptyState
        titleEn="Projects are not on your menu"
        titleFa="پروژه در منوی شما نیست"
        bodyEn="Open My Work for tasks assigned to you."
        bodyFa="کارهای واگذارشده را در «کارهای من» ببینید."
        action={
          <Button to="/my-work">
            <Bi en="My Work" fa="کارهای من" />
          </Button>
        }
      />
    );
  }

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
        actions={
          triage ? (
            <Button type="button" onClick={() => setCreating(true)}>
              <Bi en="New project" fa="پروژهٔ تازه" />
            </Button>
          ) : null
        }
      />
      <ConceptHint kind="task" />
      {triage && creating ? (
        <Dialog
          onClose={() => setCreating(false)}
          className="form-pop"
          labelledBy={createTitleId}
          closeLabel={bi("Close", "بستن")}
          busy={create.isPending}
        >
          <SectionHeader icon="plus" title={<span id={createTitleId}><Bi en="New project" fa="پروژهٔ تازه" /></span>} />
          <div className="form-grid">
            <Field label={<Bi en="Title" fa="عنوان" />}>
              <Input value={title} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <Field label={<Bi en="Request (optional)" fa="درخواست (اختیاری)" />}>
              <Select value={requestId} onChange={(event) => setRequestId(event.target.value)}>
                <option value="">بدون درخواست</option>
                {(requests.data ?? []).map((row) => (
                  <option key={row.id} value={row.id}>{row.code} — {row.title}</option>
                ))}
              </Select>
            </Field>
            <div className="span-all">
              <Button disabled={!title.trim() || create.isPending} onClick={() => create.mutate()}>
                <Bi en="Create project" fa="ساختن پروژه" />
              </Button>
            </div>
          </div>
        </Dialog>
      ) : null}
      <Card>
        <SectionHeader
          icon="layers"
          title={
            requester ? (
              <Bi en="Projects from my requests" fa="پروژه‌های درخواست‌های من" />
            ) : (
              <Bi en="Projects" fa="پروژه‌ها" />
            )
          }
          count={projects.data?.length}
          action={
            <div className="record-actions">
              <Segmented
                ariaLabel="نمای پروژه‌ها"
                value={view}
                onChange={setView}
                items={[
                  { key: "list", label: "فهرست" },
                  { key: "board", label: "کانبان" },
                ]}
              />
              {triage && view === "list" ? (
                <Select aria-label="وضعیت" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="">همهٔ وضعیت‌ها</option>
                  {Object.entries(PROJECT_STATUS_LABEL).map(([key, label]) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </Select>
              ) : null}
            </div>
          }
        />
        <WorkChainLegend variant="projects" />
        <QueryState
          isLoading={projects.isLoading}
          error={projects.error}
          isEmpty={projects.data?.length === 0}
          empty={
            statusFilter ? (
              <EmptyState
                titleEn="Nothing matches this filter"
                titleFa="این فیلتر نتیجه‌ای ندارد"
                bodyEn="Try another status, or clear the filter."
                bodyFa="وضعیت دیگری را ببینید، یا فیلتر را پاک کنید."
                action={
                  <Button type="button" variant="secondary" onClick={() => setStatusFilter("")}>
                    <Bi en="Clear filter" fa="پاک کردن فیلتر" />
                  </Button>
                }
              />
            ) : (
              <EmptyState
                titleEn="No projects yet"
                titleFa="هنوز پروژه‌ای نیست"
                bodyEn="Projects usually come from a request. You can also start one directly."
                bodyFa="پروژه معمولاً از یک درخواست ساخته می‌شود. می‌توانید مستقیم هم شروع کنید."
                action={
                  triage ? (
                    <Button type="button" onClick={() => setCreating(true)}>
                      <Bi en="New project" fa="پروژهٔ تازه" />
                    </Button>
                  ) : undefined
                }
              />
            )
          }
        >
          {projects.data && projects.data.length > 0 && view === "board" ? (
            <ProjectBoard
              rows={projects.data}
              triage={triage}
              onMove={(id, status) => patch.mutate({ id, body: { status } })}
            />
          ) : null}
          {projects.data && projects.data.length > 0 && view === "list" ? (
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
        </QueryState>
      </Card>
    </>
  );
}

const BOARD = ["new", "in_progress", "done"] as const;

function ProjectBoard({
  rows,
  triage,
  onMove,
}: {
  rows: WorkProject[];
  triage: boolean;
  onMove: (id: string, status: string) => void;
}) {
  const [over, setOver] = useState<string | null>(null);
  return (
    <div className="kanban">
      {BOARD.map((status) => {
        const cards = rows.filter((row) => row.status === status);
        return (
          <section
            key={status}
            className={over === status ? "kanban-col is-over" : "kanban-col"}
            onDragOver={(event) => {
              if (!triage) return;
              event.preventDefault();
              setOver(status);
            }}
            onDragLeave={() => setOver((current) => (current === status ? null : current))}
            onDrop={(event) => {
              event.preventDefault();
              setOver(null);
              const id = event.dataTransfer.getData("text/plain");
              const row = rows.find((item) => item.id === id);
              if (row && row.status !== status) onMove(id, status);
            }}
          >
            <h3>
              {PROJECT_STATUS_LABEL[status]}
              <span className="section-count">{cards.length.toLocaleString("fa-IR")}</span>
            </h3>
            {cards.length === 0 ? <Muted as="p">خالی</Muted> : null}
            {cards.map((row) => (
              <article
                key={row.id}
                className="kanban-card"
                draggable={triage}
                onDragStart={(event) => event.dataTransfer.setData("text/plain", row.id)}
              >
                <span className="record-code" dir="ltr">{row.code}</span>
                <strong>{row.title}</strong>
                <span className="meta-chip">{row.kind}</span>
                {row.request_code ? (
                  <Muted as="span">
                    <Bi en="Request" fa="درخواست" /> <span dir="ltr">{row.request_code}</span>
                  </Muted>
                ) : null}
                <Button variant="ghost" className="btn-sm" to={`/projects/${row.id}`}>
                  <Bi en="Open" fa="باز کردن" />
                </Button>
              </article>
            ))}
          </section>
        );
      })}
    </div>
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
    <Card as="article" className="record-card" stack>
      <div className="record-head">
        <div>
          <div className="record-code" dir="ltr">{row.code}</div>
          <h3 className="record-title">{row.title}</h3>
        </div>
        <Badge tone={STATUS_TONE[row.status] || "warn"}>{PROJECT_STATUS_LABEL[row.status] || row.status}</Badge>
      </div>
      {row.description ? <p className="record-body">{row.description}</p> : null}
      <ProjectParentRequestLine
        requestId={row.request_id}
        requestCode={row.request_code}
        requestTitle={row.request_title}
      />
      <div className="meta-row">
        <span className="meta-chip">{row.kind}</span>
        {row.team_name ? (
          <span className="meta-chip">
            {triage && row.team_id ? <Link to={`/teams/${row.team_id}`}>{row.team_name}</Link> : row.team_name}
          </span>
        ) : null}
        <span className="meta-chip"><DateText value={row.created_at} withTime /></span>
      </div>
      <div className="progress-bar" aria-hidden>
        <span style={{ width: row.status === "done" ? "100%" : row.status === "in_progress" ? "55%" : "12%" }} />
      </div>
      <div className="record-actions">
        <Button to={`/projects/${row.id}`}>
          <Bi en="Open" fa="باز کردن" />
        </Button>
        <Button variant="ghost" to={`/reports?project=${row.id}`}>
          <Bi en="Report" fa="گزارش" />
        </Button>
      </div>
      {triage ? (
        <Disclosure label={<Bi en="Manage" fa="مدیریت" />}>
          <div className="stack">
            <Field label={<Bi en="Status" fa="وضعیت" />}>
              <Select value={row.status} onChange={(event) => onPatch({ status: event.target.value })}>
                {Object.entries(PROJECT_STATUS_LABEL).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </Select>
            </Field>
            <div className="record-actions">
              <Button type="button" variant="danger-quiet" className="btn-sm" onClick={onDelete}>
                <Bi en="Delete" fa="حذف" />
              </Button>
            </div>
          </div>
        </Disclosure>
      ) : null}
    </Card>
  );
}
