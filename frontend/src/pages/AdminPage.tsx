import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getToken } from "../api";
import {
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Field,
  Input,
  LoadingState,
  Muted,
  PageHeader,
  SectionHeader,
  Segmented,
  Select,
  StatCard,
  Table,
} from "../components/ui";
import { Bi, useBi } from "../i18n";
import { useAuth } from "../auth";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { queryKeys } from "../lib/queryKeys";
import { DateText } from "../components/DateText";
import { Donut, GroupedBars, HBars } from "../components/charts";

const SCOPES: Array<[string, string, string]> = [
  ["organization", "Organization", "کل سازمان"],
  ["branch", "Branch", "شعبه"],
  ["department", "Department", "واحد"],
  ["team", "Team", "تیم"],
  ["self", "Self only", "فقط خودم"],
];

type AdminTab = "overview" | "analytics" | "people" | "monitoring" | "audit";

export function AdminPage() {
  const { has } = useAuth();
  const [tab, setTab] = useState<AdminTab>("overview");

  if (!has("org.admin")) {
    return (
      <>
        <PageHeader title={<Bi en="Organization admin" fa="مدیریت سازمان" />} />
        <Card>
          <Muted>
            <Bi
              en="You need the org.admin permission to manage users, roles and teams."
              fa="برای مدیریت کاربران، نقش‌ها و تیم‌ها به مجوز org.admin نیاز دارید."
            />
          </Muted>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Organization admin" fa="مدیریت سازمان" />}
        description={
          <Bi
            en="Organization overview, analytics, people and roles, health monitoring, and the audit trail."
            fa="نمای کلی، تحلیل‌ها، کاربران و نقش‌ها، مانیتورینگ سلامت و گزارش ممیزی."
          />
        }
        actions={
          <Segmented<AdminTab>
            value={tab}
            onChange={setTab}
            items={[
              { key: "overview", label: <Bi en="Overview" fa="نمای کلی" />, icon: "layers" },
              { key: "analytics", label: <Bi en="Analytics" fa="تحلیل‌ها" />, icon: "activity" },
              { key: "people", label: <Bi en="People & roles" fa="کاربران و نقش‌ها" />, icon: "users" },
              { key: "monitoring", label: <Bi en="Monitoring" fa="مانیتورینگ" />, icon: "circleCheck" },
              { key: "audit", label: <Bi en="Audit" fa="ممیزی" />, icon: "check" },
            ]}
          />
        }
      />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "analytics" ? <AnalyticsTab /> : null}
      {tab === "people" ? <PeopleTab /> : null}
      {tab === "monitoring" ? <MonitoringTab /> : null}
      {tab === "audit" ? <AuditTab /> : null}
    </>
  );
}

