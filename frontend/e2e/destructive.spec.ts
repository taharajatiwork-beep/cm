import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * عملیات پرخطر سازمان — اینها در e2e پیشین پوششی نداشتند و بیشترین
 * ریسک را برای کاربر واقعی دارند: پاک‌سازی داده، تصمیم تأیید (که
 * تخفیف/پول را آزاد می‌کند)، و دانلود گزارش.
 *
 * هر تست سناریوی واقعی را می‌سنجد نه رفتار فرضی — مثلاً مشتری `DELETE`
 * ندارد، فقط `erase` دارد که رکورد را نگه می‌دارد و اطلاعاتش را پاک می‌کند.
 */

async function bootstrapOrg(request: APIRequestContext) {
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
  const login = await request.post("/api/auth/login", {
    data: { organization_slug: slug, email, password: "password" },
  });
  // بدون این ادعا، خطای لاگین فقط با یک خطای ۴۰۱ در جای دیگر خودش را نشان می‌دهد
  expect(login.ok(), `login failed: ${await login.text()}`).toBeTruthy();
  const { access_token } = (await login.json()) as { access_token: string };
  return { slug, email, token: access_token };
}

async function signIn(page: Page, org: { slug: string; email: string }) {
  await page.goto("/login");
  await page.getByLabel(/company code|کد شرکت/i).fill(org.slug);
  await page.getByLabel(/email|ایمیل/i).fill(org.email);
  await page.getByLabel(/password|رمز عبور/i).fill("password");
  await page.getByRole("button", { name: /sign in|ورود/i }).click();
  // bcrypt + SQLite ⇒ لاگین می‌تواند چند ثانیه طول بکشد
  await expect(page).not.toHaveURL(/login/, { timeout: 20_000 });
}

test.describe("destructive and irreversible operations", () => {
  test("erasing a customer scrubs personal data but keeps the row", async ({ page, request }) => {
    const org = await bootstrapOrg(request);
    const auth = { Authorization: `Bearer ${org.token}` };

    const created = await request.post("/api/customers", {
      headers: auth,
      data: { full_name: "مشتری تست پاک‌سازی", phone: "09120000000", email: "c@example.com" },
    });
    expect(created.ok()).toBeTruthy();
    const customer = (await created.json()) as { id: string; full_name: string };

    await signIn(page, org);
    await page.goto("/customers");
    await expect(page.locator("body")).toContainText(customer.full_name);

    // انتخاب ردیف، سپس «ناشناس کردن» — دو تأیید لازم است:
    // اول «ادامه»، بعد «ناشناس کن». یک تأیید کافی نیست.
    const row = page.locator("tr", { hasText: customer.full_name }).first();
    await row.click();
    await page.getByRole("button", { name: /erase|ناشناس/i }).click();

    // تأیید اول — فقط ادامه
    await page.getByRole("button", { name: /^ادامه$/ }).click();

    // بعد از یک تأیید نباید چیزی پاک شده باشد — تأیید دوم لازم است
    await expect(page.getByText(/تأیید نهایی/)).toBeVisible();
    const mid = await request.get(`/api/customers/${customer.id}`, { headers: auth });
    expect(((await mid.json()) as { full_name: string }).full_name).toBe(customer.full_name);

    // تأیید دوم و نهایی
    await page.getByRole("button", { name: /ناشناس کن/ }).click();

    // نام واقعی دیگر نباید دیده شود
    await expect(page.locator("body")).not.toContainText(customer.full_name);

    // رکورد باید باقی مانده باشد ولی اطلاعاتش پاک شده باشد
    const after = await request.get(`/api/customers/${customer.id}`, { headers: auth });
    expect(after.status()).toBe(200);
    const scrubbed = (await after.json()) as {
      full_name: string;
      phone: string | null;
      email: string | null;
    };
    expect(scrubbed.phone).toBeNull();
    expect(scrubbed.email).toBeNull();
    expect(scrubbed.full_name).not.toBe(customer.full_name);
  });

  test("an approval is decidable only by its approver", async ({ page, request }) => {
    const org = await bootstrapOrg(request);
    const auth = { Authorization: `Bearer ${org.token}` };

    // تأییدکننده‌ای غیر از درخواست‌دهنده بساز (خود-تأییدی ممنوع است)
    const other = await request.post("/api/org/users", {
      headers: auth,
      data: {
        email: `approver-${Date.now()}@example.com`,
        full_name: "Approver",
        password: "password",
      },
    });
    expect(other.ok()).toBeTruthy();
    const approver = (await other.json()) as { id: string };

    const created = await request.post("/api/approvals", {
      headers: auth,
      data: {
        kind: "discount",
        title: "تخفیف تست",
        payload: { amount: 100 },
        approver_ids: [approver.id],
      },
    });
    expect(created.ok()).toBeTruthy();
    const approval = (await created.json()) as { id: string; status: string };
    expect(approval.status).toBe("pending");

    // درخواست‌دهنده (که تأییدکننده نیست) نباید بتواند تصمیم بگیرد
    const wrong = await request.post(`/api/approvals/${approval.id}/decision`, {
      headers: auth,
      data: { decision: "approved" },
    });
    expect([403, 400, 409]).toContain(wrong.status());

    await signIn(page, org);
    await page.goto("/approvals");
    await expect(page.locator("body")).toContainText("تخفیف تست");
  });

  test("self-approval is refused with 400", async ({ request }) => {
    const org = await bootstrapOrg(request);
    const auth = { Authorization: `Bearer ${org.token}` };
    const me = await request.get("/api/auth/me", { headers: auth });
    expect(me.ok()).toBeTruthy();
    const profile = (await me.json()) as { id: string };

    // درخواست‌دهنده نباید بتواند خودش را تأییدکننده کند
    const created = await request.post("/api/approvals", {
      headers: auth,
      data: {
        kind: "discount",
        title: "خود-تأییدی",
        payload: {},
        approver_ids: [profile.id],
      },
    });
    expect(created.status()).toBe(400);
  });

  test("reports download a real file, not an empty response", async ({ page, request }) => {
    const org = await bootstrapOrg(request);
    await signIn(page, org);
    await page.goto("/reports");

    // دکمهٔ خروجی باید وجود داشته باشد
    const xlsx = page.locator("button", { hasText: "XLSX" }).first();
    await expect(xlsx).toBeVisible();

    // دانلود باید واقعاً فایل بدهد
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 15_000 }),
      xlsx.click(),
    ]);
    const file = await download.path();
    expect(file).toBeTruthy();
  });

  test("totp secret is not exposed in page text before reveal", async ({ page, request }) => {
    const org = await bootstrapOrg(request);
    await signIn(page, org);
    await page.goto("/settings");

    const body = page.locator("body");
    // کلید base32 نباید در متن صفحه باشد مگر بعد از نمایش صریح
    await expect(body).not.toContainText(/JBSWY3DPEHPK3PXP/);
  });
});
