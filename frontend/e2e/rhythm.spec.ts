import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

async function signIn(page: Page, request: APIRequestContext) {
  const slug = `e2e${Date.now()}`;
  const email = `boss-${Date.now()}@example.com`;
  const boot = await request.post("/api/auth/bootstrap", {
    data: {
      organization_name: "E2E",
      organization_slug: slug,
      admin_email: email,
      admin_name: "Boss",
      admin_password: "password",
    },
  });
  expect(boot.ok()).toBeTruthy();
  await page.goto("/login");
  await page.getByLabel(/company code|کد شرکت/i).fill(slug);
  await page.getByLabel(/email|ایمیل/i).fill(email);
  await page.getByLabel(/password|رمز عبور/i).fill("password");
  await page.getByRole("button", { name: /sign in|ورود/i }).click();
  await expect(page).not.toHaveURL(/login/);
}

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
    await page.waitForTimeout(600);
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
    await page.waitForTimeout(400);
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
    await page.waitForTimeout(400);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `${path}: horizontal overflow ${overflow}px`).toBeLessThanOrEqual(0);
  }
});