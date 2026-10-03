let memoryToken: string | null = null;

export function getToken(): string | null {
  return memoryToken;
}

export function setToken(token: string | null) {
  memoryToken = token;
  localStorage.removeItem("cm_token");
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

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`/api${path}`, { ...init, headers, credentials: "include" });
  if (res.status === 401 && retry && path !== "/auth/refresh" && path !== "/auth/login") {
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
      detail = body.detail?.message || body.detail || JSON.stringify(body.detail) || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, String(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** نمای کلی سازمان برای تب «نمای کلی» صفحه ادمین (فقط org.admin). */
export interface AdminOverview {
  as_of_jalali: string;
  users: { total: number; active: number; inactive: number; locked: number };
  messages_7d: number;
  conversations_waiting_reply: number;
  avg_first_reply_minutes: number | null;
  tasks_by_branch: Array<{ branch: string; open: number; overdue: number }>;
  top_users: Array<{ user_id: string; name: string; open_tasks: number }>;
  cases: { open: number; sla_breached: number };
  approvals_pending: number;
  vehicles: { in_stock: number; reserved: number; sold: number };
  divar_errors: number;
  trend: Array<{
    week: number | null;
    date: string | null;
    kpis: Record<string, number | string>;
  }>;
}

/** تحلیل‌های تفصیلی تب «تحلیل‌ها» (فقط org.admin). */
export interface AdminAnalytics {
  as_of_jalali: string;
  tasks_weekly: Array<{ week: string; created: number; completed: number }>;
  tasks_overdue: number;
  avg_completion_hours: number | null;
  tasks_by_priority: Record<string, number>;
  cases_by_status: Record<string, number>;
  cases_by_type: Record<string, number>;
  avg_case_resolution_hours: number | null;
  reply_buckets: { lt5: number; lt30: number; lt120: number; gt120: number; no_reply: number };
  messages_daily: Array<{ day: string; count: number }>;
  vehicles_aging: { lt7: number; lt30: number; lt90: number; gt90: number };
  vehicles_value_by_status: Record<string, number>;
  audit_daily_7d: Array<{ day: string; count: number }>;
  top_actions: Array<{ action: string; count: number }>;
  login_failed_7d: number;
}

/** مانیتورینگ سلامت سیستم تب «مانیتورینگ» (فقط org.admin). */
export interface AdminMonitoring {
  as_of_jalali: string;
  database: {
    size_bytes: number | null;
    journal_mode: string | null;
    table_counts: Record<string, number>;
  };
  outbox: {
    by_status: Record<string, number>;
    oldest_pending_minutes: number | null;
    failed_samples: Array<{ provider: string; error: string; at: string }>;
  };
  job_locks: Array<{
    name: string;
    owner: string;
    expires_at: string | null;
    stale: boolean;
  }>;
  events_24h: Array<{ type: string; count: number }>;
  auth_failed_24h: number;
  audit_chain: { ok: boolean | null; rows_checked: number; broken_at: number | null; detail: string };
  integrations: Record<string, unknown>;
}

export const api = {
  login: (organization_slug: string, email: string, password: string, totp?: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      headers: totp ? { "X-Totp-Code": totp } : undefined,
      body: JSON.stringify({ organization_slug, email, password }),
    }),
  refresh: () =>
    request<{ access_token: string }>("/auth/refresh", { method: "POST" }, false),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }, false),
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
    page: (cursor?: string | null) => {
      const sp = new URLSearchParams({ envelope: "1", limit: "20" });
      if (cursor) sp.set("cursor", cursor);
      return request<{ items: Array<Record<string, unknown>>; next_cursor: string | null }>(
        `/work-items?${sp.toString()}`,
      );
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
    page: (q = "", cursor?: string | null) => {
      const sp = new URLSearchParams({ envelope: "1", limit: "20" });
      if (q) sp.set("q", q);
      if (cursor) sp.set("cursor", cursor);
      return request<{ items: Array<Record<string, unknown>>; next_cursor: string | null }>(
        `/inventory/vehicles?${sp.toString()}`,
      );
    },
    setStatus: (id: string, to_status: string, note: string) =>
      request<Record<string, unknown>>(`/inventory/vehicles/${id}/status`, {
        method: "POST",
        body: JSON.stringify({ to_status, note }),
      }),
    divar: (id: string) => request<Array<Record<string, unknown>>>(`/inventory/vehicles/${id}/divar`),
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
    update: (id: string, body: { status?: string; owner_id?: string | null }) =>
      request<Record<string, unknown>>(`/cases/${id}`, {
        method: "PATCH",
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
  markNotificationRead: (id: string) =>
    request<{ id: string; is_read: boolean }>(`/notifications/${id}/read`, { method: "POST" }),
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
  admin: {
    permissionCodes: () => request<string[]>("/org/permissions"),
    rolePermissions: (roleId: string) =>
      request<{
        id: string;
        code: string;
        name: string;
        permission_codes: string[];
        data_scope_level: string | null;
      }>(`/org/roles/${roleId}/permissions`),
    updateRole: (roleId: string, body: { permission_codes: string[]; data_scope_level?: string }) =>
      request<Record<string, unknown>>(`/org/roles/${roleId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    updateUser: (userId: string, body: { is_active?: boolean; password?: string }) =>
      request<{ id: string; is_active: boolean }>(`/org/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    addTeam: (userId: string, body: { user_id: string; team_id: string }) =>
      request<{ id: string; team_id: string }>(`/org/users/${userId}/teams`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    createUser: (body: Record<string, unknown>) =>
      request<Record<string, unknown>>("/org/users", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    /** نمای کلی سازمان — فقط org.admin در بک‌اند مجاز است. */
    overview: () => request<AdminOverview>("/admin/overview"),
    /** تحلیل‌های تفصیلی سازمان — فقط org.admin. */
    analytics: () => request<AdminAnalytics>("/admin/analytics"),
    /** مانیتورینگ سلامت سیستم — فقط org.admin. */
    monitoring: () => request<AdminMonitoring>("/admin/monitoring"),
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
    list: (opts?: { workItemId?: string; campaignId?: string; archived?: boolean }) => {
      const params = new URLSearchParams();
      if (opts?.workItemId) params.set("work_item_id", opts.workItemId);
      if (opts?.campaignId) params.set("campaign_id", opts.campaignId);
      if (opts?.archived) params.set("archived", "true");
      const qs = params.toString();
      return request<Array<Record<string, unknown>>>(
        `/conversations${qs ? `?${qs}` : ""}`,
      );
    },
    page: (cursor?: string | null) => {
      const sp = new URLSearchParams({ envelope: "1", limit: "20" });
      if (cursor) sp.set("cursor", cursor);
      return request<{ items: Array<Record<string, unknown>>; next_cursor: string | null }>(
        `/conversations?${sp.toString()}`,
      );
    },
    archive: (id: string) =>
      request<{ id: string; archived: boolean }>(`/conversations/${id}/archive`, { method: "POST" }),
    unarchive: (id: string) =>
      request<{ id: string; archived: boolean }>(`/conversations/${id}/unarchive`, { method: "POST" }),
    addParticipant: (id: string, user_id: string) =>
      request<{ id: string; user_id: string }>(`/conversations/${id}/participants`, {
        method: "POST",
        body: JSON.stringify({ user_id }),
      }),
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
    update: (id: string, body: Record<string, unknown>) =>
      request<Record<string, unknown>>(`/customers/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    page: (q = "", cursor?: string | null) => {
      const sp = new URLSearchParams({ envelope: "1", limit: "20" });
      if (q) sp.set("q", q);
      if (cursor) sp.set("cursor", cursor);
      return request<{ items: Array<Record<string, unknown>>; next_cursor: string | null }>(
        `/customers?${sp.toString()}`,
      );
    },
    exportJson: (id: string) => request<Record<string, unknown>>(`/customers/${id}/export`),
    erase: (id: string) =>
      request<{ id: string; erased: boolean }>(`/customers/${id}/erase`, { method: "POST" }),
  },
  approvals: {
    list: () => request<Array<Record<string, unknown>>>("/approvals"),
    decide: (id: string, decision: "approved" | "rejected", comment?: string) =>
      request<Record<string, unknown>>(`/approvals/${id}/decision`, {
        method: "POST",
        body: JSON.stringify({ decision, comment }),
      }),
  },
  audit: {
    list: (opts?: { actorId?: string; entityType?: string; action?: string; day?: string }) => {
      const sp = new URLSearchParams();
      if (opts?.actorId) sp.set("actor_id", opts.actorId);
      if (opts?.entityType) sp.set("entity_type", opts.entityType);
      if (opts?.action) sp.set("action", opts.action);
      if (opts?.day) sp.set("day", opts.day);
      const qs = sp.toString();
      return request<Array<Record<string, unknown>>>(`/audit${qs ? `?${qs}` : ""}`);
    },
    /** خروجی اکسل با همان فیلترهای تب ممیزی. */
    downloadXlsx: async (opts?: { actorId?: string; entityType?: string; action?: string; day?: string }) => {
      const sp = new URLSearchParams();
      if (opts?.actorId) sp.set("actor_id", opts.actorId);
      if (opts?.entityType) sp.set("entity_type", opts.entityType);
      if (opts?.action) sp.set("action", opts.action);
      if (opts?.day) sp.set("day", opts.day);
      const qs = sp.toString();
      const token = getToken();
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = ["Bearer", token].join(" ");
      const res = await fetch(`/api/audit.xlsx${qs ? `?${qs}` : ""}`, {
        headers,
        credentials: "include",
      });
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
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "audit.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    },
  },
  totp: {
    setup: () =>
      request<{ secret: string; otpauth: string; enabled: boolean }>("/auth/totp/setup", {
        method: "POST",
      }),
    enable: (code: string) =>
      request<{ enabled: boolean }>("/auth/totp/enable", {
        method: "POST",
        body: JSON.stringify({ code }),
      }),
  },
  reports: {
    kpis: () =>
      request<Record<string, number | string>>("/reports/kpis"),
    history: () => request<Array<Record<string, unknown>>>("/reports/kpis/history"),
    snapshot: () => request<Record<string, unknown>>("/reports/kpis/snapshot", { method: "POST" }),
    schedules: () => request<Array<Record<string, unknown>>>("/reports/schedules"),
    schedule: (body: { name: string; channel: string; hour_utc: number }) =>
      request<Record<string, unknown>>("/reports/schedules", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    /** Authenticated blob download for CSV / XLSX / PDF exports. */
    download: async (format: "csv" | "xlsx" | "pdf") => {
      const token = getToken();
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = ["Bearer", token].join(" ");
      const res = await fetch(`/api/reports/kpis.${format}`, {
        headers,
        credentials: "include",
      });
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
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `kpis.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    },
  },
};
