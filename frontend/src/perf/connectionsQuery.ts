import { queryOptions, useQuery } from "@tanstack/react-query";
import { perfApi } from "./api";

/**
 * وضعیت ذخیره‌شدهٔ اتصال‌ها. سرور با live=false فقط فایل تنظیم و دیتابیس را می‌خواند
 * و به گوگل‌شیت، میزیتو یا پنل‌های پیامک کال نمی‌زند؛ پس باز کردن صفحه امن است.
 */
export const savedConnectionsQuery = queryOptions({
  queryKey: ["perf", "connections", "saved"],
  queryFn: () => perfApi.connections(false),
});

/**
 * بررسی زندهٔ همهٔ اتصال‌ها (شیت، میزیتو، پیشگام، آی‌اس‌ام‌اس). خودکار اجرا نمی‌شود:
 * نه با باز شدن صفحه، نه با فوکوس پنجره، نه با زمان‌بندی. فقط refetch() از دکمهٔ
 * «بررسی همین حالا». تکرار خودکار هم ندارد، چون آی‌اس‌ام‌اس بعد از سه ورود ناموفق قفل می‌شود.
 * نتیجه تا پایان نشست در حافظه می‌ماند تا صفحه‌های دیگر هم آخرین بررسی را ببینند.
 */
export const liveConnectionsQuery = queryOptions({
  queryKey: ["perf", "connections", "live"],
  queryFn: () => perfApi.connections(true),
  enabled: false,
  retry: false,
  staleTime: Infinity,
  gcTime: Infinity,
  refetchOnMount: false,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
});

export function useSavedConnections(enabled = true) {
  return useQuery({ ...savedConnectionsQuery, enabled });
}

export function useLiveConnections() {
  return useQuery(liveConnectionsQuery);
}
