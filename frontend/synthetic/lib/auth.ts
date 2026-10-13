import { expect, type Page } from "@playwright/test";

export const DEMO_ORG_SLUG = "autoco";
export const DEMO_PASSWORD = "password";

/** bcrypt + SQLite ⇒ لاگین می‌تواند چند ثانیه طول بکشد. */
export const LOGIN_TIMEOUT = 20_000;

export async function signInDemoUser(page: Page, email: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.evaluate(() => {
    try {
      localStorage.clear();
      sessionStorage.clear();
    } catch {
      /* ignore */
    }
  });
  await page.reload();
  await page.locator("#login-slug").fill(DEMO_ORG_SLUG);
  await page.locator("#login-email").fill(email);
  await page.locator("#login-password").fill(DEMO_PASSWORD);
  await page.locator("#login-totp").fill("");
  await page.getByRole("button", { name: /sign in|ورود/i }).click();

  const leftLogin = page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: LOGIN_TIMEOUT });
  const loginError = page.locator('[role="alert"], .error, [class*="error"]').first();
  const failed = loginError.waitFor({ state: "visible", timeout: LOGIN_TIMEOUT }).then(async () => {
    const text = ((await loginError.textContent()) || "").trim();
    throw new Error(`ورود ناموفق برای ${email}: ${text || "پیام خطا دیده شد"}`);
  });
  await Promise.race([leftLogin, failed]);
  await expect(page).not.toHaveURL(/login/, { timeout: 5_000 });
}
