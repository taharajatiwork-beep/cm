import { useEffect, useState, type ReactNode } from "react";
import { Button, Input, Select } from "../components/ui";
import { Bi } from "../i18n";

export function hit(query: string, ...parts: Array<string | number | null | undefined>): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return parts.some((part) => String(part ?? "").toLowerCase().includes(needle));
}

export function choices<T>(rows: T[], pick: (row: T) => string | null | undefined): string[] {
  return Array.from(new Set(rows.map(pick).filter((item): item is string => Boolean(item)))).sort((a, b) => a.localeCompare(b, "fa"));
}

export type SortOption<T> = {
  key: string;
  label: string;
  pick: (row: T) => string | number | null | undefined;
  dir: "asc" | "desc";
};

function compare(left: string | number | null | undefined, right: string | number | null | undefined, dir: "asc" | "desc"): number {
  const empty = (value: string | number | null | undefined) => value == null || value === "";
  if (empty(left) && empty(right)) return 0;
  if (empty(left)) return 1;
  if (empty(right)) return -1;
  const delta = typeof left === "number" && typeof right === "number"
    ? left - right
    : String(left).localeCompare(String(right), "fa");
  return dir === "desc" ? -delta : delta;
}

export function orderBy<T>(rows: T[], option: SortOption<T> | undefined): T[] {
  if (!option) return rows;
  return [...rows].sort((left, right) => compare(option.pick(left), option.pick(right), option.dir));
}

export function useWindow<T>(rows: T[], step: number, resetKey: string) {
  const [count, setCount] = useState(step);
  useEffect(() => {
    setCount(step);
  }, [resetKey, step]);
  return {
    rows: rows.slice(0, count),
    total: rows.length,
    left: Math.max(0, rows.length - count),
    more: rows.length > count,
    grow: () => setCount((value) => value + step),
  };
}

export function useArrange<T>(
  rows: T[],
  step: number,
  sorts: SortOption<T>[],
  text: (row: T) => Array<string | number | null | undefined>,
  extraKey = "",
) {
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState(sorts[0]?.key ?? "");
  const sort = sorts.find((item) => item.key === sortKey) ?? sorts[0];
  const found = rows.filter((row) => hit(query, ...text(row)));
  const ordered = orderBy(found, sort);
  const windowed = useWindow(ordered, step, `${query}|${sort?.key ?? ""}|${extraKey}`);
  return {
    query,
    setQuery,
    sortKey: sort?.key ?? "",
    setSortKey,
    sorts,
    ordered,
    windowed,
    searching: query.trim() !== "",
    sortChanged: Boolean(sorts[0] && sort?.key !== sorts[0].key),
    resetSort: () => {
      setQuery("");
      setSortKey(sorts[0]?.key ?? "");
    },
  };
}

export function ArrangeBar<T>({
  query,
  onQuery,
  placeholder,
  sortKey,
  onSort,
  sorts,
  onReset,
  children,
}: {
  query: string;
  onQuery: (value: string) => void;
  placeholder: string;
  sortKey: string;
  onSort: (value: string) => void;
  sorts: SortOption<T>[];
  onReset?: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="perf-browse">
      <Input value={query} placeholder={placeholder} onChange={(event) => onQuery(event.target.value)} />
      {sorts.length ? (
        <Select aria-label="ترتیب نمایش" value={sortKey} onChange={(event) => onSort(event.target.value)}>
          {sorts.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
        </Select>
      ) : null}
      {children}
      {onReset ? (
        <Button type="button" variant="ghost" onClick={onReset}>
          <Bi en="Clear" fa="پاک کردن فیلتر" />
        </Button>
      ) : null}
    </div>
  );
}

export function ShowMore({ left, onMore }: { left: number; onMore: () => void }) {
  if (left <= 0) return null;
  return (
    <Button type="button" variant="ghost" onClick={onMore}>
      <Bi en={`Show ${left} more`} fa={`نمایش بیشتر (${left})`} />
    </Button>
  );
}
