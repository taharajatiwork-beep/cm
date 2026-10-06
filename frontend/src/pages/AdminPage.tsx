import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getToken, type AdminMessage, type AdminRecord, type AdminRef } from "../api";
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

const SCOPES: Array<[string, string, string, string, string]> = [
  ["organization", "Whole organization", "همهٔ سازمان", "Every section and every branch.", "همهٔ بخش‌ها و همهٔ شعب."],
  ["branch", "Their branch", "شعبهٔ خودش", "Only records in their own branch.", "فقط رکوردهای شعبهٔ خودش."],
  ["department", "Their section", "بخش خودش", "Only their section, such as sales or marketing.", "فقط بخش خودش، مثل فروش یا بازاریابی."],
  ["team", "Their team", "تیم خودش", "Only records of their own team.", "فقط رکوردهای تیم خودش."],
  ["self", "Only their own", "فقط کار خودش", "Only records they own or were added to.", "فقط کارهایی که خودش صاحب آن‌هاست یا در آن‌هاست."],
];

/** جملهٔ هر تیک: این مجوز دقیقاً چه کاری را باز می‌کند. */
const PERM_COPY: Record<string, [string, string]> = {
  "org.admin": [
    "Opens the admin page and skips the other ticks. Daily work in other sections stays hidden.",
    "صفحهٔ مدیریت را باز می‌کند و بقیهٔ تیک‌ها را هم دور می‌زند. کار روزمرهٔ بخش‌های دیگر را نشان نمی‌دهد.",
  ],
  "user.read": [
    "See colleagues and which team each person is on.",
    "همکاران را ببیند و بداند هر کس در کدام تیم است.",
  ],
  "user.write": [
    "Add a person, turn an account on or off, and set a password.",
    "فرد اضافه کند، حساب را فعال یا غیرفعال کند و رمز بگذارد.",
  ],
  "relationship.write": [
    "Set who manages whom.",
    "مشخص کند چه کسی مدیر چه کسی است.",
  ],
  "conversation.read": [
    "Open messages.",
    "پیام‌ها را باز کند.",
  ],
  "conversation.write": [
    "Send a message and start a conversation.",
    "پیام بفرستد و گفتگو شروع کند.",
  ],
  "work_item.read": [
    "See projects in their section.",
    "پروژه‌های بخش خودش را ببیند.",
  ],
  "work_item.write": [
    "Create a project and change it.",
    "پروژه بسازد و آن را تغییر دهد.",
  ],
  "case.read": [
    "See cases: a customer, a branch request, or a deadline.",
    "پرونده‌ها را ببیند: مشتری، درخواست شعبه، یا یک مهلت.",
  ],
  "case.write": [
    "Open a case and change its status or owner.",
    "پرونده باز کند و وضعیت یا مسئولش را عوض کند.",
  ],
  "task.read": [
    "See the to-dos on their list.",
    "کارهایی را که باید انجام شود ببیند.",
  ],
  "task.write": [
    "Add a to-do and mark it done.",
    "کار جدید اضافه کند و آن را انجام‌شده کند.",
  ],
  "task.assign": [
    "Give a to-do to a person or a team.",
    "یک کار را به یک نفر یا یک تیم بسپارد.",
  ],
  "task.delegate": [
    "Hand a to-do to someone else; the handover stays on record.",
    "کاری را که خودش دارد به فرد دیگری واگذار کند و این واگذاری ثبت شود.",
  ],
  "notification.read": [
    "See their notifications.",
    "اعلان‌های خودش را ببیند.",
  ],
  "event.read": [
    "Open reports and the activity history.",
    "گزارش‌ها و تاریخچهٔ فعالیت را باز کند.",
  ],
  "sla.manage": [
    "Set a deadline and what happens when it passes.",
    "مهلت بگذارد و تعیین کند اگر مهلت بگذرد چه شود.",
  ],
  "inventory.read": [
    "See the vehicles.",
    "خودروها را ببیند.",
  ],
  "inventory.write": [
    "Add a vehicle and change its details or status.",
    "خودرو اضافه کند و مشخصات یا وضعیتش را عوض کند.",
  ],
  "search.run": [
    "Use the search box.",
    "از جعبهٔ جستجو استفاده کند.",
  ],
  "rag.read": [
    "Ask the assistant a question that uses the company guides.",
    "از دستیار سؤالی بپرسد که جوابش از راهنماهای شرکت می‌آید.",
  ],
  "rag.index": [
    "Rebuild the search behind those guides after they change.",
    "بعد از تغییر راهنماها، جستجوی پشت آن‌ها را از نو بسازد.",
  ],
  "agent.run": [
    "Tell the assistant, in a sentence, to create a project and to-dos.",
    "با یک جمله به دستیار بگوید پروژه و کارها را بسازد.",
  ],
  "kb.read": [
    "Read the company rules and guides.",
    "قوانین و راهنماهای شرکت را بخواند.",
  ],
  "kb.write": [
    "Add or edit a rule or guide.",
    "قانون یا راهنما اضافه یا ویرایش کند.",
  ],
  "customer.read": [
    "See customers.",
    "مشتریان را ببیند.",
  ],
  "customer.write": [
    "Add a customer and edit their details.",
    "مشتری اضافه کند و مشخصاتش را ویرایش کند.",
  ],
  "campaign.read": [
    "See ad campaigns.",
    "کمپین‌های تبلیغاتی را ببیند.",
  ],
  "campaign.write": [
    "Create an ad campaign and change it.",
    "کمپین تبلیغاتی بسازد و آن را تغییر دهد.",
  ],
  "price.write": [
    "Confirm the sale price of a car, including the price used in a scheduled post.",
    "قیمت فروش خودرو را ثبت کند، از جمله قیمتی که برای یک پست زمان‌دار استفاده می‌شود.",
  ],
  "perf.read": [
    "See performance campaigns, SMS, stories and payments.",
    "کمپین، پیامک، استوری و پرداخت پرفورمنس را ببیند.",
  ],
  "perf.write": [
    "Create campaigns, SMS lists and payment requests.",
    "کمپین، لیست پیامک و درخواست پرداخت بسازد.",
  ],
  "perf.approve": [
    "Approve a performance payment before finance.",
    "درخواست پرداخت پرفورمنس را قبل از مالی تأیید کند.",
  ],
};

const PERM_GROUPS: Array<{ en: string; fa: string; codes: string[] }> = [
  {
    en: "General",
    fa: "عمومی",
    codes: ["conversation.read", "conversation.write", "notification.read", "search.run", "user.read"],
  },
  {
    en: "Projects and to-dos",
    fa: "پروژه و کار",
    codes: ["work_item.read", "work_item.write", "task.read", "task.write", "task.assign", "task.delegate"],
  },
  {
    en: "Cases and customers",
    fa: "پرونده و مشتری",
    codes: ["case.read", "case.write", "customer.read", "customer.write"],
  },
  {
    en: "Marketing",
    fa: "بازاریابی",
    codes: ["campaign.read", "campaign.write"],
  },
  {
    en: "Performance",
    fa: "پرفورمنس",
    codes: ["perf.read", "perf.write", "perf.approve"],
  },
  {
    en: "Finance",
    fa: "مالی",
    codes: ["price.write"],
  },
  {
    en: "Vehicles",
    fa: "خودرو",
    codes: ["inventory.read", "inventory.write"],
  },
  {
    en: "Guides and assistant",
    fa: "راهنما و دستیار",
    codes: ["kb.read", "kb.write", "rag.read", "rag.index", "agent.run"],
  },
  {
    en: "Administration",
    fa: "مدیریت",
    codes: ["org.admin", "user.write", "relationship.write", "event.read", "sla.manage"],
  },
];

type AdminTab = "overview" | "analytics" | "people" | "monitoring" | "audit";

const TAB_COPY: Record<AdminTab, [string, string]> = {
  overview: [
    "Where the organization stands right now, and what needs a person.",
    "وضعیت همین لحظهٔ سازمان، و کارهایی که یک نفر باید انجام دهد.",
  ],
  analytics: [
    "How each area moved recently: tasks, replies, cases, stock, and audit.",
    "روند اخیر هر بخش: کارها، پاسخ‌ها، پرونده‌ها، موجودی و ممیزی.",
  ],
  people: [
    "Add a person, turn an account on or off, and decide what each role can see.",
    "افزودن فرد، فعال یا غیرفعال کردن حساب، و تعیین اینکه هر نقش چه چیزی ببیند.",
  ],
  monitoring: [
    "Is the system healthy? This refreshes itself every 15 seconds.",
    "آیا سیستم سالم است؟ این صفحه هر ۱۵ ثانیه خودش تازه می‌شود.",
  ],
  audit: [
    "Who did what, and when. Narrow the list, then export it if you need a record.",
    "چه کسی، چه کاری، چه زمانی. فهرست را محدود کنید و اگر سند می‌خواهید خروجی بگیرید.",
  ],
};

