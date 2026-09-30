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
  // لاگین bcrypt دارد و روی SQLite می‌تواند چند ثانیه طول بکشد؛
  // پیش‌فرض ۵ ثانیهٔ Playwright برای این مسیر کم است و تست را flaky می‌کند.
  await expect(page).not.toHaveURL(/login/, { timeout: 20_000 });
  return { slug, email };
}

/** Add a colleague through the admin API so a conversation has a second side. */
async function addColleague(request: APIRequestContext, slug: string, bossEmail: string) {
  const login = await request.post("/api/auth/login", {
    data: { organization_slug: slug, email: bossEmail, password: "password" },
  });
  const { access_token } = (await login.json()) as { access_token: string };
  const created = await request.post("/api/org/users", {
    headers: { Authorization: `Bearer ${access_token}` },
    data: {
      email: `reza-${Date.now()}@example.com`,
      full_name: "Reza",
      password: "password",
    },
  });
  expect(created.ok()).toBeTruthy();
}

test("sign in", async ({ page, request }) => {
  await signIn(page, request);
});

test("start a conversation and send a message", async ({ page, request }) => {
  const { slug, email } = await signIn(page, request);
  await addColleague(request, slug, email);

  await page.goto("/communication");
  await page.getByRole("button", { name: /new message|پیام جدید/i }).click();
  await page.locator(".compose-people .chip", { hasText: /reza/i }).click();
  await page.getByPlaceholder(/what is it about|درباره چیست/i).fill("سلام رضا");
  await page.getByRole("button", { name: /start|شروع گفتگو/i }).click();
  await page.getByPlaceholder(/write a reply|پاسخ بنویس/i).fill("پرونده کمری را بررسی کن");
  await page.getByPlaceholder(/write a reply|پاسخ بنویس/i).press("Enter");
  await expect(page.locator("body")).toContainText("پرونده کمری را بررسی کن");
});

test("open my work", async ({ page, request }) => {
  await signIn(page, request);
  await page.goto("/my-work");
  await expect(page.locator("body")).toContainText(/کار|work/i);
});

test("admin overview", async ({ page, request }) => {
  await signIn(page, request);
  await page.goto("/admin");
  await expect(page.locator("body")).toContainText(/کاربران فعال|active users/i);
  await expect(page.locator("body")).toContainText(/میانگین اولین پاسخ|avg first reply/i);
});

test("search page", async ({ page, request }) => {
  await signIn(page, request);
  await page.goto("/search");
  await expect(page.getByRole("button", { name: /search|جستجو/i })).toBeVisible();
});