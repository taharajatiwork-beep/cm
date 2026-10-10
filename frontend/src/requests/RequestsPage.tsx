import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import "../perf/perf.css"; // conn-tile / perf-actions استایل‌های مشترک
import { Badge, Button, Card, ErrorMessage, Field, Input, ListItem, LoadingState, Muted, PageHeader, SectionHeader, Select, TextArea } from "../components/ui";
import { List } from "../components/ui";
import { DELETE_CONFIRM_LABEL, useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { DateText } from "../components/DateText";
import { Bi } from "../i18n";
import { useAuth } from "../auth";
import { requestsApi, type TeamOption, type WorkProject, type WorkRequest } from "./api";

const STATUS_LABEL: Record<string, string> = {
  new: "جدید",
  in_review: "در بررسی",
  converted: "تبدیل به پروژه",
  rejected: "رد شده",
  done: "انجام شد",
};

const STATUS_TONE: Record<string, "ok" | "warn" | "danger"> = {
  new: "warn",
  in_review: "warn",
  converted: "ok",
  rejected: "danger",
  done: "ok",
};

const PRIORITY_LABEL: Record<string, string> = { low: "کم", normal: "معمولی", high: "بالا" };

const PROJECT_STATUS_LABEL: Record<string, string> = {
  new: "تازه",
  in_progress: "در جریان",
  done: "تمام",
};

const REQUEST_KINDS = ["تبلیغات", "قیمت و پست‌ها", "عمومی"];
const PROJECT_KINDS = ["پرفورمنس", "تولید محتوا", "فیلم‌برداری", "طراحی", "عمومی"];

export function RequestsPage() {
  const { has } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const triage = has("request.triage") || has("request.manage") || has("org.admin");
  const [statusFilter, setStatusFilter] = useState("");
  const requests = useQuery({
    queryKey: ["requests", "work-requests", statusFilter],
    queryFn: () => requestsApi.list(statusFilter),
  });
  const teams = useQuery({ queryKey: ["org", "teams"], queryFn: requestsApi.teams });
  const projects = useQuery({ queryKey: ["requests", "work-projects"], queryFn: () => requestsApi.projects() });

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => requestsApi.patch(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["requests", "work-requests"] });
      toast("درخواست به‌روز شد");
    },
    onError: (error: Error) => toast(error.message),
  });
  const confirm = useConfirm();
  const remove = useMutation({
    mutationFn: (id: string) => requestsApi.remove(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["requests", "work-requests"] });
      toast("درخواست حذف شد");
    },
    onError: (error: Error) => toast(error.message),
  });
  const convertTask = useMutation({
    mutationFn: ({ requestId, title }: { requestId: string; title: string }) => requestsApi.convertTask(requestId, title),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["requests"] });
      toast("وظیفه ساخته شد و درخواست تبدیل شد");
    },
    onError: (error: Error) => toast(error.message),
  });
  const createProject = useMutation({
    mutationFn: async ({ requestId, bodies }: { requestId: string; bodies: Array<Record<string, unknown>> }) => {
      const created = [];
      for (const body of bodies) created.push(await requestsApi.createProject(requestId, body));
      return created;
    },
    onSuccess: (created) => {
      void qc.invalidateQueries({ queryKey: ["requests", "work-requests"] });
      void qc.invalidateQueries({ queryKey: ["requests", "work-projects"] });
      toast(created.length > 1 ? `${created.length.toLocaleString("fa-IR")} پروژه از این درخواست ساخته شد` : "پروژه ساخته شد. باز هم می‌توانید پروژهٔ دیگری اضافه کنید");
    },
    onError: (error: Error) => toast(error.message),
  });

  return (
    <>
      <PageHeader
        title={<Bi en="Requests" fa="درخواست‌ها" />}
        description={
          <Bi
            en="Managers file a request for a team. The team turns it into projects; each project holds its own campaigns."
            fa="مدیرها برای تیم درخواست ثبت می‌کنند. تیم همان را به یک یا چند پروژه تبدیل می‌کند؛ هر پروژه کمپین‌های خودش را می‌گیرد."
          />
        }
      />
      {has("request.create") || triage ? <CreateRequestCard teams={teams.data ?? []} /> : null}
      <RequestsReportCard requests={requests.data ?? []} projects={projects.data ?? []} triage={triage} />
      <Card>
        <SectionHeader
          icon="clock"
          title={triage ? <Bi en="Request queue" fa="صف درخواست‌ها" /> : <Bi en="My requests" fa="درخواست‌های من" />}
          count={requests.data?.length}
          action={
            triage ? (
              <Select aria-label="وضعیت" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="">همهٔ وضعیت‌ها</option>
                {Object.entries(STATUS_LABEL).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </Select>
            ) : null
          }
        />
        {requests.isLoading ? <LoadingState /> : null}
        {requests.error ? <ErrorMessage error={requests.error instanceof Error ? requests.error.message : String(requests.error)} /> : null}
        {requests.data && requests.data.length === 0 ? <Muted as="p">درخواستی با این فیلتر نیست.</Muted> : null}
        {requests.data && requests.data.length > 0 ? (
          <div className="conn-grid">
            {requests.data.map((row) => (
              <RequestCard
                key={row.id}
                row={row}
                teams={teams.data ?? []}
                projects={(projects.data ?? []).filter((project) => project.request_id === row.id)}
                triage={triage}
                onPatch={(body) => patch.mutate({ id: row.id, body })}
                onDelete={() => {
                  void confirm("حذف درخواست", `درخواست «${row.title}» حذف شود؟`, DELETE_CONFIRM_LABEL, { danger: true }).then((ok) => {
                    if (ok) remove.mutate(row.id);
                  });
                }}
                onCreateProject={(bodies) => createProject.mutate({ requestId: row.id, bodies })}
                onConvertTask={() => convertTask.mutate({ requestId: row.id, title: row.title })}
              />
            ))}
          </div>
        ) : null}
      </Card>
    </>
  );
}

