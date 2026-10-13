export type ScenarioStep =
  | { kind: "goto"; path: string }
  | { kind: "click"; role: "link" | "button" | "tab"; name: string }
  | { kind: "expectVisible"; role?: "heading" | "link" | "button"; name?: string }
  | { kind: "note"; text: string };

export type Scenario = {
  id: string;
  personaFile: string;
  loginEmail: string;
  missionFa: string;
  successCriteriaFa: string;
  steps: ScenarioStep[];
  /** حداکثر گام عامل LLM بعد از لاگین (فقط با کلید API) */
  maxLlmSteps?: number;
};

export type SessionLogEntry =
  | { at: string; type: "step"; step: ScenarioStep; ok: boolean; detail?: string }
  | { at: string; type: "llm"; thought: string; action: string; ok: boolean; detail?: string }
  | { at: string; type: "error"; message: string };

export type FrictionPoint = {
  severity: "blocker" | "major" | "minor";
  where: string;
  what_expected: string;
  what_happened: string;
  quote_as_persona: string;
};

export type SessionReport = {
  meta: {
    scenarioId: string;
    personaFile: string;
    loginEmail: string;
    baseUrl: string;
    startedAt: string;
    finishedAt: string;
    durationSec: number;
    mode: "scripted" | "agent" | "scripted+agent";
    mockLlm: boolean;
  };
  mission: { text: string; successCriteria: string; result: "completed" | "partial" | "failed" };
  friction_points: FrictionPoint[];
  positives: string[];
  sus_short: { clarity: number; ease: number; confidence: number };
  top_recommendation: string;
  log: SessionLogEntry[];
  artifacts: { screenshots: string[] };
  interview?: { answers: { question: string; answer: string }[] };
};
