import { ApiError, getToken, setToken } from "../api";
import { apiErrorDetail } from "../lib/httpErrorDetail";
import { toman } from "../fa";

export { toman };

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`/api${path}`, { ...init, headers, credentials: "include" });
  if (res.status === 401 && retry) {
    const refreshed = await fetch("/api/auth/refresh", { method: "POST", credentials: "include" });
    if (refreshed.ok) {
      const body = (await refreshed.json()) as { access_token: string };
      setToken(body.access_token);
      return request<T>(path, init, false);
    }
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      const raw = body.detail;
      if (raw && typeof raw === "object") {
        const code = raw.pishgam_statusCode != null ? ` [${raw.pishgam_statusCode}]` : "";
        const msg = raw.pishgam_message || raw.message || JSON.stringify(raw);
        detail = `${msg}${code}`;
      } else {
        detail = apiErrorDetail(raw, detail);
      }
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, String(detail));
  }
  if (res.status === 204) return undefined as T;
  const ctype = res.headers.get("content-type") || "";
  if (ctype.includes("sheet") || ctype.includes("octet-stream")) {
    return (await res.blob()) as T;
  }
  return res.json() as Promise<T>;
}

/** صفر در فهرست کمپین یعنی ورودی ثبت نشده، نه نتیجهٔ صفر. */
export function leadsLabel(value: number | null | undefined): string {
  if (!value) return "—";
  return toman(value);
}

