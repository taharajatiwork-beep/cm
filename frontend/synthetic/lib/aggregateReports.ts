import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { SessionReport } from "./types";

export function loadReports(runRoot: string): SessionReport[] {
  const out: SessionReport[] = [];
  for (const name of readdirSync(runRoot)) {
    const dir = path.join(runRoot, name);
    const p = path.join(dir, "report.json");
    try {
      if (statSync(dir).isDirectory()) {
        const raw = readFileSync(p, "utf8");
        out.push(JSON.parse(raw) as SessionReport);
      }
    } catch {
      /* skip */
    }
  }
  return out;
}

export function writeSynthesis(runRoot: string, reports: SessionReport[]): string {
  const friction = reports.flatMap((r) =>
    r.friction_points.map((f) => ({ scenario: r.meta.scenarioId, ...f })),
  );
  const blockers = friction.filter((f) => f.severity === "blocker");
  const failed = reports.filter((r) => r.mission.result === "failed");

  const lines = [
    "# تجمیع synthetic users",
    "",
    `جلسات: ${reports.length} | شکست: ${failed.length} | blocker: ${blockers.length}`,
    "",
    "## خلاصه هر سناریو",
    ...reports.map(
      (r) =>
        `- **${r.meta.scenarioId}** (${r.meta.loginEmail}): ${r.mission.result} — ${r.top_recommendation}`,
    ),
    "",
    "## اصطکاک‌های گزارش‌شده",
    ...(friction.length
      ? friction.map((f) => `- [${f.severity}] ${f.scenario} @ ${f.where}: ${f.what_happened}`)
      : ["- (هیچ)"]),
    "",
    "## پیشنهادهای تکراری",
    ...summarizeRecommendations(reports),
    "",
  ];

  const outPath = path.join(path.resolve(runRoot), "synthesis.md");
  writeFileSync(outPath, lines.join("\n"), "utf8");
  return outPath;
}

function summarizeRecommendations(reports: SessionReport[]): string[] {
  const counts = new Map<string, number>();
  for (const r of reports) {
    const key = r.top_recommendation.trim();
    if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([text, n]) => `- (${n}×) ${text}`);
}
