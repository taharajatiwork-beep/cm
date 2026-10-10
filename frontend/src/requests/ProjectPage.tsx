import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Button, Card, EmptyState, ErrorMessage, Field, Input, LoadingState, Muted, PageHeader, SectionHeader } from "../components/ui";
import { useAuth } from "../auth";
import { Bi } from "../i18n";
import { requestsApi } from "./api";

const TABS = ["overview", "tasks", "links", "chat", "costs", "activity", "type"] as const;
type Tab = (typeof TABS)[number];

const TAB_LABEL: Record<Tab, [string, string]> = {
  overview: ["Overview", "نمای کلی"],
  tasks: ["Tasks", "وظایف"],
  links: ["Links", "لینک"],
  chat: ["Chat", "گفتگو"],
  costs: ["Costs", "هزینه"],
  activity: ["Activity", "فعالیت"],
  type: ["Type", "پنل نوع"],
};

export function ProjectPage() {
  const { id = "" } = useParams();
  const { has } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");
  const [title, setTitle] = useState("");
  const [assignees, setAssignees] = useState<string[]>([]);
  const canEdit = has("request.triage") || has("request.manage") || has("task.write");
  const canOpenCampaign = has("perf.read") || has("perf.write");
  const detail = useQuery({
    queryKey: ["project", id],
    queryFn: () => requestsApi.project(id),
    enabled: Boolean(id),
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["project", id] });
  const addTask = useMutation({
    mutationFn: () => requestsApi.addTask(id, title, assignees),
    onSuccess: () => {
      setTitle("");
      refresh();
    },
  });
  const apply = useMutation({ mutationFn: () => requestsApi.applyTemplate(id), onSuccess: refresh });

  if (detail.isLoading) return <LoadingState />;
  if (detail.error) return <ErrorMessage error={detail.error instanceof Error ? detail.error.message : String(detail.error)} />;
  const row = detail.data ?? {};
  const tasks = (row.tasks as Array<Record<string, string>> | undefined) ?? [];
  const attachments = (row.attachments as Array<Record<string, string>> | undefined) ?? [];
  const designs = (row.designs as Array<Record<string, string>> | undefined) ?? [];
  const shoots = (row.shoots as Array<Record<string, string>> | undefined) ?? [];
  const members = (row.members as Array<{ id: string; full_name: string }> | undefined) ?? [];
  const memberChoices = (row.member_choices as Array<{ id: string; full_name: string }> | undefined) ?? [];
  const campaigns = (row.campaigns as Array<{ id: string; code: string; title: string }> | undefined) ?? [];
  const campaignChoices = (row.campaign_choices as Array<{ id: string; code: string; title: string; project_id: string | null }> | undefined) ?? [];
  const done = tasks.filter((task) => task.status === "COMPLETED").length;
  const budget = (row.budget as Record<string, number | boolean> | undefined) ?? {};

  return (
    <>
      <PageHeader
        title={String(row.title || "")}
        description={<Bi en={`${row.code || ""} · ${row.kind || ""}`} fa={`${row.code || ""} · ${row.kind || ""}`} />}
      />
      <div className="row perf-actions">
        {TABS.map((key) => (
          <Button key={key} type="button" className="btn-sm" variant={tab === key ? "primary" : "secondary"} onClick={() => setTab(key)}>
            <Bi en={TAB_LABEL[key][0]} fa={TAB_LABEL[key][1]} />
          </Button>
        ))}
      </div>
      {tab === "overview" ? (
        <Card>
          <p>{String(row.description || "")}</p>
          <Muted as="p">
            <Bi en={`${done} of ${tasks.length} tasks done`} fa={`${done} از ${tasks.length} وظیفه تمام شده`} />
          </Muted>
          {row.request_id ? <Link to="/requests">{String(row.request_code || "درخواست")}</Link> : null}
          <SectionHeader title={<Bi en="People on this project" fa="اعضای این پروژه" />} />
          {members.length === 0 ? <Muted as="p"><Bi en="No one is on it yet." fa="هنوز کسی روی این پروژه نیست." /></Muted> : (
            <ul className="plain-list">
              {members.map((person) => <li key={person.id}>{person.full_name}</li>)}
            </ul>
          )}
          {canEdit ? (
            <PickList
              key={`members-${members.map((person) => person.id).join()}`}
              options={memberChoices.map((person) => ({ id: person.id, label: person.full_name }))}
              initial={members.map((person) => person.id)}
              saveLabel="ذخیرهٔ اعضا"
              empty="عضوی در این بخش نیست."
              onSave={(userIds) => requestsApi.setMembers(id, userIds).then(refresh)}
            />
          ) : null}
          <SectionHeader title={<Bi en="Campaigns" fa="کمپین‌های این پروژه" />} />
          {campaigns.length === 0 ? <Muted as="p"><Bi en="No campaign is attached yet." fa="هنوز کمپینی به این پروژه وصل نیست." /></Muted> : (
            <ul className="plain-list">
              {campaigns.map((campaign) => (
                <li key={campaign.id}>
                  {canOpenCampaign ? <Link to={`/perf/campaigns/${campaign.id}`}>{campaign.code} — {campaign.title}</Link> : `${campaign.code} — ${campaign.title}`}
                </li>
              ))}
            </ul>
          )}
          {canEdit ? (
            <PickList
              key={`campaigns-${campaigns.map((campaign) => campaign.id).join()}`}
              options={campaignChoices.map((campaign) => ({ id: campaign.id, label: `${campaign.code} — ${campaign.title}` }))}
              initial={campaigns.map((campaign) => campaign.id)}
              saveLabel="ذخیرهٔ کمپین‌ها"
              empty="کمپینی در سازمان نیست."
              onSave={(campaignIds) => requestsApi.setCampaigns(id, campaignIds).then(refresh)}
            />
          ) : null}
        </Card>
      ) : null}
      {tab === "tasks" ? (
        <Card>
          <SectionHeader title={<Bi en="Tasks" fa="وظایف" />} />
          {tasks.length === 0 ? <EmptyState titleEn="No tasks" titleFa="وظیفه‌ای نیست" bodyEn="Add one or apply the template." bodyFa="یکی بسازید یا قالب را اعمال کنید." /> : null}
          <ul className="plain-list">
            {tasks.map((task) => (
              <li key={task.id}>{task.title} — {task.status}</li>
            ))}
          </ul>
          <div className="form-grid">
            <Field label={<Bi en="New task" fa="وظیفهٔ تازه" />}>
              <Input value={title} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            {members.length > 0 ? (
              <Field className="span-all" label={<Bi en="Assignees" fa="با هم انجام می‌دهند" />}>
                <div className="row" style={{ flexWrap: "wrap", gap: "var(--space-2)" }}>
                  {members.map((person) => (
                    <label key={person.id}>
                      <input
                        type="checkbox"
                        checked={assignees.includes(person.id)}
                        onChange={() => setAssignees((cur) => (cur.includes(person.id) ? cur.filter((item) => item !== person.id) : [...cur, person.id]))}
                      />{" "}
                      {person.full_name}
                    </label>
                  ))}
                </div>
              </Field>
            ) : null}
            <Button type="button" onClick={() => title.trim() && addTask.mutate()} disabled={addTask.isPending}>
              <Bi en="Add" fa="افزودن" />
            </Button>
            <Button type="button" variant="ghost" onClick={() => apply.mutate()} disabled={apply.isPending}>
              <Bi en="Apply template" fa="اعمال قالب" />
            </Button>
          </div>
        </Card>
      ) : null}
      {tab === "links" ? (
        <Card>
          {attachments.length === 0 ? <EmptyState titleEn="No links" titleFa="لینکی نیست" bodyEn="Links stay on the project." bodyFa="لینک‌ها روی پروژه می‌مانند." /> : null}
          <ul className="plain-list">
            {attachments.map((item) => (
              <li key={item.id}><a href={item.url}>{item.title}</a></li>
            ))}
          </ul>
        </Card>
      ) : null}
      {tab === "chat" ? (
        <Card>
          <Link to={`/communication?conversation=${row.thread_id || ""}`}>
            <Bi en="Open the project thread" fa="رشتهٔ گفتگوی پروژه" />
          </Link>
        </Card>
      ) : null}
      {tab === "costs" ? (
        <Card>
          <Muted as="p">
            <Bi
              en={`Planned ${budget.planned ?? 0} · committed ${budget.committed ?? 0} · actual ${budget.actual ?? 0}${budget.over ? " · over plan" : ""}`}
              fa={`برنامه‌ای ${budget.planned ?? 0} · متعهد ${budget.committed ?? 0} · واقعی ${budget.actual ?? 0}${budget.over ? " · بیشتر از برنامه" : ""}`}
            />
          </Muted>
        </Card>
      ) : null}
      {tab === "activity" ? (
        <Card>
          <Muted as="p"><Bi en="Status changes land in the project thread as system messages." fa="تغییر وضعیت در رشتهٔ پروژه به‌صورت پیام سیستم می‌آید." /></Muted>
        </Card>
      ) : null}
      {tab === "type" ? (
        <Card>
          <SectionHeader title={String(row.kind || "")} />
          {designs.map((item) => <p key={item.id}>{item.title} — {item.status}</p>)}
          {shoots.map((item) => <p key={item.id}>{item.title} — {item.status}</p>)}
          {designs.length + shoots.length === 0 ? <EmptyState titleEn="No type items yet" titleFa="هنوز موردی برای این نوع نیست" bodyEn="Design and shoot items show up here." bodyFa="طرح و فیلم‌برداری اینجا دیده می‌شود." /> : null}
        </Card>
      ) : null}
    </>
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
  if (options.length === 0) return <Muted as="p">{empty}</Muted>;
  return (
    <div className="form-grid">
      <div className="span-all row" style={{ flexWrap: "wrap", gap: "var(--space-2)" }}>
        {options.map((option) => (
          <label key={option.id}>
            <input
              type="checkbox"
              checked={ids.includes(option.id)}
              onChange={() => setIds((cur) => (cur.includes(option.id) ? cur.filter((item) => item !== option.id) : [...cur, option.id]))}
            />{" "}
            {option.label}
          </label>
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
