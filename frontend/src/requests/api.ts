import { ApiError, getToken, setToken } from "../api";
import { apiErrorDetail } from "../lib/httpErrorDetail";

export type TeamHome = {
  team: { id: string; name: string; code: string };
  shared: boolean;
  can_edit: boolean;
  requests: Array<{ id: string; code: string; title: string; status: string }>;
  projects: Array<{ id: string; code: string; title: string; request_code: string; team_name: string; status: string; due_date: string | null; progress: { total: number; done: number; ratio: number } }>;
  sections: Array<{ id: string; name: string; code: string }>;
  campaigns?: Array<{ id: string; code: string; title: string; project_id: string | null; status: string }>;
  own_section: boolean;
  counts?: { open_requests: number; active_projects: number; active_campaigns: number; month_cost: number };
};

export type WorkRequest = {
  id: string;
  code: string;
  title: string;
  description: string;
  kind: string;
  priority: string;
  due_date: string | null;
  status: string;
  requested_by: string | null;
  requester_name: string;
  team_id: string | null;
  team_name: string;
  created_at: string;
  updated_at: string | null;
};

export type WorkProject = {
  id: string;
  code: string;
  title: string;
  description: string;
  kind: string;
  request_id: string | null;
  mizito_lane?: string | null;
  mizito_card_id?: string | null;
  mizito_board?: string | null;
  mizito_code?: string | null;
  mizito_progress?: number | null;
  mizito_checklist_done?: number | null;
  mizito_checklist_total?: number | null;
  mizito_attachments?: number | null;
  mizito_has_comments?: boolean | null;
  mizito_created_at?: string | null;
  mizito_modified_at?: string | null;
  mizito_deadline?: string | null;
  source?: "mizito" | "cm";
  request_code: string;
  request_title?: string;
  team_id: string | null;
  team_name: string;
  status: string;
  due_date?: string | null;
  task_total?: number;
  task_done?: number;
  requester_acceptance?: string | null;
  created_at: string;
  updated_at: string | null;
};

export type RequestDetail = {
  request: WorkRequest;
  projects: WorkProject[];
  tasks: Array<{ id: string; title: string; status: string; project_id?: string | null }>;
  spine: Array<{ at?: string; kind: string; label: string; status?: string; code?: string }>;
};

export type CampaignReportRow = {
  id: string;
  code: string;
  title: string;
  brand: string;
  status: string;
  cost_toman: number;
  leads: number;
  views: number;
  cpl: number | null;
  cpv: number | null;
};

export type CampaignReportResponse = {
  count: number;
  cost_toman: number;
  leads: number;
  campaigns: CampaignReportRow[];
};

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

export type MizitoKanbanCardBrief = {
  id: string;
  code: string;
  title: string;
  status: string;
  source?: "mizito" | "cm";
  mizito_card_id?: string | null;
  mizito_status?: string | null;
  mizito_code?: string | null;
  weight?: number;
  due?: string | null;
  overdue?: boolean;
  checklist_done?: number;
  checklist_total?: number;
  attachments?: number;
  has_comments?: boolean;
  modified_at?: string | null;
  assignee_names?: string[];
  assignee_extra?: number;
};

export type MizitoKanbanColumn = {
  board_id: string;
  title: string;
  position: number;
  is_archive?: boolean;
  total: number;
  open_count: number;
  done_count: number;
  has_more: boolean;
  projects: MizitoKanbanCardBrief[];
};

export type MizitoKanbanResponse = {
  lane: string;
  lane_title: string;
  import_ready: boolean;
  lane_total: number;
  columns: MizitoKanbanColumn[];
};

export type MizitoKanbanColumnResponse = {
  board_id: string;
  total: number;
  open_count: number;
  done_count: number;
  projects: MizitoKanbanCardBrief[];
  offset: number;
  limit: number;
  has_more: boolean;
};

export type TeamOption = { id: string; name: string; code: string; parent_team_id?: string | null };

