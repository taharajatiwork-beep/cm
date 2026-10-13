import { ApiError, getToken, setToken } from "./api";

export type CalendarEntry = {
  id: string;
  on_date: string;
  tier: string;
  format: string;
  channel: string;
  topic: string;
  cta: string;
  kpi: string;
  status: string;
  campaign_id: string | null;
  assignee_id: string | null;
  assignee_name: string;
  project_id: string | null;
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
};

export type DraftEntry = Omit<CalendarEntry, "id" | "campaign_id" | "assignee_id" | "assignee_name" | "project_id">;

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
  return res.json() as Promise<T>;
}

export const calendarApi = {
  range: (from: string, to: string, year: number, month: number) =>
    request<CalendarPayload>(`/calendar?from=${from}&to=${to}&year=${year}&month=${month}`),
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
