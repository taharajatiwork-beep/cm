import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { DateText } from "../components/DateText";
import { Button, Card, Checkbox, Disclosure, EmptyState, ErrorMessage, Field, Icon, Input, LoadingState, Muted, PageHeader, SectionHeader, Segmented, Select, StatCard } from "../components/ui";
import { Donut, HBars } from "../components/charts";
import { faNum, tomanText } from "../fa";
import { useAuth } from "../auth";
import { Bi, useBi } from "../i18n";
import { canFinishTask } from "../lib/collaboration";
import { PROJECT_TABS, type ProjectTab } from "../lib/focus";
import { StatusLabel } from "../ux";
import { requestsApi } from "./api";
import { DeliveryReviewCard } from "./DeliveryReview";
import { PROJECT_STATUS_LABEL } from "./ProjectsPage";

function activeTaskStats(tasks: Array<{ status: string }>) {
  const active = tasks.filter((task) => task.status !== "CANCELLED");
  const done = active.filter((task) => task.status === "COMPLETED").length;
  return { active, done, total: active.length };
}

function spineStatusLabel(kind: string, status: string) {
  if (kind === "task") return status;
  if (kind === "work_project" || kind === "project") return PROJECT_STATUS_LABEL[status] || status;
  return status;
}

const TAB_LABEL: Record<ProjectTab, [string, string]> = {
  overview: ["Overview", "نمای کلی"],
  tasks: ["Work", "کارها"],
  resources: ["Resources", "منابع"],
};

const DESIGN_STATUS: Record<string, string> = {
  draft: "پیش‌نویس",
  in_review: "در بررسی",
  approved: "تأیید شده",
  changes_requested: "نیاز به اصلاح",
};

const SHOOT_STATUS: Record<string, string> = {
  planned: "برنامه‌ریزی",
  shot: "فیلم‌برداری شد",
  delivered: "تحویل شد",
};