/** گزارش مخصوص هر نقش: مدیر وضعیت درخواست‌های خودش، ترییج/ادمین کل صف را می‌بیند. */
function RequestsReportCard({ requests, projects, triage }: { requests: WorkRequest[]; projects: WorkProject[]; triage: boolean }) {
  const { has } = useAuth();
  if (requests.length === 0) return null;
  const byStatus = new Map<string, number>();
  for (const row of requests) byStatus.set(row.status, (byStatus.get(row.status) || 0) + 1);
  const ownRequests = new Set(requests.map((row) => row.id));
  const linkedProjects = projects.filter((project) => project.request_id && ownRequests.has(project.request_id));
  return (
    <Card>
      <SectionHeader
        icon="activity"
        title={triage ? <Bi en="Team report" fa="گزارش تیم" /> : <Bi en="My report" fa="گزارش من" />}
        hint={
          triage
            ? <Bi en="Whole queue at a glance." fa="نمای کلی صف درخواست‌ها و پروژه‌های تیم‌ها." />
            : <Bi en="What happened to what you asked for." fa="برای درخواست‌های شما چه شده است." />
        }
      />
      <div className="row" style={{ flexWrap: "wrap", gap: "var(--space-2)" }}>
        {Object.entries(STATUS_LABEL)
          .filter(([key]) => (byStatus.get(key) || 0) > 0 || (triage && key === "new"))
          .map(([key, label]) => (
            <Badge key={key} tone={STATUS_TONE[key] || ""}>
              {label}: {(byStatus.get(key) || 0).toLocaleString("fa-IR")}
            </Badge>
          ))}
        {has("request.triage") || has("request.manage") || has("org.admin") ? (
          <Badge tone="ok">
            <Bi en="Projects" fa="پروژه‌ها" />: {projects.length.toLocaleString("fa-IR")}
          </Badge>
        ) : null}
        {!triage && linkedProjects.length > 0 ? (
          <Badge tone="ok">
            <Bi en="Projects from your requests" fa="پروژه‌های درخواست‌های شما" />: {linkedProjects.length.toLocaleString("fa-IR")}
          </Badge>
        ) : null}
      </div>
    </Card>
  );
}

