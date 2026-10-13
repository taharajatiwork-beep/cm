import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const apiPort = process.env.E2E_API_PORT || "8011";
const webPort = Number(process.env.E2E_WEB_PORT || "5174");
const backendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../backend");
const venvPython =
  process.platform === "win32"
    ? path.join(backendRoot, ".venv", "Scripts", "python.exe")
    : path.join(backendRoot, ".venv", "bin", "python");
const python = existsSync(venvPython) ? `"${venvPython}"` : "python";

export default defineConfig({
  testDir: "./e2e",
  // همهٔ تست‌ها یک دیتابیس Postgres (`cm_e2e`) را به اشتراک می‌گذارند؛
  // یک worker از تداخل bootstrap جلوگیری می‌کند.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? "line" : "list",
  timeout: 60_000,
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    ...devices["Desktop Chrome"],
    ...(!process.env.CI && existsSync("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
      ? { channel: "chrome" as const }
      : {}),
  },
  webServer: [
    {
      command: `${python} -m scripts.ensure_pg_db && ${python} -m alembic upgrade head && ${python} -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: "../backend",
      port: Number(apiPort),
      reuseExistingServer: false,
      env: {
        DATABASE_URL: "postgresql+asyncpg://cm:cm@localhost:5432/cm_e2e",
        APP_ENV: "development",
        TELEGRAM_MODE: "off",
        TELEGRAM_BOT_TOKEN: "",
        LLM_PROVIDER: "rules",
        SECRET_KEY: "e2e-secret-not-for-production",
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
      port: webPort,
      reuseExistingServer: false,
      env: { VITE_API_PROXY: `http://127.0.0.1:${apiPort}` },
    },
  ],
});
