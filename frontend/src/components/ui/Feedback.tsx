import type { ReactNode } from "react";
import { Bi } from "../../i18n";

export type BadgeTone = "" | "ok" | "warn" | "danger";

export function Badge({
  children,
  tone = "",
  className = "",
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}) {
  return <span className={`badge ${tone} ${className}`.trim()}>{children}</span>;
}

export function EmptyState({
  titleEn,
  titleFa,
  bodyEn,
  bodyFa,
  action,
  className = "",
}: {
  titleEn: string;
  titleFa: string;
  bodyEn: string;
  bodyFa: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`empty-state ui-empty ${className}`.trim()}>
      <h3>
        <Bi en={titleEn} fa={titleFa} />
      </h3>
      <p>
        <Bi en={bodyEn} fa={bodyFa} />
      </p>
      {action}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="ui-page-header">
      <div>
        <h1>{title}</h1>
        {description ? <div className="ui-page-desc">{description}</div> : null}
      </div>
      {actions ? <div className="row ui-page-actions">{actions}</div> : null}
    </div>
  );
}

export function Muted({
  children,
  className = "",
  as: Tag = "span",
}: {
  children: ReactNode;
  className?: string;
  as?: "span" | "div" | "p";
}) {
  return <Tag className={`muted ${className}`.trim()}>{children}</Tag>;
}

export function List({
  children,
  className = "",
  variant = "work",
}: {
  children: ReactNode;
  className?: string;
  variant?: "work" | "attention" | "timeline" | "checklist";
}) {
  const map = {
    work: "work-list",
    attention: "attention-list",
    timeline: "timeline",
    checklist: "checklist",
  };
  return <ul className={`ui-list ${map[variant]} ${className}`.trim()}>{children}</ul>;
}

export function ListItem({
  children,
  className = "",
  tone,
}: {
  children: ReactNode;
  className?: string;
  tone?: "danger" | "warn";
}) {
  return (
    <li className={`${tone === "danger" ? "is-danger" : tone === "warn" ? "is-warn" : ""} ${className}`.trim()}>
      {children}
    </li>
  );
}
