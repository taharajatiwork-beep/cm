import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  CASE_STATUS_LABELS,
  CASE_TYPE_LABELS,
  PRIORITY_LABELS,
  SLA_STATE_LABELS,
} from "./labels";

/**
 * نگهبان هم‌خوانی برچسب‌های فرانت با enumهای واقعی بک‌اند.
 * enum بک‌اند مستقیم import نمی‌شود (TS/Python)؛ متن فایل enum خوانده و مقدارها استخراج می‌شود
 * تا اگر بک‌اند مقداری اضافه/حذف کرد، این تست خراب شود و لیست فرانت به‌روز شود.
 */
const here = dirname(fileURLToPath(import.meta.url));
const enumsPath = resolve(here, "../../backend/app/models/enums.py");
const enumsSource = readFileSync(enumsPath, "utf-8");

function enumValues(name: string): string[] {
  const start = enumsSource.indexOf(`class ${name}(`);
  const body = enumsSource.slice(start);
  const next = body.indexOf("\nclass ");
  return [
    ...body.slice(0, next === -1 ? undefined : next).matchAll(/=\s*"([A-Z_]+)"/g),
  ].map((m) => m[1]);
}

describe("frontend labels match backend enums", () => {
  it("CASE_TYPE_LABELS covers exactly backend CaseType", () => {
    const backend = enumValues("CaseType");
    expect(backend.length).toBeGreaterThan(0);
    expect(Object.keys(CASE_TYPE_LABELS).sort()).toEqual([...backend].sort());
  });

  it("CASE_STATUS_LABELS covers exactly backend CaseStatus", () => {
    const backend = enumValues("CaseStatus");
    expect(backend.length).toBeGreaterThan(0);
    expect(Object.keys(CASE_STATUS_LABELS).sort()).toEqual([...backend].sort());
  });

  it("PRIORITY_LABELS covers exactly backend Priority", () => {
    const backend = enumValues("Priority");
    expect(backend.length).toBeGreaterThan(0);
    expect(Object.keys(PRIORITY_LABELS).sort()).toEqual([...backend].sort());
  });

  it("SLA_STATE_LABELS covers exactly backend SlaState", () => {
    const backend = enumValues("SlaState");
    expect(backend.length).toBeGreaterThan(0);
    expect(Object.keys(SLA_STATE_LABELS).sort()).toEqual([...backend].sort());
  });
});