export const requestsApi = {
  list: (status: string = "") =>
    request<WorkRequest[]>(`/requests${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  get: (id: string) => request<RequestDetail>(`/requests/${id}`),
  spine: (id: string) =>
    request<{ request_id: string; items: Array<{ at?: string; kind: string; label: string; status?: string; code?: string }> }>(
      `/requests/${id}/spine`,
    ),
  create: (body: Record<string, unknown>) => request<WorkRequest>("/requests", { method: "POST", body: JSON.stringify(body) }),
  patch: (id: string, body: Record<string, unknown>) =>
    request<WorkRequest>(`/requests/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => request<void>(`/requests/${id}`, { method: "DELETE" }),
  mizitoLanes: (counts = false) =>
    request<Array<{ slug: string; title: string; team_code: string; project_count?: number }>>(
      `/requests/mizito-lanes${counts ? "?counts=true" : ""}`,
    ),
  syncMizitoWork: (purgeManual = false) =>
    request<Record<string, unknown>>(
      `/requests/mizito/sync-work?purge_manual=${purgeManual ? "true" : "false"}`,
      { method: "POST" },
    ),
  mizitoKanban: (opts: {
    lane: string;
    source?: string;
    q?: string;
    hide_done?: boolean;
    include_archive?: boolean;
    per_column?: number;
  }) => {
    const params = new URLSearchParams({ lane: opts.lane });
    if (opts.source) params.set("source", opts.source);
    if (opts.q?.trim()) params.set("q", opts.q.trim());
    if (opts.hide_done) params.set("hide_done", "true");
    if (opts.include_archive) params.set("include_archive", "true");
    if (opts.per_column != null) params.set("per_column", String(opts.per_column));
    return request<MizitoKanbanResponse>(`/requests/mizito-kanban?${params.toString()}`);
  },
  mizitoKanbanColumn: (opts: {
    lane: string;
    board_id: string;
    source?: string;
    q?: string;
    hide_done?: boolean;
    offset?: number;
    limit?: number;
  }) => {
    const params = new URLSearchParams({ lane: opts.lane, board_id: opts.board_id });
    if (opts.source) params.set("source", opts.source);
    if (opts.q?.trim()) params.set("q", opts.q.trim());
    if (opts.hide_done) params.set("hide_done", "true");
    if (opts.offset != null) params.set("offset", String(opts.offset));
    if (opts.limit != null) params.set("limit", String(opts.limit));
    return request<MizitoKanbanColumnResponse>(`/requests/mizito-kanban/column?${params.toString()}`);
  },
  projectsPage: (opts: {
    q?: string;
    mizito_lane?: string;
    source?: string;
    status?: string;
    sort?: string;
    order?: string;
    limit?: number;
    offset?: number;
  }) => {
    const params = new URLSearchParams();
    if (opts.q?.trim()) params.set("q", opts.q.trim());
    if (opts.mizito_lane) params.set("mizito_lane", opts.mizito_lane);
    if (opts.source) params.set("source", opts.source);
    if (opts.status) params.set("status", opts.status);
    if (opts.sort) params.set("sort", opts.sort);
    if (opts.order) params.set("order", opts.order);
    if (opts.limit != null) params.set("limit", String(opts.limit));
    if (opts.offset != null) params.set("offset", String(opts.offset));
    const qs = params.toString();
    return request<{ items: WorkProject[]; total: number; limit: number; offset: number }>(
      `/requests/projects/page${qs ? `?${qs}` : ""}`,
    );
  },
  projects: (requestId: string = "", status: string = "", mizitoLane: string = "", source: string = "") => {
    const params = new URLSearchParams();
    if (requestId) params.set("request_id", requestId);
    if (status) params.set("status", status);
    if (mizitoLane) params.set("mizito_lane", mizitoLane);
    if (source) params.set("source", source);
    const qs = params.toString();
    return request<WorkProject[]>(`/requests/projects${qs ? `?${qs}` : ""}`);
  },
  mizitoSyncStatus: () =>
    request<{
      pending_count: number;
      card_url_prefix: string;
      last_run: {
        ok: boolean;
        error: string;
        finished_at: string | null;
        created: number;
        updated: number;
        unchanged: number;
        pending: number;
        truncated: boolean;
      } | null;
    }>("/requests/mizito/sync-status"),
  mizitoChanges: (status = "", projectId = "") => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (projectId) params.set("project_id", projectId);
    const qs = params.toString();
    return request<Array<{ id: string; project_id: string | null; kind: string; field: string; old_value: string; new_value: string; status: string; created_at: string }>>(
      `/requests/mizito/changes${qs ? `?${qs}` : ""}`,
    );
  },
  decideMizitoChange: (id: string, approve: boolean) =>
    request<{ id: string; status: string }>(`/requests/mizito/changes/${id}/${approve ? "approve" : "ignore"}`, { method: "POST" }),
  createProject: (requestId: string, body: Record<string, unknown>) =>
    request<WorkProject>(`/requests/${requestId}/projects`, { method: "POST", body: JSON.stringify(body) }),
  createStandaloneProject: (body: Record<string, unknown>, requestId = "") =>
    request<WorkProject>(`/requests/projects${requestId ? `?request_id=${encodeURIComponent(requestId)}` : ""}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  patchProject: (id: string, body: Record<string, unknown>) =>
    request<WorkProject>(`/requests/projects/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteProject: (id: string) => request<void>(`/requests/projects/${id}`, { method: "DELETE" }),
  teams: () => request<TeamOption[]>("/teams"),
  teamHome: (id: string) => request<TeamHome>(`/teams/${id}`),
  project: (id: string) => request<Record<string, unknown>>(`/requests/projects/${id}`),
  openProjectThread: (id: string) =>
    request<{ id: string; topic: string }>(`/requests/projects/${id}/thread`, { method: "POST" }),
  convertTask: (requestId: string, title: string) =>
    request<Record<string, unknown>>(`/requests/${requestId}/tasks`, { method: "POST", body: JSON.stringify({ title }) }),
  applyTemplate: (projectId: string) =>
    request<Record<string, unknown>>(`/requests/projects/${projectId}/apply-template`, {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    }),
  addTask: (projectId: string, title: string, assigneeIds: string[] = []) =>
    request<Record<string, unknown>>(`/requests/projects/${projectId}/tasks`, {
      method: "POST",
      body: JSON.stringify({ title, assignee_ids: assigneeIds }),
    }),
  setMembers: (projectId: string, userIds: string[]) =>
    request<Array<{ id: string; full_name: string }>>(`/requests/projects/${projectId}/members`, {
      method: "PUT",
      body: JSON.stringify({ user_ids: userIds }),
    }),
  setCampaigns: (projectId: string, campaignIds: string[]) =>
    request<Array<{ id: string; code: string; title: string }>>(`/requests/projects/${projectId}/campaigns`, {
      method: "PUT",
      body: JSON.stringify({ campaign_ids: campaignIds }),
    }),
  createCampaign: (projectId: string, title: string, tag: string) =>
    request<{ id: string; code: string; title: string; brand: string }>(`/requests/projects/${projectId}/campaigns`, {
      method: "POST",
      body: JSON.stringify({ title, tag }),
    }),
  addAttachment: (projectId: string, body: { title: string; url: string }) =>
    request<Record<string, string>>(`/requests/projects/${projectId}/attachments`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  addDesign: (projectId: string, title: string) =>
    request<Record<string, string>>(`/requests/projects/${projectId}/designs`, {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  patchDesign: (projectId: string, itemId: string, status: string) =>
    request<Record<string, string>>(`/requests/projects/${projectId}/designs/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  addShoot: (projectId: string, title: string) =>
    request<Record<string, string>>(`/requests/projects/${projectId}/shoots`, {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  patchShoot: (projectId: string, itemId: string, status: string) =>
    request<Record<string, string>>(`/requests/projects/${projectId}/shoots/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  myWork: () =>
    request<Record<string, Array<Record<string, string>>>>("/requests/my-work"),
  workReportDownload: async (scope: string, projectId = "", requestId = "") => {
    const params = new URLSearchParams({ scope });
    if (projectId) params.set("project_id", projectId);
    if (requestId) params.set("request_id", requestId);
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`/api/reports/work.xlsx?${params.toString()}`, { headers, credentials: "include" });
    if (!res.ok) throw new Error(res.statusText);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "work.xlsx";
    a.click();
    URL.revokeObjectURL(url);
  },
  workReport: (scope: string, projectId = "", requestId = "") => {
    const params = new URLSearchParams({ scope });
    if (projectId) params.set("project_id", projectId);
    if (requestId) params.set("request_id", requestId);
    return request<Record<string, unknown>>(`/reports/work?${params.toString()}`);
  },
  campaignReport: (scope = "me", projectId = "") => {
    const params = new URLSearchParams({ scope });
    if (projectId) params.set("project_id", projectId);
    return request<CampaignReportResponse>(`/reports/campaigns?${params.toString()}`);
  },
  projectAcceptance: (projectId: string, decision: "accepted" | "returned", note = "") =>
    request<{ ok: boolean }>(`/requests/projects/${projectId}/acceptance`, {
      method: "POST",
      body: JSON.stringify({ decision, note }),
    }),
};