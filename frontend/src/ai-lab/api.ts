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
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type AiLabConfig = { enabled: boolean; mode: string; result_source?: string };

export type AiTaskKind =
  | "period_review"
  | "campaign_review"
  | "channel_budget"
  | "sms_copy_review"
  | "projects_health"
  | "team_load"
  | "finance_reconcile"
  | "my_work_review";

export type AiLabWorkspace = {
  key: string;
  label_en: string;
  label_fa: string;
  kinds: AiTaskKind[];
  private: boolean;
};
export type AiTaskTrigger = "manual" | "scheduled" | "anomaly";

export type AiFollowupMetrics = {
  period?: { from: string; to: string };
  cost_toman?: number;
  leads?: number;
  cpl?: number | null;
};

export type AiRecFollowup = {
  cm_task_id: string | null;
  baseline: AiFollowupMetrics;
  followup: AiFollowupMetrics | null;
  followup_due_on: string;
  measured_at: string | null;
};

export type AiFinding = { title: string; evidence: string; severity: string };
export type AiRecommendation = {
  id: string;
  action: string;
  reason: string;
  expected_impact: string;
  confidence: string;
};
export type AiResult = {
  summary: string;
  findings: AiFinding[];
  recommendations: AiRecommendation[];
  data_gaps: string[];
};

export type AiTask = {
  id: string;
  kind: AiTaskKind;
  trigger?: AiTaskTrigger;
  input: Record<string, unknown>;
  snapshot: Record<string, unknown>;
  status: string;
  result: AiResult | null;
  error: string | null;
  rating: number | null;
  useful: boolean | null;
  eval_note: string | null;
  decisions: Record<string, string>;
  followups?: Record<string, AiRecFollowup>;
  accepted_count: number;
  latency_seconds: number | null;
  created_at: string | null;
  completed_at: string | null;
  last_polled_at: string | null;
};

export type EvalSummary = {
  by_kind: Record<
    string,
    { tasks: number; avg_rating: number | null; accept_rate: number | null; median_latency_seconds: number | null }
  >;
  avg_accepted_cpl_change_pct?: number | null;
};

export const aiLabApi = {
  config: () => request<AiLabConfig>("/ai-lab/config"),
  workspaces: () => request<{ workspaces: AiLabWorkspace[] }>("/ai-lab/workspaces"),
  evaluationSummary: () => request<EvalSummary>("/ai-lab/evaluation-summary"),
  previewSnapshot: (kind: AiTaskKind, input: Record<string, unknown>) =>
    request<Record<string, unknown>>("/ai-lab/snapshot", { method: "POST", body: JSON.stringify({ kind, input }) }),
  tasks: (params?: { kind?: string; trigger?: string }) => {
    const q = new URLSearchParams();
    if (params?.kind) q.set("kind", params.kind);
    if (params?.trigger) q.set("trigger", params.trigger);
    const suffix = q.toString() ? `?${q}` : "";
    return request<AiTask[]>(`/ai-lab/tasks${suffix}`);
  },
  task: (id: string) => request<AiTask>(`/ai-lab/tasks/${id}`),
  createTask: (kind: AiTaskKind, input: Record<string, unknown>) =>
    request<AiTask>("/ai-lab/tasks", { method: "POST", body: JSON.stringify({ kind, input }) }),
  manualResult: (id: string, payload: Record<string, unknown>) =>
    request<AiTask>(`/ai-lab/tasks/${id}/manual-result`, {
      method: "POST",
      body: JSON.stringify({ payload }),
    }),
  decide: (id: string, recId: string, decision: "accepted" | "rejected" | "done") =>
    request<AiTask>(`/ai-lab/tasks/${id}/recommendations/${recId}`, {
      method: "PATCH",
      body: JSON.stringify({ decision }),
    }),
  evaluate: (id: string, rating: number, useful: boolean, eval_note: string) =>
    request<AiTask>(`/ai-lab/tasks/${id}/evaluation`, {
      method: "PATCH",
      body: JSON.stringify({ rating, useful, eval_note }),
    }),
  pollNow: (id: string) => request<AiTask>(`/ai-lab/tasks/${id}/poll`, { method: "POST" }),
  toTask: (id: string, recId: string, body: { deadline?: string; priority?: string }) =>
    request<AiTask & { cm_task_id?: string }>(`/ai-lab/tasks/${id}/recommendations/${recId}/to-task`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
