import type { Page } from "@playwright/test";
import path from "node:path";
import { runLlmAction, runStep } from "./actions";
import { signInDemoUser } from "./auth";
import { chooseLlmAction, debriefWithLlm, interviewWithLlm, isMockLlm, loadPersona } from "./llm";
import { defaultReportFromLog, writeReport } from "./reporter";
import { capturePageContext } from "./snapshot";
import type { Scenario, SessionLogEntry } from "./types";

export type RunScenarioOptions = {
  scenario: Scenario;
  page: Page;
  baseUrl: string;
  outDir: string;
  useAgent?: boolean;
};

export async function runScenario(opts: RunScenarioOptions): Promise<string> {
  const { scenario, page, baseUrl, outDir } = opts;
  const useAgent = opts.useAgent ?? process.env.SYNTHETIC_AGENT === "1";
  const startedAt = new Date().toISOString();
  const log: SessionLogEntry[] = [];
  const screenshots: string[] = [];
  const personaMd = loadPersona(scenario.personaFile);

  await signInDemoUser(page, scenario.loginEmail);
  await page.screenshot({ path: path.join(outDir, "01-after-login.png") });
  screenshots.push("01-after-login.png");

  let stepsOk = true;
  for (const step of scenario.steps) {
    const at = new Date().toISOString();
    const result = await runStep(page, step);
    log.push({ at, type: "step", step, ok: result.ok, detail: result.detail });
    if (!result.ok) {
      stepsOk = false;
      await page.screenshot({ path: path.join(outDir, `fail-step-${log.length}.png`) });
      screenshots.push(`fail-step-${log.length}.png`);
      break;
    }
  }

  let mode: "scripted" | "agent" | "scripted+agent" = "scripted";
  if (stepsOk && useAgent && !isMockLlm()) {
    mode = "scripted+agent";
    const max = scenario.maxLlmSteps ?? 10;
    const history: string[] = [];
    for (let i = 0; i < max; i++) {
      const ctx = await capturePageContext(page);
      const action = await chooseLlmAction({
        personaMd,
        mission: scenario.missionFa,
        pageContext: ctx,
        history,
      });
      const at = new Date().toISOString();
      const result = await runLlmAction(page, action);
      const actionStr = JSON.stringify(action);
      history.push(actionStr);
      log.push({
        at,
        type: "llm",
        thought: action.type === "think" ? action.text : action.type,
        action: actionStr,
        ok: result.ok,
        detail: result.detail,
      });
      if (action.type === "done" || action.type === "fail") break;
      if (!result.ok) break;
    }
  } else if (stepsOk && useAgent && isMockLlm()) {
    log.push({
      at: new Date().toISOString(),
      type: "llm",
      thought: "mock",
      action: '{"type":"done"}',
      ok: true,
      detail: "عامل LLM در حالت mock غیرفعال است.",
    });
  }

  await page.screenshot({ path: path.join(outDir, "99-final.png") });
  screenshots.push("99-final.png");

  const finishedAt = new Date().toISOString();
  const logText = log.map((e) => JSON.stringify(e)).join("\n");
  let report = defaultReportFromLog({
    scenario,
    baseUrl,
    startedAt,
    finishedAt,
    mode,
    mockLlm: isMockLlm(),
    log,
    screenshots,
    stepsOk,
  });

  const debrief = await debriefWithLlm({
    personaMd,
    mission: scenario.missionFa,
    successCriteria: scenario.successCriteriaFa,
    logText,
  });
  if (debrief) {
    report = {
      ...report,
      mission: { ...report.mission, result: debrief.mission_result },
      friction_points: debrief.friction_points,
      positives: debrief.positives,
      sus_short: debrief.sus_short,
      top_recommendation: debrief.top_recommendation,
    };
  } else if (!isMockLlm()) {
    report = {
      ...report,
      top_recommendation:
        "debrief LLM جواب نداد (۹router/مدل/اعتبار). `npx tsx synthetic/scripts/probe-llm.ts` یا SYNTHETIC_DEBUG=1.",
      friction_points: [
        ...report.friction_points,
        {
          severity: "minor",
          where: "پایان جلسه",
          what_expected: "تحلیل کیفی UX از LLM",
          what_happened: "درخواست debrief به API ناموفق بود (مثلاً ۴۲۹ اعتبار یا مدل بد).",
          quote_as_persona: "نتوانستم بازخورد مفصل بنویسم؛ سیستم فقط مسیر را اجرا کرد.",
        },
      ],
    };
  }

  if (process.env.SYNTHETIC_INTERVIEW === "1") {
    const interview = await interviewWithLlm({
      personaMd,
      mission: scenario.missionFa,
      logText,
    });
    if (interview) report = { ...report, interview };
  }

  writeReport(outDir, report);
  return outDir;
}
