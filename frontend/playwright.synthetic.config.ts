import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const apiPort = process.env.SYNTHETIC_API_PORT || "8012";
const webPort = Number(process.env.SYNTHETIC_WEB_PORT || "5175");
const backendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../backend");
const venvPython =
  process.platform === "win32"
    ? path.join(backendRoot, ".venv", "Scripts", "python.exe")
    : path.join(backendRoot, ".venv", "bin", "python");
const python = existsSync(venvPython) ? `"${venvPython}"` : "python";

export default defineConfig({
  testDir: "./synthetic/tests",
  workers: 1,
  fullyParallel: false,
  timeout: 90_000,
  globalTimeout: 20 * 60_000,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    ...devices["Desktop Chrome"],
    locale: "fa-IR",
    ...(!process.env.CI && existsSync("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
      ? { channel: "chrome" as const }
      : {}),
  },
  webServer: [
    {
      command: `${python} -m scripts.ensure_pg_db && ${python} -m alembic upgrade head && ${python} -m scripts.seed_demo && ${python} -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: "../backend",
      port: Number(apiPort),
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL: "postgresql+asyncpg://cm:cm@localhost:5432/cm_synthetic",
        APP_ENV: "development",
        TELEGRAM_MODE: "off",
        TELEGRAM_BOT_TOKEN: "",
        LLM_PROVIDER: "rules",
        SECRET_KEY: "synthetic-ci-not-for-production",
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
      port: webPort,
      reuseExistingServer: !process.env.CI,
      env: { VITE_API_PROXY: `http://127.0.0.1:${apiPort}` },
    },
  ],
});
