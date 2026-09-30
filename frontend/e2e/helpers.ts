/**
 * ورود مشترک برای تست‌های e2e.
 *
 * چرا یک فایل مشترک: هر سه فایل تست نسخهٔ خودشان از این تابع را داشتند و
 * یکی از آن‌ها timeout لاگین را فراموش کرده بود. لاگین bcrypt دارد و روی
 * SQLite چند ثانیه طول می‌کشد، پس پیش‌فرض ۵ ثانیهٔ Playwright باعث می‌شد
 * تست گاهی flake شود. یک نسخهٔ مشترک یعنی یک جا برای اصلاح.
 */
import { expect, type APIRequestContext, type Page } from "@playwright/test";

/** bcrypt + SQLite ⇒ لاگین می‌تواند چند ثانیه طول بکشد. */
export const LOGIN_TIMEOUT = 20_000;

export type TestOrg = { slug: string; email: string; token: string };

let seq = 0;

/**
 * یک سازمان تازه می‌سازد و توکن ادمینش را برگرداند.
 *
 * `slug` باید در کل اجرا یکتا باشد: اگر دو تست در یک worker سازمانی با یک slug
 * بسازند، دومی رکورد اول را overwrite می‌کند و لاگینش «Organization not found»
 * می‌گیرد — خطایی که ربطی به تستِ در حال اجرا ندارد. شمارندهٔ ماژولی به‌علاوهٔ
 * `Date.now()` تضمین می‌کند هیچ‌وقت تکراری نشود.
 *
 * توکن همیشه برگردانده می‌شود چون تقریباً هر فراخوانی API در e2e به آن نیاز
 * دارد؛ فراخوانی بدون `Authorization` فقط ۴۰۱ می‌گیرد و تست با retry
 * «تصادفی» سبز می‌شود که بدترین حالت ممیزی است.
 */
export async function bootstrapOrg(request: APIRequestContext): Promise<TestOrg> {
  const slug = `e2e${Date.now()}${(seq++).toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;
  const email = `boss-${slug}@example.com`;
  const boot = await request.post("/api/auth/bootstrap", {
    data: {
      organization_name: "E2E",
      organization_slug: slug,
      admin_email: email,
      admin_name: "Boss",
      admin_password: "password",
    },
  });
  // بدون این ادعا، خطای bootstrap فقط یک expect بی‌پیام می‌دهد
  expect(boot.ok(), `bootstrap failed: ${await boot.text()}`).toBeTruthy();

  const login = await request.post("/api/auth/login", {
    data: { organization_slug: slug, email, password: "password" },
  });
  // بدون این ادعا، خطای لاگین فقط با یک ۴۰۱ در جای دیگر خودش را نشان می‌دهد
  expect(login.ok(), `login failed: ${await login.text()}`).toBeTruthy();
  const { access_token } = (await login.json()) as { access_token: string };
  return { slug, email, token: access_token };
}

export async function signIn(page: Page, request: APIRequestContext): Promise<TestOrg> {
  const org = await bootstrapOrg(request);
  await page.goto("/login");
  await page.getByLabel(/company code|کد شرکت/i).fill(org.slug);
  await page.getByLabel(/email|ایمیل/i).fill(org.email);
  await page.getByLabel(/password|رمز عبور/i).fill("password");
  await page.getByRole("button", { name: /sign in|ورود/i }).click();
  await expect(page).not.toHaveURL(/login/, { timeout: LOGIN_TIMEOUT });
  return org;
}