export function ProjectPage() {
  const { id = "" } = useParams();
  const { has, user } = useAuth();
  const bi = useBi();
  const qc = useQueryClient();
  const [tab, setTab] = useState<ProjectTab>("tasks");
  const [title, setTitle] = useState("");
  const [assignees, setAssignees] = useState<string[]>([]);
  const [linkTitle, setLinkTitle] = useState("");
  const [linkUrl, setLinkUrl] = useState("");
  const [designTitle, setDesignTitle] = useState("");
  const [shootTitle, setShootTitle] = useState("");
  const detail = useQuery({
    queryKey: ["project", id],
    queryFn: () => requestsApi.project(id),
    enabled: Boolean(id),
  });
  const canEdit = (has("request.triage") || has("request.manage")) && !detail.data?.readonly;
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["project", id] });
    void qc.invalidateQueries({ queryKey: ["my-work"] });
    void qc.invalidateQueries({ queryKey: ["requests", "my-work"] });
    void qc.invalidateQueries({ queryKey: ["requests", "work-projects"] });
    void qc.invalidateQueries({ queryKey: ["requests", "work-requests"] });
    void qc.invalidateQueries({ queryKey: ["team-home"] });
  };
  const completeTask = useMutation({
    mutationFn: (taskId: string) => api.tasks.complete(taskId),
    onSuccess: refresh,
  });
  const addTask = useMutation({
    mutationFn: () => requestsApi.addTask(id, title, assignees),
    onSuccess: () => {
      setTitle("");
      refresh();
    },
  });
  const apply = useMutation({ mutationFn: () => requestsApi.applyTemplate(id), onSuccess: refresh });
  const addLink = useMutation({
    mutationFn: () => requestsApi.addAttachment(id, { title: linkTitle.trim(), url: linkUrl.trim() }),
    onSuccess: () => {
      setLinkTitle("");
      setLinkUrl("");
      refresh();
    },
  });
  const addDesign = useMutation({
    mutationFn: () => requestsApi.addDesign(id, designTitle.trim() || "طرح"),
    onSuccess: () => {
      setDesignTitle("");
      refresh();
    },
  });
  const addShoot = useMutation({
    mutationFn: () => requestsApi.addShoot(id, shootTitle.trim() || "فیلم"),
    onSuccess: () => {
      setShootTitle("");
      refresh();
    },
  });

  if (detail.isLoading) return <LoadingState />;
  if (detail.error) return <ErrorMessage error={detail.error instanceof Error ? detail.error.message : String(detail.error)} />;
  const row = detail.data ?? {};
  const tasks = (row.tasks as Array<{ id: string; title: string; status: string; owner_id?: string; assignee_ids?: string[] }> | undefined) ?? [];
  const attachments = (row.attachments as Array<Record<string, string>> | undefined) ?? [];
  const designs = (row.designs as Array<Record<string, string>> | undefined) ?? [];
  const shoots = (row.shoots as Array<Record<string, string>> | undefined) ?? [];
  const members = (row.members as Array<{ id: string; full_name: string }> | undefined) ?? [];
  const memberChoices = (row.member_choices as Array<{ id: string; full_name: string }> | undefined) ?? [];
  const campaigns = (row.campaigns as Array<{ id: string; code: string; title: string }> | undefined) ?? [];
  const campaignChoices = (row.campaign_choices as Array<{ id: string; code: string; title: string; project_id: string | null }> | undefined) ?? [];
  const campaignTags = (row.campaign_tags as Array<{ tag: string; brand: string }> | undefined) ?? [];
  const { done, total: taskTotal } = activeTaskStats(tasks);
  const budget = (row.budget as Record<string, number | boolean> | undefined) ?? {};
  const fresh = tasks.length === 0 && campaigns.length === 0;
  const spine = (row.spine as Array<{ at?: string; kind: string; label: string; status?: string; code?: string }> | undefined) ?? [];

  return (
    <>
      <PageHeader
        title={String(row.title || "")}
        description={`${row.code || ""} · ${row.kind || ""} · ${PROJECT_STATUS_LABEL[String(row.status || "")] || String(row.status || "")}`}
        actions={
          <div className="row">
            {row.request_id ? (
              <Button variant="secondary" to={`/requests/${String(row.request_id)}`}>
                <Bi en="Request" fa="درخواست" />
              </Button>
            ) : null}
            <Button variant="secondary" to={`/reports?project=${id}`}><Bi en="Report" fa="گزارش" /></Button>
          </div>
        }
      />
      {row.readonly && row.blocked ? (
        <p className="banner banner-warn"><Bi en="Blocked: overdue work on this project." fa="مسدود: کار عقب‌افتاده در این پروژه." /></p>
      ) : null}
      {row.readonly && row.status === "done" && !row.requester_acceptance ? (
        <DeliveryReviewCard projectId={id} onSuccess={refresh} />
      ) : null}
      <div className="kpi-row">
        <StatCard icon="layers" tone="accent" label={<Bi en="Stage" fa="مرحله" />} value={PROJECT_STATUS_LABEL[String(row.status || "")] || String(row.status || "—")} />
        {row.readonly && row.lead_name ? (
          <StatCard icon="users" label={<Bi en="Lead team" fa="تیم مجری" />} value={String(row.lead_name)} />
        ) : null}
        <StatCard
          icon="check"
          tone="ok"
          label={<Bi en="Progress" fa="پیشرفت" />}
          value={
            row.planning_pending || taskTotal === 0
              ? bi("Not planned yet", "هنوز برنامه‌ریزی نشده")
              : `${Math.round((done / taskTotal) * 100)}٪`
          }
        />
        <StatCard icon="megaphone" tone="accent" label={<Bi en="Campaigns" fa="کمپین" />} value={campaigns.length} to={campaigns[0] ? `/perf/campaigns/${campaigns[0].id}` : undefined} />
        {!row.readonly ? <StatCard icon="users" tone="ai" label={<Bi en="People" fa="اعضا" />} value={members.length} /> : null}
      </div>
      <div className="section-head">
        <Segmented
          idBase="project"
          ariaLabel={bi("Project sections", "بخش‌های پروژه")}
          value={tab}
          onChange={setTab}
          items={PROJECT_TABS.map((key) => ({
            key,
            label: bi(TAB_LABEL[key][0], TAB_LABEL[key][1]),
          }))}
        />
      </div>
      <div role="tabpanel" id={`project-panel-${tab}`} aria-labelledby={`project-tab-${tab}`}>
      {tab === "overview" ? (
        <Card>
          {fresh ? (
            <EmptyState
              titleEn="This project is ready to start"
              titleFa="این پروژه آمادهٔ شروع است"
              bodyEn="Add the first task. People and campaigns can wait until the work needs them."
              bodyFa="اولین کار را اضافه کنید. اعضا و کمپین می‌توانند تا وقتی لازم نشده‌اند بمانند."
              action={
                <Button type="button" onClick={() => setTab("tasks")}>
                  <Bi en="Add work" fa="افزودن کار" />
                </Button>
              }
            />
          ) : (
            <>
              <p>{String(row.description || "")}</p>
              {taskTotal > 0 ? (
                <Muted as="p">
                  <Bi en={`${done} of ${taskTotal} done`} fa={`${done} از ${taskTotal} کار تمام شده`} />
                </Muted>
              ) : null}
            </>
          )}
          {row.request_id ? (
            <p>
              <Link to={`/requests/${String(row.request_id)}`}>{String(row.request_code || "درخواست")}</Link>
            </p>
          ) : null}
          {fresh ? (
            <Disclosure label={<Bi en="People and campaigns" fa="اعضا و کمپین" />}>
                <PeopleAndCampaigns
                  id={id}
                  canEdit={canEdit}
                  members={members}
                  memberChoices={memberChoices}
                  campaigns={campaigns}
                  campaignChoices={campaignChoices}
                  campaignTags={campaignTags}
                  refresh={refresh}
                />
            </Disclosure>
          ) : (
            <PeopleAndCampaigns
              id={id}
              canEdit={canEdit}
              members={members}
              memberChoices={memberChoices}
              campaigns={campaigns}
              campaignChoices={campaignChoices}
              campaignTags={campaignTags}
              refresh={refresh}
            />
          )}
          {!row.readonly && taskTotal > 0 ? (
            <div className="dash-charts">
              <Card>
                <Donut
                  data={[
                    { label: "تمام", value: done },
                    { label: "مانده", value: Math.max(taskTotal - done, 0) },
                  ]}
                  centerLabel={`${Math.round((done / taskTotal) * 100)}٪`}
                />
              </Card>
              <Card>
                <HBars
                  data={[
                    { label: "کار", value: taskTotal },
                    { label: "کمپین", value: campaigns.length },
                    { label: "عضو", value: members.length },
                  ]}
                />
              </Card>
            </div>
          ) : null}
        </Card>
      ) : null}
      {tab === "tasks" ? (
        <Card className="record-card" stack>
          <SectionHeader title={<Bi en="Work" fa="کارها" />} />
          {tasks.length === 0 ? (
            <EmptyState
              titleEn="No tasks yet"
              titleFa="هنوز کاری نیست"
              bodyEn="Add one, or apply the template to start with the usual steps."
              bodyFa="یکی بسازید، یا قالب را اعمال کنید تا قدم‌های معمول از قبل آماده شود."
              action={
                <Button type="button" variant="secondary" onClick={() => apply.mutate()} disabled={apply.isPending}>
                  <Bi en="Apply template" fa="اعمال قالب" />
                </Button>
              }
            />
          ) : (
            <>
            {completeTask.error ? (
              <ErrorMessage error={completeTask.error instanceof Error ? completeTask.error.message : String(completeTask.error)} />
            ) : null}
            <ul className="record-subs">
              {tasks.map((task) => {
                const finished = task.status === "COMPLETED" || task.status === "CANCELLED";
                return (
                  <li key={task.id} className="record-line">
                    {finished ? (
                      <span className="check-mark check-mark--ok" aria-hidden>✓</span>
                    ) : canFinishTask(task, user?.id) ? (
                      <button
                        type="button"
                        className="done-btn"
                        title={bi("Mark done", "انجام شد")}
                        aria-label={bi("Mark done", "انجام شد")}
                        disabled={completeTask.isPending}
                        onClick={() => completeTask.mutate(task.id)}
                      >
                        <Icon name="check" size={12} />
                      </button>
                    ) : null}
                    <strong>{task.title}</strong>
                    <StatusLabel status={task.status} />
                  </li>
                );
              })}
            </ul>
            </>
          )}
          <Disclosure label={<Bi en="New work item" fa="کار تازه" />}>
            <div className="stack">
              <Field label={<Bi en="Title" fa="عنوان" />}>
                <Input value={title} onChange={(event) => setTitle(event.target.value)} />
              </Field>
              {members.length > 0 ? (
                <Field label={<Bi en="Assignees" fa="با هم انجام می‌دهند" />}>
                  <div className="choice-grid">
                    {members.map((person) => (
                      <Checkbox
                        key={person.id}
                        label={person.full_name}
                        checked={assignees.includes(person.id)}
                        onChange={() => setAssignees((cur) => (cur.includes(person.id) ? cur.filter((item) => item !== person.id) : [...cur, person.id]))}
                      />
                    ))}
                  </div>
                </Field>
              ) : null}
              <div className="record-actions">
                <Button type="button" onClick={() => title.trim() && addTask.mutate()} disabled={addTask.isPending || !title.trim()}>
                  <Bi en="Add" fa="افزودن" />
                </Button>
                {tasks.length > 0 ? (
                  <Button type="button" variant="ghost" onClick={() => apply.mutate()} disabled={apply.isPending}>
                    <Bi en="Apply template" fa="اعمال قالب" />
                  </Button>
                ) : null}
              </div>
            </div>
          </Disclosure>
        </Card>
      ) : null}
      {tab === "resources" ? (
        <div className="report-board">
          <Card className="record-card" stack>
            <SectionHeader title={<Bi en="Links" fa="لینک‌ها" />} />
            {attachments.length === 0 ? (
              <Muted as="p"><Bi en="A link stays on this project." fa="لینک روی همین پروژه می‌ماند." /></Muted>
            ) : (
              <ul className="record-subs">
                {attachments.map((item) => (
                  <li key={item.id}>
                    {item.url ? (
                      <a className="record-sub" href={item.url} target="_blank" rel="noreferrer">
                        <span className="record-code">{item.kind || "لینک"}</span>
                        <strong>{item.title}</strong>
                        <span className="record-code" dir="ltr">↗</span>
                      </a>
                    ) : (
                      <div className="record-line">
                        <strong>{item.title}</strong>
                        <span className="meta-chip">{item.kind || "لینک"}</span>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {canEdit ? (
              <Disclosure label={<Bi en="Add a link" fa="لینک تازه" />}>
                <div className="stack">
                  <Field label={<Bi en="Title" fa="عنوان" />}>
                    <Input value={linkTitle} onChange={(event) => setLinkTitle(event.target.value)} />
                  </Field>
                  <Field label={<Bi en="Address" fa="آدرس" />}>
                    <Input value={linkUrl} dir="ltr" onChange={(event) => setLinkUrl(event.target.value)} placeholder="https://" />
                  </Field>
                  <div className="record-actions">
                    <Button type="button" disabled={!linkTitle.trim() || addLink.isPending} onClick={() => addLink.mutate()}>
                      <Bi en="Save link" fa="ذخیرهٔ لینک" />
                    </Button>
                  </div>
                </div>
              </Disclosure>
            ) : null}
          </Card>
          <Card className="record-card" stack>
            <SectionHeader title={<Bi en="Conversation" fa="گفتگو" />} />
            <Muted as="p"><Bi en="Status changes land in the project thread as system messages." fa="تغییر وضعیت در رشتهٔ پروژه به‌صورت پیام سیستم می‌آید." /></Muted>
            <div className="record-actions">
              <Button to={`/communication?conversation=${row.thread_id || ""}`}>
                <Bi en="Open the thread" fa="باز کردن گفتگو" />
              </Button>
            </div>
          </Card>
          <Card className="record-card" stack>
            <SectionHeader
              title={<Bi en="Costs" fa="هزینه" />}
              action={budget.over ? <span className="meta-chip">بیشتر از برنامه</span> : undefined}
            />
            <div className="kpi-row kpi-row--3">
              <StatCard icon="layers" label={<Bi en="Planned" fa="برنامه‌ای" />} value={tomanText(Number(budget.planned ?? 0))} />
              <StatCard icon="check" tone="warn" label={<Bi en="Committed" fa="متعهد" />} value={tomanText(Number(budget.committed ?? 0))} />
              <StatCard icon="megaphone" tone={budget.over ? "danger" : "ok"} label={<Bi en="Actual" fa="واقعی" />} value={tomanText(Number(budget.actual ?? 0))} />
            </div>
          </Card>
          <Card className="record-card" stack>
            <SectionHeader title={<Bi en="Design and shoot" fa="طرح و فیلم‌برداری" />} />
            {designs.length + shoots.length === 0 ? (
              <Muted as="p"><Bi en="Design drafts and shoot days show up here." fa="پیش‌نویس طرح و نوبت فیلم‌برداری اینجا دیده می‌شود." /></Muted>
            ) : (
              <ul className="record-subs">
                {designs.map((item) => (
                  <li key={item.id} className="record-line">
                    <strong>{item.title}</strong>
                    {canEdit ? (
                      <Select value={item.status} onChange={(event) => requestsApi.patchDesign(id, item.id, event.target.value).then(refresh)}>
                        {Object.entries(DESIGN_STATUS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                      </Select>
                    ) : (
                      <span className="meta-chip">{DESIGN_STATUS[item.status] || item.status}</span>
                    )}
                  </li>
                ))}
                {shoots.map((item) => (
                  <li key={item.id} className="record-line">
                    <strong>{item.title}</strong>
                    {canEdit ? (
                      <Select value={item.status} onChange={(event) => requestsApi.patchShoot(id, item.id, event.target.value).then(refresh)}>
                        {Object.entries(SHOOT_STATUS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                      </Select>
                    ) : (
                      <span className="meta-chip">{SHOOT_STATUS[item.status] || item.status}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {canEdit ? (
              <div className="stack">
                <Disclosure label={<Bi en="Add a design" fa="طرح تازه" />}>
                  <div className="stack">
                    <Field label={<Bi en="Title" fa="عنوان" />}>
                      <Input value={designTitle} onChange={(event) => setDesignTitle(event.target.value)} />
                    </Field>
                    <div className="record-actions">
                      <Button type="button" disabled={addDesign.isPending} onClick={() => addDesign.mutate()}>
                        <Bi en="Add" fa="افزودن" />
                      </Button>
                    </div>
                  </div>
                </Disclosure>
                <Disclosure label={<Bi en="Add a shoot" fa="فیلم تازه" />}>
                  <div className="stack">
                    <Field label={<Bi en="Title" fa="عنوان" />}>
                      <Input value={shootTitle} onChange={(event) => setShootTitle(event.target.value)} />
                    </Field>
                    <div className="record-actions">
                      <Button type="button" disabled={addShoot.isPending} onClick={() => addShoot.mutate()}>
                        <Bi en="Add" fa="افزودن" />
                      </Button>
                    </div>
                  </div>
                </Disclosure>
              </div>
            ) : null}
          </Card>
        </div>
      ) : null}
      </div>
      {spine.length > 0 ? (
        <Card className="stack">
          <Disclosure
            label={
              <SectionHeader
                title={<Bi en="Activity history" fa="تاریخچهٔ فعالیت" />}
                hint={<Bi en="Work request, tasks, payments, perf campaigns" fa="درخواست کار، وظایف، پرداخت، کمپین پرفورمنس" />}
              />
            }
          >
            <ul className="plain-list">
              {spine.slice(-12).map((item, index) => (
                <li key={`${item.kind}-${index}`}>
                  <Muted>{item.at ? <DateText value={item.at} withTime /> : "—"}</Muted>
                  {" · "}
                  {item.code ? `${item.code} — ` : ""}
                  {item.label}
                  {item.status ? ` (${spineStatusLabel(item.kind, item.status)})` : ""}
                </li>
              ))}
            </ul>
          </Disclosure>
        </Card>
      ) : null}
    </>
  );
}

function PeopleAndCampaigns({
  id,
  canEdit,
  members,
  memberChoices,
  campaigns,
  campaignChoices,
  campaignTags,
  refresh,
}: {
  id: string;
  canEdit: boolean;
  members: Array<{ id: string; full_name: string }>;
  memberChoices: Array<{ id: string; full_name: string }>;
  campaigns: Array<{ id: string; code: string; title: string }>;
  campaignChoices: Array<{ id: string; code: string; title: string }>;
  campaignTags: Array<{ tag: string; brand: string }>;
  refresh: () => void;
}) {
  const [campaignTitle, setCampaignTitle] = useState("");
  const [campaignTag, setCampaignTag] = useState(campaignTags[0]?.tag || "S");
  const [campaignNote, setCampaignNote] = useState("");
  const createCampaign = useMutation({
    mutationFn: () => requestsApi.createCampaign(id, campaignTitle.trim(), campaignTag),
    onSuccess: (row) => {
      setCampaignTitle("");
      setCampaignNote(`${row.code} ساخته و به پروژه وصل شد.`);
      refresh();
    },
    onError: (error: unknown) => setCampaignNote(error instanceof Error ? error.message : "کمپین ساخته نشد."),
  });
  return (
    <>
      <SectionHeader title={<Bi en="People on this project" fa="اعضای این پروژه" />} />
      {canEdit ? (
        <PickList
          key={`members-${members.map((person) => person.id).join()}`}
          options={memberChoices.map((person) => ({ id: person.id, label: person.full_name }))}
          initial={members.map((person) => person.id)}
          saveLabel="ذخیرهٔ اعضا"
          empty="عضوی در این بخش نیست."
          onSave={(userIds) => requestsApi.setMembers(id, userIds).then(refresh)}
        />
      ) : members.length === 0 ? (
        <EmptyState
          titleEn="No one is on it yet"
          titleFa="هنوز کسی روی این پروژه نیست"
          bodyEn="People appear here when a lead adds them."
          bodyFa="وقتی سرپرست کسی را اضافه کند، اینجا دیده می‌شود."
        />
      ) : (
        <div className="choice-grid">
          {members.map((person) => <span key={person.id} className="meta-chip">{person.full_name}</span>)}
        </div>
      )}
      <SectionHeader title={<Bi en="Campaigns" fa="کمپین‌های این پروژه" />} />
      {!canEdit && campaigns.length > 0 ? (
        <ul className="record-subs">
          {campaigns.map((campaign) => (
            <li key={campaign.id}>
              <Link className="record-sub" to={`/perf/campaigns/${campaign.id}`}>
                <span className="record-code" dir="ltr">{campaign.code}</span>
                <strong>{campaign.title}</strong>
                <span />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
      {!canEdit && campaigns.length === 0 ? (
        <EmptyState
          titleEn="No campaign is attached yet"
          titleFa="هنوز کمپینی وصل نیست"
          bodyEn="A campaign shows up here after it is attached."
          bodyFa="بعد از وصل شدن، کمپین اینجا دیده می‌شود."
        />
      ) : null}
      {canEdit ? (
        <Disclosure label={<Bi en="New campaign" fa="کمپین تازه" />}>
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              if (campaignTitle.trim()) createCampaign.mutate();
            }}
          >
            <Field label={<Bi en="Title" fa="عنوان" />}>
              <Input value={campaignTitle} onChange={(event) => setCampaignTitle(event.target.value)} />
            </Field>
            <Field label={<Bi en="Brand" fa="برند" />}>
              <Select value={campaignTag} onChange={(event) => setCampaignTag(event.target.value)}>
                {campaignTags.map((item) => (
                  <option key={item.tag} value={item.tag}>{item.brand}</option>
                ))}
              </Select>
            </Field>
            <div className="record-actions">
              <Button type="submit" className="btn-sm" disabled={createCampaign.isPending || !campaignTitle.trim()}>
                <Bi en="Create" fa="بساز" />
              </Button>
            </div>
            {campaignNote ? <Muted as="p">{campaignNote}</Muted> : null}
          </form>
        </Disclosure>
      ) : null}
      {canEdit ? (
        <CampaignPick
          key={`campaigns-${campaigns.map((campaign) => campaign.id).join()}`}
          options={campaignChoices}
          initial={campaigns.map((campaign) => campaign.id)}
          onSave={(campaignIds) => requestsApi.setCampaigns(id, campaignIds).then(refresh)}
        />
      ) : null}
    </>
  );
}

function campaignHit(campaign: { code: string; title: string }, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return false;
  return `${campaign.code} ${campaign.title}`.toLowerCase().includes(needle);
}

function CampaignPick({
  options,
  initial,
  onSave,
}: {
  options: Array<{ id: string; code: string; title: string }>;
  initial: string[];
  onSave: (ids: string[]) => Promise<unknown>;
}) {
  const [ids, setIds] = useState(initial);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  if (options.length === 0) return <Muted as="p">کمپینی در سازمان نیست.</Muted>;
  const byId = new Map(options.map((campaign) => [campaign.id, campaign]));
  const selected = ids.map((item) => byId.get(item)).filter((campaign) => campaign != null);
  const pool = options.filter((campaign) => !ids.includes(campaign.id) && campaignHit(campaign, query));
  const matches = pool.slice(0, 8);
  return (
    <div className="stack campaign-pick">
      {selected.length === 0 ? (
        <Muted as="p"><Bi en="Attach one when the work needs an ad." fa="وقتی کار به آگهی نیاز داشت، یکی را وصل کنید." /></Muted>
      ) : (
        <ul className="record-subs">
          {selected.map((campaign) => (
            <li key={campaign.id} className="campaign-row">
              <Link className="record-sub" to={`/perf/campaigns/${campaign.id}`}>
                <span className="record-code" dir="ltr">{campaign.code}</span>
                <strong>{campaign.title}</strong>
                <span />
              </Link>
              <Button
                type="button"
                variant="ghost"
                className="btn-sm"
                onClick={() => setIds((cur) => cur.filter((item) => item !== campaign.id))}
              >
                <Bi en="Remove" fa="برداشتن" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <Field label={<Bi en="Find a campaign" fa="جستجوی کمپین" />}>
        <Input
          value={query}
          placeholder="کد یا نام"
          onChange={(event) => setQuery(event.target.value)}
        />
      </Field>
      {query.trim() && matches.length === 0 ? (
        <Muted as="p"><Bi en="No campaign matches." fa="کمپینی با این عبارت نیست." /></Muted>
      ) : null}
      {matches.length > 0 ? (
        <>
          <ul className="record-subs campaign-results">
            {matches.map((campaign) => (
              <li key={campaign.id}>
                <button
                  type="button"
                  className="record-sub"
                  onClick={() => setIds((cur) => (cur.includes(campaign.id) ? cur : [...cur, campaign.id]))}
                >
                  <span className="record-code" dir="ltr">{campaign.code}</span>
                  <strong>{campaign.title}</strong>
                  <span><Bi en="Add" fa="افزودن" /></span>
                </button>
              </li>
            ))}
          </ul>
          {pool.length > matches.length ? (
            <Muted as="p">
              <Bi
                en={`${matches.length} of ${pool.length}. Narrow the search.`}
                fa={`${faNum(matches.length)} از ${faNum(pool.length)}. جستجو را دقیق‌تر کنید.`}
              />
            </Muted>
          ) : null}
        </>
      ) : null}
      {!query.trim() ? (
        <Muted as="p"><Bi en="Type a code or a name. The full list stays hidden." fa="کد یا نام را بنویسید. فهرست کامل باز نمی‌شود." /></Muted>
      ) : null}
      <Button
        type="button"
        className="btn-sm"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          void onSave(ids).finally(() => setBusy(false));
        }}
      >
        <Bi en="Save campaigns" fa="ذخیرهٔ کمپین‌ها" />
      </Button>
    </div>
  );
}

function PickList({
  options,
  initial,
  saveLabel,
  empty,
  onSave,
}: {
  options: Array<{ id: string; label: string }>;
  initial: string[];
  saveLabel: string;
  empty: string;
  onSave: (ids: string[]) => Promise<unknown>;
}) {
  const [ids, setIds] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  if (options.length === 0) return <Muted as="p">{empty}</Muted>;
  const shown = query.trim()
    ? options.filter((option) => option.label.includes(query.trim()))
    : options;
  return (
    <div className="stack">
      {options.length > 8 ? (
        <Field label={<Bi en="Find" fa="جستجو" />}>
          <Input value={query} onChange={(event) => setQuery(event.target.value)} />
        </Field>
      ) : null}
      <div className="choice-grid">
        {shown.map((option) => (
          <Checkbox
            key={option.id}
            label={option.label}
            checked={ids.includes(option.id)}
            onChange={() => setIds((cur) => (cur.includes(option.id) ? cur.filter((item) => item !== option.id) : [...cur, option.id]))}
          />
        ))}
      </div>
      <Button type="button" className="btn-sm" disabled={busy} onClick={() => {
        setBusy(true);
        void onSave(ids).finally(() => setBusy(false));
      }}>
        {saveLabel}
      </Button>
    </div>
  );
}
