import { ApiError, getToken, setToken } from "./api";
import { apiErrorDetail } from "./lib/httpErrorDetail";

export type CalendarEntry = {
  id: string;
  entry_id: string;
  on_date: string;
  entry_type: string;
  title: string;
  topic: string;
  tier: string;
  format: string;
  channel: string;
  cta: string;
  kpi: string;
  status: string;
  production_status: string;
  published_url: string;
  all_day: boolean;
  start_time: string | null;
  end_time: string | null;
  start: string;
  end: string;
  location: string;
  notes: string;
  recurrence: string;
  recur_until: string | null;
  recurrence_parent_id: string | null;
  campaign_id: string | null;
  assignee_id: string | null;
  assignee_name: string;
  attendee_ids: string[];
  project_id: string | null;
  color_key: string;
  late: boolean;
  kind: string;
  conflicts?: string[];
};

export type CalendarEvent = {
  kind: string;
  date: string;
  title: string;
  person: string;
  person_id: string | null;
  link: string;
  status: string;
  id: string;
  color_key?: string;
  late?: boolean;
  start?: string;
  end?: string;
};

export type CalendarOccasion = {
  id: string;
  on_date: string;
  title: string;
  kind: string;
  is_off: boolean;
  global: boolean;
};

export type CalendarLoad = {
  person_id: string;
  date: string;
  count: number;
};

export type CalendarMonth = {
  year: number;
  month: number;
  title: string;
  goal: string;
  logic: string[];
  weeks: Array<{ from: string; to: string; title: string; body: string }>;
  mix: Array<{ label: string; share: number; note: string }>;
  kpis: Array<{ stage: string; kpi: string; use: string }>;
  rules: string[];
};

export type CalendarPayload = {
  entries: CalendarEntry[];
  month: CalendarMonth | null;
  events: CalendarEvent[];
  occasions: CalendarOccasion[];
  load: CalendarLoad[];
};

export type DraftEntry = Omit<
  CalendarEntry,
  | "id"
  | "entry_id"
  | "campaign_id"
  | "assignee_id"
  | "assignee_name"
  | "project_id"
  | "title"
  | "attendee_ids"
  | "color_key"
  | "late"
  | "kind"
  | "conflicts"
  | "start"
  | "end"
>;

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
      detail = apiErrorDetail(body.detail, detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, String(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const calendarApi = {
  range: (from: string, to: string, year: number, month: number, layers?: string, mine?: boolean) => {
    const params = new URLSearchParams({ from, to, year: String(year), month: String(month) });
    if (layers) params.set("layers", layers);
    if (mine) params.set("mine", "1");
    return request<CalendarPayload>(`/calendar?${params}`);
  },
  create: (body: Record<string, unknown>) =>
    request<CalendarEntry>("/calendar/entries", { method: "POST", body: JSON.stringify(body) }),
  bulk: (entries: DraftEntry[]) =>
    request<{ added: number }>("/calendar/entries/bulk", { method: "POST", body: JSON.stringify({ entries }) }),
  patch: (id: string, body: Record<string, unknown>) =>
    request<CalendarEntry>(`/calendar/entries/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => request<void>(`/calendar/entries/${id}`, { method: "DELETE" }),
  saveMonth: (year: number, month: number, body: Record<string, unknown>) =>
    request<CalendarMonth>(`/calendar/month/${year}/${month}`, { method: "PUT", body: JSON.stringify(body) }),
  draft: (year: number, month: number) =>
    request<{ source: string; entries: DraftEntry[] }>(`/calendar/month/${year}/${month}/draft`, { method: "POST" }),
  occasions: (from: string, to: string) =>
    request<CalendarOccasion[]>(`/calendar/occasions?from=${from}&to=${to}`),
  createOccasion: (body: Record<string, unknown>) =>
    request<CalendarOccasion>("/calendar/occasions", { method: "POST", body: JSON.stringify(body) }),
  removeOccasion: (id: string) => request<void>(`/calendar/occasions/${id}`, { method: "DELETE" }),
  async download(from: string, to: string) {
    const headers = new Headers();
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const res = await fetch(`/api/calendar/export.xlsx?from=${from}&to=${to}`, { headers, credentials: "include" });
    if (!res.ok) throw new ApiError(res.status, "دانلود فایل نشد");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "calendar.xlsx";
    link.click();
    URL.revokeObjectURL(url);
  },
};
