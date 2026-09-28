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
    return (
      <span className={className}>
        {withTime ? d.toLocaleString() : d.toLocaleDateString()}
      </span>
    );
  }
  const text = withTime ? formatJalaliDateTime(value) : formatJalali(value);
  return text ? <span className={className}>{text}</span> : null;
}
