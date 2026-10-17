import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import "../perf/perf.css";
import { Button, Card, Dialog, EmptyState, Field, Input, Muted, PageHeader, SectionHeader, Select } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { Bi, useBi } from "../i18n";
import { useAuth } from "../auth";
import { canSeeProjects } from "../lib/access";
import { requestsApi } from "./api";
import { MizitoKanban } from "./projects/MizitoKanban";
import { ProjectQuickSheet } from "./projects/ProjectQuickSheet";
import { ProjectsTable } from "./projects/ProjectsTable";
import { ProjectsToolbar } from "./projects/ProjectsToolbar";
import { LIST_PAGE_SIZE } from "./projects/constants";
import { useProjectsUrlState } from "./projects/useProjectsUrlState";

export { PROJECT_STATUS_LABEL } from "./projects/constants";

export function ProjectsPage() {
  const { has, user } = useAuth();
  const accessUser = {
    roleCode: user?.roleCode,
    permissions: user?.permissions ?? [],
    teamId: user?.team_id,
    teamHomeTeamId: user?.team_home_team_id,
  };
  const allowed = canSeeProjects(accessUser, has);
  const { state: url, patch, openProject, closeProject } = useProjectsUrlState();
  const qc = useQueryClient();
  const toast = useToast();
  const triage = has("request.triage") || has("request.manage") || has("org.admin");
  const requester = has("request.create") && !triage;
  const [reviewing, setReviewing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [requestId, setRequestId] = useState("");
  const [laneChoice, setLaneChoice] = useState("");

  const requesterBoot = useRef(false);
  useEffect(() => {
    if (!requester || requesterBoot.current) return;
    requesterBoot.current = true;
    const next: Partial<typeof url> = {};
    if (url.view !== "list") next.view = "list";
    if (url.lane) next.lane = "";
    if (url.source === "mizito") next.source = "";
    if (Object.keys(next).length) patch(next);
  }, [requester, patch, url.lane, url.source, url.view]);

  const lanes = useQuery({
    queryKey: ["requests", "mizito-lanes", "counts"],
    queryFn: () => requestsApi.mizitoLanes(true),
    enabled: allowed && !requester,
  });

  const syncStatus = useQuery({
    queryKey: ["requests", "mizito-sync"],
    queryFn: () => requestsApi.mizitoSyncStatus(),
    enabled: allowed,
  });
  const changes = useQuery({
    queryKey: ["requests", "mizito-changes", "pending"],
    queryFn: () => requestsApi.mizitoChanges("pending"),
    enabled: allowed && reviewing,
  });
  const listPage = useQuery({
    queryKey: [
      "requests",
      "projects-page",
      url.q,
      url.lane,
      url.source,
      url.status,
      url.sort,
      url.order,
      url.page,
    ],
    queryFn: () =>
      requestsApi.projectsPage({
        q: url.q,
        mizito_lane: url.lane,
        source: url.source,
        status: url.status,
        sort: url.sort,
        order: url.order,
        limit: LIST_PAGE_SIZE,
        offset: (url.page - 1) * LIST_PAGE_SIZE,
      }),
    enabled: allowed && url.view === "list",
  });
  const requests = useQuery({
    queryKey: ["requests", "work-requests", "picker"],
    queryFn: () => requestsApi.list(),
    enabled: allowed && triage,
  });

  const create = useMutation({
    mutationFn: () =>
      requestsApi.createStandaloneProject(
        { title: title.trim(), kind: "عمومی", status: "new", mizito_lane: laneChoice || null },
        requestId,
      ),
    onSuccess: () => {
      setTitle("");
      setRequestId("");
      setCreating(false);
      void qc.invalidateQueries({ queryKey: ["requests"] });
      toast("پروژه ساخته شد");
    },
    onError: (error: Error) => toast(error.message),
  });
  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) => requestsApi.decideMizitoChange(id, approve),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["requests", "mizito-changes"] });
      void qc.invalidateQueries({ queryKey: ["requests", "mizito-sync"] });
      void qc.invalidateQueries({ queryKey: ["requests", "mizito-kanban"] });
      toast("ثبت شد");
    },
    onError: (error: Error) => toast(error.message),
  });
  const syncNow = useMutation({
    mutationFn: () => requestsApi.syncMizitoWork(false),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["requests"] });
      toast("همگام‌سازی انجام شد");
    },
    onError: (error: Error) => toast(error.message),
  });
  const bi = useBi();
  const createTitleId = useId();
  const cmBoard = url.view === "board" && url.source === "cm";

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
        title={requester ? <Bi en="Projects from my requests" fa="پروژه‌های درخواست‌های من" /> : <Bi en="Projects" fa="پروژه‌ها" />}
        actions={
          triage ? (
            <Button type="button" onClick={() => setCreating(true)}>
              <Bi en="New project" fa="پروژهٔ تازه" />
            </Button>
          ) : null
        }
      />
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
            <Field label={<Bi en="Mizito lane" fa="دسته (اختیاری)" />}>
              <Select value={laneChoice} onChange={(event) => setLaneChoice(event.target.value)}>
                <option value="">بدون دسته</option>
                {(lanes.data ?? []).map((lane) => (
                  <option key={lane.slug} value={lane.slug}>{lane.title}</option>
                ))}
              </Select>
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
      <Card className="projects-page">
        <ProjectsToolbar
          url={url}
          onPatch={patch}
          lanes={lanes.data ?? []}
          triage={triage}
          requester={requester}
          syncPending={syncStatus.data?.pending_count}
          syncFinishedAt={syncStatus.data?.last_run?.finished_at}
          syncOk={syncStatus.data?.last_run?.ok}
          syncError={syncStatus.data?.last_run?.error}
          onSyncNow={triage ? () => syncNow.mutate() : undefined}
          onReviewChanges={() => setReviewing(true)}
        />
        {url.view === "board" ? (
          <MizitoKanban
            url={url}
            onOpenCard={openProject}
            cmMode={cmBoard}
            laneCount={lanes.data?.find((lane) => lane.slug === url.lane)?.project_count}
            onShowArchive={() => patch({ archive: true })}
            onShowList={() => patch({ view: "list" })}
          />
        ) : (
          <div className="projects-list">
            <ProjectsTable
              url={url}
              onPatch={patch}
              rows={listPage.data?.items ?? []}
              total={listPage.data?.total ?? 0}
              isLoading={listPage.isLoading}
              error={listPage.error as Error | null}
              onRowOpen={openProject}
              requester={requester}
            />
          </div>
        )}
      </Card>
      <ProjectQuickSheet
        projectId={url.project}
        open={Boolean(url.project)}
        onClose={closeProject}
        cardUrlPrefix={syncStatus.data?.card_url_prefix}
      />
      {reviewing ? (
        <Dialog onClose={() => setReviewing(false)} labelledBy="mizito-review" closeLabel={bi("Close", "بستن")}>
          <SectionHeader title={<span id="mizito-review">تغییرهای منتظر تأیید</span>} />
          {(changes.data ?? []).length === 0 ? <Muted>موردی نیست.</Muted> : null}
          {(changes.data ?? []).map((change) => (
            <div key={change.id} className="meta-row">
              <span>{change.kind} — {change.field}: {change.old_value}</span>
              <Button type="button" onClick={() => decide.mutate({ id: change.id, approve: true })}>آرشیو در CM</Button>
              <Button type="button" variant="secondary" onClick={() => decide.mutate({ id: change.id, approve: false })}>نادیده بگیر</Button>
            </div>
          ))}
        </Dialog>
      ) : null}
    </>
  );
}
