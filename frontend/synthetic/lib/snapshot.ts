import type { Page } from "@playwright/test";

/** خلاصهٔ صفحه برای عامل LLM — محدود به اندازهٔ توکن. */
export async function capturePageContext(page: Page): Promise<string> {
  const url = page.url();
  const title = await page.title();
  let tree = "";
  try {
    const snap = await page.accessibility.snapshot();
    tree = JSON.stringify(snap, null, 0);
  } catch {
    tree = "(accessibility snapshot unavailable)";
  }
  const max = 14_000;
  if (tree.length > max) tree = `${tree.slice(0, max)}…`;
  return `URL: ${url}\nTitle: ${title}\nA11y tree:\n${tree}`;
}
