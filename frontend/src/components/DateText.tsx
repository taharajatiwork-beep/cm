import { formatJalali, formatJalaliDateTime } from "../jalali";

/** تاریخ شمسی. `withTime` ساعت ۲۴ساعته را هم با رقم فارسی نشان می‌دهد. */
export function DateText({
  value,
  withTime = false,
  className,
}: {
  value: unknown;
  withTime?: boolean;
  className?: string;
}) {
  if (value == null || value === "") return null;
  const text = withTime ? formatJalaliDateTime(value) : formatJalali(value);
  return text ? <span className={className}>{text}</span> : null;
}