function PeopleTab() {
  const bi = useBi();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const toast = useToast();
  const confirm = useConfirm();
  useEffect(() => {
    if (message) toast(message);
  }, [message, toast]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const res = await fetch("/api/org/users", {
      method: "POST",
      credentials: "include",
      headers: {
        Authorization: `Bearer ${getToken() ?? ""}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, full_name: name, password }),
    });
    setMessage(res.ok ? "ساخته شد" : await res.text());
  }

  const [formError, setFormError] = useState("");
  const [resetFor, setResetFor] = useState<string | null>(null);
  const [resetValue, setResetValue] = useState("");
  const [teamFor, setTeamFor] = useState<string | null>(null);
  const [teamId, setTeamId] = useState("");
  const [selectedRole, setSelectedRole] = useState("");

  const invalidateAdmin = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.peopleRoot });
    void qc.invalidateQueries({ queryKey: ["admin"] });
  };

  const peopleQuery = useQuery({
    queryKey: ["admin", "people"],
    queryFn: () => api.people.list(),
  });
  const rolesQuery = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: () => api.roles(),
  });
  const teamsQuery = useQuery({ queryKey: queryKeys.teams, queryFn: () => api.teams.list() });
  const codesQuery = useQuery({
    queryKey: ["admin", "permission-codes"],
    queryFn: () => api.admin.permissionCodes(),
  });
  const roleId = selectedRole || rolesQuery.data?.[0]?.id || "";
  const roleQuery = useQuery({
    queryKey: ["admin", "role", roleId],
    enabled: Boolean(roleId),
    queryFn: () => api.admin.rolePermissions(roleId),
  });

  const [userQuery, setUserQuery] = useState("");
  const people = (peopleQuery.data ?? []).filter((person) => {
    const blob = `${person.full_name || ""} ${person.email || ""}`.toLowerCase();
    return blob.includes(userQuery.trim().toLowerCase());
  });
  const roles = rolesQuery.data ?? [];
  const teams = teamsQuery.data ?? [];
  const loadError = peopleQuery.isError ? String((peopleQuery.error as Error).message) : "";

  const updateUser = useMutation({
    mutationFn: (body: { user_id: string; is_active: boolean }) =>
      api.admin.updateUser(body.user_id, { is_active: body.is_active }),
    onSuccess: () => {
      setMessage(bi("User updated", "کاربر به‌روزرسانی شد"));
      invalidateAdmin();
    },
    onError: (e) => setFormError(String((e as Error).message)),
  });

  const resetPassword = useMutation({
    mutationFn: (body: { user_id: string; password: string }) =>
      api.admin.updateUser(body.user_id, { password: body.password }),
    onSuccess: () => {
      setResetFor(null);
      setResetValue("");
      setMessage(bi("Password reset", "رمز عبور بازنشانی شد"));
      invalidateAdmin();
    },
    onError: (e) => setFormError(String((e as Error).message)),
  });

  const addTeam = useMutation({
    mutationFn: (body: { user_id: string; team_id: string }) =>
      api.admin.addTeam(body.user_id, body),
    onSuccess: () => {
      setTeamFor(null);
      setTeamId("");
      setMessage(bi("Added to team", "به تیم اضافه شد"));
      invalidateAdmin();
    },
    onError: (e) => setFormError(String((e as Error).message)),
  });

  const updateRole = useMutation({
    mutationFn: (body: { permission_codes: string[]; data_scope_level: string }) =>
      api.admin.updateRole(roleId, body),
    onSuccess: () => {
      setMessage(bi("Role saved", "نقش ذخیره شد"));
      void qc.invalidateQueries({ queryKey: ["admin", "role", roleId] });
    },
    onError: (e) => setFormError(String((e as Error).message)),
  });

  return (
    <>
      <ErrorMessage error={formError || loadError} />

      <Card>
        <SectionHeader icon="plus" title={<Bi en="New user" fa="کاربر جدید" />} />
        <form className="form-grid" onSubmit={onSubmit}>
          <Field label={<Bi en="Full name" fa="نام کامل" />}>
            <Input value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <Field label={<Bi en="Email" fa="ایمیل" />}>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </Field>
          <Field label={<Bi en="Password" fa="رمز عبور" />}>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Field>
          <div className="span-all">
            <Button type="submit">{bi("Create", "ساختن")}</Button>
          </div>
        </form>
      </Card>

      <Card padded={false}>
        <SectionHeader icon="users" title={<Bi en="People" fa="کاربران" />} count={people.length} />
        <Input value={userQuery} onChange={(e) => setUserQuery(e.target.value)} placeholder={bi("Search users", "جستجوی کاربر")} />
        {peopleQuery.isLoading ? (
          <LoadingState />
        ) : people.length === 0 ? (
          <EmptyState
            titleEn="No users yet"
            titleFa="هنوز کاربری نیست"
            bodyEn="Create the first account above."
            bodyFa="اولین حساب را بالا بسازید."
          />
        ) : (
          <Table
            rows={people}
            rowKey={(u) => String(u.id)}
            columns={[
              {
                key: "name",
                header: <Bi en="Name" fa="نام" />,
                render: (u) => (
                  <span className="cell-main">
                    <strong>{String(u.full_name)}</strong>
                    <Muted className="mono ltr-value">{String(u.email)}</Muted>
                  </span>
                ),
              },
              {
                key: "active",
                header: <Bi en="Status" fa="وضعیت" />,
                render: (u) => (
                  <Bi
                    en={u.is_active ? "Active" : "Deactivated"}
                    fa={u.is_active ? "فعال" : "غیرفعال"}
                  />
                ),
              },
              {
                key: "actions",
                header: <Bi en="Actions" fa="عملیات" />,
                render: (u) => (
                  <span className="chip-row">
                    <Button
                      variant="secondary"
                      disabled={updateUser.isPending}
                      onClick={() => {
                        void (async () => {
                          if (u.is_active) {
                            const ok = await confirm(
                              bi("Deactivate this user?", "این کاربر غیرفعال شود؟"),
                              bi("They will not be able to sign in.", "دیگر نمی‌تواند وارد شود."),
                              bi("Deactivate", "غیرفعال"),
                            );
                            if (!ok) return;
                          }
                          updateUser.mutate({
                            user_id: String(u.id),
                            is_active: !u.is_active,
                          });
                        })();
                      }}
                    >
                      {u.is_active
                        ? bi("Deactivate", "غیرفعال کردن")
                        : bi("Activate", "فعال کردن")}
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setFormError("");
                        setResetFor(resetFor === String(u.id) ? null : String(u.id));
                        setResetValue("");
                      }}
                    >
                      {bi("Reset password", "بازنشانی رمز")}
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setFormError("");
                        setTeamFor(teamFor === String(u.id) ? null : String(u.id));
                        setTeamId(String(u.team_id ?? teams[0]?.id ?? ""));
                      }}
                    >
                      {bi("Add to team", "افزودن به تیم")}
                    </Button>
                  </span>
                ),
              },
            ]}
          />
        )}
        {resetFor ? (
          <form
            className="form-grid"
            onSubmit={(e) => {
              e.preventDefault();
              resetPassword.mutate({ user_id: resetFor, password: resetValue });
            }}
          >
            <Field label={<Bi en="New password" fa="رمز جدید" />} className="span-all">
              <Input
                type="password"
                value={resetValue}
                onChange={(e) => setResetValue(e.target.value)}
                required
                autoFocus
              />
            </Field>
            <div className="span-all">
              <Button type="submit" disabled={resetPassword.isPending}>
                {bi("Save new password", "ذخیره رمز جدید")}
              </Button>
            </div>
          </form>
        ) : null}
        {teamFor ? (
          <form
            className="form-grid"
            onSubmit={(e) => {
              e.preventDefault();
              addTeam.mutate({ user_id: teamFor, team_id: teamId });
            }}
          >
            <Field label={<Bi en="Team" fa="تیم" />} className="span-all">
              <Select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                {teams.map((t) => (
                  <option key={String(t.id)} value={String(t.id)}>
                    {String(t.name)}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="span-all">
              <Button type="submit" disabled={addTeam.isPending || !teamId}>
                {bi("Add to team", "افزودن به تیم")}
              </Button>
            </div>
          </form>
        ) : null}
      </Card>

      <Card>
        <SectionHeader icon="check" title={<Bi en="Role permissions" fa="مجوزهای نقش" />} />
        <div className="form-grid">
          <Field label={<Bi en="Role" fa="نقش" />} className="span-all">
            <Select value={roleId} onChange={(e) => setSelectedRole(e.target.value)}>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        {roleQuery.isLoading ? (
          <LoadingState />
        ) : roleQuery.isError ? (
          <ErrorMessage error={String((roleQuery.error as Error).message)} />
        ) : roleQuery.data ? (
          <RoleEditor
            codes={codesQuery.data ?? []}
            selected={roleQuery.data.permission_codes}
            scope={roleQuery.data.data_scope_level}
            busy={updateRole.isPending}
            onSave={(permission_codes, data_scope_level) =>
              updateRole.mutate({ permission_codes, data_scope_level })
            }
          />
        ) : null}
      </Card>
    </>
  );
}

/** تب «نمای کلی» — فقط خواندنی، پشت org.admin در بک‌اند. */
function OverviewTab() {
  const bi = useBi();
  const query = useQuery({
    queryKey: ["admin", "overview"],
    queryFn: () => api.admin.overview(),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data) {
    return <ErrorMessage error={String((query.error as Error)?.message ?? "")} />;
  }
  const d = query.data;
  const maxTasks = Math.max(...d.trend.map((t) => Number(t.kpis?.open_tasks ?? 0)), 1);

  return (
    <>
      <div className="kpi-row kpi-row--4 kpi-row--even">
        <StatCard
          icon="users"
          tone={d.users.inactive + d.users.locked > 0 ? "warn" : "ok"}
          label={<Bi en="Active users" fa="کاربران فعال" />}
          value={`${d.users.active}`}
          hint={
            <Bi
              en={`${d.users.total} total · ${d.users.inactive} inactive · ${d.users.locked} locked`}
              fa={`${d.users.total} کل · ${d.users.inactive} غیرفعال · ${d.users.locked} قفل‌شده`}
            />
          }
        />
        <StatCard
          icon="message"
          tone="accent"
          label={<Bi en="Messages · 7 days" fa="پیام‌ها · ۷ روز" />}
          value={`${d.messages_7d}`}
        />
        <StatCard
          icon="chat"
          tone={d.conversations_waiting_reply > 0 ? "warn" : "ok"}
          label={<Bi en="Waiting for reply" fa="منتظر پاسخ" />}
          value={`${d.conversations_waiting_reply}`}
        />
        <StatCard
          icon="clock"
          tone={d.avg_first_reply_minutes == null ? "neutral" : d.avg_first_reply_minutes > 30 ? "warn" : "ok"}
          label={<Bi en="Avg first reply" fa="میانگین اولین پاسخ" />}
          value={
            d.avg_first_reply_minutes == null
              ? "–"
              : bi(`${d.avg_first_reply_minutes} min`, `${d.avg_first_reply_minutes} دقیقه`)
          }
        />
      </div>

      <div className="kpi-row kpi-row--4 kpi-row--even">
        <StatCard
          icon="briefcase"
          tone="accent"
          label={<Bi en="Open cases" fa="پرونده‌های باز" />}
          value={`${d.cases.open}`}
        />
        <StatCard
          icon="alert"
          tone={d.cases.sla_breached > 0 ? "danger" : "ok"}
          label={<Bi en="SLA breached" fa="SLA نقض‌شده" />}
          value={`${d.cases.sla_breached}`}
        />
        <StatCard
          icon="check"
          tone={d.approvals_pending > 0 ? "warn" : "ok"}
          label={<Bi en="Pending approvals" fa="تأییدهای منتظر" />}
          value={`${d.approvals_pending}`}
        />
        <StatCard
          icon="alert"
          tone={d.divar_errors > 0 ? "danger" : "ok"}
          label={<Bi en="Divar errors" fa="خطاهای دیوار" />}
          value={`${d.divar_errors}`}
        />
      </div>

      <Card>
        <SectionHeader icon="car" title={<Bi en="Vehicles" fa="خودروها" />} />
        <div className="kpi-row kpi-row--3 kpi-row--even">
          <StatCard icon="car" tone="ok" label={<Bi en="In stock" fa="موجود" />} value={`${d.vehicles.in_stock}`} />
          <StatCard icon="clock" tone="warn" label={<Bi en="Reserved" fa="رزرو" />} value={`${d.vehicles.reserved}`} />
          <StatCard icon="check" tone="accent" label={<Bi en="Sold" fa="فروخته" />} value={`${d.vehicles.sold}`} />
        </div>
      </Card>

      <div className="grid grid-2">
        <Card padded={false}>
          <SectionHeader
            icon="branch"
            title={<Bi en="Open tasks by branch" fa="کارهای باز به تفکیک شعبه" />}
            count={d.tasks_by_branch.length}
          />
          {d.tasks_by_branch.length === 0 ? (
            <div className="flush-foot">
              <EmptyState
                titleEn="No open tasks"
                titleFa="کار بازی نیست"
                bodyEn="Nothing is pending right now."
                bodyFa="الان کار بازی وجود ندارد."
              />
            </div>
          ) : (
            <Table
              rows={d.tasks_by_branch}
              rowKey={(r) => r.branch}
              columns={[
                { key: "branch", header: <Bi en="Branch" fa="شعبه" />, render: (r) => r.branch },
                { key: "open", header: <Bi en="Open" fa="باز" />, render: (r) => `${r.open}` },
                {
                  key: "overdue",
                  header: <Bi en="Overdue" fa="عقب‌افتاده" />,
                  render: (r) => (
                    <span className={r.overdue > 0 ? "cell-warn" : undefined}>{`${r.overdue}`}</span>
                  ),
                },
              ]}
            />
          )}
        </Card>

        <Card padded={false}>
          <SectionHeader
            icon="users"
            title={<Bi en="Busiest people" fa="پرکارترین‌ها" />}
            count={d.top_users.length}
          />
          {d.top_users.length === 0 ? (
            <div className="flush-foot">
              <EmptyState
                titleEn="No assignments"
                titleFa="ارجاعی نیست"
                bodyEn="Nobody has an open task right now."
                bodyFa="الان هیچ‌کس کار باز ندارد."
              />
            </div>
          ) : (
            <Table
              rows={d.top_users}
              rowKey={(r) => r.user_id}
              columns={[
                { key: "name", header: <Bi en="Person" fa="نفر" />, render: (r) => r.name },
                {
                  key: "tasks",
                  header: <Bi en="Open tasks" fa="کارهای باز" />,
                  render: (r) => `${r.open_tasks}`,
                },
              ]}
            />
          )}
        </Card>
      </div>

      <Card>
        <SectionHeader icon="activity" title={<Bi en="Weekly trend · open tasks" fa="روند هفتگی · کارهای باز" />} />
        {d.trend.length === 0 ? (
          <EmptyState
            titleEn="No snapshots yet"
            titleFa="هنوز اسنپ‌شاتی نیست"
            bodyEn="The worker stores one KPI snapshot per week."
            bodyFa="worker هر هفته یک اسنپ‌شات KPI ذخیره می‌کند."
          />
        ) : (
          <div className="trend-bars">
            {d.trend.map((t) => {
              const open = Number(t.kpis?.open_tasks ?? 0);
              return (
                <div key={t.date ?? `w-${t.week}`} className="trend-col">
                  <div
                    className="trend-bar"
                    style={{ height: `${Math.max(Math.round((open / maxTasks) * 100), 2)}%` }}
                  />
                  <Muted className="trend-label">
                    {t.week != null ? bi(`Week ${t.week}`, `هفته ${t.week}`) : "–"}
                  </Muted>
                </div>
              );
            })}
          </div>
        )}
        <Muted>
          <Bi en={`Weekly worker snapshot · ${d.as_of_jalali}`} fa={`اسنپ‌شات هفتگی worker · ${d.as_of_jalali}`} />
        </Muted>
      </Card>
    </>
  );
}

function shortWeek(week: string): string {
  return week.includes("-W") ? `W${week.split("-W")[1]}` : week;
}

function shortDay(day: string): string {
  return day.length >= 10 ? day.slice(5) : day;
}

function fmtBytes(bytes: number | null): string {
  if (bytes == null) return "–";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function rankedEntries(obj: Record<string, number>): Array<{ label: string; value: number }> {
  return Object.entries(obj)
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value);
}

/** تب «تحلیل‌ها» — نمودار و جدول تفصیلی از هر بخش (فقط org.admin). */
function AnalyticsTab() {
  const bi = useBi();
  const query = useQuery({
    queryKey: ["admin", "analytics"],
    queryFn: () => api.admin.analytics(),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data) {
    return <ErrorMessage error={String((query.error as Error)?.message ?? "")} />;
  }
  const d = query.data;

  return (
    <>
      <div className="kpi-row kpi-row--4 kpi-row--even">
        <StatCard
          icon="alert"
          tone={d.tasks_overdue > 0 ? "warn" : "ok"}
          label={<Bi en="Overdue tasks" fa="کارهای عقب‌افتاده" />}
          value={`${d.tasks_overdue}`}
        />
        <StatCard
          icon="clock"
          tone="accent"
          label={<Bi en="Avg completion · 30d" fa="میانگین تکمیل · ۳۰ روز" />}
          value={
            d.avg_completion_hours == null
              ? "–"
              : bi(`${d.avg_completion_hours}h`, `${d.avg_completion_hours} ساعت`)
          }
        />
        <StatCard
          icon="check"
          tone="accent"
          label={<Bi en="Avg case resolution · 90d" fa="میانگین حل پرونده · ۹۰ روز" />}
          value={
            d.avg_case_resolution_hours == null
              ? "–"
              : bi(`${d.avg_case_resolution_hours}h`, `${d.avg_case_resolution_hours} ساعت`)
          }
        />
        <StatCard
          icon="alert"
          tone={d.login_failed_7d > 0 ? "danger" : "ok"}
          label={<Bi en="Failed logins · 7d" fa="ورود ناموفق · ۷ روز" />}
          value={`${d.login_failed_7d}`}
        />
      </div>

      <div className="grid grid-2">
        <Card>
          <SectionHeader
            icon="briefcase"
            title={<Bi en="Tasks · created vs completed" fa="کارها · ساخته‌شده در برابر تکمیل‌شده" />}
          />
          <GroupedBars
            data={d.tasks_weekly.map((w) => ({
              label: shortWeek(w.week),
              values: [w.created, w.completed],
            }))}
            legend={[bi("Created", "ساخته‌شده"), bi("Completed", "تکمیل‌شده")]}
            height={190}
          />
        </Card>
        <Card>
          <SectionHeader icon="message" title={<Bi en="Messages · last 14 days" fa="پیام‌ها · ۱۴ روز اخیر" />} />
          <GroupedBars
            data={d.messages_daily.map((m) => ({ label: m.day.slice(8), values: [m.count] }))}
            height={190}
          />
        </Card>
      </div>

      <div className="grid grid-2">
        <Card>
          <SectionHeader icon="flag" title={<Bi en="Open tasks by priority" fa="کارهای باز به تفکیک اولویت" />} />
          <HBars data={rankedEntries(d.tasks_by_priority)} color="var(--warn)" />
        </Card>
        <Card>
          <SectionHeader icon="chat" title={<Bi en="First reply time" fa="زمان اولین پاسخ" />} />
          <Donut
            data={[
              { label: bi("< 5 min", "زیر ۵ دقیقه"), value: d.reply_buckets.lt5 },
              { label: bi("5–30 min", "۵ تا ۳۰ دقیقه"), value: d.reply_buckets.lt30 },
              { label: bi("30–120 min", "۳۰ تا ۱۲۰ دقیقه"), value: d.reply_buckets.lt120 },
              { label: bi("> 2 hours", "بیش از ۲ ساعت"), value: d.reply_buckets.gt120 },
              { label: bi("No reply", "بی‌پاسخ"), value: d.reply_buckets.no_reply },
            ]}
            caption={bi("conversations", "گفتگو")}
          />
        </Card>
      </div>

      <div className="grid grid-2">
        <Card>
          <SectionHeader icon="chat" title={<Bi en="Cases by status" fa="پرونده‌ها به تفکیک وضعیت" />} />
          <HBars data={rankedEntries(d.cases_by_status)} />
        </Card>
        <Card>
          <SectionHeader icon="chat" title={<Bi en="Cases by type" fa="پرونده‌ها به تفکیک نوع" />} />
          <HBars data={rankedEntries(d.cases_by_type)} color="var(--ok)" />
        </Card>
      </div>

      <div className="grid grid-2">
        <Card>
          <SectionHeader icon="car" title={<Bi en="Vehicle aging in stock" fa="پیری خودروهای انبار" />} />
          <HBars
            data={[
              { label: bi("< 7 days", "کمتر از ۷ روز"), value: d.vehicles_aging.lt7 },
              { label: bi("7–30 days", "۷ تا ۳۰ روز"), value: d.vehicles_aging.lt30 },
              { label: bi("30–90 days", "۳۰ تا ۹۰ روز"), value: d.vehicles_aging.lt90 },
              { label: bi("> 90 days", "بیش از ۹۰ روز"), value: d.vehicles_aging.gt90 },
            ]}
            color="#8b5cf6"
          />
        </Card>
        <Card>
          <SectionHeader
            icon="car"
            title={<Bi en="Estimated value by status" fa="ارزش تقریبی به تفکیک وضعیت" />}
          />
          <HBars
            data={rankedEntries(d.vehicles_value_by_status)}
            format={(v) => v.toLocaleString("en-US")}
          />
        </Card>
      </div>

      <div className="grid grid-2">
        <Card padded={false}>
          <SectionHeader
            icon="activity"
            title={<Bi en="Most frequent actions" fa="پرتکرارترین اقدام‌ها" />}
            count={d.top_actions.length}
          />
          {d.top_actions.length === 0 ? (
            <div className="flush-foot">
              <EmptyState
                titleEn="No audit activity"
                titleFa="فعالیت ممیزی نیست"
                bodyEn="Actions will appear here as people work."
                bodyFa="با انجام کارها، اقدام‌ها اینجا دیده می‌شوند."
              />
            </div>
          ) : (
            <Table
              rows={d.top_actions}
              rowKey={(r) => r.action}
              columns={[
                {
                  key: "action",
                  header: <Bi en="Action" fa="اقدام" />,
                  render: (r) => <span className="mono">{r.action}</span>,
                },
                { key: "count", header: <Bi en="Count" fa="تعداد" />, render: (r) => `${r.count}` },
              ]}
            />
          )}
        </Card>
        <Card>
          <SectionHeader icon="check" title={<Bi en="Audit · last 7 days" fa="ممیزی · ۷ روز اخیر" />} />
          <GroupedBars
            data={d.audit_daily_7d.map((a) => ({ label: shortDay(a.day), values: [a.count] }))}
            colors={["#8b5cf6"]}
            height={190}
          />
        </Card>
      </div>

      <Muted>
        <Bi en={`Analytics · ${d.as_of_jalali}`} fa={`تحلیل‌ها · ${d.as_of_jalali}`} />
      </Muted>
    </>
  );
}

/** تب «مانیتورینگ» — سلامت سیستم با تازه‌سازی خودکار ۱۵ ثانیه‌ای. */
function MonitoringTab() {
  const bi = useBi();
  const query = useQuery({
    queryKey: ["admin", "monitoring"],
    queryFn: () => api.admin.monitoring(),
    refetchInterval: 15000,
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data) {
    return <ErrorMessage error={String((query.error as Error)?.message ?? "")} />;
  }
  const d = query.data;
  const failed = d.outbox.by_status.failed ?? 0;
  const pending = d.outbox.by_status.pending ?? 0;
  const oldest = d.outbox.oldest_pending_minutes;
  const integrations = Object.entries(d.integrations).filter(
    ([, v]) => typeof v === "string" || typeof v === "boolean" || typeof v === "number",
  );
  const tableRows = Object.entries(d.database.table_counts).map(([name, rows]) => ({
    name,
    rows,
  }));

  return (
    <>
      <div className="kpi-row kpi-row--4 kpi-row--even">
        <StatCard
          icon="layers"
          tone="ok"
          label={<Bi en="Database size" fa="حجم دیتابیس" />}
          value={fmtBytes(d.database.size_bytes)}
          hint={
            d.database.journal_mode ? (
              <Bi
                en={`journal: ${d.database.journal_mode}`}
                fa={`ژورنال: ${d.database.journal_mode}`}
              />
            ) : undefined
          }
        />
        <StatCard
          icon="alert"
          tone={d.auth_failed_24h > 0 ? "danger" : "ok"}
          label={<Bi en="Failed logins · 24h" fa="ورود ناموفق · ۲۴ ساعت" />}
          value={`${d.auth_failed_24h}`}
        />
        <StatCard
          icon="clock"
          tone={oldest != null && oldest > 10 ? "warn" : "ok"}
          label={<Bi en="Outbox oldest pending" fa="قدیمی‌ترین پیام صف خروجی" />}
          value={
            oldest == null ? "–" : bi(`${oldest} min`, `${oldest.toLocaleString("fa-IR")} دقیقه`)
          }
        />
        <StatCard
          icon="send"
          tone={failed > 0 ? "danger" : "ok"}
          label={<Bi en="Outbox failed" fa="پیام‌های ناموفق" />}
          hint={<Bi en={`${pending} pending`} fa={`${pending.toLocaleString("fa-IR")} در صف`} />}
          value={`${failed}`}
        />
      </div>

      <div className="grid grid-2">
        <Card>
          <SectionHeader icon="circleCheck" title={<Bi en="Audit chain integrity" fa="یکپارچگی زنجیرهٔ ممیزی" />} />
          {d.audit_chain.ok === true ? (
            <span className="badge ok">
              <Bi
                en={`Intact · ${d.audit_chain.rows_checked.toLocaleString("en-US")} rows`}
                fa={`سالم · ${d.audit_chain.rows_checked.toLocaleString("fa-IR")} ردیف`}
              />
            </span>
          ) : d.audit_chain.ok === false ? (
            <span className="badge danger">
              <Bi
                en={`Broken at row ${d.audit_chain.broken_at}`}
                fa={`شکسته در ردیف ${d.audit_chain.broken_at}`}
              />
            </span>
          ) : (
            <span className="badge warn">
              <Bi en="Unknown" fa="نامشخص" />
            </span>
          )}
          {d.audit_chain.detail ? (
            <Muted className="mt-3">
              <span className="mono mono-xs">{d.audit_chain.detail}</span>
            </Muted>
          ) : null}
        </Card>
        <Card>
          <SectionHeader icon="activity" title={<Bi en="Events · last 24h" fa="رویدادها · ۲۴ ساعت اخیر" />} />
          <HBars
            data={d.events_24h.map((e) => ({ label: e.type, value: e.count }))}
            color="#8b5cf6"
          />
        </Card>
      </div>

      <div className="grid grid-2">
        <Card padded={false}>
          <SectionHeader icon="clock" title={<Bi en="Job locks" fa="قفل‌های job" />} count={d.job_locks.length} />
          {d.job_locks.length === 0 ? (
            <div className="flush-foot">
              <EmptyState
                titleEn="No job locks"
                titleFa="قفلی ثبت نشده"
                bodyEn="Background workers will acquire locks here."
                bodyFa="ورکرهای پس‌زمینه قفل‌ها را اینجا می‌گیرند."
              />
            </div>
          ) : (
            <Table
              rows={d.job_locks}
              rowKey={(lk) => lk.name}
              columns={[
                {
                  key: "name",
                  header: <Bi en="Job" fa="job" />,
                  render: (lk) => <span className="mono">{lk.name}</span>,
                },
                {
                  key: "owner",
                  header: <Bi en="Owner" fa="دارنده" />,
                  render: (lk) => (
                    <span className="mono mono-xs" title={lk.owner || undefined}>
                      {lk.owner ? `${lk.owner.slice(0, 12)}…` : "–"}
                    </span>
                  ),
                },
                {
                  key: "expires",
                  header: <Bi en="Expires" fa="انقضا" />,
                  render: (lk) => <DateText value={lk.expires_at ?? ""} />,
                },
                {
                  key: "stale",
                  header: <Bi en="Status" fa="وضعیت" />,
                  render: (lk) =>
                    lk.stale ? (
                      <span className="badge warn">
                        <Bi en="Stale" fa="منقضی" />
                      </span>
                    ) : (
                      <span className="badge ok">
                        <Bi en="Held" fa="فعال" />
                      </span>
                    ),
                },
              ]}
            />
          )}
        </Card>

        <Card padded={false}>
          <SectionHeader
            icon="send"
            title={<Bi en="Outbox failure samples" fa="نمونهٔ خطاهای صف خروجی" />}
            count={d.outbox.failed_samples.length}
          />
          {d.outbox.failed_samples.length === 0 ? (
            <div className="flush-foot">
              <EmptyState
                titleEn="No failures"
                titleFa="خطایی نیست"
                bodyEn="Recent outbox failures will show up here."
                bodyFa="خطاهای اخیر صف خروجی اینجا نمایش داده می‌شوند."
              />
            </div>
          ) : (
            <Table
              rows={d.outbox.failed_samples}
              rowKey={(s) => `${s.provider}-${s.at}`}
              columns={[
                {
                  key: "provider",
                  header: <Bi en="Provider" fa="ارائه‌دهنده" />,
                  render: (s) => <span className="mono">{s.provider}</span>,
                },
                {
                  key: "error",
                  header: <Bi en="Error" fa="خطا" />,
                  render: (s) => <span className="mono mono-xs">{s.error || "–"}</span>,
                },
                {
                  key: "at",
                  header: <Bi en="When" fa="زمان" />,
                  render: (s) => <DateText value={s.at} />,
                },
              ]}
            />
          )}
        </Card>
      </div>

      <div className="grid grid-2">
        <Card padded={false}>
          <SectionHeader icon="layers" title={<Bi en="Table row counts" fa="تعداد ردیف جداول" />} count={tableRows.length} />
          <Table
            rows={tableRows}
            rowKey={(r) => r.name}
            columns={[
              {
                key: "name",
                header: <Bi en="Table" fa="جدول" />,
                render: (r) => <span className="mono">{r.name}</span>,
              },
              {
                key: "rows",
                header: <Bi en="Rows" fa="ردیف‌ها" />,
                render: (r) => `${r.rows.toLocaleString("en-US")}`,
              },
            ]}
          />
        </Card>

        <Card padded={false}>
          <SectionHeader icon="branch" title={<Bi en="Integrations" fa="اتصال‌ها" />} count={integrations.length} />
          {integrations.length === 0 ? (
            <div className="flush-foot">
              <EmptyState
                titleEn="No integrations configured"
                titleFa="اتصالی پیکربندی نشده"
                bodyEn="Configure SMS, email, Telegram and other channels."
                bodyFa="پیامک، ایمیل، تلگرام و بقیه کانال‌ها را پیکربندی کنید."
              />
            </div>
          ) : (
            <Table
              rows={integrations}
              rowKey={([key]) => key}
              columns={[
                {
                  key: "key",
                  header: <Bi en="Channel" fa="کانال" />,
                  render: ([key]) => <span className="mono">{key}</span>,
                },
                {
                  key: "value",
                  header: <Bi en="Mode" fa="حالت" />,
                  render: ([, value]) => <span className="mono mono-xs">{String(value)}</span>,
                },
              ]}
            />
          )}
        </Card>
      </div>

      <Muted>
        <Bi
          en={`Auto-refreshes every 15 seconds · ${d.as_of_jalali}`}
          fa={`هر ۱۵ ثانیه تازه می‌شود · ${d.as_of_jalali}`}
        />
      </Muted>
    </>
  );
}

const AUDIT_ENTITIES = [
  "",
  "work_item",
  "task",
  "case",
  "conversation",
  "customer",
  "approval",
  "report",
  "user",
  "auth",
];

/** تب «ممیزی» — فیلتر کاربر/موجودیت/اقدام/تاریخ + خروجی اکسل. */
function AuditTab() {
  const bi = useBi();
  const [actor, setActor] = useState("");
  const [entity, setEntity] = useState("");
  const [action, setAction] = useState("");
  const [day, setDay] = useState("");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");

  const filters = {
    ...(actor ? { actorId: actor.trim() } : {}),
    ...(entity ? { entityType: entity } : {}),
    ...(action ? { action: action.trim() } : {}),
    ...(day ? { day } : {}),
  };
  const filterKey = JSON.stringify(filters);

  const query = useQuery({
    queryKey: ["admin", "audit", filterKey],
    queryFn: () => api.audit.list(filters),
  });
  const rows = query.data ?? [];

  return (
    <Card padded={false}>
      <SectionHeader
        icon="check"
        title={<Bi en="Audit trail" fa="گزارش ممیزی" />}
        count={rows.length}
        action={
          <Button
            variant="secondary"
            disabled={exporting}
            onClick={() => {
              setExportError("");
              setExporting(true);
              void api.audit
                .downloadXlsx(filters)
                .catch((e: unknown) => setExportError(String((e as Error).message)))
                .finally(() => setExporting(false));
            }}
          >
            {bi("Export Excel", "خروجی اکسل")}
          </Button>
        }
      />
      <div className="form-grid">
        <Field label={<Bi en="User id" fa="شناسه کاربر" />}>
          <Input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="…" />
        </Field>
        <Field label={<Bi en="Entity type" fa="نوع موجودیت" />}>
          <Select value={entity} onChange={(e) => setEntity(e.target.value)}>
            {AUDIT_ENTITIES.map((v) => (
              <option key={v || "all"} value={v}>
                {v === "" ? bi("All", "همه") : v}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={<Bi en="Action" fa="اقدام" />}>
          <Input value={action} onChange={(e) => setAction(e.target.value)} placeholder="auth.login" />
        </Field>
        <Field label={<Bi en="Day" fa="تاریخ" />}>
          <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        </Field>
      </div>
      <ErrorMessage error={exportError} />
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorMessage error={String((query.error as Error).message)} />
      ) : rows.length === 0 ? (
        <EmptyState
          titleEn="No audit rows"
          titleFa="ردیف ممیزی نیست"
          bodyEn="Clear the filters to see more."
          bodyFa="برای دیدن موارد بیشتر فیلترها را پاک کنید."
        />
      ) : (
        <Table
          rows={rows}
          rowKey={(r) => String(r.id)}
          columns={[
            { key: "action", header: <Bi en="Action" fa="اقدام" />, render: (r) => String(r.action) },
            { key: "entity", header: <Bi en="Entity" fa="موجودیت" />, render: (r) => String(r.entity_type) },
            {
              key: "entity_id",
              header: <Bi en="Entity id" fa="شناسه" />,
              render: (r) => <span className="mono">{String(r.entity_id)}</span>,
            },
            {
              key: "actor",
              header: <Bi en="Actor" fa="کاربر" />,
              render: (r) => (r.actor_id ? <span className="mono">{String(r.actor_id)}</span> : "–"),
            },
            {
              key: "when",
              header: <Bi en="When" fa="زمان" />,
              render: (r) => <DateText value={String(r.created_at ?? "")} />,
            },
          ]}
        />
      )}
    </Card>
  );
}

function RoleEditor({
  codes,
  selected,
  scope,
  busy,
  onSave,
}: {
  codes: string[];
  selected: string[];
  scope: string | null;
  busy: boolean;
  onSave: (codes: string[], scope: string) => void;
}) {
  const bi = useBi();
  const [checked, setChecked] = useState<Set<string>>(() => new Set(selected));
  const [level, setLevel] = useState(scope || "organization");

  // Reset local edits whenever another role (or a saved state) is loaded.
  const signature = selected.join(",");
  const [seen, setSeen] = useState(signature);
  if (seen !== signature) {
    setSeen(signature);
    setChecked(new Set(selected));
    setLevel(scope || "organization");
  }

  function toggle(code: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  return (
    <>
      <Field label={<Bi en="Data scope" fa="محدوده داده" />}>
        <Select value={level} onChange={(e) => setLevel(e.target.value)}>
          {SCOPES.map(([value, en, fa]) => (
            <option key={value} value={value}>
              {bi(en, fa)}
            </option>
          ))}
        </Select>
      </Field>
      <ul className="tag-list mt-3">
        {codes.map((code) => (
          <li key={code}>
            <label className="chip-row">
              <input
                type="checkbox"
                checked={checked.has(code)}
                onChange={() => toggle(code)}
              />
              <span className="mono mono-xs">
                {code}
              </span>
            </label>
          </li>
        ))}
      </ul>
      <div className="mt-3">
        <Button disabled={busy} onClick={() => onSave(Array.from(checked).sort(), level)}>
          {bi("Save role", "ذخیره نقش")}
        </Button>
      </div>
    </>
  );
}