const PRIORITY_FA: Record<string, [string, string]> = {
  LOW: ["Low", "کم"],
  MEDIUM: ["Medium", "متوسط"],
  HIGH: ["High", "زیاد"],
  URGENT: ["Urgent", "فوری"],
};

const CASE_STATUS_FA: Record<string, [string, string]> = {
  OPEN: ["Open", "باز"],
  ASSIGNED: ["Assigned", "ارجاع‌شده"],
  IN_PROGRESS: ["In progress", "در حال انجام"],
  WAITING_FOR_RESPONSE: ["Waiting for reply", "در انتظار پاسخ"],
  WAITING_FOR_USER: ["Waiting on user", "در انتظار کاربر"],
  COMPLETED: ["Done", "انجام‌شده"],
  CANCELLED: ["Cancelled", "لغو‌شده"],
  ESCALATED: ["Escalated", "ارجاع به بالا"],
};

const CASE_TYPE_FA: Record<string, [string, string]> = {
  GENERAL_OPERATIONAL_REQUEST: ["Operational request", "درخواست عملیاتی"],
  BRANCH_REQUEST: ["Branch request", "درخواست شعبه"],
  BUYER_REQUEST: ["Buyer request", "درخواست خریدار"],
  SELLER_REQUEST: ["Seller request", "درخواست فروشنده"],
  FOLLOW_UP: ["Follow-up", "پیگیری"],
  INVENTORY_OPPORTUNITY: ["Stock opportunity", "فرصت موجودی"],
  CUSTOMER_INTEREST: ["Customer interest", "علاقهٔ مشتری"],
  TRANSFER: ["Transfer", "انتقال"],
  ESCALATION: ["Escalation", "ارجاع به بالا"],
};

const VEHICLE_FA: Record<string, [string, string]> = {
  IN_STOCK: ["In stock", "موجود"],
  RESERVED: ["Reserved", "رزرو"],
  SOLD: ["Sold", "فروخته‌شده"],
};

const TABLE_FA: Record<string, [string, string]> = {
  users: ["People", "کاربران"],
  tasks: ["To-dos", "کارها"],
  work_items: ["Projects", "پروژه‌ها"],
  messages: ["Messages", "پیام‌ها"],
  cases: ["Cases", "پرونده‌ها"],
  vehicles: ["Vehicles", "خودروها"],
  audit_logs: ["Audit rows", "ردیف‌های ممیزی"],
  events: ["Events", "رویدادها"],
};

const MSG_CHANNEL: Record<string, [string, string]> = {
  TELEGRAM: ["Telegram", "تلگرام"],
  WEB: ["Web", "وب"],
  SYSTEM: ["System", "سیستم"],
  WHATSAPP: ["WhatsApp", "واتساپ"],
  EMAIL: ["Email", "ایمیل"],
  PHONE: ["Phone", "تلفن"],
};

const CHANNEL_FA: Record<string, [string, string]> = {
  sms_mode: ["SMS", "پیامک"],
  email_mode: ["Email", "ایمیل"],
  voip_mode: ["Phone calls", "تماس"],
  erp_mode: ["Accounting", "حسابداری"],
  divar_mode: ["Divar listings", "آگهی دیوار"],
  telegram_mode: ["Telegram", "تلگرام"],
  bale_mode: ["Bale", "بله"],
  worker_mode: ["Background jobs", "کارهای پس‌زمینه"],
};

const MODE_FA: Record<string, [string, string]> = {
  live: ["Live", "واقعی"],
  stub: ["Test only", "فقط آزمایشی"],
  mock: ["Simulated", "شبیه‌سازی"],
  off: ["Off", "خاموش"],
  disabled: ["Off", "خاموش"],
};

const EVENT_FA: Record<string, [string, string]> = {
  "sla.escalated": ["Deadline escalated", "مهلت به مدیر ارجاع شد"],
  "sla.breached": ["Deadline missed", "مهلت رد شد"],
  "sla.warning": ["Deadline close", "مهلت نزدیک است"],
};

const JOB_FA: Record<string, [string, string]> = {
  poll_telegram: ["Check Telegram", "بررسی پیام‌های تلگرام"],
};

const SECTION_FA: Record<string, [string, string]> = {
  task: ["To-do", "کار"],
  work_item: ["Project", "پروژه"],
  case: ["Case", "پرونده"],
  conversation: ["Conversation", "گفتگو"],
  message: ["Message", "پیام"],
  vehicle: ["Vehicle", "خودرو"],
  customer: ["Customer", "مشتری"],
  user: ["Person", "کاربر"],
  approval: ["Approval", "تأیید"],
  auth: ["Sign-in", "ورود"],
};

const EVENT_ABOUT: Record<string, [string, string]> = {
  ...EVENT_FA,
  "task.assigned": ["To-do assigned", "کار ارجاع شد"],
  "task.completed": ["To-do finished", "کار انجام شد"],
  "case.created": ["Case opened", "پرونده باز شد"],
  "message.created": ["New message", "پیام جدید"],
  "approval.requested": ["Approval requested", "درخواست تأیید"],
};

function entityHref(row: {
  entity_type?: string | null;
  entity_id?: string | null;
  work_item_id?: string | null;
  conversation_id?: string | null;
}): string | null {
  const type = (row.entity_type || "").toLowerCase();
  const id = row.entity_id || null;
  if (row.conversation_id) return `/communication?c=${row.conversation_id}`;
  if (type === "conversation" && id) return `/communication?c=${id}`;
  if (type === "work_item" && id) return `/work-items/${id}`;
  if ((type === "task" || type === "case") && row.work_item_id) return `/work-items/${row.work_item_id}`;
  if (type === "case" && id) return `/cases?c=${id}`;
  if (type === "vehicle" && id) return `/vehicles/${id}`;
  if (type === "approval") return "/approvals";
  if (type === "user" && id) return "/people";
  if (row.work_item_id) return `/work-items/${row.work_item_id}`;
  return null;
}

function RecordLink({
  href,
  children,
}: {
  href: string | null;
  children: ReactNode;
}) {
  if (!href) return <span>{children}</span>;
  return (
    <Link to={href} className="record-link">
      {children}
    </Link>
  );
}

function named(
  bi: (en: string, fa: string) => string,
  map: Record<string, [string, string]>,
  key: string,
): string {
  const hit = map[key] ?? map[key.toUpperCase()];
  return hit ? bi(hit[0], hit[1]) : key.replaceAll("_", " ");
}

function present(rows: Array<{ label: string; value: number }>) {
  return rows.filter((row) => row.value > 0);
}

