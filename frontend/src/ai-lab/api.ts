import { getToken, setToken } from "../api";

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
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type AiLabConfig = { enabled: boolean; mode: string };

export type AiTaskKind = "period_review" | "campaign_review" | "channel_budget";

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
  input: Record<string, unknown>;
  snapshot: Record<string, unknown>;
  status: string;
  result: AiResult | null;
  error: string | null;
  rating: number | null;
  useful: boolean | null;
  eval_note: string | null;
  decisions: Record<string, string>;
  accepted_count: number;
  latency_seconds: number | null;
  created_at: string | null;
  completed_at: string | null;
};

export type EvalSummary = {
  by_kind: Record<
    string,
    { tasks: number; avg_rating: number | null; accept_rate: number | null; median_latency_seconds: number | null }
  >;
};

export const aiLabApi = {
  config: () => request<AiLabConfig>("/ai-lab/config"),
  evaluationSummary: () => request<EvalSummary>("/ai-lab/evaluation-summary"),
  previewSnapshot: (kind: AiTaskKind, input: Record<string, unknown>) =>
    request<Record<string, unknown>>("/ai-lab/snapshot", { method: "POST", body: JSON.stringify({ kind, input }) }),
  tasks: () => request<AiTask[]>("/ai-lab/tasks"),
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
};
