import { Bi } from "../../i18n";

export type LoadingStateProps = {
  labelEn?: string;
  labelFa?: string;
  /** full page block vs inline */
  block?: boolean;
  className?: string;
};

export function LoadingState({
  labelEn = "Loading…",
  labelFa = "در حال بارگذاری…",
  block = true,
  className = "",
}: LoadingStateProps) {
  return (
    <div
      className={`ui-loading ${block ? "ui-loading--block" : "ui-loading--inline"} ${className}`.trim()}
      role="status"
      aria-live="polite"
    >
      <span className="ui-spinner" aria-hidden />
      <span className="muted">
        <Bi en={labelEn} fa={labelFa} />
      </span>
    </div>
  );
}