/** قدم بعدی، فقط وقتی واقعاً کاری هست — لینک یا هشدار کوتاه. */
function Guide({
  items,
}: {
  items: Array<{ to?: string; text: ReactNode }>;
}) {
  if (items.length === 0) return null;
  return (
    <div className="admin-guide">
      {items.map((item, index) =>
        item.to ? (
          <Link key={index} to={item.to} className="admin-guide-link">
            {item.text}
          </Link>
        ) : (
          <span key={index} className="admin-guide-note">
            {item.text}
          </span>
        ),
      )}
    </div>
  );
}

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
        description={<Bi en={TAB_COPY[tab][0]} fa={TAB_COPY[tab][1]} />}
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
        <SectionHeader
          icon="plus"
          title={<Bi en="New user" fa="کاربر جدید" />}
          hint={
            <Bi
              en="They sign in with this email and password. You can change the password later."
              fa="با همین ایمیل و رمز وارد می‌شوند. رمز را بعداً هم می‌توانید عوض کنید."
            />
          }
        />
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
        <SectionHeader
          icon="users"
          title={<Bi en="People" fa="کاربران" />}
          count={people.length}
          hint={
            <Bi
              en="Deactivate to block sign-in. Reset password or add them to a team from the row."
              fa="غیرفعال کردن یعنی دیگر نمی‌تواند وارد شود. بازنشانی رمز و افزودن به تیم از همان ردیف است."
            />
          }
        />
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
          <Table className="table-fit"
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
        <SectionHeader
          icon="check"
          title={<Bi en="Role permissions" fa="مجوزهای نقش" />}
          hint={
            <Bi
              en="Each tick is one thing this role is allowed to do, written in plain words."
              fa="هر تیک یک کار است که این نقش اجازهٔ انجامش را دارد، به زبان ساده."
            />
          }
        />
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
  const [messagesOpen, setMessagesOpen] = useState(false);
  const [trendOpen, setTrendOpen] = useState(false);
  const [recordPop, setRecordPop] = useState<{
    kind: string;
    days?: number;
    group?: string;
    groupBy: string;
    bucket?: string;
    title: ReactNode;
  } | null>(null);
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

  const guide: Array<{ to?: string; text: ReactNode }> = [];
  if (d.conversations_waiting_reply > 0) {
    guide.push({
      to: "/communication",
      text: (
        <Bi
          en={`${d.conversations_waiting_reply} conversations need a reply`}
          fa={`${d.conversations_waiting_reply} گفتگو منتظر پاسخ است`}
        />
      ),
    });
  }
  if (d.approvals_pending > 0) {
    guide.push({
      to: "/approvals",
      text: (
        <Bi
          en={`${d.approvals_pending} approvals waiting`}
          fa={`${d.approvals_pending} تأیید منتظر تصمیم است`}
        />
      ),
    });
  }
  if (d.cases.sla_breached > 0) {
    guide.push({
      to: "/cases",
      text: (
        <Bi
          en={`${d.cases.sla_breached} cases missed their deadline`}
          fa={`${d.cases.sla_breached} پرونده از مهلت گذشته`}
        />
      ),
    });
  }

  return (
    <>
      <Guide items={guide} />
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
          onMore={() =>
            setRecordPop({
              kind: "users",
              groupBy: "user_status",
              title: <Bi en="Active users" fa="کاربران فعال" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
        <StatCard
          icon="message"
          tone="accent"
          label={<Bi en="Messages · 7 days" fa="پیام‌ها · ۷ روز" />}
          value={`${d.messages_7d}`}
          onMore={() => setMessagesOpen(true)}
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
        <StatCard
          icon="chat"
          tone={d.conversations_waiting_reply > 0 ? "warn" : "ok"}
          label={<Bi en="Waiting for reply" fa="منتظر پاسخ" />}
          value={`${d.conversations_waiting_reply}`}
          onMore={() =>
            setRecordPop({
              kind: "waiting",
              groupBy: "state",
              title: <Bi en="Waiting for reply" fa="منتظر پاسخ" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
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
          onMore={() =>
            setRecordPop({
              kind: "replies",
              groupBy: "bucket",
              title: <Bi en="Avg first reply" fa="میانگین اولین پاسخ" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
      </div>

      <div className="kpi-row kpi-row--4 kpi-row--even">
        <StatCard
          icon="briefcase"
          tone="accent"
          label={<Bi en="Open cases" fa="پرونده‌های باز" />}
          value={`${d.cases.open}`}
          onMore={() =>
            setRecordPop({
              kind: "cases_open",
              groupBy: "case_status",
              title: <Bi en="Open cases" fa="پرونده‌های باز" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
        <StatCard
          icon="alert"
          tone={d.cases.sla_breached > 0 ? "danger" : "ok"}
          label={<Bi en="SLA breached" fa="SLA نقض‌شده" />}
          value={`${d.cases.sla_breached}`}
          onMore={() =>
            setRecordPop({
              kind: "cases_sla",
              groupBy: "sla",
              title: <Bi en="SLA breached" fa="SLA نقض‌شده" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
        <StatCard
          icon="check"
          tone={d.approvals_pending > 0 ? "warn" : "ok"}
          label={<Bi en="Pending approvals" fa="تأییدهای منتظر" />}
          value={`${d.approvals_pending}`}
          onMore={() =>
            setRecordPop({
              kind: "approvals",
              groupBy: "kind",
              title: <Bi en="Pending approvals" fa="تأییدهای منتظر" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
        <StatCard
          icon="alert"
          tone={d.divar_errors > 0 ? "danger" : "ok"}
          label={<Bi en="Divar errors" fa="خطاهای دیوار" />}
          value={`${d.divar_errors}`}
          onMore={() =>
            setRecordPop({
              kind: "divar",
              groupBy: "divar_status",
              title: <Bi en="Divar errors" fa="خطاهای دیوار" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
      </div>

      <Card>
        <SectionHeader
          icon="car"
          title={<Bi en="Vehicles" fa="خودروها" />}
          hint={
            <Bi
              en="In stock can be sold. Reserved is held for a buyer. Sold has left the yard."
              fa="موجود قابل فروش است. رزرو برای یک خریدار نگه داشته شده. فروخته از انبار خارج شده."
            />
          }
        />
        <div className="kpi-row kpi-row--3 kpi-row--even">
          <StatCard
            icon="car"
            tone="ok"
            label={<Bi en="In stock" fa="موجود" />}
            value={`${d.vehicles.in_stock}`}
            onMore={() =>
              setRecordPop({
                kind: "vehicles",
                groupBy: "vehicle_status",
                bucket: "IN_STOCK",
                title: <Bi en="In stock" fa="موجود" />,
              })
            }
            moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
          />
          <StatCard
            icon="clock"
            tone="warn"
            label={<Bi en="Reserved" fa="رزرو" />}
            value={`${d.vehicles.reserved}`}
            onMore={() =>
              setRecordPop({
                kind: "vehicles",
                groupBy: "vehicle_status",
                bucket: "RESERVED",
                title: <Bi en="Reserved" fa="رزرو" />,
              })
            }
            moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
          />
          <StatCard
            icon="check"
            tone="accent"
            label={<Bi en="Sold" fa="فروخته" />}
            value={`${d.vehicles.sold}`}
            onMore={() =>
              setRecordPop({
                kind: "vehicles",
                groupBy: "vehicle_status",
                bucket: "SOLD",
                title: <Bi en="Sold" fa="فروخته" />,
              })
            }
            moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
          />
        </div>
      </Card>

      <div className="grid grid-2">
        <Card padded={false}>
          <SectionHeader
            icon="branch"
            title={<Bi en="Open tasks by branch" fa="کارهای باز به تفکیک شعبه" />}
            count={d.tasks_by_branch.length}
            hint={
              <Bi
                en="Overdue means the deadline has already passed."
                fa="عقب‌افتاده یعنی مهلتش گذشته و هنوز باز است."
              />
            }
            action={
              <MoreButton
                onClick={() =>
                  setRecordPop({
                    kind: "tasks",
                    group: "branch",
                    groupBy: "branch",
                    title: <Bi en="Open tasks by branch" fa="کارهای باز به تفکیک شعبه" />,
                  })
                }
              />
            }
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
            <Table className="table-fit"
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
            hint={
              <Bi
                en="Who is carrying the most open to-dos right now."
                fa="چه کسی همین حالا بیشترین کار باز را دارد."
              />
            }
            action={
              <MoreButton
                onClick={() =>
                  setRecordPop({
                    kind: "tasks",
                    group: "assignee",
                    groupBy: "assignee",
                    title: <Bi en="Busiest people" fa="پرکارترین‌ها" />,
                  })
                }
              />
            }
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
            <Table className="table-fit"
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
        <SectionHeader
          icon="activity"
          title={<Bi en="Weekly trend · open tasks" fa="روند هفتگی · کارهای باز" />}
          hint={
            <Bi
              en="Each bar is one weekly snapshot saved by the background worker."
              fa="هر ستون یک عکس هفتگی است که کار پس‌زمینه ذخیره کرده."
            />
          }
          action={<MoreButton onClick={() => setTrendOpen(true)} />}
        />
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
      {messagesOpen ? (
        <MessageDetail
          days={7}
          title={<Bi en="Messages · 7 days" fa="پیام‌ها · ۷ روز" />}
          onClose={() => setMessagesOpen(false)}
        />
      ) : null}
      {trendOpen ? <TrendDetail trend={d.trend} onClose={() => setTrendOpen(false)} /> : null}
      {recordPop ? (
        <RecordsDetail
          kind={recordPop.kind}
          days={recordPop.days}
          group={recordPop.group}
          groupBy={recordPop.groupBy}
          bucket={recordPop.bucket}
          title={recordPop.title}
          onClose={() => setRecordPop(null)}
        />
      ) : null}
    </>
  );
}

function MoreButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="kpi-more" onClick={onClick}>
      <Bi en="Show more" fa="نمایش بیشتر" />
    </button>
  );
}

function DetailShell({
  title,
  count,
  onClose,
  children,
}: {
  title: ReactNode;
  count?: number;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="detail-pop" role="dialog" aria-modal="true">
      <button type="button" className="detail-pop-backdrop" onClick={onClose} />
      <div className="detail-pop-card">
        <SectionHeader
          title={title}
          count={count}
          action={
            <button type="button" className="kpi-more" onClick={onClose}>
              <Bi en="Close" fa="بستن" />
            </button>
          }
        />
        {children}
      </div>
    </div>
  );
}

function MessageDetail({
  days,
  title,
  onClose,
}: {
  days: number;
  title: ReactNode;
  onClose: () => void;
}) {
  const bi = useBi();
  const query = useQuery({
    queryKey: ["admin", "messages", days],
    queryFn: () => api.admin.messages({ days }),
  });
  const [q, setQ] = useState("");
  const [channel, setChannel] = useState("");
  const [day, setDay] = useState("");
  const rows = query.data ?? [];
  const needle = q.trim().toLowerCase();
  const filtered = rows.filter((row) => {
    if (channel && row.channel !== channel) return false;
    if (day && !row.at.startsWith(day)) return false;
    if (!needle) return true;
    return `${row.text} ${row.topic} ${row.sender}`.toLowerCase().includes(needle);
  });
  const dayOptions = [...new Set(rows.map((row) => row.at.slice(0, 10)).filter(Boolean))];
  const channelOptions = [...new Set(rows.map((row) => row.channel).filter(Boolean))];

  return (
    <DetailShell title={title} count={query.isSuccess ? filtered.length : undefined} onClose={onClose}>
      <div className="detail-filters">
        <Input
          value={q}
          placeholder={bi("Search text, topic, or sender", "جستجو در متن، موضوع یا فرستنده")}
          onChange={(event) => setQ(event.target.value)}
        />
        <Select value={channel} onChange={(event) => setChannel(event.target.value)}>
          <option value="">{bi("All channels", "همه کانال‌ها")}</option>
          {channelOptions.map((value) => (
            <option key={value} value={value}>
              {named(bi, MSG_CHANNEL, value)}
            </option>
          ))}
        </Select>
        <Select value={day} onChange={(event) => setDay(event.target.value)}>
          <option value="">{bi("All days", "همه روزها")}</option>
          {dayOptions.map((value) => (
            <option key={value} value={value}>
              {shortDay(value)}
            </option>
          ))}
        </Select>
      </div>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorMessage error={String((query.error as Error)?.message ?? "")} />
      ) : null}
      {query.isSuccess && filtered.length === 0 ? (
        <EmptyState
          titleEn="No messages in this filter"
          titleFa="پیامی با این فیلتر نیست"
          bodyEn="Clear the search or pick another channel or day."
          bodyFa="جستجو را پاک کنید یا کانال و روز دیگری را انتخاب کنید."
        />
      ) : null}
      {filtered.length > 0 ? (
        <Table
          className="table-fit"
          rows={filtered}
          rowKey={(row: AdminMessage) => row.id}
          columns={[
            {
              key: "text",
              header: <Bi en="Message" fa="پیام" />,
              render: (row: AdminMessage) => (
                <span className="cell-stack">
                  <RecordLink href={`/communication?c=${row.conversation_id}`}>
                    {row.text || row.topic || bi("Open conversation", "باز کردن گفتگو")}
                  </RecordLink>
                  {row.topic && row.topic !== row.text ? (
                    <Muted className="cell-sub">{row.topic}</Muted>
                  ) : null}
                </span>
              ),
            },
            {
              key: "sender",
              header: <Bi en="Sender" fa="فرستنده" />,
              render: (row: AdminMessage) => row.sender || "–",
            },
            {
              key: "channel",
              header: <Bi en="Channel" fa="کانال" />,
              render: (row: AdminMessage) => named(bi, MSG_CHANNEL, row.channel),
            },
            {
              key: "at",
              header: <Bi en="When" fa="زمان" />,
              render: (row: AdminMessage) => <DateText value={row.at} withTime />,
            },
          ]}
        />
      ) : null}
    </DetailShell>
  );
}

function RefDetail({
  title,
  groups,
  initialBucket = "",
  onClose,
}: {
  title: ReactNode;
  groups: Array<{ key: string; label: string; rows: AdminRef[] }>;
  initialBucket?: string;
  onClose: () => void;
}) {
  const bi = useBi();
  const [q, setQ] = useState("");
  const [bucket, setBucket] = useState(initialBucket);
  const needle = q.trim().toLowerCase();
  const filtered = groups.flatMap((group) => {
    if (bucket && group.key !== bucket) return [];
    return group.rows
      .filter((row) => {
        if (!needle) return true;
        return `${row.title} ${row.detail}`.toLowerCase().includes(needle);
      })
      .map((row) => ({ ...row, bucketKey: group.key, bucketLabel: group.label }));
  });

  return (
    <DetailShell title={title} count={filtered.length} onClose={onClose}>
      <div className="detail-filters">
        <Input
          value={q}
          placeholder={bi("Search title", "جستجو در عنوان")}
          onChange={(event) => setQ(event.target.value)}
        />
        {groups.length > 1 ? (
          <Select value={bucket} onChange={(event) => setBucket(event.target.value)}>
            <option value="">{bi("All groups", "همه گروه‌ها")}</option>
            {groups.map((group) => (
              <option key={group.key} value={group.key}>
                {group.label}
              </option>
            ))}
          </Select>
        ) : null}
      </div>
      {filtered.length === 0 ? (
        <EmptyState
          titleEn="Nothing in this filter"
          titleFa="موردی با این فیلتر نیست"
          bodyEn="Clear the search or pick another group."
          bodyFa="جستجو را پاک کنید یا گروه دیگری را انتخاب کنید."
        />
      ) : (
        <Table
          className="table-fit"
          rows={filtered}
          rowKey={(row) => `${row.bucketKey}-${row.entity_type}-${row.entity_id}-${row.title}`}
          columns={[
            {
              key: "title",
              header: <Bi en="What" fa="موضوع" />,
              render: (row) => (
                <span className="cell-stack">
                  <RecordLink href={entityHref(row)}>{row.title}</RecordLink>
                  {row.detail ? <Muted className="cell-sub">{row.detail}</Muted> : null}
                </span>
              ),
            },
            {
              key: "group",
              header: <Bi en="Group" fa="گروه" />,
              render: (row) => row.bucketLabel,
            },
            {
              key: "section",
              header: <Bi en="Section" fa="بخش" />,
              render: (row) => named(bi, SECTION_FA, row.entity_type),
            },
          ]}
        />
      )}
    </DetailShell>
  );
}

function refGroups(
  map: Record<string, AdminRef[]> | undefined,
  labelOf: (key: string) => string,
): Array<{ key: string; label: string; rows: AdminRef[] }> {
  return Object.entries(map ?? {})
    .filter(([, rows]) => rows.length > 0)
    .map(([key, rows]) => ({ key, label: labelOf(key), rows }));
}

function recordFacetLabel(
  bi: (en: string, fa: string) => string,
  facet: string,
  key: string,
): string {
  if (!key) return bi("All", "همه");
  if (facet === "day") return shortDay(key);
  if (facet === "user_status") {
    return named(bi, {
      active: ["Active", "فعال"],
      inactive: ["Inactive", "غیرفعال"],
      locked: ["Locked", "قفل‌شده"],
    }, key);
  }
  if (facet === "bucket") {
    return named(bi, {
      lt5: ["Under 5 min", "زیر ۵ دقیقه"],
      lt30: ["5–30 min", "۵ تا ۳۰ دقیقه"],
      lt120: ["30–120 min", "۳۰ تا ۱۲۰ دقیقه"],
      gt120: ["Over 2 hours", "بیش از ۲ ساعت"],
      no_reply: ["No reply", "بی‌پاسخ"],
    }, key);
  }
  if (facet === "case_status") return named(bi, CASE_STATUS_FA, key);
  if (facet === "case_type") return named(bi, CASE_TYPE_FA, key);
  if (facet === "sla") {
    return named(bi, {
      NONE: ["No SLA", "بدون SLA"],
      ACTIVE: ["On track", "در مهلت"],
      WARNING: ["Nearing deadline", "نزدیک مهلت"],
      BREACHED: ["Breached", "نقض‌شده"],
      ESCALATED: ["Escalated", "ارجاع به بالا"],
    }, key);
  }
  if (facet === "vehicle_status") return named(bi, VEHICLE_FA, key);
  if (facet === "priority") return named(bi, PRIORITY_FA, key);
  if (facet === "overdue") {
    return named(bi, { yes: ["Overdue", "عقب‌افتاده"], no: ["On time", "در مهلت"] }, key);
  }
  if (facet === "action" || facet === "event") return named(bi, EVENT_ABOUT, key);
  if (facet === "outbox_status") {
    return named(bi, { failed: ["Did not arrive", "نرسید"], pending: ["Queued", "در صف"] }, key);
  }
  if (facet === "state") return bi("Waiting", "منتظر پاسخ");
  return key;
}

function RecordsDetail({
  kind,
  days,
  group,
  groupBy,
  bucket,
  title,
  onClose,
}: {
  kind: string;
  days?: number;
  group?: string;
  groupBy: string;
  bucket?: string;
  title: ReactNode;
  onClose: () => void;
}) {
  const bi = useBi();
  const query = useQuery({
    queryKey: ["admin", "records", kind, days ?? 0, group ?? ""],
    queryFn: () => api.admin.records({ kind, days, group }),
  });
  if (!query.isSuccess) {
    return (
      <DetailShell title={title} onClose={onClose}>
        {query.isLoading ? <LoadingState /> : <ErrorMessage error={String((query.error as Error)?.message ?? "")} />}
      </DetailShell>
    );
  }
  const grouped = new Map<string, AdminRecord[]>();
  for (const row of query.data) {
    const key = row.facets[groupBy] || "";
    grouped.set(key, [...(grouped.get(key) ?? []), row]);
  }
  return (
    <RefDetail
      title={title}
      initialBucket={bucket}
      onClose={onClose}
      groups={[...grouped.entries()].map(([key, rows]) => ({
        key,
        label: recordFacetLabel(bi, groupBy, key),
        rows,
      }))}
    />
  );
}

function TrendDetail({
  trend,
  onClose,
}: {
  trend: Array<{ week: number | null; date: string | null; kpis: Record<string, number | string> }>;
  onClose: () => void;
}) {
  const bi = useBi();
  const [week, setWeek] = useState("");
  const metricLabel: Record<string, [string, string]> = {
    open_tasks: ["Open to-dos", "کارهای باز"],
    vehicles: ["Vehicles", "خودروها"],
    cases: ["Cases", "پرونده‌ها"],
    work_items: ["Projects", "پروژه‌ها"],
  };
  const rows = trend.flatMap((snapshot) =>
    Object.entries(snapshot.kpis).map(([metric, value]) => ({
      id: `${snapshot.date ?? snapshot.week}-${metric}`,
      week: snapshot.week == null ? "" : String(snapshot.week),
      date: snapshot.date ?? "",
      metric,
      value: String(value),
    })),
  );
  const weeks = [...new Set(rows.map((row) => row.week).filter(Boolean))];
  const filtered = rows.filter((row) => !week || row.week === week);
  return (
    <DetailShell
      title={<Bi en="Weekly trend · open tasks" fa="روند هفتگی · کارهای باز" />}
      count={filtered.length}
      onClose={onClose}
    >
      <div className="detail-filters">
        <Select value={week} onChange={(event) => setWeek(event.target.value)}>
          <option value="">{bi("All weeks", "همه هفته‌ها")}</option>
          {weeks.map((value) => (
            <option key={value} value={value}>
              {bi(`Week ${value}`, `هفته ${value}`)}
            </option>
          ))}
        </Select>
      </div>
      {filtered.length === 0 ? (
        <EmptyState
          titleEn="No snapshots yet"
          titleFa="هنوز اسنپ‌شاتی نیست"
          bodyEn="The worker stores one KPI snapshot per week."
          bodyFa="worker هر هفته یک اسنپ‌شات KPI ذخیره می‌کند."
        />
      ) : (
        <Table
          className="table-fit"
          rows={filtered}
          rowKey={(row) => row.id}
          columns={[
            {
              key: "week",
              header: <Bi en="Week" fa="هفته" />,
              render: (row) => (row.week ? bi(`Week ${row.week}`, `هفته ${row.week}`) : "–"),
            },
            {
              key: "date",
              header: <Bi en="Date" fa="تاریخ" />,
              render: (row) => <DateText value={row.date} />,
            },
            {
              key: "metric",
              header: <Bi en="Measure" fa="سنجه" />,
              render: (row) => named(bi, metricLabel, row.metric),
            },
            { key: "value", header: <Bi en="Value" fa="مقدار" />, render: (row) => row.value },
          ]}
        />
      )}
    </DetailShell>
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
  const [messagesOpen, setMessagesOpen] = useState(false);
  const [refs, setRefs] = useState<{
    title: ReactNode;
    groups: Array<{ key: string; label: string; rows: AdminRef[] }>;
  } | null>(null);
  const [recordPop, setRecordPop] = useState<{
    kind: string;
    days?: number;
    group?: string;
    groupBy: string;
    bucket?: string;
    title: ReactNode;
  } | null>(null);
  const query = useQuery({
    queryKey: ["admin", "analytics"],
    queryFn: () => api.admin.analytics(),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data) {
    return <ErrorMessage error={String((query.error as Error)?.message ?? "")} />;
  }
  const d = query.data;
  const priorities = present(
    rankedEntries(d.tasks_by_priority).map((row) => ({
      label: named(bi, PRIORITY_FA, row.label),
      value: row.value,
    })),
  );
  const caseStatuses = present(
    rankedEntries(d.cases_by_status).map((row) => ({
      label: named(bi, CASE_STATUS_FA, row.label),
      value: row.value,
    })),
  );
  const caseTypes = present(
    rankedEntries(d.cases_by_type).map((row) => ({
      label: named(bi, CASE_TYPE_FA, row.label),
      value: row.value,
    })),
  );
  const aging = present([
    { label: bi("< 7 days", "کمتر از ۷ روز"), value: d.vehicles_aging.lt7 },
    { label: bi("7–30 days", "۷ تا ۳۰ روز"), value: d.vehicles_aging.lt30 },
    { label: bi("30–90 days", "۳۰ تا ۹۰ روز"), value: d.vehicles_aging.lt90 },
    { label: bi("> 90 days", "بیش از ۹۰ روز"), value: d.vehicles_aging.gt90 },
  ]);
  const stockValue = present(
    rankedEntries(d.vehicles_value_by_status).map((row) => ({
      label: named(bi, VEHICLE_FA, row.label),
      value: row.value,
    })),
  );
  const replies = present([
    { label: bi("< 5 min", "زیر ۵ دقیقه"), value: d.reply_buckets.lt5 },
    { label: bi("5–30 min", "۵ تا ۳۰ دقیقه"), value: d.reply_buckets.lt30 },
    { label: bi("30–120 min", "۳۰ تا ۱۲۰ دقیقه"), value: d.reply_buckets.lt120 },
    { label: bi("> 2 hours", "بیش از ۲ ساعت"), value: d.reply_buckets.gt120 },
    { label: bi("No reply", "بی‌پاسخ"), value: d.reply_buckets.no_reply },
  ]);

  return (
    <>
      <Guide
        items={[
          ...(d.tasks_overdue > 0
            ? [
                {
                  to: "/my-work",
                  text: (
                    <Bi
                      en="Close overdue to-dos from My Work"
                      fa="کارهای عقب‌افتاده را از «کارهای من» ببندید"
                    />
                  ),
                },
              ]
            : []),
          ...(d.reply_buckets.no_reply > 0
            ? [
                {
                  to: "/communication",
                  text: (
                    <Bi
                      en={`${d.reply_buckets.no_reply} conversations still have no reply`}
                      fa={`${d.reply_buckets.no_reply} گفتگو هنوز بی‌پاسخ است`}
                    />
                  ),
                },
              ]
            : []),
        ]}
      />
      <div className="kpi-row kpi-row--4 kpi-row--even">
        <StatCard
          icon="alert"
          tone={d.tasks_overdue > 0 ? "warn" : "ok"}
          label={<Bi en="Overdue tasks" fa="کارهای عقب‌افتاده" />}
          hint={<Bi en="Deadline passed, still open" fa="مهلت گذشته و هنوز باز است" />}
          value={`${d.tasks_overdue}`}
          onMore={() =>
            setRecordPop({
              kind: "tasks",
              group: "overdue",
              groupBy: "priority",
              title: <Bi en="Overdue tasks" fa="کارهای عقب‌افتاده" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
        <StatCard
          icon="clock"
          tone="accent"
          label={<Bi en="Avg completion · 30d" fa="میانگین تکمیل · ۳۰ روز" />}
          hint={
            d.avg_completion_hours == null ? (
              <Bi en="No task was finished in 30 days" fa="در ۳۰ روز اخیر کاری تمام نشده" />
            ) : (
              <Bi en="From created to done" fa="از ساخت تا انجام" />
            )
          }
          value={
            d.avg_completion_hours == null
              ? "–"
              : bi(`${d.avg_completion_hours}h`, `${d.avg_completion_hours} ساعت`)
          }
          onMore={() =>
            setRecordPop({
              kind: "tasks_done",
              days: 30,
              groupBy: "priority",
              title: <Bi en="Avg completion · 30d" fa="میانگین تکمیل · ۳۰ روز" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
        <StatCard
          icon="check"
          tone="accent"
          label={<Bi en="Avg case resolution · 90d" fa="میانگین حل پرونده · ۹۰ روز" />}
          hint={
            d.avg_case_resolution_hours == null ? (
              <Bi en="No case was closed in 90 days" fa="در ۹۰ روز اخیر پرونده‌ای بسته نشده" />
            ) : (
              <Bi en="From opened to closed" fa="از باز شدن تا بسته شدن" />
            )
          }
          value={
            d.avg_case_resolution_hours == null
              ? "–"
              : bi(`${d.avg_case_resolution_hours}h`, `${d.avg_case_resolution_hours} ساعت`)
          }
          onMore={() =>
            setRecordPop({
              kind: "cases_closed",
              days: 90,
              groupBy: "case_type",
              title: <Bi en="Avg case resolution · 90d" fa="میانگین حل پرونده · ۹۰ روز" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
        <StatCard
          icon="alert"
          tone={d.login_failed_7d > 0 ? "danger" : "ok"}
          label={<Bi en="Failed logins · 7d" fa="ورود ناموفق · ۷ روز" />}
          hint={<Bi en="Wrong password attempts" fa="تلاش با رمز اشتباه" />}
          value={`${d.login_failed_7d}`}
          onMore={() =>
            setRecordPop({
              kind: "logins",
              days: 7,
              groupBy: "day",
              title: <Bi en="Failed logins · 7d" fa="ورود ناموفق · ۷ روز" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
      </div>

      <div className="grid grid-2">
        <Card>
          <SectionHeader
            icon="briefcase"
            title={<Bi en="Tasks · created vs completed" fa="کارها · ساخته‌شده در برابر تکمیل‌شده" />}
            hint={<Bi en="Last 8 weeks. Green is finished work." fa="۸ هفتهٔ اخیر. سبز یعنی کار تمام‌شده." />}
            action={
              <MoreButton
                onClick={() => {
                  const groups: Array<{ key: string; label: string; rows: AdminRef[] }> = [];
                  for (const [week, sides] of Object.entries(d.drilldown?.tasks_week ?? {})) {
                    if (sides.created.length > 0) {
                      groups.push({
                        key: `${week}:created`,
                        label: `${shortWeek(week)} · ${bi("Created", "ساخته‌شده")}`,
                        rows: sides.created,
                      });
                    }
                    if (sides.completed.length > 0) {
                      groups.push({
                        key: `${week}:completed`,
                        label: `${shortWeek(week)} · ${bi("Completed", "تکمیل‌شده")}`,
                        rows: sides.completed,
                      });
                    }
                  }
                  setRefs({
                    title: <Bi en="Tasks · created vs completed" fa="کارها · ساخته‌شده در برابر تکمیل‌شده" />,
                    groups,
                  });
                }}
              />
            }
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
          <SectionHeader
            icon="message"
            title={<Bi en="Messages · last 14 days" fa="پیام‌ها · ۱۴ روز اخیر" />}
            hint={<Bi en="How many messages were sent each day." fa="هر روز چند پیام رد و بدل شده." />}
            action={<MoreButton onClick={() => setMessagesOpen(true)} />}
          />
          <GroupedBars
            data={d.messages_daily.map((m) => ({ label: m.day.slice(8), values: [m.count] }))}
            height={190}
          />
        </Card>
      </div>

      <div className="grid grid-2">
        <Card>
          <SectionHeader
            icon="flag"
            title={<Bi en="Open tasks by priority" fa="کارهای باز به تفکیک اولویت" />}
            hint={<Bi en="Urgent and high should move first." fa="فوری و زیاد را اول جلو ببرید." />}
            action={
              <MoreButton
                onClick={() =>
                  setRefs({
                    title: <Bi en="Open tasks by priority" fa="کارهای باز به تفکیک اولویت" />,
                    groups: refGroups(d.drilldown?.priority, (key) => named(bi, PRIORITY_FA, key)),
                  })
                }
              />
            }
          />
          {priorities.length === 0 ? (
            <Muted><Bi en="No open tasks." fa="کار بازی نیست." /></Muted>
          ) : (
            <HBars data={priorities} color="var(--warn)" />
          )}
        </Card>
        <Card>
          <SectionHeader
            icon="chat"
            title={<Bi en="First reply time" fa="زمان اولین پاسخ" />}
            hint={<Bi en="How long until someone answers a new conversation." fa="چقدر طول می‌کشد تا به گفتگوی جدید جواب داده شود." />}
            action={
              <MoreButton
                onClick={() =>
                  setRefs({
                    title: <Bi en="First reply time" fa="زمان اولین پاسخ" />,
                    groups: refGroups(d.drilldown?.reply, (key) => {
                      const labels: Record<string, [string, string]> = {
                        lt5: ["Under 5 min", "زیر ۵ دقیقه"],
                        lt30: ["5–30 min", "۵ تا ۳۰ دقیقه"],
                        lt120: ["30–120 min", "۳۰ تا ۱۲۰ دقیقه"],
                        gt120: ["Over 2 hours", "بیش از ۲ ساعت"],
                        no_reply: ["No reply", "بی‌پاسخ"],
                      };
                      return named(bi, labels, key);
                    }),
                  })
                }
              />
            }
          />
          {replies.length === 0 ? (
            <Muted><Bi en="No conversations yet." fa="هنوز گفتگویی نیست." /></Muted>
          ) : (
            <Donut data={replies} caption={bi("conversations", "گفتگو")} />
          )}
        </Card>
      </div>

      <div className="grid grid-2">
        <Card>
          <SectionHeader
            icon="chat"
            title={<Bi en="Cases by status" fa="پرونده‌ها به تفکیک وضعیت" />}
            hint={<Bi en="Where follow-ups sit in their lifecycle." fa="پرونده‌ها الان در کدام مرحله‌اند." />}
            action={
              <MoreButton
                onClick={() =>
                  setRefs({
                    title: <Bi en="Cases by status" fa="پرونده‌ها به تفکیک وضعیت" />,
                    groups: refGroups(d.drilldown?.case_status, (key) => named(bi, CASE_STATUS_FA, key)),
                  })
                }
              />
            }
          />
          {caseStatuses.length === 0 ? (
            <Muted><Bi en="No cases yet." fa="هنوز پرونده‌ای نیست." /></Muted>
          ) : (
            <HBars data={caseStatuses} />
          )}
        </Card>
        <Card>
          <SectionHeader
            icon="chat"
            title={<Bi en="Cases by type" fa="پرونده‌ها به تفکیک نوع" />}
            hint={<Bi en="What kind of request people opened." fa="مردم چه نوع درخواستی باز کرده‌اند." />}
            action={
              <MoreButton
                onClick={() =>
                  setRefs({
                    title: <Bi en="Cases by type" fa="پرونده‌ها به تفکیک نوع" />,
                    groups: refGroups(d.drilldown?.case_type, (key) => named(bi, CASE_TYPE_FA, key)),
                  })
                }
              />
            }
          />
          {caseTypes.length === 0 ? (
            <Muted><Bi en="No cases yet." fa="هنوز پرونده‌ای نیست." /></Muted>
          ) : (
            <HBars data={caseTypes} color="var(--ok)" />
          )}
        </Card>
      </div>

      <div className="grid grid-2">
        <Card>
          <SectionHeader
            icon="car"
            title={<Bi en="How long cars have been in stock" fa="خودروها چند روز در انبار مانده‌اند" />}
            hint={<Bi en="Older than 90 days is stock that needs a plan." fa="بیش از ۹۰ روز یعنی موجودی که نیاز به تصمیم دارد." />}
            action={
              <MoreButton
                onClick={() =>
                  setRefs({
                    title: <Bi en="How long cars have been in stock" fa="خودروها چند روز در انبار مانده‌اند" />,
                    groups: refGroups(d.drilldown?.aging, (key) => {
                      const labels: Record<string, [string, string]> = {
                        lt7: ["Under 7 days", "کمتر از ۷ روز"],
                        lt30: ["7–30 days", "۷ تا ۳۰ روز"],
                        lt90: ["30–90 days", "۳۰ تا ۹۰ روز"],
                        gt90: ["Over 90 days", "بیش از ۹۰ روز"],
                      };
                      return named(bi, labels, key);
                    }),
                  })
                }
              />
            }
          />
          {aging.length === 0 ? (
            <Muted><Bi en="Nothing in stock." fa="موجودی در انبار نیست." /></Muted>
          ) : (
            <HBars data={aging} color="#8b5cf6" />
          )}
        </Card>
        <Card>
          <SectionHeader
            icon="car"
            title={<Bi en="Estimated value by status" fa="ارزش تقریبی به تفکیک وضعیت" />}
            hint={<Bi en="Sale price, or purchase price when sale price is empty." fa="قیمت فروش؛ اگر نباشد، قیمت خرید." />}
            action={
              <MoreButton
                onClick={() =>
                  setRecordPop({
                    kind: "vehicles",
                    groupBy: "vehicle_status",
                    title: <Bi en="Estimated value by status" fa="ارزش تقریبی به تفکیک وضعیت" />,
                  })
                }
              />
            }
          />
          {stockValue.length === 0 ? (
            <Muted><Bi en="No priced vehicles." fa="خودرویی با قیمت ثبت‌شده نیست." /></Muted>
          ) : (
            <HBars data={stockValue} format={(v) => v.toLocaleString("en-US")} />
          )}
        </Card>
      </div>

      <div className="grid grid-2">
        <Card padded={false}>
          <SectionHeader
            icon="activity"
            title={<Bi en="Most frequent actions" fa="پرتکرارترین اقدام‌ها" />}
            count={d.top_actions.length}
            hint={<Bi en="Technical names from the last 7 days. Open Audit for the full list." fa="نام فنی ۷ روز اخیر. فهرست کامل در تب ممیزی است." />}
            action={
              <MoreButton
                onClick={() =>
                  setRecordPop({
                    kind: "audit",
                    days: 7,
                    groupBy: "action",
                    title: <Bi en="Most frequent actions" fa="پرتکرارترین اقدام‌ها" />,
                  })
                }
              />
            }
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
            <Table className="table-fit"
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
          <SectionHeader
            icon="check"
            title={<Bi en="Audit · last 7 days" fa="ممیزی · ۷ روز اخیر" />}
            hint={<Bi en="How many recorded actions happened each day." fa="هر روز چند اقدام ثبت شده است." />}
            action={
              <MoreButton
                onClick={() =>
                  setRecordPop({
                    kind: "audit",
                    days: 7,
                    groupBy: "day",
                    title: <Bi en="Audit · last 7 days" fa="ممیزی · ۷ روز اخیر" />,
                  })
                }
              />
            }
          />
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
      {messagesOpen ? (
        <MessageDetail
          days={14}
          title={<Bi en="Messages · last 14 days" fa="پیام‌ها · ۱۴ روز اخیر" />}
          onClose={() => setMessagesOpen(false)}
        />
      ) : null}
      {refs ? (
        <RefDetail title={refs.title} groups={refs.groups} onClose={() => setRefs(null)} />
      ) : null}
      {recordPop ? (
        <RecordsDetail
          kind={recordPop.kind}
          days={recordPop.days}
          group={recordPop.group}
          groupBy={recordPop.groupBy}
          bucket={recordPop.bucket}
          title={recordPop.title}
          onClose={() => setRecordPop(null)}
        />
      ) : null}
    </>
  );
}

/** تب «مانیتورینگ» — سلامت سیستم با تازه‌سازی خودکار ۱۵ ثانیه‌ای. */
function MonitoringTab() {
  const bi = useBi();
  const [recordPop, setRecordPop] = useState<{
    kind: string;
    days?: number;
    group?: string;
    groupBy: string;
    bucket?: string;
    title: ReactNode;
  } | null>(null);
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
  const staleLocks = d.job_locks.filter((lk) => lk.stale).length;
  const journalOk = (d.database.journal_mode ?? "").toLowerCase() === "wal";

  return (
    <>
      <Guide
        items={[
          ...(failed > 0
            ? [
                {
                  to: "/settings",
                  text: (
                    <Bi
                      en="Messages failed to send — check Telegram in Settings"
                      fa="پیام‌ها نرسیده‌اند — تلگرام را در تنظیمات بررسی کنید"
                    />
                  ),
                },
              ]
            : []),
          ...(staleLocks > 0
            ? [
                {
                  text: (
                    <Bi
                      en="A background job looks stopped. Restart the worker."
                      fa="یک کار پس‌زمینه متوقف به نظر می‌رسد. ورکر را دوباره روشن کنید."
                    />
                  ),
                },
              ]
            : []),
          ...(d.audit_chain.ok === false
            ? [
                {
                  text: (
                    <Bi
                      en="The audit history no longer matches. Treat it as tampered."
                      fa="تاریخچهٔ ممیزی دیگر جور درنمی‌آید. آن را دستکاری‌شده بدانید."
                    />
                  ),
                },
              ]
            : []),
        ]}
      />
      <div className="kpi-row kpi-row--4 kpi-row--even">
        <StatCard
          icon="layers"
          tone="ok"
          label={<Bi en="Database size" fa="حجم داده‌ها" />}
          value={fmtBytes(d.database.size_bytes)}
          hint={
            journalOk ? (
              <Bi en="Saving is stable" fa="ذخیره پایدار است" />
            ) : d.database.journal_mode ? (
              <Bi
                en={`Save mode: ${d.database.journal_mode}`}
                fa={`حالت ذخیره: ${d.database.journal_mode}`}
              />
            ) : undefined
          }
        />
        <StatCard
          icon="alert"
          tone={d.auth_failed_24h > 0 ? "danger" : "ok"}
          label={<Bi en="Failed logins · 24h" fa="ورود ناموفق · ۲۴ ساعت" />}
          hint={<Bi en="A sudden rise means someone is guessing passwords" fa="اگر ناگهان زیاد شد، کسی رمز را حدس می‌زند" />}
          value={`${d.auth_failed_24h}`}
          onMore={() =>
            setRecordPop({
              kind: "logins",
              days: 1,
              groupBy: "day",
              title: <Bi en="Failed logins · 24h" fa="ورود ناموفق · ۲۴ ساعت" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
        <StatCard
          icon="clock"
          tone={oldest != null && oldest > 10 ? "warn" : "ok"}
          label={<Bi en="Oldest unsent message" fa="قدیمی‌ترین پیام ارسال‌نشده" />}
          hint={
            oldest == null ? (
              <Bi en="Nothing is waiting to be sent" fa="چیزی در صف ارسال نیست" />
            ) : (
              <Bi en="A large number means sending is stuck" fa="عدد بزرگ یعنی ارسال گیر کرده" />
            )
          }
          value={
            oldest == null ? "–" : bi(`${oldest} min`, `${oldest.toLocaleString("fa-IR")} دقیقه`)
          }
          onMore={() =>
            setRecordPop({
              kind: "outbox",
              groupBy: "outbox_status",
              bucket: "pending",
              title: <Bi en="Oldest unsent message" fa="قدیمی‌ترین پیام ارسال‌نشده" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
        <StatCard
          icon="send"
          tone={failed > 0 ? "danger" : "ok"}
          label={<Bi en="Messages that did not arrive" fa="پیام‌هایی که نرسیدند" />}
          hint={<Bi en={`${pending} still queued`} fa={`${pending.toLocaleString("fa-IR")} هنوز در صف`} />}
          value={`${failed}`}
          onMore={() =>
            setRecordPop({
              kind: "outbox",
              groupBy: "outbox_status",
              bucket: "failed",
              title: <Bi en="Messages that did not arrive" fa="پیام‌هایی که نرسیدند" />,
            })
          }
          moreLabel={<Bi en="Show more" fa="نمایش بیشتر" />}
        />
      </div>

      <div className="grid grid-2">
        <Card>
          <SectionHeader
            icon="circleCheck"
            title={<Bi en="Can the history be trusted?" fa="آیا تاریخچه قابل اعتماد است؟" />}
            hint={
              <Bi
                en="Intact means nobody changed a past audit row."
                fa="سالم یعنی هیچ‌کس ردیف‌های گذشتهٔ ممیزی را عوض نکرده."
              />
            }
          />
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
          <SectionHeader
            icon="activity"
            title={<Bi en="What happened in the last day" fa="در ۲۴ ساعت اخیر چه اتفاقی افتاد" />}
            hint={<Bi en="Automatic system events, not things a person typed." fa="رویدادهای خودکار سیستم، نه چیزی که کسی تایپ کرده." />}
            action={
              <MoreButton
                onClick={() =>
                  setRecordPop({
                    kind: "events",
                    days: 1,
                    groupBy: "event",
                    title: <Bi en="What happened in the last day" fa="در ۲۴ ساعت اخیر چه اتفاقی افتاد" />,
                  })
                }
              />
            }
          />
          {d.events_24h.length === 0 ? (
            <Muted><Bi en="No events in the last day." fa="در یک روز اخیر رویدادی نبوده." /></Muted>
          ) : (
            <HBars
              data={d.events_24h.map((e) => ({ label: named(bi, EVENT_FA, e.type), value: e.count }))}
              color="#8b5cf6"
            />
          )}
        </Card>
      </div>

      <Card padded={false}>
        <SectionHeader
          icon="activity"
          title={<Bi en="Latest events, one by one" fa="آخرین رویدادها، مورد به مورد" />}
          count={d.recent_events.length}
          hint={
            <Bi
              en="Each row is one thing that happened, and opens that record."
              fa="هر ردیف یک اتفاق مشخص است و همان رکورد را باز می‌کند."
            />
          }
          action={
            <MoreButton
              onClick={() =>
                setRecordPop({
                  kind: "events",
                  days: 7,
                  groupBy: "event",
                  title: <Bi en="Latest events, one by one" fa="آخرین رویدادها، مورد به مورد" />,
                })
              }
            />
          }
        />
        {d.recent_events.length === 0 ? (
          <div className="flush-foot">
            <EmptyState
              titleEn="No recent events"
              titleFa="رویداد تازه‌ای نیست"
              bodyEn="When work moves, the record and its section show up here."
              bodyFa="با جابه‌جایی کارها، موضوع و بخشش اینجا می‌آید."
            />
          </div>
        ) : (
          <Table
            className="table-fit"
            rows={d.recent_events}
            rowKey={(row) => `${row.type}-${row.entity_id}-${row.at}`}
            columns={[
              {
                key: "title",
                header: <Bi en="What" fa="موضوع" />,
                render: (row) => <RecordLink href={entityHref(row)}>{row.title}</RecordLink>,
              },
              {
                key: "section",
                header: <Bi en="Section" fa="بخش" />,
                render: (row) => named(bi, SECTION_FA, row.entity_type),
              },
              {
                key: "type",
                header: <Bi en="What happened" fa="چه اتفاقی" />,
                render: (row) => named(bi, EVENT_ABOUT, row.type),
              },
              {
                key: "at",
                header: <Bi en="When" fa="زمان" />,
                render: (row) => <DateText value={row.at} />,
              },
            ]}
          />
        )}
      </Card>

      <div className="grid grid-2">
        <Card padded={false}>
          <SectionHeader
            icon="clock"
            title={<Bi en="Background jobs" fa="کارهای پس‌زمینه" />}
            count={d.job_locks.length}
            hint={
              <Bi
                en="Active means a worker is running it. Expired means that worker stopped."
                fa="فعال یعنی یک ورکر در حال انجام آن است. منقضی یعنی آن ورکر متوقف شده."
              />
            }
          />
          {d.job_locks.length === 0 ? (
            <div className="flush-foot">
              <EmptyState
                titleEn="No background jobs yet"
                titleFa="هنوز کار پس‌زمینه‌ای نیست"
                bodyEn="They appear here while a worker is running."
                bodyFa="وقتی ورکر روشن باشد، اینجا دیده می‌شوند."
              />
            </div>
          ) : (
            <Table className="table-fit"
              rows={d.job_locks}
              rowKey={(lk) => lk.name}
              columns={[
                {
                  key: "name",
                  header: <Bi en="Job" fa="کار" />,
                  render: (lk) => named(bi, JOB_FA, lk.name),
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
            title={<Bi en="Why messages failed" fa="چرا پیام‌ها نرسیدند" />}
            count={d.outbox.failed_samples.length}
            hint={
              <Bi
                en="The three most recent send errors."
                fa="سه خطای ارسال اخیر."
              />
            }
            action={
              <MoreButton
                onClick={() =>
                  setRecordPop({
                    kind: "outbox",
                    groupBy: "outbox_status",
                    bucket: "failed",
                    title: <Bi en="Why messages failed" fa="چرا پیام‌ها نرسیدند" />,
                  })
                }
              />
            }
          />
          {d.outbox.failed_samples.length === 0 ? (
            <div className="flush-foot">
              <EmptyState
                titleEn="Nothing failed"
                titleFa="ارسالی ناموفق نیست"
                bodyEn="Recent send errors will show up here."
                bodyFa="اگر پیامی نرسد، دلیلش اینجا دیده می‌شود."
              />
            </div>
          ) : (
            <Table
              className="table-fit"
              rows={d.outbox.failed_samples}
              rowKey={(s) => `${s.entity_id ?? s.provider}-${s.at}`}
              columns={[
                {
                  key: "title",
                  header: <Bi en="About" fa="دربارهٔ چه" />,
                  render: (s) => (
                    <span className="cell-stack">
                      <RecordLink href={entityHref(s)}>{s.title || s.preview || "–"}</RecordLink>
                      <Muted className="cell-sub">
                        {named(bi, EVENT_ABOUT, s.event_type)}
                        {s.recipient ? ` · ${s.recipient}` : ""}
                      </Muted>
                    </span>
                  ),
                },
                {
                  key: "section",
                  header: <Bi en="Section" fa="بخش" />,
                  render: (s) =>
                    s.entity_type ? named(bi, SECTION_FA, s.entity_type) : named(bi, CHANNEL_FA, `${s.provider}_mode`),
                },
                {
                  key: "error",
                  header: <Bi en="Why it failed" fa="چرا نرسید" />,
                  render: (s) => (
                    <span className="mono mono-xs ltr-value cell-clip" title={s.error || undefined}>
                      {s.error || "–"}
                    </span>
                  ),
                },
              ]}
            />
          )}
        </Card>
      </div>

      <div className="grid grid-2">
        <Card padded={false}>
          <SectionHeader
            icon="layers"
            title={<Bi en="How much is stored" fa="چقدر داده ذخیره شده" />}
            count={tableRows.length}
            hint={<Bi en="Row counts per area of the organization." fa="تعداد رکورد هر بخش سازمان." />}
          />
          <Table className="table-fit"
            rows={tableRows}
            rowKey={(r) => r.name}
            columns={[
              {
                key: "name",
                header: <Bi en="Area" fa="بخش" />,
                render: (r) => named(bi, TABLE_FA, r.name),
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
          <SectionHeader
            icon="branch"
            title={<Bi en="Connections" fa="اتصال‌ها" />}
            count={integrations.length}
            hint={
              <Bi
                en="Live sends for real. Test only does not leave the system."
                fa="واقعی یعنی ارسال واقعی. فقط آزمایشی از سیستم خارج نمی‌شود."
              />
            }
          />
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
            <Table className="table-fit"
              rows={integrations}
              rowKey={([key]) => key}
              columns={[
                {
                  key: "key",
                  header: <Bi en="Channel" fa="کانال" />,
                  render: ([key]) => named(bi, CHANNEL_FA, key),
                },
                {
                  key: "value",
                  header: <Bi en="Mode" fa="حالت" />,
                  render: ([, value]) => named(bi, MODE_FA, String(value)),
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
      {recordPop ? (
        <RecordsDetail
          kind={recordPop.kind}
          days={recordPop.days}
          group={recordPop.group}
          groupBy={recordPop.groupBy}
          bucket={recordPop.bucket}
          title={recordPop.title}
          onClose={() => setRecordPop(null)}
        />
      ) : null}
    </>
  );
}

const AUDIT_ENTITIES: Array<[string, string, string]> = [
  ["", "All", "همه"],
  ["work_item", "Project", "پروژه"],
  ["task", "To-do", "کار"],
  ["case", "Case", "پرونده"],
  ["conversation", "Conversation", "گفتگو"],
  ["customer", "Customer", "مشتری"],
  ["approval", "Approval", "تأیید"],
  ["report", "Report", "گزارش"],
  ["user", "Person", "کاربر"],
  ["auth", "Sign-in", "ورود"],
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
        hint={
          <Bi
            en="Leave a filter empty to see everything. Excel export uses the same filters."
            fa="فیلتر خالی یعنی همه. خروجی اکسل همین فیلترها را ذخیره می‌کند."
          />
        }
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
            {AUDIT_ENTITIES.map(([value, en, fa]) => (
              <option key={value || "all"} value={value}>
                {bi(en, fa)}
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
        <Table className="table-fit"
          rows={rows}
          rowKey={(r) => String(r.id)}
          columns={[
            {
              key: "action",
              header: <Bi en="Action" fa="اقدام" />,
              render: (r) => named(bi, EVENT_ABOUT, String(r.action ?? "")),
            },
            {
              key: "entity",
              header: <Bi en="Opens" fa="باز می‌شود در" />,
              render: (r) => {
                const entityType = String(r.entity_type ?? "");
                const entityId = r.entity_id ? String(r.entity_id) : null;
                const href = entityHref({ entity_type: entityType, entity_id: entityId });
                return <RecordLink href={href}>{named(bi, SECTION_FA, entityType)}</RecordLink>;
              },
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

  const scopeCopy = SCOPES.find((row) => row[0] === level);

  return (
    <>
      <Field label={<Bi en="Whose records" fa="رکوردهای چه کسی" />}>
        <Select value={level} onChange={(e) => setLevel(e.target.value)}>
          {SCOPES.map(([value, en, fa]) => (
            <option key={value} value={value}>
              {bi(en, fa)}
            </option>
          ))}
        </Select>
      </Field>
      {scopeCopy ? (
        <p className="concept-hint">
          <Bi en={scopeCopy[3]} fa={scopeCopy[4]} />
        </p>
      ) : null}
      {PERM_GROUPS.map((group) => {
        const items = group.codes.filter((code) => codes.includes(code));
        if (items.length === 0) return null;
        return (
          <section key={group.en} className="perm-group">
            <h3 className="perm-group-title">{bi(group.en, group.fa)}</h3>
            <ul className="perm-list">
              {items.map((code) => {
                const copy = PERM_COPY[code];
                return (
                  <li key={code}>
                    <label className="perm-item">
                      <input
                        type="checkbox"
                        checked={checked.has(code)}
                        onChange={() => toggle(code)}
                      />
                      <span>{copy ? <Bi en={copy[0]} fa={copy[1]} /> : code}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
      {codes.some((code) => !PERM_GROUPS.some((group) => group.codes.includes(code))) ? (
        <section className="perm-group">
          <h3 className="perm-group-title">{bi("Other", "سایر")}</h3>
          <ul className="perm-list">
            {codes
              .filter((code) => !PERM_GROUPS.some((group) => group.codes.includes(code)))
              .map((code) => (
                <li key={code}>
                  <label className="perm-item">
                    <input
                      type="checkbox"
                      checked={checked.has(code)}
                      onChange={() => toggle(code)}
                    />
                    <span>{PERM_COPY[code] ? <Bi en={PERM_COPY[code][0]} fa={PERM_COPY[code][1]} /> : code}</span>
                  </label>
                </li>
              ))}
          </ul>
        </section>
      ) : null}
      <div className="mt-3">
        <Button disabled={busy} onClick={() => onSave(Array.from(checked).sort(), level)}>
          {bi("Save role", "ذخیره نقش")}
        </Button>
      </div>
    </>
  );
}
