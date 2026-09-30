import { useLocale } from "../i18n";
import { formatJalali, formatJalaliDateTime } from "../jalali";

/**
 * Renders an ISO date in the user's calendar: Jalali under the Persian
 * locale, Gregorian under English. Pass `withTime` for timestamps.
 */
export function DateText({
  value,
  withTime = false,
  className,
}: {
  value: unknown;
  withTime?: boolean;
  className?: string;
}) {
  const { locale } = useLocale();
  if (value == null || value === "") return null;
  if (locale !== "fa") {
    const d = new Date(String(value));
    if (Number.isNaN(d.getTime())) return null;
    // قالب ثابت و ۲۴ساعته — `toLocaleString` خروجی‌اش بسته به مرورگر
    // و منطقهٔ زمانیِ دستگاه کاربر تغییر می‌کند (و گاهی AM/PM می‌آورد).
    const date = `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
    if (!withTime) return <span className={className}>{date}</span>;
    const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    return (
      <span className={className}>
        {date} {time}
      </span>
    );
  }
  const text = withTime ? formatJalaliDateTime(value) : formatJalali(value);
  return text ? <span className={className}>{text}</span> : null;
}
