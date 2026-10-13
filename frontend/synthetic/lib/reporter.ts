import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { SessionReport } from "./types";

export function writeReport(outDir: string, report: SessionReport): void {
  mkdirSync(outDir, { recursive: true });
  writeFileSync(path.join(outDir, "report.json"), JSON.stringify(report, null, 2), "utf8");
  writeFileSync(path.join(outDir, "report.md"), formatMarkdown(report), "utf8");
}

function formatMarkdown(r: SessionReport): string {
  const lines: string[] = [
    `# گزارش synthetic user — ${r.meta.scenarioId}`,
    "",
    `- **پرسونا:** ${r.meta.personaFile} (${r.meta.loginEmail})`,
    `- **نتیجه ماموریت:** ${r.mission.result}`,
    `- **مدت:** ${r.meta.durationSec}s | **حالت:** ${r.meta.mode}`,
    "",
    "## ماموریت",
    r.mission.text,
    "",
    "**معیار موفقیت:** " + r.mission.successCriteria,
    "",
    "## SUS کوتاه (۱–۵)",
    `- وضوح: ${r.sus_short.clarity}`,
    `- سهولت: ${r.sus_short.ease}`,
    `- اطمینان: ${r.sus_short.confidence}`,
    "",
    "## پیشنهاد اصلی",
    r.top_recommendation,
    "",
  ];
  if (r.positives.length) {
    lines.push("## نکات مثبت", ...r.positives.map((p) => `- ${p}`), "");
  }
  if (r.interview?.answers?.length) {
    lines.push("## مصاحبه follow-up");
    for (const a of r.interview.answers) {
      lines.push(`**${a.question}**`, "", a.answer, "");
    }
  }
  if (r.friction_points.length) {
    lines.push("## نقاط اصطکاک");
    for (const f of r.friction_points) {
      lines.push(
        `### ${f.severity} — ${f.where}`,
        `- انتظار: ${f.what_expected}`,
        `- واقعیت: ${f.what_happened}`,
        `> ${f.quote_as_persona}`,
        "",
      );
    }
  }
  lines.push("## لاگ", "```json", JSON.stringify(r.log, null, 2), "```");
  return lines.join("\n");
}

export function defaultReportFromLog(partial: {
  scenario: import("./types").Scenario;
  baseUrl: string;
  startedAt: string;
  finishedAt: string;
  mode: SessionReport["meta"]["mode"];
  mockLlm: boolean;
  log: SessionReport["log"];
  screenshots: string[];
  stepsOk: boolean;
}): SessionReport {
  const durationSec = Math.round((Date.parse(partial.finishedAt) - Date.parse(partial.startedAt)) / 1000);
  const failed = partial.log.some((e) => e.type === "error" || (e.type === "step" && !e.ok) || (e.type === "llm" && !e.ok));
  return {
    meta: {
      scenarioId: partial.scenario.id,
      personaFile: partial.scenario.personaFile,
      loginEmail: partial.scenario.loginEmail,
      baseUrl: partial.baseUrl,
      startedAt: partial.startedAt,
      finishedAt: partial.finishedAt,
      durationSec,
      mode: partial.mode,
      mockLlm: partial.mockLlm,
    },
    mission: {
      text: partial.scenario.missionFa,
      successCriteria: partial.scenario.successCriteriaFa,
      result: failed ? "failed" : partial.stepsOk ? "completed" : "partial",
    },
    friction_points: failed
      ? [
          {
            severity: "major",
            where: partial.log.at(-1)?.type === "step" ? "آخرین گام scripted" : "جلسه",
            what_expected: partial.scenario.successCriteriaFa,
            what_happened: "یک گام شکست خورد یا عامل متوقف شد.",
            quote_as_persona: "نتوانستم ماموریت را تا آخر جلو ببرم.",
          },
        ]
      : [],
    positives: failed ? [] : ["مسیر scripted بدون خطا اجرا شد."],
    sus_short: { clarity: failed ? 3 : 4, ease: failed ? 2 : 4, confidence: failed ? 2 : 4 },
    top_recommendation: failed
      ? "خطای Playwright را در لاگ ببینید؛ احتمالاً برچسب منو یا seed دمو با UI فرق دارد."
      : "برای فیدبک عمیق‌تر SYNTHETIC_AGENT=1 و کلید LLM را فعال کنید.",
    log: partial.log,
    artifacts: { screenshots: partial.screenshots },
  };
}
