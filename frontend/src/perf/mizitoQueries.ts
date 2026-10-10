import { queryOptions } from "@tanstack/react-query";
import { ApiError } from "../api";
import { perfApi } from "./api";

/**
 * فهرست‌های میزیتو در صفحهٔ کمپین‌ها. همه از دیتابیس پنل و آخرین خواندن میزیتو می‌آیند
 * و به خود میزیتو کال نمی‌زنند؛ پس شمارهٔ تب‌ها هزینهٔ بیرونی ندارد.
 * کلیدها با کامپوننت‌ها یکی است تا شمارهٔ تب و محتوای تب از یک کش خوانده شوند.
 */
export function mizitoRequestsQuery(filter: string) {
  return queryOptions({
    queryKey: ["perf", "mizito", "requests", filter],
    queryFn: () => perfApi.mizitoRequests(filter),
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 1,
  });
}

export const mizitoMissingQuery = queryOptions({
  queryKey: ["perf", "mizito", "missing"],
  queryFn: perfApi.mizitoMissing,
});

export function mizitoTriageQuery(days: number | null) {
  return queryOptions({
    queryKey: ["perf", "mizito", "triage", days],
    queryFn: () => perfApi.mizitoTriage(days),
  });
}
