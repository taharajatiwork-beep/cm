import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Badge,
  Button,
  Checkbox,
  Dialog,
  Field,
  Input,
  Muted,
  SectionHeader,
  Select,
  TextArea,
} from "../components/ui";
import { DELETE_CONFIRM_LABEL, useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { Bi } from "../i18n";
import { DEFAULT_PROJECT_KIND } from "../lib/focus";
import { requestsApi, type TeamOption, type WorkProject, type WorkRequest } from "./api";
import { REQUEST_STATUS_LABEL } from "./labels";

const STATUS_LABEL = REQUEST_STATUS_LABEL;
const PROJECT_KINDS = ["پرفورمنس", "تولید محتوا", "فیلم‌برداری", "طراحی", "عمومی"];

const PROJECT_STATUS_LABEL: Record<string, string> = {
  new: "تازه",
  in_progress: "در جریان",
  done: "تمام",
};

export function RequestTriagePanel({ row, projects }: { row: WorkRequest; projects: WorkProject[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const teams = useQuery({ queryKey: ["org", "teams"], queryFn: requestsApi.teams });
  const [convertOpen, setConvertOpen] = useState(false);
  const [patchFeedback, setPatchFeedback] = useState<{ ok: boolean; message: string } | null>(null);

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => requestsApi.patch(row.id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["request", row.id] });
      void qc.invalidateQueries({ queryKey: ["requests", "work-requests"] });
      setPatchFeedback({ ok: true, message: "ذخیره شد" });
    },
    onError: (error: Error) => setPatchFeedback({ ok: false, message: error.message }),
  });
  const remove = useMutation({
    mutationFn: () => requestsApi.remove(row.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["requests"] });
      toast("درخواست حذف شد");
      window.location.href = "/requests";
    },
    onError: (error: Error) => toast(error.message),
  });
  const convertTask = useMutation({
    mutationFn: () => requestsApi.convertTask(row.id, row.title),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["requests"] });
      toast("کار ساخته شد و درخواست تبدیل شد");
      setConvertOpen(false);
    },
    onError: (error: Error) => toast(error.message),
  });
  const createProject = useMutation({
    mutationFn: async (bodies: Array<Record<string, unknown>>) => {
      const created = [];
      for (const body of bodies) created.push(await requestsApi.createProject(row.id, body));
      return created;
    },
    onSuccess: (created) => {
      void qc.invalidateQueries({ queryKey: ["request", row.id] });
      void qc.invalidateQueries({ queryKey: ["requests"] });
      toast(
        created.length > 1
          ? `${created.length.toLocaleString("fa-IR")} پروژه ساخته شد`
          : "پروژه ساخته شد",
      );
      setConvertOpen(false);
    },
    onError: (error: Error) => toast(error.message),
  });

  const teamList = teams.data ?? [];
  const busy = patch.isPending || convertTask.isPending || createProject.isPending;

  return (
    <div className="record-actions">
      <Button type="button" className="btn-sm" onClick={() => setConvertOpen(true)}>
        <Bi en="Convert" fa="تبدیل" />
      </Button>
      <Button
        type="button"
        variant="danger-quiet"
        className="btn-sm"
        onClick={() => {
          void confirm("حذف درخواست", `درخواست «${row.title}» حذف شود؟`, DELETE_CONFIRM_LABEL, { danger: true }).then((ok) => {
            if (ok) remove.mutate();
          });
        }}
      >
        <Bi en="Delete" fa="حذف" />
      </Button>
      {convertOpen ? (
        <RequestConvertDialog
          row={row}
          teams={teamList}
          projects={projects}
          busy={busy}
          patchBusy={patch.isPending}
          patchFeedback={patchFeedback}
          onClose={() => setConvertOpen(false)}
          onPatch={(body) => patch.mutate(body)}
          onConvertTask={() => convertTask.mutate()}
          onCreateProject={(bodies) => createProject.mutateAsync(bodies)}
        />
      ) : null}
    </div>
  );
}

function RequestConvertDialog({
  row,
  teams,
  projects,
  busy,
  patchBusy,
  patchFeedback,
  onClose,
  onPatch,
  onConvertTask,
  onCreateProject,
}: {
  row: WorkRequest;
  teams: TeamOption[];
  projects: WorkProject[];
  busy?: boolean;
  patchBusy?: boolean;
  patchFeedback?: { ok: boolean; message: string } | null;
  onClose: () => void;
  onPatch: (body: Record<string, unknown>) => void;
  onConvertTask: () => void;
  onCreateProject: (bodies: Array<Record<string, unknown>>) => Promise<unknown>;
}) {
  const titleId = useId();
  const [mode, setMode] = useState<"review" | "project">("review");

  return (
    <Dialog onClose={onClose} className="detail-pop" labelledBy={titleId} closeLabel="بستن" busy={busy}>
      <SectionHeader
        title={<span id={titleId}><Bi en="Request triage" fa="رسیدگی درخواست" /></span>}
        hint={<Bi en="Set status and team, then turn into projects or a single task." fa="وضعیت و تیم را تنظیم کنید؛ بعد به پروژه یا کار تبدیل کنید." />}
      />
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
        {projects.length > 0 ? (
          <ul className="record-subs">
            {projects.map((project) => (
              <li key={project.id}>
                <Link className="record-sub" to={`/projects/${project.id}`}>
                  <strong>{project.title}</strong>
                  <Badge tone={project.status === "done" ? "ok" : "warn"}>
                    {PROJECT_STATUS_LABEL[project.status] || project.status}
                  </Badge>
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
        <div className="row">
          <Button type="button" variant={mode === "review" ? "primary" : "secondary"} className="btn-sm" onClick={() => setMode("review")}>
            <Bi en="Quick actions" fa="اقدام سریع" />
          </Button>
          <Button type="button" variant={mode === "project" ? "primary" : "secondary"} className="btn-sm" onClick={() => setMode("project")}>
            <Bi en="New project" fa="پروژهٔ جدید" />
          </Button>
        </div>
        {mode === "review" ? (
          <div className="record-actions">
            <Button type="button" className="btn-sm" variant="secondary" disabled={busy} onClick={onConvertTask}>
              <Bi en="Turn into work" fa="تبدیل مستقیم به کار" />
            </Button>
          </div>
        ) : (
          <ProjectFromRequest
            teams={teams}
            defaultTeamId={row.team_id || ""}
            busy={busy}
            onCancel={onClose}
            onCreate={onCreateProject}
          />
        )}
      </div>
    </Dialog>
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
