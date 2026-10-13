import type { ReactNode } from "react";
import { Bi, useBi } from "../../i18n";
import { isForbiddenError } from "../../lib/apiError";
import { friendlyError } from "../../lib/errors";
import { ForbiddenState } from "./ForbiddenState";

export type ErrorMessageProps = {
  /** Raw error from API / catch */
  error?: unknown;
  /** Raw error string from API / catch (legacy) */
  errorMessage?: string | null;
  /** Already-localized message */
  message?: string | null;
  /** Map known technical errors to friendly copy */
  friendly?: boolean;
  className?: string;
  action?: ReactNode;
};

export function ErrorMessage({
  error,
  errorMessage,
  message,
  friendly = true,
  className = "",
  action,
}: ErrorMessageProps) {
  const bi = useBi();
  if (error != null && isForbiddenError(error)) {
    return <ForbiddenState className={className} action={action} />;
  }
  const raw =
    (typeof error === "string" ? error : error instanceof Error ? error.message : null) ||
    errorMessage ||
    message;
  if (!raw) return null;

  const text =
    friendly && typeof raw === "string"
      ? (() => {
          const f = friendlyError(raw);
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
