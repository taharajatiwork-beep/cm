import type { ReactNode } from "react";
import { Bi, useBi } from "../../i18n";
import { friendlyError } from "../../lib/errors";

export type ErrorMessageProps = {
  /** Raw error string from API / catch */
  error?: string | null;
  /** Already-localized message */
  message?: string | null;
  /** Map known technical errors to friendly copy */
  friendly?: boolean;
  className?: string;
  action?: ReactNode;
};

export function ErrorMessage({
  error,
  message,
  friendly = true,
  className = "",
  action,
}: ErrorMessageProps) {
  const bi = useBi();
  const raw = error || message;
  if (!raw) return null;

  const text =
    friendly && error
      ? (() => {
          const f = friendlyError(error);
          return bi(f.en, f.fa);
        })()
      : raw;

  return (
    <div className={`ui-error ${className}`.trim()} role="alert">
      <p className="error">
        {text}
      </p>
      {action}
    </div>
  );
}

/** Wrap an async action result zone */
export function ErrorBoundaryFallback({
  titleEn = "Something went wrong",
  titleFa = "مشکلی پیش آمد",
  detail,
}: {
  titleEn?: string;
  titleFa?: string;
  detail?: string;
}) {
  return (
    <div className="ui-error ui-error--block" role="alert">
      <strong>
        <Bi en={titleEn} fa={titleFa} />
      </strong>
      {detail ? <p className="error">{detail}</p> : null}
    </div>
  );
}
