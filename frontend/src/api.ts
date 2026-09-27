const TOKEN_KEY = "cm_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail?.message || body.detail || JSON.stringify(body.detail) || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, String(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  login: (organization_slug: string, email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ organization_slug, email, password }),
    }),
  me: () =>
    request<{
      id: string;
      full_name: string;
      email: string;
      organization_id: string;
      role_id: string | null;
      branch_id: string | null;
      team_id: string | null;
      permissions: string[];
    }>("/auth/me"),
  roles: () => request<Array<{ id: string; name: string; code: string }>>("/org/roles"),
  search: (q: string) =>
    request<{ total: number; hits: Array<Record<string, unknown>> }>(
      `/search?q=${encodeURIComponent(q)}&limit=30`,
    ),
  workItems: {
    list: (params?: { status?: string }) => {
      const q = params?.status ? `?status=${encodeURIComponent(params.status)}` : "";
      return request<Array<Record<string, unknown>>>(`/work-items${q}`);
    },
    get: (id: string) => request<Record<string, unknown>>(`/work-items/${id}`),
    progress: (id: string) =>
      request<{
        work_item_id: string;
        title: string;
        status: string;
        total_tasks: number;
        completed_tasks: number;
        overdue_tasks?: number;
        progress_pct: number;
        tasks: Array<Record<string, unknown>>;
        participants?: Array<Record<string, unknown>>;
      }>(`/work-items/${id}/progress`),
    timeline: (id: string) =>
      request<Array<Record<string, unknown>>>(`/work-items/${id}/timeline`),
    create: (body: Record<string, unknown>) =>
      request<Record<string, unknown>>("/work-items", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    addParticipant: (id: string, userId: string) =>
      request<Record<string, unknown>>(`/work-items/${id}/participants`, {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      }),
  },
  vehicles: {
    list: (q = "") =>
      request<Array<Record<string, unknown>>>(
        `/inventory/vehicles${q ? `?q=${encodeURIComponent(q)}` : ""}`,
      ),
    get: (id: string) => request<Record<string, unknown>>(`/inventory/vehicles/${id}`),
    context: (id: string) =>
      request<{
        vehicle: Record<string, unknown>;
        work_items: Array<Record<string, unknown>>;
        cases: Array<Record<string, unknown>>;
        history: Array<Record<string, unknown>>;
      }>(`/inventory/vehicles/${id}/context`),
    create: (body: Record<string, unknown>) =>
      request<Record<string, unknown>>("/inventory/vehicles", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    importFile: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return request<{
        created: number;
        skipped: number;
        errors: string[];
        vehicles: Array<Record<string, unknown>>;
      }>("/inventory/vehicles/import", { method: "POST", body: fd });
    },
    downloadImportTemplate: async (format: "xlsx" | "csv" = "xlsx") => {
      const token = getToken();
      const res = await fetch(`/api/inventory/vehicles/import-template?format=${format}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new ApiError(res.status, res.statusText);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `vehicles_import_template.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    },
  },
  cases: {
    list: (params?: { type?: string; status?: string; owner_id?: string }) => {
      const sp = new URLSearchParams();
      if (params?.type) sp.set("type", params.type);
      if (params?.status) sp.set("status", params.status);
      if (params?.owner_id) sp.set("owner_id", params.owner_id);
      const q = sp.toString();
      return request<Array<Record<string, unknown>>>(`/cases${q ? `?${q}` : ""}`);
    },
    create: (body: Record<string, unknown>) =>
      request<Record<string, unknown>>("/cases", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    timeline: (id: string) =>
      request<Array<Record<string, unknown>>>(`/timeline/case/${id}`),
  },
  tasks: {
    list: (params?: { assignee_id?: string; overdue_only?: boolean; work_item_id?: string }) => {
      const sp = new URLSearchParams();
      if (params?.assignee_id) sp.set("assignee_id", params.assignee_id);
      if (params?.work_item_id) sp.set("work_item_id", params.work_item_id);
      if (params?.overdue_only) sp.set("overdue_only", "true");
      const q = sp.toString();
      return request<Array<Record<string, unknown>>>(`/tasks${q ? `?${q}` : ""}`);
    },
    complete: (id: string) =>
      request<Record<string, unknown>>(`/tasks/${id}/complete`, { method: "POST" }),
    create: (body: Record<string, unknown>) =>
      request<Record<string, unknown>>("/tasks", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    assign: (id: string, body: Record<string, unknown>) =>
      request<Record<string, unknown>>(`/tasks/${id}/assign`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    addParticipant: (id: string, userId: string) =>
      request<Record<string, unknown>>(`/tasks/${id}/participants`, {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      }),
  },
  notifications: () => request<Array<Record<string, unknown>>>("/notifications"),
  telegram: {
    status: (provider = "telegram") =>
      request<{
        linked: boolean;
        provider: string;
        bot_username: string | null;
        username: string | null;
        disabled: boolean;
        notify_prefs: Record<string, boolean> | null;
        quiet_start_hour: number | null;
        quiet_end_hour: number | null;
        digest_enabled: boolean;
        deep_link_template: string | null;
      }>(`/telegram/status?provider=${encodeURIComponent(provider)}`),
    linkCode: (provider = "telegram") =>
      request<{
        link_code: string;
        deep_link: string | null;
        instructions: string;
        expires_in_minutes: number;
        provider: string;
      }>(`/telegram/link-code?provider=${encodeURIComponent(provider)}`, {
        method: "POST",
      }),
    unlink: (provider = "telegram") =>
      request<{ ok: boolean }>(`/telegram/unlink?provider=${encodeURIComponent(provider)}`, {
        method: "POST",
      }),
    updatePrefs: (body: {
      notify_prefs?: Record<string, boolean>;
      quiet_start_hour?: number | null;
      quiet_end_hour?: number | null;
      clear_quiet?: boolean;
      digest_enabled?: boolean;
      provider?: string;
    }) =>
      request<Record<string, unknown>>("/telegram/prefs", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
  },
  people: {
    list: (q?: string) =>
      request<Array<Record<string, unknown>>>(
        `/people${q ? `?q=${encodeURIComponent(q)}` : ""}`,
      ),
    get: (id: string) => request<Record<string, unknown>>(`/people/${id}`),
    reports: (id: string) =>
      request<Array<Record<string, unknown>>>(`/people/${id}/reports`),
    workload: (id: string) =>
      request<{
        user_id: string;
        open_tasks: number;
        overdue_tasks: number;
        active_work_items: number;
        tasks: Array<Record<string, unknown>>;
      }>(`/users/${id}/workload`),
  },
  teams: {
    list: () => request<Array<Record<string, unknown>>>("/teams"),
    members: (id: string) =>
      request<Array<Record<string, unknown>>>(`/org/teams/${id}/members`),
  },
  branches: {
    list: () => request<Array<Record<string, unknown>>>("/branches"),
  },
  departments: {
    list: () => request<Array<Record<string, unknown>>>("/departments"),
  },
  relationships: {
    list: () => request<Array<Record<string, unknown>>>("/relationships"),
  },
  conversations: {
    list: (opts?: { workItemId?: string; campaignId?: string }) => {
      const params = new URLSearchParams();
      if (opts?.workItemId) params.set("work_item_id", opts.workItemId);
      if (opts?.campaignId) params.set("campaign_id", opts.campaignId);
      const qs = params.toString();
      return request<Array<Record<string, unknown>>>(
        `/conversations${qs ? `?${qs}` : ""}`,
      );
    },
    create: (body: Record<string, unknown>) =>
      request<Record<string, unknown>>("/conversations", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    messages: (id: string) =>
      request<Array<Record<string, unknown>>>(`/conversations/${id}/messages`),
    postMessage: (id: string, text: string) =>
      request<Record<string, unknown>>(`/conversations/${id}/messages`, {
        method: "POST",
        body: JSON.stringify({ text, channel: "WEB" }),
      }),
  },
  campaigns: {
    list: (q?: string) =>
      request<Array<Record<string, unknown>>>(
        `/campaigns${q ? `?q=${encodeURIComponent(q)}` : ""}`,
      ),
    create: (body: Record<string, unknown>) =>
      request<Record<string, unknown>>("/campaigns", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },
  agent: (message: string) =>
    request<{
      request_id: string;
      ok: boolean;
      intent: string;
      message: string;
      clarification?: string;
      work_item_id?: string;
      task_ids: string[];
    }>("/agent/communication", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  inventoryAgent: (body: {
    message?: string;
    min_days?: number;
    min_branch_requests?: number;
    auto_create?: boolean;
  }) =>
    request<{
      request_id: string;
      ok: boolean;
      intent: string;
      message: string;
      opportunities_found: number;
      cases_created: string[];
      work_item_ids: string[];
    }>("/agent/inventory", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  salesAgent: (body: {
    message?: string;
    stale_days?: number;
    auto_create?: boolean;
    case_id?: string;
  }) =>
    request<{
      request_id: string;
      ok: boolean;
      intent: string;
      message: string;
      follow_ups_found: number;
      cases_created: string[];
      work_item_ids: string[];
      task_ids: string[];
    }>("/agent/sales", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  purchaseAgent: (body: {
    message?: string;
    stale_days?: number;
    auto_create?: boolean;
  }) =>
    request<{
      request_id: string;
      ok: boolean;
      intent: string;
      message: string;
      opportunities_found: number;
      cases_created: string[];
      work_item_ids: string[];
      task_ids: string[];
    }>("/agent/purchase", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  divarAgent: (body: {
    message?: string;
    vehicle_id?: string;
    auto_create?: boolean;
    limit?: number;
  }) =>
    request<{
      request_id: string;
      ok: boolean;
      intent: string;
      message: string;
      listings_prepared: number;
      listing_ids: string[];
      work_item_ids: string[];
    }>("/agent/divar", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  assignment: {
    recommend: (body: Record<string, unknown>) =>
      request<{
        recommended_user_id: string | null;
        candidates: Array<Record<string, unknown>>;
        auto_assign_allowed: boolean;
      }>("/assignment/recommend", { method: "POST", body: JSON.stringify(body) }),
  },
  knowledge: {
    list: () => request<Array<Record<string, unknown>>>("/knowledge/documents"),
    upload: (body: Record<string, unknown>) =>
      request<Record<string, unknown>>("/knowledge/documents", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    search: (query: string, category?: string) =>
      request<Array<Record<string, unknown>>>("/knowledge/search", {
        method: "POST",
        body: JSON.stringify({ query, category, top_k: 5 }),
      }),
  },
  rag: {
    ask: (query: string) =>
      request<{
        request_id: string;
        intent: string;
        query: string;
        total: number;
        answer: string;
        answer_mode?: string;
        hits: Array<{
          entity_type: string;
          entity_id: string;
          title: string;
          content: string;
          sources: string[];
          score: number;
          metadata?: Record<string, unknown>;
        }>;
        context: string;
        analyzed: Record<string, unknown>;
      }>("/rag/hybrid", {
        method: "POST",
        body: JSON.stringify({ query, top_k: 8 }),
      }),
  },
  customers: {
    list: (q?: string) =>
      request<Array<Record<string, unknown>>>(
        `/customers${q ? `?q=${encodeURIComponent(q)}` : ""}`,
      ),
    create: (body: Record<string, unknown>) =>
      request<Record<string, unknown>>("/customers", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },
};
