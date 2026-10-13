import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { LlmAction } from "./actions";
import { llmApiKey, llmBaseUrl, syntheticRootDir } from "./env";
import { chatCompletionsWithFallback } from "./llmModels";

export { llmApiKey, llmBaseUrl } from "./env";

const syntheticRoot = syntheticRootDir();

export function isMockLlm(): boolean {
  return process.env.SYNTHETIC_MOCK_LLM === "1" || !llmApiKey();
}

export function loadPersona(personaFile: string): string {
  const p = path.join(syntheticRoot, "personas", personaFile);
  return readFileSync(p, "utf8");
}

const ACTION_SCHEMA = `Respond with a single JSON object only, no markdown:
{"type":"click","role":"link|button|tab","name":"visible label substring"}
{"type":"goto","path":"/requests"}
{"type":"think","text":"short thought in Persian as the persona"}
{"type":"done","summary":"Persian summary when mission complete"}
{"type":"fail","reason":"Persian reason if stuck"}`;

export async function chooseLlmAction(input: {
  personaMd: string;
  mission: string;
  pageContext: string;
  history: string[];
}): Promise<LlmAction> {
  if (isMockLlm()) {
    return { type: "done", summary: "(mock) ماموریت بدون عامل LLM — فقط گام‌های ثابت اجرا شد." };
  }

  const key = llmApiKey();
  if (!key) {
    return { type: "done", summary: "بدون کلید API — پایان scripted." };
  }

  const system = `${input.personaMd}\n\nYou are simulating this user in a Persian RTL web app (CM). ${ACTION_SCHEMA}`;
  const user = `ماموریت: ${input.mission}\n\nتاریخچه:\n${input.history.join("\n") || "(شروع)"}\n\nوضعیت صفحه:\n${input.pageContext}`;

  const res = await chatCompletionsWithFallback({
    temperature: 0.3,
    messages: [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
    response_format: { type: "json_object" },
  });
  if (!res.ok) {
    return { type: "fail", reason: `LLM: ${res.body.slice(0, 200)}` };
  }
  const raw = res.content || "{}";
  try {
    return JSON.parse(raw) as LlmAction;
  } catch {
    return { type: "fail", reason: `پاسخ JSON نامعتبر: ${raw.slice(0, 120)}` };
  }
}

export async function debriefWithLlm(input: {
  personaMd: string;
  mission: string;
  successCriteria: string;
  logText: string;
}): Promise<{
  friction_points: import("./types").FrictionPoint[];
  positives: string[];
  sus_short: { clarity: number; ease: number; confidence: number };
  top_recommendation: string;
  mission_result: "completed" | "partial" | "failed";
} | null> {
  if (isMockLlm()) return null;

  const key = llmApiKey();
  if (!key) return null;

  const template = readFileSync(path.join(syntheticRoot, "prompts", "debrief-fa.md"), "utf8");

  const res = await chatCompletionsWithFallback({
    temperature: 0.2,
    messages: [
      { role: "system", content: template },
      {
        role: "user",
        content: `پرسونا:\n${input.personaMd}\n\nماموریت: ${input.mission}\nمعیار موفقیت: ${input.successCriteria}\n\nلاگ جلسه:\n${input.logText}`,
      },
    ],
    response_format: { type: "json_object" },
  });
  if (!res.ok) {
    if (process.env.SYNTHETIC_DEBUG === "1") {
      console.error(`[synthetic] debrief LLM failed: ${res.body.slice(0, 400)}`);
    }
    return null;
  }
  const raw = res.content || "{}";
  try {
    return JSON.parse(raw) as {
      friction_points: import("./types").FrictionPoint[];
      positives: string[];
      sus_short: { clarity: number; ease: number; confidence: number };
      top_recommendation: string;
      mission_result: "completed" | "partial" | "failed";
    };
  } catch {
    return null;
  }
}

export async function interviewWithLlm(input: {
  personaMd: string;
  mission: string;
  logText: string;
}): Promise<{ answers: { question: string; answer: string }[] } | null> {
  if (isMockLlm()) return null;
  const key = llmApiKey();
  if (!key) return null;

  const template = readFileSync(path.join(syntheticRoot, "prompts", "interview-fa.md"), "utf8");

  const res = await chatCompletionsWithFallback({
    temperature: 0.3,
    messages: [
      { role: "system", content: template },
      {
        role: "user",
        content: `پرسونا:\n${input.personaMd}\n\nماموریت: ${input.mission}\n\nلاگ:\n${input.logText}`,
      },
    ],
    response_format: { type: "json_object" },
  });
  if (!res.ok) return null;
  const raw = res.content || "{}";
  try {
    return JSON.parse(raw) as { answers: { question: string; answer: string }[] };
  } catch {
    return null;
  }
}
