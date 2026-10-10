import type { Column } from "../components/ui/Table";

/**
 * ستون‌هایی که در همهٔ ردیف‌ها خالی‌اند حذف می‌شوند. فقط ستون‌هایی که در filled
 * تابع دارند بررسی می‌شوند؛ بقیه همیشه می‌مانند. بدون ردیف، چیزی حذف نمی‌شود.
 */
export function withoutEmptyColumns<T>(
  columns: Column<T>[],
  rows: T[],
  filled: Partial<Record<string, (row: T) => boolean>>,
): Column<T>[] {
  if (rows.length === 0) return columns;
  return columns.filter((column) => {
    const test = filled[column.key];
    return !test || rows.some((row) => test(row));
  });
}
