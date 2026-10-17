import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import "../perf/perf.css"; // conn-tile / perf-actions استایل‌های مشترک
import { Badge, Button, Card, Checkbox, Dialog, Disclosure, EmptyState, Field, Input, Muted, PageHeader, QueryState, SectionHeader, Select, TextArea } from "../components/ui";
import { DELETE_CONFIRM_LABEL, useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { DateText } from "../components/DateText";
import { JalaliDateInput } from "../components/JalaliDateInput";
import { Bi, useBi } from "../i18n";
import { useAuth } from "../auth";
import { caughtUpTarget, DEFAULT_PROJECT_KIND, DEFAULT_REQUEST_KIND, DEFAULT_REQUEST_PRIORITY, suggestTeamId } from "../lib/focus";
import { requestsApi, type TeamOption, type WorkProject, type WorkRequest } from "./api";
import { REQUEST_STATUS_LABEL } from "./labels";
import { WorkChainLegend, WorkListKindBadge } from "../lib/workContext";

const STATUS_LABEL = REQUEST_STATUS_LABEL;

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
  const { has, user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const triage = has("request.triage") || has("request.manage") || has("org.admin");
  const canReviewDelivery = has("request.create") && !triage;
  const [statusFilter, setStatusFilter] = useState("");
  const [reviewFilter, setReviewFilter] = useState(false);
  const [creating, setCreating] = useState(false);
  const requests = useQuery({
    queryKey: ["requests", "work-requests", statusFilter],
    queryFn: () => requestsApi.list(statusFilter),
  });
  const teams = useQuery({ queryKey: ["org", "teams"], queryFn: requestsApi.teams });
  const projects = useQuery({ queryKey: ["requests", "work-projects"], queryFn: () => requestsApi.projects() });

  const [patchFeedback, setPatchFeedback] = useState<{ id: string; ok: boolean; message: string } | null>(null);
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => requestsApi.patch(id, body),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["requests", "work-requests"] });
      setPatchFeedback({ id: vars.id, ok: true, message: "ذخیره شد" });
    },
    onError: (error: Error, vars) => {
      setPatchFeedback({ id: vars.id, ok: false, message: error.message });
    },
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
      toast("کار ساخته شد و درخواست تبدیل شد");
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
        title={<Bi en="Work requests" fa="درخواست‌های کار" />}
        description={
          <Bi
            en="Ask the team for work; projects and tasks come next."
            fa="از تیم کار می‌خواهید؛ بعد پروژه و کار ساخته می‌شود."
          />
        }
        actions={
          has("request.create") && !creating ? (
            <Button type="button" onClick={() => setCreating(true)}>
              <Bi en="New work request" fa="درخواست کار جدید" />
            </Button>
          ) : null
        }
      />
      {creating && has("request.create") ? (
        <CreateRequestCard
          teams={teams.data ?? []}
          userTeamId={user?.team_id}
          onDone={() => setCreating(false)}
        />
      ) : null}
      <RequestsReportCard requests={requests.data ?? []} projects={projects.data ?? []} triage={triage} />
      <Card>
        <SectionHeader
          icon="clock"
          title={triage ? <Bi en="Request queue" fa="صف درخواست‌ها" /> : <Bi en="My requests" fa="درخواست‌های من" />}
          count={requests.data?.length}
          action={
            <div className="row">
              {canReviewDelivery ? (
                <Button
                  type="button"
                  variant={reviewFilter ? "primary" : "secondary"}
                  className="btn-sm"
                  onClick={() => setReviewFilter((v) => !v)}
                >
                  <Bi en="My reviews" fa="بررسی‌های من" />
                </Button>
              ) : null}
              {triage ? (
                <Select aria-label="وضعیت" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="">همهٔ وضعیت‌ها</option>
                  {Object.entries(STATUS_LABEL).map(([key, label]) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </Select>
              ) : null}
            </div>
          }
        />
        <WorkChainLegend variant="requests" />
        <QueryState
          isLoading={requests.isLoading}
          error={requests.error}
          isEmpty={requests.data?.length === 0}
          empty={
            statusFilter ? (
              <EmptyState
                titleEn="Nothing matches this filter"
                titleFa="این فیلتر نتیجه‌ای ندارد"
                bodyEn="The queue may still have requests under another status."
                bodyFa="صف ممکن است زیر وضعیت دیگری درخواست داشته باشد."
                action={
                  <Button type="button" variant="secondary" onClick={() => setStatusFilter("")}>
                    <Bi en="Clear filter" fa="پاک کردن فیلتر" />
                  </Button>
                }
              />
            ) : (
              <EmptyState
                titleEn="No requests yet"
                titleFa="هنوز درخواستی نیست"
                bodyEn="A request is the starting point. The team turns it into a project."
                bodyFa="درخواست نقطهٔ شروع است. تیم آن را به پروژه تبدیل می‌کند. از دکمهٔ بالای صفحه درخواست جدید بسازید."
                action={
                  <Button to={caughtUpTarget({ roleCode: user?.roleCode, permissions: user?.permissions ?? [] })}>
                    <Bi en="Next step" fa="قدم بعد" />
                  </Button>
                }
              />
            )
          }
        >
          {requests.data && requests.data.length > 0 ? (
          <div className="conn-grid">
            {requests.data
              .filter((row) => {
                if (!reviewFilter) return true;
                const child = (projects.data ?? []).filter((project) => project.request_id === row.id);
                return child.some((project) => project.status === "done" && !project.requester_acceptance);
              })
              .map((row) => (
              <RequestCard
                key={row.id}
                row={row}
                teams={teams.data ?? []}
                projects={(projects.data ?? []).filter((project) => project.request_id === row.id)}
                triage={triage}
                patchBusy={patch.isPending && patch.variables?.id === row.id}
                patchFeedback={patchFeedback?.id === row.id ? patchFeedback : null}
                convertBusy={convertTask.isPending && convertTask.variables?.requestId === row.id}
                convertError={convertTask.isError && convertTask.variables?.requestId === row.id ? String((convertTask.error as Error).message) : ""}
                createBusy={createProject.isPending && createProject.variables?.requestId === row.id}
                onPatch={(body) => patch.mutate({ id: row.id, body })}
                onDelete={() => {
                  void confirm("حذف درخواست", `درخواست «${row.title}» حذف شود؟`, DELETE_CONFIRM_LABEL, { danger: true }).then((ok) => {
                    if (ok) remove.mutate(row.id);
                  });
                }}
                onCreateProject={(bodies) => createProject.mutateAsync({ requestId: row.id, bodies })}
                onConvertTask={() => convertTask.mutate({ requestId: row.id, title: row.title })}
              />
            ))}
          </div>
          ) : null}
        </QueryState>
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

function CreateRequestCard({
  teams,
  userTeamId,
  onDone,
}: {
  teams: TeamOption[];
  userTeamId?: string | null;
  onDone: () => void;
}) {
  const bi = useBi();
  const titleId = useId();
  const qc = useQueryClient();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState(DEFAULT_REQUEST_KIND);
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState(DEFAULT_REQUEST_PRIORITY);
  const [due, setDue] = useState("");
  const [teamChoice, setTeamChoice] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const teamId = teamChoice ?? suggestTeamId(teams, userTeamId);
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
      .then((created) => {
        toast(`درخواست ثبت شد (${created.code}). از فهرست «دیدن درخواست» را بزنید.`);
        setTitle("");
        setDescription("");
        setDue("");
        setTeamChoice(undefined);
        void qc.invalidateQueries({ queryKey: ["requests", "work-requests"] });
        onDone();
      })
      .catch((error: Error) => toast(error.message))
      .finally(() => setBusy(false));
  }
  return (
    <Dialog onClose={onDone} className="form-pop" labelledBy={titleId} closeLabel={bi("Close", "بستن")} busy={busy}>
      <SectionHeader
        icon="send"
        title={<span id={titleId}><Bi en="New request" fa="ایجاد درخواست" /></span>}
        hint={<Bi en="Title, what you need, and when — team can take it from there." fa="عنوان، خروجی مورد انتظار و زمان — تیم از همین‌جا ادامه می‌دهد." />}
      />
      <div className="form-grid">
        <Field className="span-2" label={<Bi en="Title" fa="عنوان" />}>
          <Input value={title} placeholder="مثلاً کمپین فروش بهمن" onChange={(event) => setTitle(event.target.value)} />
        </Field>
        <Field label={<Bi en="Team" fa="تیم" />}>
          <Select value={teamId} onChange={(event) => setTeamChoice(event.target.value)}>
            <option value="">— بعداً تعیین می‌شود —</option>
            {teams.filter((team) => !team.parent_team_id).map((team) => (
              <option key={team.id} value={team.id}>{team.name}</option>
            ))}
          </Select>
        </Field>
        <Field className="span-all" label={<Bi en="Description / expected output" fa="توضیح / خروجی مورد انتظار" />}>
          <TextArea value={description} rows={3} placeholder="جزئیات، بودجه، خروجی…" onChange={(event) => setDescription(event.target.value)} />
        </Field>
        <Field label={<Bi en="Needed by" fa="تاریخ لازم" />}>
          <JalaliDateInput value={due} onChange={setDue} />
        </Field>
        <div className="span-all">
          <Disclosure
            label={
              <>
                <Bi en="More details" fa="جزئیات بیشتر" />
                <Muted>
                  {" "}
                  <Bi en={`Kind ${kind} · priority ${PRIORITY_LABEL[priority] || priority}`} fa={`نوع ${kind} · اولویت ${PRIORITY_LABEL[priority] || priority}`} />
                </Muted>
              </>
            }
          >
              <div className="form-grid">
                <Field label={<Bi en="Kind" fa="نوع" />}>
                  <Select value={kind} onChange={(event) => setKind(event.target.value)}>
                    {REQUEST_KINDS.map((item) => (
                      <option key={item} value={item}>{item}</option>
                    ))}
                  </Select>
                </Field>
                <Field label={<Bi en="Priority" fa="اولویت" />}>
                  <Select value={priority} onChange={(event) => setPriority(event.target.value)}>
                    <option value="low">کم</option>
                    <option value="normal">معمولی</option>
                    <option value="high">بالا</option>
                  </Select>
                </Field>
              </div>
          </Disclosure>
        </div>
        <div className="span-all perf-actions">
          <Button type="button" disabled={!title.trim() || busy} onClick={submit}>
            {busy ? <Bi en="Saving" fa="در حال ثبت…" /> : <Bi en="File request" fa="ثبت درخواست" />}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function RequestCard({
  row,
  teams,
  projects,
  triage,
  patchBusy,
  patchFeedback,
  convertBusy,
  convertError,
  createBusy,
  onPatch,
  onDelete,
  onCreateProject,
  onConvertTask,
}: {
  row: WorkRequest;
  teams: TeamOption[];
  projects: WorkProject[];
  triage: boolean;
  patchBusy?: boolean;
  patchFeedback?: { ok: boolean; message: string } | null;
  convertBusy?: boolean;
  convertError?: string;
  createBusy?: boolean;
  onPatch: (body: Record<string, unknown>) => void;
  onDelete: () => void;
  onCreateProject: (bodies: Array<Record<string, unknown>>) => Promise<unknown>;
  onConvertTask: () => void;
}) {
  const [adding, setAdding] = useState(false);
  return (
    <Card as="article" className="record-card" stack>
      <div className="record-head">
        <div>
          <div className="record-code record-code--subtle" dir="ltr">{row.code}</div>
          <h3 className="record-title">
            <Link to={`/requests/${row.id}`}>{row.title}</Link>
          </h3>
        </div>
        <Badge tone={STATUS_TONE[row.status] || "warn"}>{STATUS_LABEL[row.status] || row.status}</Badge>
      </div>
      {row.description ? <p className="record-body">{row.description}</p> : null}
      <div className="record-actions">
        <Button className="btn-sm" to={`/requests/${row.id}`}>
          <Bi en="Open request" fa="دیدن درخواست" />
        </Button>
      </div>
      <div className="meta-row">
        <WorkListKindBadge kind="request" />
        <span className="meta-chip">{row.kind}</span>
        <span className="meta-chip">اولویت {PRIORITY_LABEL[row.priority] || row.priority}</span>
        {row.requester_name ? <span className="meta-chip">{row.requester_name}</span> : null}
        {row.team_name ? (
          <span className="meta-chip">
            {triage && row.team_id ? <Link to={`/teams/${row.team_id}`}>{row.team_name}</Link> : row.team_name}
          </span>
        ) : null}
        {row.due_date ? <span className="meta-chip">لازم تا <DateText value={row.due_date} /></span> : null}
        <span className="meta-chip"><DateText value={row.created_at} withTime /></span>
      </div>
      {projects.length > 0 ? (
        <div>
          <Muted as="p">
            <Bi
              en="Child projects (team work packages under this request)"
              fa="پروژه‌های زیرمجموعه (بستهٔ کار تیم برای این درخواست)"
            />{" "}
            ({projects.length.toLocaleString("fa-IR")})
          </Muted>
          <ul className="record-subs">
            {projects.map((project) => (
              <li key={project.id}>
                <Link className="record-sub" to={`/projects/${project.id}`}>
                  <strong>{project.title}</strong>
                  {project.code ? <span className="record-code mono muted" dir="ltr">{project.code}</span> : null}
                  <Badge tone={project.status === "done" ? "ok" : "warn"}>{PROJECT_STATUS_LABEL[project.status] || project.status}</Badge>
                </Link>
                <span className="row-meta work-parent-context">
                  <WorkListKindBadge kind="project" />
                  <span className="meta-chip">{project.kind}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {triage || row.status === "new" ? (
        <Disclosure label={<Bi en="Review" fa="رسیدگی" />}>
          {triage ? (
            <div className="stack">
              <Field label={<Bi en="Status" fa="وضعیت" />}>
                <Select disabled={patchBusy} value={row.status} onChange={(event) => onPatch({ status: event.target.value })}>
                  {Object.entries(STATUS_LABEL).map(([key, label]) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </Select>
              </Field>
              <Field label={<Bi en="Team" fa="تیم" />}>
                <Select disabled={patchBusy} value={row.team_id || ""} onChange={(event) => onPatch({ team_id: event.target.value || null })}>
                  <option value="">—</option>
                  {teams.filter((team) => !team.parent_team_id).map((team) => (
                    <option key={team.id} value={team.id}>{team.name}</option>
                  ))}
                </Select>
              </Field>
              {patchFeedback ? (
                <Muted className={patchFeedback.ok ? undefined : "danger-text"}>{patchFeedback.message}</Muted>
              ) : null}
            </div>
          ) : null}
          {triage ? (
            adding ? (
              <ProjectFromRequest
                teams={teams}
                defaultTeamId={row.team_id || ""}
                busy={createBusy}
                onCancel={() => setAdding(false)}
                onCreate={onCreateProject}
              />
            ) : (
              <div className="record-actions">
                <Button type="button" className="btn-sm" onClick={() => setAdding(true)}>
                  <Bi
                    en={projects.length ? "Add another project" : "Turn into projects"}
                    fa={projects.length ? "پروژهٔ دیگر" : "تبدیل به پروژه"}
                  />
                </Button>
                <Button type="button" className="btn-sm" variant="secondary" disabled={convertBusy} onClick={onConvertTask}>
                  {convertBusy ? <Bi en="Working…" fa="در حال ساخت…" /> : <Bi en="Turn into work" fa="تبدیل مستقیم به کار" />}
                </Button>
                {convertError ? <Muted className="danger-text">{convertError}</Muted> : null}
                <Button type="button" variant="danger-quiet" className="btn-sm" onClick={onDelete}>
                  <Bi en="Delete" fa="حذف" />
                </Button>
              </div>
            )
          ) : (
            <div className="record-actions">
              <Button type="button" variant="danger-quiet" className="btn-sm" onClick={onDelete}>
                <Bi en="Delete" fa="حذف" />
              </Button>
            </div>
          )}
        </Disclosure>
      ) : null}
    </Card>
  );
}

function ProjectFromRequest({
  teams,
  defaultTeamId,
  busy,
  onCancel,
  onCreate,
}: {
  teams: TeamOption[];
  defaultTeamId: string;
  busy?: boolean;
  onCancel: () => void;
  onCreate: (bodies: Array<Record<string, unknown>>) => Promise<unknown>;
}) {
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState(DEFAULT_PROJECT_KIND);
  const [teamId, setTeamId] = useState(defaultTeamId);
  const [picked, setPicked] = useState<string[]>([]);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const parentTeam = teams.find((team) => team.id === defaultTeamId);
  const childTeams = teams.filter((team) => team.parent_team_id === defaultTeamId);
  const otherTeams = teams.filter((team) => !team.parent_team_id && team.id !== defaultTeamId);
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
          <div className="choice-grid">
            {childTeams.map((team) => (
              <Checkbox
                key={team.id}
                label={team.name}
                checked={picked.includes(team.id)}
                onChange={() => setPicked((cur) => (cur.includes(team.id) ? cur.filter((id) => id !== team.id) : [...cur, team.id]))}
              />
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
      {formError ? <Muted className="danger-text span-all">{formError}</Muted> : null}
      <div className="span-all row perf-actions">
        <Button
          type="button"
          className="btn-sm"
          disabled={!title.trim() || submitting || busy}
          onClick={() => {
            const bodies = picked.length
              ? picked.map((id) => {
                  const team = teams.find((item) => item.id === id);
                  const teamKind = team && PROJECT_KINDS.includes(team.name) ? team.name : kind;
                  return {
                    title,
                    kind: teamKind,
                    description,
                    team_id: id,
                  };
                })
              : [{ title, kind, description, team_id: teamId || null }];
            setSubmitting(true);
            setFormError("");
            void onCreate(bodies)
              .then(() => {
                setTitle("");
                setDescription("");
                setPicked([]);
                onCancel();
              })
              .catch((error: Error) => setFormError(error.message))
              .finally(() => setSubmitting(false));
          }}
        >
          {submitting || busy ? (
            <Bi en="Creating…" fa="در حال ساخت…" />
          ) : (
            <Bi
              en={picked.length > 1 ? `Create ${picked.length} projects` : "Create project"}
              fa={picked.length > 1 ? `ساخت ${picked.length.toLocaleString("fa-IR")} پروژه` : "ساخت پروژه"}
            />
          )}
        </Button>
        <Button type="button" className="btn-sm" disabled={submitting} onClick={onCancel}>
          <Bi en="Cancel" fa="بی‌خیال" />
        </Button>
      </div>
    </div>
  );
}