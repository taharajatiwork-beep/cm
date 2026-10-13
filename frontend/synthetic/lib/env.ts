import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const syntheticRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(syntheticRoot, "..", "..");

function applyEnvFile(filePath: string, override: boolean): void {
  if (!existsSync(filePath)) return;
  for (const line of readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith("#")) continue;
    const i = t.indexOf("=");
    if (i < 1) continue;
    const key = t.slice(0, i).trim();
    const val = t.slice(i + 1).trim().replace(/^["']|["']$/g, "");
    if (override || process.env[key] === undefined) process.env[key] = val;
  }
}

/** Repo `.env` then `synthetic/llm.env.local` (local wins on conflicts). */
export function loadSyntheticEnv(): void {
  applyEnvFile(path.join(repoRoot, ".env"), false);
  applyEnvFile(path.join(repoRoot, "backend", ".env"), false);
  applyEnvFile(path.join(syntheticRoot, "llm.env.local"), true);
}

export function syntheticRootDir(): string {
  return syntheticRoot;
}

export function llmApiKey(): string | undefined {
  return (
    process.env.SYNTHETIC_LLM_API_KEY ||
    process.env.LLM_API_KEY ||
    process.env.OPENCODE_API_KEY ||
    process.env.OPENAI_API_KEY ||
    undefined
  );
}

export function llmBaseUrl(): string {
  const base =
    process.env.SYNTHETIC_LLM_BASE_URL ||
    process.env.LLM_API_BASE ||
    "http://127.0.0.1:20128/v1";
  return base.replace(/\/$/, "");
}
