import { ApiError, getToken, setToken } from "../api";

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
      detail = body.detail?.message || body.detail || detail;
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

export function toman(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 }).format(Math.round(Number(value)));
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
  advance: (id: string, action: string) =>
    request<Payment>(`/perf/payments/${id}/advance`, { method: "POST", body: JSON.stringify({ action }) }),
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
  connections: (live = false) => request<Connections>(`/perf/connections?live=${live ? "true" : "false"}`),
  saveMizito: (token: string) =>
    request<{ saved: boolean; hint: string }>("/perf/connections/mizito", { method: "PUT", body: JSON.stringify({ token }) }),
  isms: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>("/perf/integrations/isms", { method: "POST", body: JSON.stringify(body) }),
  pishgamBalance: (panelId: string) =>
    request<Record<string, unknown>>(`/perf/integrations/pishgam/balance?panel_id=${panelId}`),
};

export type MizitoCard = { project: string; board: string; title: string; code: string };

export type MizitoSnapshot = {
  connected: boolean;
  reason?: string;
  projects: Array<{ title: string; id: string }>;
  cards: MizitoCard[];
  open_count: number;
  read_at?: string | null;
};

export type SheetLink = { configured: boolean; connected: boolean; title: string; reason: string };

export type Connections = {
  sheets_ready: boolean;
  service_account: string;
  sheets: Record<string, SheetLink>;
  mizito: { saved: boolean; hint: string };
  panels: Array<{ name: string; code: string; ready: boolean }>;
  insight: { ready: boolean; provider: string };
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
  starts_on: string | null;
  ends_on: string | null;
  source?: "sheet" | "google";
};

export type CampaignDetail = CampaignRow & { report: Report };

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
