import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

test("request becomes a project the requester can open", async ({ page, request }) => {
  const org = await signIn(page, request);
  const created = await request.post("/api/requests", {
    headers: { Authorization: `Bearer ${org.token}` },
    data: { title: "تبلیغ بهمن", kind: "تبلیغات" },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const row = (await created.json()) as { id: string };
  const project = await request.post(`/api/requests/${row.id}/projects`, {
    headers: { Authorization: `Bearer ${org.token}` },
    data: { title: "پروژه پرفورمنس", kind: "پرفورمنس" },
  });
  expect(project.ok(), await project.text()).toBeTruthy();
  const made = (await project.json()) as { id: string };
  await page.getByRole("link", { name: "پروژه‌ها", exact: true }).click();
  await page.getByRole("link", { name: "باز کردن" }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${made.id}`));
  await expect(page.getByRole("heading", { name: "پروژه پرفورمنس" })).toBeVisible();
  await page.getByRole("button", { name: "وظایف" }).click();
  await expect(page.getByRole("button", { name: "اعمال قالب" })).toBeVisible();
});

test("price request converts to a task", async ({ page, request }) => {
  const org = await signIn(page, request);
  const created = await request.post("/api/requests", {
    headers: { Authorization: `Bearer ${org.token}` },
    data: { title: "قیمت امروز", kind: "قیمت و پست‌ها" },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const row = (await created.json()) as { id: string };
  const task = await request.post(`/api/requests/${row.id}/tasks`, {
    headers: { Authorization: `Bearer ${org.token}` },
    data: { title: "اصلاح قیمت امروز" },
  });
  expect(task.ok(), await task.text()).toBeTruthy();
  await page.getByRole("link", { name: "درخواست‌ها" }).click();
  await expect(page.getByRole("heading", { name: /قیمت امروز/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "تبدیل مستقیم به وظیفه" })).toBeVisible();
});