function CreateRequestCard({ teams }: { teams: TeamOption[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("تبلیغات");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("normal");
  const [due, setDue] = useState("");
  const [teamId, setTeamId] = useState("");
  const [busy, setBusy] = useState(false);
  function submit() {
    setBusy(true);
    requestsApi.create({
      title,
      kind,
      description,
      priority,
      due_date: due || null,
      team_id: teamId || null,
    })
      .then(() => {
        toast("درخواست ثبت شد و برای تیم رفت");
        setTitle("");
        setDescription("");
        setDue("");
        setTeamId("");
        void qc.invalidateQueries({ queryKey: ["requests", "work-requests"] });
      })
      .catch((error: Error) => toast(error.message))
      .finally(() => setBusy(false));
  }
  return (
    <Card>
      <SectionHeader
        icon="send"
        title={<Bi en="New request" fa="ایجاد درخواست" />}
        hint={<Bi en="The request goes to the team you pick. The team decides how to turn it into projects." fa="درخواست به تیمی که انتخاب می‌کنید می‌رود. تیم تصمیم می‌گیرد چطور به پروژه تبدیلش کند." />}
      />
      <div className="form-grid">
        <Field className="span-2" label={<Bi en="Title" fa="عنوان" />}>
          <Input value={title} placeholder="مثلاً کمپین فروش بهمن" onChange={(event) => setTitle(event.target.value)} />
        </Field>
        <Field label={<Bi en="Kind" fa="نوع" />}>
          <Select value={kind} onChange={(event) => setKind(event.target.value)}>
            {REQUEST_KINDS.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </Select>
        </Field>
        <Field label={<Bi en="Team" fa="تیم" />}>
          <Select value={teamId} onChange={(event) => setTeamId(event.target.value)}>
            <option value="">— بعداً تعیین می‌شود —</option>
            {teams.filter((team) => !team.parent_team_id).map((team) => (
              <option key={team.id} value={team.id}>{team.name}</option>
            ))}
          </Select>
        </Field>
        <Field className="span-all" label={<Bi en="Description" fa="توضیح" />}>
          <TextArea value={description} rows={3} placeholder="جزئیات، بودجه، تاریخ لازم…" onChange={(event) => setDescription(event.target.value)} />
        </Field>
        <Field label={<Bi en="Priority" fa="اولویت" />}>
          <Select value={priority} onChange={(event) => setPriority(event.target.value)}>
            <option value="low">کم</option>
            <option value="normal">معمولی</option>
            <option value="high">بالا</option>
          </Select>
        </Field>
        <Field label={<Bi en="Needed by" fa="تاریخ لازم" />}>
          <Input type="date" value={due} onChange={(event) => setDue(event.target.value)} />
        </Field>
        <div className="span-all perf-actions">
          <Button type="button" disabled={!title.trim() || busy} onClick={submit}>
            {busy ? <Bi en="Saving" fa="در حال ثبت…" /> : <Bi en="File request" fa="ثبت درخواست" />}
          </Button>
        </div>
      </div>
    </Card>
  );
}

function RequestCard({
  row,
  teams,
  projects,
  triage,
  onPatch,
  onDelete,
  onCreateProject,
  onConvertTask,
}: {
  row: WorkRequest;
  teams: TeamOption[];
  projects: WorkProject[];
  triage: boolean;
  onPatch: (body: Record<string, unknown>) => void;
  onDelete: () => void;
  onCreateProject: (bodies: Array<Record<string, unknown>>) => void;
  onConvertTask: () => void;
}) {
  const [adding, setAdding] = useState(false);
  return (
    <article className="conn-tile" data-tone={STATUS_TONE[row.status] || "warn"}>
      <div className="conn-tile-head">
        <h3><span dir="ltr">{row.code}</span> — {row.title}</h3>
        <Badge tone={STATUS_TONE[row.status] || "warn"}>{STATUS_LABEL[row.status] || row.status}</Badge>
      </div>
      <p className="conn-help">{row.description || "بدون توضیح."}</p>
      <Muted>
        {row.kind} · اولویت {PRIORITY_LABEL[row.priority] || row.priority}
        {row.requester_name ? ` · ${row.requester_name}` : ""}
        {row.team_id && row.team_name ? (
          <>
            {" · "}
            {triage ? <Link to={`/teams/${row.team_id}`}>{row.team_name}</Link> : row.team_name}
          </>
        ) : ""}
        {row.due_date ? <> · لازم تا <DateText value={row.due_date} /></> : ""}
        {" · "}
        <DateText value={row.created_at} withTime />
      </Muted>
      {projects.length > 0 ? (
        <div>
          <Muted as="p" className="conn-help">
            <Bi en="Projects" fa="پروژه‌های این درخواست" /> ({projects.length.toLocaleString("fa-IR")}):
          </Muted>
          <List>
            {projects.map((project) => (
              <ListItem key={project.id}>
                <span dir="ltr">{project.code}</span>
                {" — "}
                {triage ? <Link to={`/projects/${project.id}`}>{project.title}</Link> : <Link to="/projects">{project.title}</Link>}
                {" · "}
                {project.kind}
                {project.team_id && project.team_name ? (
                  <>
                    {" · "}
                    {triage ? <Link to={`/teams/${project.team_id}`}>{project.team_name}</Link> : project.team_name}
                  </>
                ) : ""}
                {" · "}
                {PROJECT_STATUS_LABEL[project.status] || project.status}
              </ListItem>
            ))}
          </List>
        </div>
      ) : null}
      {triage ? (
        <div className="form-grid">
          <Field label={<Bi en="Status" fa="وضعیت" />}>
            <Select value={row.status} onChange={(event) => onPatch({ status: event.target.value })}>
              {Object.entries(STATUS_LABEL).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </Select>
          </Field>
          <Field label={<Bi en="Team" fa="تیم" />}>
            <Select value={row.team_id || ""} onChange={(event) => onPatch({ team_id: event.target.value || null })}>
              <option value="">—</option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>{team.name}</option>
              ))}
            </Select>
          </Field>
        </div>
      ) : null}
      {triage ? (
        adding ? (
          <ProjectFromRequest teams={teams} defaultTeamId={row.team_id || ""} onCancel={() => setAdding(false)} onCreate={onCreateProject} />
        ) : (
          <div className="row perf-actions">
            <Button type="button" className="btn-sm" onClick={() => setAdding(true)}>
              <Bi
                en={projects.length ? "Add another project" : "Turn into projects"}
                fa={projects.length ? "پروژهٔ دیگر" : "تبدیل به پروژه"}
              />
            </Button>
            <Button type="button" className="btn-sm" variant="secondary" onClick={onConvertTask}>
              <Bi en="Turn into a task" fa="تبدیل مستقیم به وظیفه" />
            </Button>
            <Button type="button" variant="danger-quiet" className="btn-sm" onClick={onDelete}>
              <Bi en="Delete" fa="حذف" />
            </Button>
          </div>
        )
      ) : (
        <div className="row perf-actions">
          {row.status === "new" ? (
            <Button type="button" variant="danger-quiet" className="btn-sm" onClick={onDelete}>
              <Bi en="Delete" fa="حذف" />
            </Button>
          ) : null}
        </div>
      )}
    </article>
  );
}

function ProjectFromRequest({
  teams,
  defaultTeamId,
  onCancel,
  onCreate,
}: {
  teams: TeamOption[];
  defaultTeamId: string;
  onCancel: () => void;
  onCreate: (bodies: Array<Record<string, unknown>>) => void;
}) {
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("پرفورمنس");
  const [teamId, setTeamId] = useState(defaultTeamId);
  const [picked, setPicked] = useState<string[]>([]);
  const [description, setDescription] = useState("");
  const parentTeam = teams.find((team) => team.id === defaultTeamId);
  const childTeams = teams.filter((team) => team.parent_team_id === defaultTeamId);
  const otherTeams = teams.filter(
    (team) => team.id !== defaultTeamId && team.parent_team_id !== defaultTeamId,
  );
  return (
    <div className="form-grid" style={{ marginTop: "var(--space-2)" }}>
      <Field className="span-2" label={<Bi en="Project title" fa="عنوان پروژه" />}>
        <Input value={title} placeholder="مثلاً کمپین پرفورمنس بهمن" onChange={(event) => setTitle(event.target.value)} />
      </Field>
      <Field label={<Bi en="Kind" fa="نوع پروژه" />}>
        <Select value={kind} onChange={(event) => setKind(event.target.value)}>
          {PROJECT_KINDS.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </Select>
      </Field>
      {childTeams.length > 0 ? (
        <Field className="span-all" label={<Bi en="Sections" fa="بخش‌ها" />}>
          <div className="row" style={{ flexWrap: "wrap", gap: "var(--space-2)" }}>
            {childTeams.map((team) => (
              <label key={team.id}>
                <input
                  type="checkbox"
                  checked={picked.includes(team.id)}
                  onChange={() => setPicked((cur) => (cur.includes(team.id) ? cur.filter((id) => id !== team.id) : [...cur, team.id]))}
                />{" "}
                {team.name}
              </label>
            ))}
          </div>
          <Muted as="p">هر بخش تیک‌خورده یک پروژهٔ جدا می‌شود. اگر هیچ‌کدام را نزنید، یک پروژه روی خودِ {parentTeam?.name || "تیم"} ساخته می‌شود.</Muted>
        </Field>
      ) : (
        <Field label={<Bi en="Team" fa="تیم مجری" />}>
          <Select value={teamId} onChange={(event) => setTeamId(event.target.value)}>
            <option value="">—</option>
            {otherTeams.map((team) => (
              <option key={team.id} value={team.id}>{team.name}</option>
            ))}
          </Select>
        </Field>
      )}
      <Field className="span-all" label={<Bi en="Description" fa="توضیح" />}>
        <TextArea value={description} rows={2} onChange={(event) => setDescription(event.target.value)} />
      </Field>
      <div className="span-all row perf-actions">
        <Button
          type="button"
          className="btn-sm"
          disabled={!title.trim()}
          onClick={() => {
            const bodies = picked.length
              ? picked.map((id) => {
                  const team = teams.find((item) => item.id === id);
                  const teamKind = team && PROJECT_KINDS.includes(team.name) ? team.name : kind;
                  return {
                    title: picked.length > 1 ? `${title} — ${team?.name || ""}` : title,
                    kind: teamKind,
                    description,
                    team_id: id,
                  };
                })
              : [{ title, kind, description, team_id: teamId || null }];
            onCreate(bodies);
            setTitle("");
            setDescription("");
            setPicked([]);
            onCancel();
          }}
        >
          <Bi
            en={picked.length > 1 ? `Create ${picked.length} projects` : "Create project"}
            fa={picked.length > 1 ? `ساخت ${picked.length.toLocaleString("fa-IR")} پروژه` : "ساخت پروژه"}
          />
        </Button>
        <Button type="button" className="btn-sm" onClick={onCancel}>
          <Bi en="Cancel" fa="بی‌خیال" />
        </Button>
      </div>
    </div>
  );
}