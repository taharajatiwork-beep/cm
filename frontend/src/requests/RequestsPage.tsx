import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import "../perf/perf.css"; // conn-tile / perf-actions استایل‌های مشترک
import { Badge, Button, Card, Dialog, Disclosure, EmptyState, Field, Input, Muted, PageHeader, QueryState, SectionHeader, Select, TextArea } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { JalaliDateInput } from "../components/JalaliDateInput";
import { Bi, useBi } from "../i18n";
import { useAuth } from "../auth";
import { caughtUpTarget, DEFAULT_REQUEST_KIND, DEFAULT_REQUEST_PRIORITY, suggestTeamId } from "../lib/focus";
import { requestsApi, type TeamOption, type WorkRequest } from "./api";
import { REQUEST_STATUS_LABEL } from "./labels";
import { WorkChainLegend } from "../lib/workContext";

const STATUS_LABEL = REQUEST_STATUS_LABEL;

const STATUS_TONE: Record<string, "ok" | "warn" | "danger"> = {
  new: "warn",
  in_review: "warn",
  converted: "ok",
  rejected: "danger",
  done: "ok",
};

const PRIORITY_LABEL: Record<string, string> = { low: "کم", normal: "معمولی", high: "بالا" };

const REQUEST_KINDS = ["تبلیغات", "قیمت و پست‌ها", "عمومی"];

export function RequestsPage() {
  const { has, user } = useAuth();
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

  return (
    <>
      <PageHeader
        title={<Bi en="Work requests" fa="درخواست‌های کار" />}
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
                  has("request.create") ? (
                    <Button type="button" onClick={() => setCreating(true)}>
                      <Bi en="New work request" fa="درخواست کار جدید" />
                    </Button>
                  ) : (
                    <Button to={caughtUpTarget({ roleCode: user?.roleCode, permissions: user?.permissions ?? [] })}>
                      <Bi en="Next step" fa="قدم بعد" />
                    </Button>
                  )
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
              <RequestCard key={row.id} row={row} />
            ))}
          </div>
          ) : null}
        </QueryState>
      </Card>
    </>
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

function RequestCard({ row }: { row: WorkRequest }) {
  return (
    <Card as="article" className="record-card" stack>
      <div className="record-head">
        <h3 className="record-title">
          <Link to={`/requests/${row.id}`}>{row.title}</Link>
        </h3>
        <Badge tone={STATUS_TONE[row.status] || "warn"}>{STATUS_LABEL[row.status] || row.status}</Badge>
      </div>
      <div className="record-actions">
        <Button className="btn-sm" to={`/requests/${row.id}`}>
          <Bi en="Open" fa="باز کردن" />
        </Button>
      </div>
    </Card>
  );
}