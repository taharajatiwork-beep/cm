import type { Page } from "@playwright/test";
import type { ScenarioStep } from "./types";

export async function runStep(page: Page, step: ScenarioStep): Promise<{ ok: boolean; detail?: string }> {
  try {
    switch (step.kind) {
      case "goto":
        await page.goto(step.path);
        return { ok: true };
      case "click": {
        const re = new RegExp(step.name, "i");
        const inNav = page.getByRole("navigation").getByRole(step.role, { name: re });
        if ((await inNav.count()) > 0) {
          await inNav.first().click({ timeout: 15_000 });
        } else {
          await page.getByRole(step.role, { name: re }).first().click({ timeout: 15_000 });
        }
        return { ok: true };
      }
      case "expectVisible": {
        if (step.role && step.name) {
          const re = new RegExp(step.name, "i");
          await page.getByRole(step.role, { name: re }).first().waitFor({ state: "visible", timeout: 10_000 });
        } else if (step.name) {
          await page.getByText(new RegExp(step.name, "i")).first().waitFor({ state: "visible", timeout: 10_000 });
        }
        return { ok: true };
      }
      case "note":
        return { ok: true, detail: step.text };
      default:
        return { ok: false, detail: "unknown step kind" };
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, detail: msg };
  }
}

export type LlmAction =
  | { type: "click"; role: "link" | "button" | "tab"; name: string }
  | { type: "goto"; path: string }
  | { type: "think"; text: string }
  | { type: "done"; summary: string }
  | { type: "fail"; reason: string };

export async function runLlmAction(page: Page, action: LlmAction): Promise<{ ok: boolean; detail?: string }> {
  try {
    switch (action.type) {
      case "think":
        return { ok: true, detail: action.text };
      case "goto":
        await page.goto(action.path.startsWith("/") ? action.path : `/${action.path}`);
        return { ok: true };
      case "click": {
        const re = new RegExp(action.name, "i");
        await page.getByRole(action.role, { name: re }).click();
        return { ok: true };
      }
      case "done":
        return { ok: true, detail: action.summary };
      case "fail":
        return { ok: false, detail: action.reason };
      default:
        return { ok: false, detail: "unknown action" };
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, detail: msg };
  }
}
