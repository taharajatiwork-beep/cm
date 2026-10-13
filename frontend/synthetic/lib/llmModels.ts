import { llmApiKey, llmBaseUrl } from "./env";

export type GatewayModel = { id: string; owned_by?: string };

let modelChainCache: string[] | null = null;
let modelChainLogged = false;

function preferredComboName(): string | undefined {
  // Primary: 9Router combo from repo `.env` (`LLM_MODEL=taha`). Override only if SYNTHETIC_LLM_COMBO set.
  const v = process.env.SYNTHETIC_LLM_COMBO || process.env.LLM_MODEL || undefined;
  return v?.trim() || undefined;
}

function extraFallbacks(): string[] {
  const raw = process.env.SYNTHETIC_LLM_FALLBACKS || "";
  return raw
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export async function fetchGatewayModels(): Promise<GatewayModel[]> {
  const key = llmApiKey();
  if (!key) return [];
  const base = llmBaseUrl();
  try {
    const res = await fetch(`${base}/models`, { headers: { Authorization: `Bearer ${key}` } });
    if (!res.ok) return [];
    const j = (await res.json()) as { data?: GatewayModel[] };
    return j.data ?? [];
  } catch {
    return [];
  }
}

/** Ordered model ids: user combo → other combos → OpenCode free (`oc/…`) → extras. */
export function buildModelChain(models: GatewayModel[], preferred?: string): string[] {
  const ids = new Set(models.map((m) => m.id));
  const combos = models.filter((m) => m.owned_by === "combo").map((m) => m.id);
  const ocFree = models
    .map((m) => m.id)
    .filter((id) => id.startsWith("oc/") && /free/i.test(id));
  const ocOther = models.map((m) => m.id).filter((id) => id.startsWith("oc/") && !ocFree.includes(id));

  const chain: string[] = [];
  const push = (id: string) => {
    if (!id || chain.includes(id)) return;
    chain.push(id);
  };

  const pref = preferred?.trim();
  if (pref) push(pref);

  for (const c of combos) {
    if (c !== pref) push(c);
  }

  for (const id of ocFree) push(id);
  for (const id of ocOther) push(id);

  for (const id of extraFallbacks()) push(id);

  return chain;
}

export async function getModelChain(): Promise<string[]> {
  if (modelChainCache) return modelChainCache;
  const preferred = preferredComboName();
  const models = await fetchGatewayModels();
  modelChainCache = buildModelChain(models, preferred);
  if (!modelChainLogged && modelChainCache.length) {
    modelChainLogged = true;
    const label = preferred ? `combo/preferred=${preferred}` : "auto";
    console.log(`[synthetic] LLM model chain (${label}): ${modelChainCache.slice(0, 6).join(" → ")}${modelChainCache.length > 6 ? " → …" : ""}`);
  }
  if (!modelChainCache.length && preferred) {
    modelChainCache = [preferred, ...extraFallbacks()];
  }
  return modelChainCache;
}

export function resetModelChainCache(): void {
  modelChainCache = null;
  modelChainLogged = false;
}

export type ChatPayload = {
  temperature: number;
  messages: { role: string; content: string }[];
  response_format?: { type: "json_object" };
  max_tokens?: number;
};

export type ChatResult =
  | { ok: true; model: string; content: string }
  | { ok: false; model?: string; status?: number; body: string };

export async function chatCompletionsWithFallback(payload: ChatPayload): Promise<ChatResult> {
  const key = llmApiKey();
  if (!key) return { ok: false, body: "no API key" };

  const base = llmBaseUrl();
  const chain = await getModelChain();
  if (!chain.length) return { ok: false, body: "no models in chain (check 9Router and LLM_MODEL in .env)" };

  let last: ChatResult = { ok: false, body: "no attempts" };

  for (const model of chain) {
    const attempt = await postChat(base, key, model, payload, true);
    if (attempt.ok) return attempt;

    if (attempt.status === 401) {
      last = attempt;
      break;
    }

    if (attempt.status === 400 || attempt.status === 422) {
      const plain = await postChat(base, key, model, payload, false);
      if (plain.ok) return plain;
    }

    if (process.env.SYNTHETIC_DEBUG === "1") {
      console.warn(`[synthetic] model ${model} failed (${attempt.status ?? "?"}), trying next…`);
    }
    last = attempt;
  }

  return last;
}

async function postChat(
  base: string,
  key: string,
  model: string,
  payload: ChatPayload,
  jsonMode: boolean,
): Promise<ChatResult> {
  const body: Record<string, unknown> = { model, ...payload };
  if (!jsonMode) delete body.response_format;

  try {
    const res = await fetch(`${base}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    if (!res.ok) {
      return { ok: false, model, status: res.status, body: text.slice(0, 400) };
    }
    const data = JSON.parse(text) as { choices?: { message?: { content?: string } }[] };
    const content = data.choices?.[0]?.message?.content ?? "";
    return { ok: true, model, content };
  } catch (e) {
    return { ok: false, model, body: e instanceof Error ? e.message : String(e) };
  }
}
