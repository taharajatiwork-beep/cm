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

test("sign in", async ({ page, request }) => {
  await signIn(page, request);
});

test("open my work", async ({ page, request }) => {
  await signIn(page, request);
  await page.goto("/my-work");
  await expect(page.locator("body")).toContainText(/کار|work/i);
});

test("approvals page", async ({ page, request }) => {
  await signIn(page, request);
  await page.goto("/approvals");
  await expect(page.locator("body")).toContainText(/تأیید|approval/i);
});

test("reports page", async ({ page, request }) => {
  await signIn(page, request);
  await page.goto("/reports");
  await expect(page.getByRole("button", { name: "CSV" })).toBeVisible();
});

test("search page", async ({ page, request }) => {
  await signIn(page, request);
  await page.goto("/search");
  await expect(page.getByRole("button", { name: /search|جستجو/i })).toBeVisible();
});
