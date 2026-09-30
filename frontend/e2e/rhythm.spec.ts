import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers";

/** Consecutive visible children of <main> must be separated by exactly --space-4. */
function topLevelGaps(page: Page): Promise<number[]> {
  return page.evaluate(() => {
    const main = document.querySelector("main");
    if (!main) return [];
    const blocks = [...main.children].filter(
      (el) => el.getBoundingClientRect().height > 0,
    );
    const gaps: number[] = [];
    for (let i = 0; i < blocks.length - 1; i++) {
      const a = blocks[i].getBoundingClientRect();
      const b = blocks[i + 1].getBoundingClientRect();
      gaps.push(b.top - a.bottom);
    }
    return gaps;
  });
}

/** انتظار تا رندر کامل شود — ظاهر شدن <main> به‌تنهایی کافی نیست. */
function waitForRenderSettled(page: Page, timeout = 15_000): Promise<unknown> {
  return page.waitForFunction(
    () =>
      new Promise<boolean>((resolve) => {
        let last = -1;
        let stable = 0;
        const tick = () => {
          const now = document.querySelector("main")?.children.length ?? -1;
          stable = now === last ? stable + 1 : 0;
          last = now;
          if (stable >= 3) resolve(true);
          else requestAnimationFrame(tick);
        };
        tick();
      }),
    null,
    { timeout },
  );
}

const PAGES = [
  "/",
  "/admin",
  "/settings",
  "/cases",
  "/approvals",
  "/vehicles",
  "/communication",
  "/my-work",
  "/knowledge",
  "/search",
  "/reports",
  "/work-items",
  "/customers",
  "/people",
  "/agent",
];

test("vertical rhythm is uniform on every page", async ({ page, request }) => {
  test.setTimeout(120_000);
  await signIn(page, request);
  for (const path of PAGES) {
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    // فونت باید لود شده باشد تا ارتفاع فونت fallback اندازه‌ها را منحرف نکند
    await page.evaluate(() => document.fonts.ready.then(() => undefined));
    // فقط ظاهر شدن <main> کافی نیست: صفحه‌ای که داده‌اش دیر برسد ابتدا یک
    // اسپینر رندر می‌کند و بلوک‌ها بعداً اضافه می‌شوند، پس فاصله‌گیری روی
    // درخت ناقص انجام می‌شود و تست flake می‌خورد.
    await waitForRenderSettled(page);
    const gaps = await topLevelGaps(page);
    const bad = gaps
      .map((g, i) => ({ i, g: Math.round(g) }))
      .filter(({ g }) => g < 15 || g > 17);
    expect(bad, `${path}: uneven gaps ${JSON.stringify(bad)}`).toEqual([]);
  }
});

test("no horizontal overflow on desktop", async ({ page, request }) => {
  test.setTimeout(120_000);
  await signIn(page, request);
  for (const path of PAGES) {
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    // فونت‌های self-host هنوز ممکن است لود نشده باشند؛ فونت fallback عرض
    // متفاوتی دارد و اندازه‌گیری زودهنگام سرریز جعلی می‌دهد.
    await page.evaluate(() => document.fonts.ready.then(() => undefined));
    await waitForRenderSettled(page);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `${path}: horizontal overflow ${overflow}px`).toBeLessThanOrEqual(0);
  }
});

test("no horizontal overflow on mobile (390px)", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, request);
  for (const path of ["/", "/cases", "/people", "/vehicles", "/communication", "/settings", "/my-work"]) {
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    // فونت باید قبل از اندازه‌گیری لود شده باشد (ریشهٔ سرریز جعلی)
    await page.evaluate(() => document.fonts.ready.then(() => undefined));
    await waitForRenderSettled(page);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `${path}: horizontal overflow ${overflow}px`).toBeLessThanOrEqual(0);
  }
});