#!/usr/bin/env node
/**
 * اجرای synthetic user روی CM (نیاز به frontend+backend با seed دمو).
 *
 *   cd frontend
 *   npm run synthetic -- --scenario requester-home-requests
 *   npm run synthetic -- --all
 */
import { existsSync, mkdirSync } from "node:fs";
import { chromium } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { writeSynthesis, loadReports } from "./lib/aggregateReports";
import { runScenario } from "./lib/runScenario";
import { loadSyntheticEnv, syntheticRootDir } from "./lib/env";
import { SCENARIOS, getScenario } from "./scenarios";

const syntheticRoot = syntheticRootDir();

function parseArgs(argv: string[]): { all: boolean; scenarioId?: string; out?: string } {
  let all = false;
  let scenarioId: string | undefined;
  let out: string | undefined;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--all") all = true;
    else if (a === "--scenario" && argv[i + 1]) scenarioId = argv[++i];
    else if (a === "--out" && argv[i + 1]) out = argv[++i];
    else if (a === "--help" || a === "-h") {
      console.log(`Usage:
  npm run synthetic -- --scenario <id>
  npm run synthetic -- --all
  npm run synthetic -- --list

Env:
  SYNTHETIC_BASE_URL     default http://127.0.0.1:5173
  SYNTHETIC_MOCK_LLM=1   no API calls (default if no API key)
  SYNTHETIC_AGENT=1      LLM loop after scripted steps
  SYNTHETIC_INTERVIEW=1  three follow-up Q&A (needs API key)
  OPENAI_API_KEY / SYNTHETIC_LLM_API_KEY
  LLM_MODEL / LLM_API_*    from repo .env (9Router combo, e.g. taha) — auto + fallbacks
  SYNTHETIC_LLM_COMBO      override combo name only for synthetic runs
  SYNTHETIC_LLM_FALLBACKS  extra model ids, comma-separated (optional)

Loads: .env → backend/.env → synthetic/llm.env.local
`);
      process.exit(0);
    } else if (a === "--list") {
      for (const s of SCENARIOS) console.log(s.id);
      process.exit(0);
    }
  }
  return { all, scenarioId, out };
}

async function main(): Promise<void> {
  loadSyntheticEnv();
  const { all, scenarioId, out } = parseArgs(process.argv.slice(2));
  const ids = all ? SCENARIOS.map((s) => s.id) : scenarioId ? [scenarioId] : [];
  if (!ids.length) {
    console.error("Specify --scenario <id> or --all (or --list).");
    process.exit(1);
  }

  const baseUrl = (process.env.SYNTHETIC_BASE_URL || "http://127.0.0.1:5173").replace(/\/$/, "");
  const runRoot = out || path.join(syntheticRoot, "reports", new Date().toISOString().replace(/[:.]/g, "-"));
  mkdirSync(runRoot, { recursive: true });

  const chromePath = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
  const browser = await chromium.launch({
    headless: process.env.SYNTHETIC_HEADED !== "1",
    ...(!process.env.CI && existsSync(chromePath) ? { channel: "chrome" as const } : {}),
  });
  const written: string[] = [];
  try {
    for (const id of ids) {
      const scenario = getScenario(id);
      if (!scenario) {
        console.error(`Unknown scenario: ${id}`);
        process.exitCode = 1;
        continue;
      }
      const outDir = path.join(runRoot, id);
      mkdirSync(outDir, { recursive: true });
      console.log(`Running ${id} → ${outDir}`);
      const context = await browser.newContext({ baseURL: baseUrl, locale: "fa-IR" });
      const page = await context.newPage();
      try {
        const dir = await runScenario({ scenario, page, baseUrl, outDir });
        written.push(dir);
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }

  console.log(`Done. Reports:\n${written.map((d) => `  ${d}`).join("\n")}`);
  if (written.length > 1) {
    const reports = loadReports(runRoot);
    const synthesis = writeSynthesis(runRoot, reports);
    console.log(`Synthesis: ${synthesis}`);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