export async function downloadPerf(path: string, filename: string) {
  const blob = await request<Blob>(path);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export const perfApi = {
  home: () => request<Home>("/perf/home"),
  campaigns: () => request<CampaignRow[]>("/perf/campaigns"),
  patchCampaign: (id: string, body: Record<string, unknown>) =>
    request<CampaignRow>(`/perf/campaigns/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteCampaign: (id: string) => request<void>(`/perf/campaigns/${id}`, { method: "DELETE" }),
  campaign: (id: string) => request<CampaignDetail>(`/perf/campaigns/${id}`),
  campaignThread: (id: string) =>
    request<{ id: string }>(`/perf/campaigns/${id}/thread`, { method: "POST", body: "{}" }),
  briefDraft: (id: string) =>
    request<BriefDraft>(`/perf/campaigns/${id}/brief/draft`, { method: "POST", body: "{}" }),
  createCampaign: (body: Record<string, unknown>) =>
    request<CampaignRow>("/perf/campaigns", { method: "POST", body: JSON.stringify(body) }),
  campaignRegister: () =>
    request<{
      next: number;
      tags: Array<{ tag: string; en: string; brand: string }>;
      rows: RegisterRow[];
      legacy: RegisterRow[];
    }>("/perf/campaign-register"),
  panels: () => request<Panel[]>("/perf/panels"),
  updatePanel: (id: string, body: Record<string, unknown>) =>
    request<Panel>(`/perf/panels/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  checkSms: (body: Record<string, unknown>) =>
    request<SmsCheck>("/perf/sms/check", { method: "POST", body: JSON.stringify(body) }),
  draftSms: (body: Record<string, unknown>) =>
    request<SmsDraft>("/perf/sms/drafts", { method: "POST", body: JSON.stringify(body) }),
  sends: () => request<SmsSend[]>("/perf/sms/sends"),
  smsPull: () => request<{ imported: number; note: string }>("/perf/sms/pull", { method: "POST", body: "{}" }),
  createSend: (body: Record<string, unknown>) =>
    request<SmsSend>("/perf/sms/sends", { method: "POST", body: JSON.stringify(body) }),
  patchSend: (id: string, body: Record<string, unknown>) =>
    request<SmsSend>(`/perf/sms/sends/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteSend: (id: string) => request<void>(`/perf/sms/sends/${id}`, { method: "DELETE" }),
  delivery: (id: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<{ delivered_count: number }>(`/perf/sms/sends/${id}/delivery`, { method: "POST", body: data });
  },
  pishgamSendDelivery: (id: string, body: { message_id?: number | null; recipients: string[] }) =>
    request<PishgamDelivery & { send_id: string }>(`/perf/sms/sends/${id}/pishgam-delivery`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  lists: () => request<RecipientList[]>("/perf/lists"),
  prepareList: (data: FormData) => request<RecipientList>("/perf/lists/prepare", { method: "POST", body: data }),
  blacklist: () => request<Array<{ id: string; phone: string; note: string }>>("/perf/blacklist"),
  addBlacklist: (phone: string, note: string) =>
    request("/perf/blacklist", { method: "POST", body: JSON.stringify({ phone, note }) }),
  deleteBlacklist: (id: string) => request<void>(`/perf/blacklist/${id}`, { method: "DELETE" }),
  deleteList: (id: string) => request<void>(`/perf/lists/${id}`, { method: "DELETE" }),
  payments: () => request<Payment[]>("/perf/payments"),
  createPayment: (body: Record<string, unknown>) =>
    request<Payment>("/perf/payments", { method: "POST", body: JSON.stringify(body) }),
  patchPayment: (id: string, body: Record<string, unknown>) =>
    request<Payment>(`/perf/payments/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deletePayment: (id: string) => request<void>(`/perf/payments/${id}`, { method: "DELETE" }),
  matchDelivery: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<{ send_id: string; delivered_count: number; campaign_code: string }>("/perf/sms/delivery", {
      method: "POST",
      body: data,
    });
  },
  advance: (id: string, action: string, seenAmount?: number) =>
    request<Payment>(`/perf/payments/${id}/advance`, { method: "POST", body: JSON.stringify({ action, seen_amount_toman: seenAmount ?? null }) }),
  pages: () => request<PageRow[]>("/perf/pages"),
  createPage: (body: Record<string, unknown>) =>
    request<PageRow>("/perf/pages", { method: "POST", body: JSON.stringify(body) }),
  updatePage: (id: string, body: Record<string, unknown>) =>
    request<PageRow>(`/perf/pages/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deletePage: (id: string) => request<void>(`/perf/pages/${id}`, { method: "DELETE" }),
  suggest: (budget: number) => request<Suggest>(`/perf/pages/suggest?budget=${budget}`),
  requests: () => request<CarRequest[]>("/perf/car-requests"),
  createRequest: (raw_text: string, campaign_id?: string) =>
    request<CarRequest>("/perf/car-requests", {
      method: "POST",
      body: JSON.stringify({ raw_text, source: "panel", campaign_id: campaign_id || null }),
    }),
  patchRequest: (id: string, body: { status?: string; campaign_id?: string }) =>
    request<CarRequest>(`/perf/car-requests/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteRequest: (id: string) => request<void>(`/perf/car-requests/${id}`, { method: "DELETE" }),
  stories: () => request<Story[]>("/perf/stories"),
  createStory: (body: Record<string, unknown>) =>
    request<Story>("/perf/stories", { method: "POST", body: JSON.stringify(body) }),
  publishStory: (id: string, body: { published_on?: string | null; views?: number | null; leads?: number | null }) =>
    request<Story>(`/perf/stories/${id}/publish`, { method: "POST", body: JSON.stringify(body) }),
  patchStory: (id: string, body: Record<string, unknown>) =>
    request<Story>(`/perf/stories/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteStory: (id: string) => request<void>(`/perf/stories/${id}`, { method: "DELETE" }),
  patchCost: (id: string, body: Record<string, unknown>) =>
    request(`/perf/costs/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteCost: (id: string) => request<void>(`/perf/costs/${id}`, { method: "DELETE" }),
  insight: (id: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<{ ok: boolean; reason?: string; source?: string; fields?: Record<string, number | null> }>(
      `/perf/stories/${id}/insight`,
      { method: "POST", body: data },
    );
  },
  importCosts: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<{ added: number }>("/perf/excel/costs", { method: "POST", body: data });
  },
  importLeads: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<{ added: number }>("/perf/leads/import", { method: "POST", body: data });
  },
  sheet: () => request<Sheet>("/perf/sheet"),
  syncSheets: () => request<{ pushed: boolean; reason?: string; spreadsheet_url?: string; sources?: Record<string, number> }>("/perf/integrations/sheets", { method: "POST", body: JSON.stringify({ kind: "costs" }) }),
  mizito: () => request<MizitoSnapshot>("/perf/integrations/mizito"),
  refreshMizito: () => request<MizitoSnapshot>("/perf/integrations/mizito/refresh", { method: "POST" }),
  mizitoMissing: () => request<MizitoMissing>("/perf/integrations/mizito/missing"),
  mizitoFinance: () => request<MizitoFinance>("/perf/integrations/mizito/finance"),
  mizitoTriage: (days?: number | null) => request<MizitoTriage>(`/perf/integrations/mizito/triage${days ? `?days=${days}` : ""}`),
  mizitoRequests: (status = "new") => request<MizitoRequests>(`/perf/integrations/mizito/requests?status=${encodeURIComponent(status)}`),
  checkMizitoRequests: () => request<MizitoRequestCheck>("/perf/integrations/mizito/requests/check", { method: "POST" }),
  approveMizitoRequest: (id: string, body: Record<string, unknown>) =>
    request<{ request: MizitoRequest; campaign: CampaignRow }>(`/perf/integrations/mizito/requests/${id}/approve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  rejectMizitoRequest: (id: string) => request<MizitoRequest>(`/perf/integrations/mizito/requests/${id}/reject`, { method: "POST" }),
  connections: (live = false) => request<Connections>(`/perf/connections?live=${live ? "true" : "false"}`),
  saveMizito: (token: string) =>
    request<{ saved: boolean; hint: string }>("/perf/connections/mizito", { method: "PUT", body: JSON.stringify({ token }) }),
  saveNovinHub: (token: string) =>
    request<{ saved: boolean; hint: string }>("/perf/connections/novinhub", { method: "PUT", body: JSON.stringify({ token }) }),
  saveVardast: (token: string) =>
    request<{ saved: boolean; hint: string }>("/perf/connections/vardast", { method: "PUT", body: JSON.stringify({ token }) }),
  vardast: () => request<VardastSnapshot>("/perf/integrations/vardast"),
  isms: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>("/perf/integrations/isms", { method: "POST", body: JSON.stringify(body) }),
  pishgamBalance: (panelId: string) =>
    request<Record<string, unknown>>(`/perf/integrations/pishgam/balance?panel_id=${panelId}`),
  pishgamDelivery: (body: PishgamDeliveryIn) =>
    request<PishgamDelivery>("/perf/integrations/pishgam/delivery", { method: "POST", body: JSON.stringify(body) }),
  pishgamTargeting: () => request<PishgamTargeting>("/perf/pishgam/targeting"),
  syncPishgamTargeting: () => request<PishgamRefCounts>("/perf/pishgam/targeting/sync", { method: "POST" }),
  checkPishgamPolygons: (keys: string[], operators: number[] = [1, 2]) =>
    request<PishgamPolygonCheck>("/perf/pishgam/targeting/check-polygons", {
      method: "POST",
      body: JSON.stringify({ keys, operators }),
    }),
  previewPishgamAudience: (body: PishgamPreviewIn) =>
    request<PishgamPreviewStart>("/perf/pishgam/targeting/preview", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export type PishgamDeliveryIn = {
  panel_id: string;
  message_id: number;
  recipients: string[];
};

export type PishgamDelivery = {
  ok: boolean;
  reason: string;
  rows: Array<{ to_number: string; status: number; text: string }>;
  delivered_count: number;
};

export type PishgamArea = {
  key: string;
  name_fa: string;
  tier: string;
  approximate: boolean;
  verified: boolean;
  points: number;
  closed: boolean;
  fragment_count?: number;
  edge_km?: { width: number; height: number };
  contact_code?: string;
  links_allowed?: boolean;
};

export type PishgamRefCounts = {
  provinces: number;
  cities: number;
  brands: number;
  types: number;
};

export type PishgamPolygonCheck = {
  all_valid: boolean;
  areas: Array<{
    key: string;
    name_fa: string;
    verified: boolean;
    fragment_count?: number;
    valid: boolean;
    checks: Array<{ operator: number; operator_name: string; is_valid: boolean; is_valid_area: boolean }>;
  }>;
};

export type PishgamPreviewIn = {
  keys: string[];
  operators: number[];
  residence_enabled: boolean;
  start_datetime: string | null;
  end_datetime: string | null;
  sms_body: string;
  links_allowed: boolean;
  force_refresh?: boolean;
};

export type PishgamPreviewProgress = {
  phase?: string;
  message?: string;
  area_index?: number;
  area_total?: number;
  area_key?: string;
  area_name?: string;
  request_index?: number;
  request_total?: number;
  smart_sms_request_id?: number;
};

export type PishgamPreviewRecipient = {
  operator: number;
  operator_name: string;
  count: number;
  persian_price: number;
  english_price?: number;
  sms_parts?: number;
  api_one_part_total?: number;
  tariff_one_part_total?: number;
  tariff_rial?: number;
};

export type PishgamPreviewArea = {
  key: string;
  name_fa: string;
  verified?: boolean;
  fragment_count?: number;
  valid?: boolean;
  checks?: Array<{ operator: number; operator_name: string; is_valid: boolean; is_valid_area: boolean }>;
  requests?: Array<{
    key: string;
    name_fa: string;
    smart_sms_request_id: number;
    title?: string;
    polygon_count?: number;
    expire_date?: string | null;
    status?: number | null;
    recipients?: PishgamPreviewRecipient[];
  }>;
  recipients?: PishgamPreviewRecipient[];
  total_count?: number;
};

export type PishgamPreviewResult = {
  status?: "checking" | "creating" | "waiting" | "refreshing" | "done" | "error";
  progress?: PishgamPreviewProgress;
  cache_key?: string;
  from_cache?: boolean;
  keys: string[];
  operators?: number[];
  window?: { start: string; end: string };
  residence_enabled?: boolean;
  credit?: number;
  unit_note?: string;
  recipients: PishgamPreviewRecipient[];
  estimates?: {
    api_total: number;
    tariff_total: number;
    sms_parts: number;
    total_count: number;
    lines?: PishgamPreviewRecipient[];
  };
  affordability_one_part?: Record<string, number | null>;
  polygon_batches?: number;
  polygon_total?: number;
  areas?: PishgamPreviewArea[];
  requests?: PishgamPreviewArea["requests"];
  smart_lines?: Array<{ operator: number; operator_name: string; number: string }>;
  expire_date?: string | null;
  counted_at?: string | null;
  sms_parts?: number;
  error?: { message: string; pishgam_status_code?: number | null; pishgam_message?: string | null };
};

export type PishgamPreviewStart = {
  started: boolean;
  from_cache: boolean;
  preview: PishgamPreviewResult;
};

export type PishgamTargeting = {
  areas: PishgamArea[];
  catalog: { read: number; gated: number; build?: number; mutating: number };
  refs: PishgamRefCounts;
  audit: Array<{ method: string; endpoint: string; is_mutating: boolean; status_code: number | null; created_at: string | null }>;
  smart: {
    preview_enabled: boolean;
    send_enabled: boolean;
    send_reason: string;
    tariffs_rial: Record<number, number>;
    unit_note: string;
    limits: { max_polygons_per_request: number; max_edge_km: number; max_send_recipients: number; max_balance_percent: number };
  };
  preview: PishgamPreviewResult | null;
};

export type MizitoCard = {
  project: string;
  board: string;
  title: string;
  code: string;
  // فیلدهای زیر در عکس‌های قدیمی نیستند.
  id?: string;
  code_source?: string;
  project_id?: string;
  board_id?: string;
  board_position?: number | null;
  status?: string;
  active?: boolean;
  completed?: boolean;
  completed_at?: string | null;
  assignees?: string[];
  owner?: string;
  created_at?: string | null;
  modified_at?: string | null;
  deadline?: string | null;
  checklist_done?: number;
  checklist_total?: number;
  checklist_items?: Array<{ title: string; checked: boolean }>;
  progress?: number;
  attachments?: number;
  has_comments?: boolean;
  last_comment_at?: string | null;
};

export const MIZITO_STATUS: Record<string, string> = {
  idea: "ایده",
  todo: "برای انجام",
  in_progress: "در حال انجام",
  review: "بررسی",
  waiting_approval: "منتظر تأیید",
  waiting_payment: "منتظر پرداخت",
  paid: "پرداخت‌شده",
  not_in_cost_tracking: "ثبت‌نشده در Cost Tracking",
  done: "تمام‌شده",
  cancelled: "کنسل",
  paused: "متوقف",
  info: "قانون/اطلاعیه",
  other: "سایر",
};

export function mizitoStatus(card: { status?: string }): string {
  const key = card.status || "other";
  return MIZITO_STATUS[key] || (card.status ? "وضعیت نامشخص" : "—");
}

/** کد برای مقایسه: رقم فارسی/عربی به انگلیسی، حروف بزرگ، بدون فاصله. */
export function mizitoCode(code: string | null | undefined): string {
  return (code ?? "")
    .replace(/[۰-۹]/g, (digit) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)))
    .replace(/\s+/g, "")
    .toUpperCase();
}

export type MizitoFinanceCard = {
  id: string;
  title: string;
  board: string;
  status: string;
  code: string;
  code_source: string;
  completed: boolean;
  modified_at?: string | null;
  match: "suggested" | "no_cost_row" | "no_code";
  suggested_costs: number[];
};

export type MizitoFinance = {
  connected: boolean;
  read_at?: string | null;
  match_basis: string;
  counts: Record<string, { total: number; open: number }>;
  to_register: MizitoFinanceCard[];
  to_register_count: number;
  paid_without_cost: MizitoFinanceCard[];
  paid_without_cost_count: number;
  paid_suggested_count: number;
  panel_without_card?: Array<{
    campaign_code: string;
    cost_number: number;
    amount_toman: number | null;
    kind: string;
    description: string;
  }>;
  panel_without_card_count?: number;
};

export function triageLabel(flag: string, days: number): string {
  if (flag === "stuck") return `بیش از ${toman(days)} روز بدون تغییر`;
  return ({ no_code: "بدون کد", no_assignee: "بدون مسئول", overdue: "مهلت گذشته" } as Record<string, string>)[flag] || flag;
}

export type MizitoTriageCard = {
  id: string;
  title: string;
  project: string;
  board: string;
  status: string;
  code: string;
  flags: string[];
  days_since_change: number | null;
  modified_at?: string | null;
  deadline?: string | null;
  assignees: number | null;
};

export type MizitoTriage = {
  connected: boolean;
  read_at?: string | null;
  days: number;
  checked: number;
  counts: Record<string, number>;
  total: number;
  cards: MizitoTriageCard[];
};

export type MizitoMissing = {
  connected: boolean;
  read_at?: string | null;
  codes: Array<{
    code: string;
    id?: string;
    title: string;
    project: string;
    status: string;
    active: boolean;
    completed: boolean;
    cards: number;
    modified_at?: string | null;
  }>;
};

export type MizitoSnapshot = {
  connected: boolean;
  reason?: string;
  projects: Array<{ title: string; id: string }>;
  cards: MizitoCard[];
  open_count: number;
  total_count?: number;
  read_at?: string | null;
  card_url_prefix?: string;
};

export type VardastChannel = { id: string; name: string; platform: string };

export type VardastSnapshot = {
  connected: boolean;
  reason: string;
  channels: VardastChannel[];
  usage: Record<string, unknown> | null;
};

export type SheetLink = { configured: boolean; connected: boolean; title: string; reason: string };

export type SheetSyncState = {
  running: boolean;
  actor_name: string;
  started_at: string | null;
  finished_at: string | null;
  result: string;
  error: string;
};

export type Connections = {
  sheets_ready: boolean;
  service_account: string;
  sheets: Record<string, SheetLink>;
  sheet_sync?: SheetSyncState;
  mizito: {
    saved: boolean;
    hint: string;
    connected?: boolean;
    reason?: string;
    read_at?: string | null;
    last_error_at?: string | null;
    checked_at?: string | null;
    open_count?: number;
  };
  novinhub: {
    saved: boolean;
    hint: string;
    connected?: boolean;
    reason?: string;
    checked_at?: string | null;
    account_count?: number;
  };
  vardast: {
    saved: boolean;
    hint: string;
    connected?: boolean;
    reason?: string;
    checked_at?: string | null;
    channel_count?: number;
  };
  panels: PanelStatus[];
  insight: { ready: boolean; provider: string };
};

export type PanelStatus = {
  id: string;
  name: string;
  code: string;
  ready: boolean;
  detail?: string;
  has_token?: boolean;
  api_base?: string;
  live?: { ok: boolean; reason: string; balance: string; credit_rial?: number; lines?: string[] } | null;
};

export type NextStep = {
  tone: string;
  label: string;
  title: string;
  href: string;
};

export type Home = {
  active_campaigns: CampaignRow[];
  panels: Panel[];
  waiting_payments: number;
  payments: Payment[];
  next: NextStep[];
};

export type RegisterRow = {
  tag: string;
  seq: number;
  code: string;
  title: string;
  when: string;
  brand: string;
};

export type CampaignRow = {
  id: string;
  code: string;
  title: string;
  brand: string;
  goal: string;
  starts_on: string | null;
  ends_on: string | null;
  budget_toman: number | null;
  status: string;
  channels: string[];
  project_id?: string | null;
  cost_toman?: number;
  leads?: number;
  cpl?: number | null;
  created_at?: string | null;
};

export type Report = {
  cost_toman: number;
  leads: number;
  views: number;
  clicks: number;
  cpl: number | null;
  cpv: number | null;
  channels: Array<{ label: string; cost: number; leads: number; views: number }>;
  trend: Array<{ day: string; cost: number; leads: number }>;
  pages: Array<{ name: string; cost: number; views: number; leads: number; cpv: number | null; cpl: number | null }>;
  notes: string[];
  advice?: string;
  budget_toman?: number | null;
  budget_over?: boolean;
  budget_warning?: string;
  starts_on: string | null;
  ends_on: string | null;
  source?: "sheet" | "google";
};

export type CampaignDetail = CampaignRow & { report: Report; brief?: CampaignBriefData };

export type BriefPlanRow = { day: string; kind: string; details: string; place: string };
export type BriefAdPhase = { name: string; goal: string; audience: string; budget_share: number | null; text: string };
export type CampaignBriefData = {
  slogan: string;
  goals: string[];
  angle: string;
  content_plan: BriefPlanRow[];
  caption: string;
  reels: string[];
  ad_phases: BriefAdPhase[];
  ctas: string[];
  hashtags: string[];
  highlight: string;
  pinned: string;
};
export type BriefDraft = { brief: CampaignBriefData; source: "llm" | "template" };

export type Panel = {
  id: string;
  code: string;
  name: string;
  sender_line: string;
  tariff_toman: number;
  balance_toman: number;
  low_balance_toman: number;
  low: boolean;
  spent_toman?: number;
  charged_toman?: number;
  api_username?: string;
  has_secret?: boolean;
};

export type SmsCheck = {
  pages: number;
  chars: number;
  ok: boolean;
  issues: string[];
  warnings?: string[];
  room?: number;
  capacity?: number;
  language?: string;
  single_limit?: number;
  estimated_cost_toman: number;
};

export type SmsDraft = {
  source: string;
  messages: Array<{ kind?: string; label?: string; note?: string; text: string; check: SmsCheck }>;
};

export type SmsSend = {
  id: string;
  campaign_code: string;
  body: string;
  pages: number;
  recipient_count: number;
  cost_toman: number;
  delivered_count: number;
  leads: number;
  sent_at: string | null;
  panel_name?: string;
  pishgam_message_id?: number | null;
};

export type RecipientList = {
  id: string;
  name: string;
  campaign_id?: string | null;
  raw_count: number;
  duplicate_count: number;
  blacklist_count: number;
  recent_count: number;
  invalid_count: number;
  final_count: number;
};

export type Payment = {
  id: string;
  kind: string;
  amount_toman: number;
  beneficiary: string;
  iban: string;
  status: string;
  cost_center: string;
  note: string;
  requester_id?: string | null;
  requester_name?: string;
  created_at?: string | null;
  campaign_id: string | null;
  panel_id: string | null;
  project_id?: string | null;
  request_id?: string | null;
};

export type PageRow = {
  id: string;
  name: string;
  followers: number;
  topic: string;
  contact: string;
  price_toman: number;
  cpl?: number | null;
  cpv?: number | null;
  prices?: Array<{ price_toman: number; note: string; created_at: string | null }>;
};

export type Suggest = {
  remaining_toman: number;
  pages: Array<{ id: string; name: string; price_toman: number; cpl: number | null; cpv: number | null }>;
};

export type CarRequest = {
  id: string;
  summary: string;
  brand: string;
  source: string;
  status: string;
  raw_text: string;
  campaign_id: string | null;
};

export type Sheet = {
  google_connected: boolean;
  spreadsheet_url?: string;
  reason?: string;
  campaigns: Array<Pick<CampaignRow, "id" | "code" | "title" | "brand" | "cost_toman" | "leads" | "cpl"> & { views: number }>;
  sms: SmsSend[];
  stories: Array<Story & { campaign_code?: string }>;
  costs: Array<{ id: string; cost_number: number; spent_on: string | null; amount_toman: number; kind: string; detail: string; brand: string; campaign_code: string; description: string }>;
};

export type Story = {
  id: string;
  campaign_id?: string | null;
  campaign_code?: string;
  kind?: string;
  status?: string;
  payment_id?: string | null;
  payment_status?: string;
  page: string;
  published_on: string | null;
  cost_toman: number;
  views: number;
  leads: number;
  cpl: number | null;
  cpv: number | null;
  ctr: number | null;
  cpc: number | null;
  cpr: number | null;
  engagement: number | null;
  completion: number | null;
  exit_rate: number | null;
};

export type MizitoRequestFields = {
  intent?: string;
  brand?: string;
  tag?: string;
  cars?: string[];
  offer?: {
    no_price?: boolean;
    delivery_days?: number | null;
    prices?: string[];
    prepayment?: string;
    installments?: boolean;
    no_budget_limit?: boolean;
  };
  channels?: string[];
  branches?: string[];
  dates?: string[];
  code?: string;
  card_title?: string;
};

export type CampaignBrief = { id: string; code: string; title: string; status: string };

export type MizitoRequest = {
  id: string;
  kind: string;
  status: string;
  source_kind: string;
  source_title: string;
  msg_index: number | null;
  happened_at: string | null;
  created_at: string | null;
  decided_at: string | null;
  fields: MizitoRequestFields;
  excerpt: string;
  suggested: { title: string; tag: string; brand: string; channels: string[] };
  campaign: CampaignBrief | null;
  matched_campaign: CampaignBrief | null;
};

export type MizitoRequests = { requests: MizitoRequest[]; counts: Record<string, number>; checked_at: string | null };

export type MizitoRequestCheck = {
  checked: boolean;
  reason: string;
  added: number;
  found?: number;
  dialogs?: number;
  pages?: number;
  checked_at?: string;
};

export const MIZITO_REQUEST_KIND: Record<string, string> = {
  start: "شروع/افزایش تبلیغ",
  stop: "توقف",
  sms: "پیامک",
  circular: "بخشنامه",
};

export const MIZITO_CHANNEL: Record<string, string> = {
  sms: "پیامک",
  lbs: "LBS",
  ig_story: "استوری/پیج",
  influencer: "بلاگر",
  divar: "دیوار",
  google: "گوگل",
  banner: "بنر",
  content: "تولید محتوا",
};
