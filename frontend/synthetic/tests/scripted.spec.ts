import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "@playwright/test";
import { runScenario } from "../lib/runScenario";
import { SCENARIOS } from "../scenarios";

const syntheticDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const runRoot = path.join(syntheticDir, "reports", `ci-${new Date().toISOString().replace(/[:.]/g, "-")}`);

for (const scenario of SCENARIOS) {
  test(`synthetic scripted: ${scenario.id}`, async ({ page, baseURL }) => {
    process.env.SYNTHETIC_MOCK_LLM = "1";
    const outDir = path.join(runRoot, scenario.id);
    mkdirSync(outDir, { recursive: true });
    await runScenario({
      scenario,
      page,
      baseUrl: baseURL ?? "http://127.0.0.1:5175",
      outDir,
      useAgent: false,
    });
  });
}
