import type { HTMLAttributes, ReactNode } from "react";

export type CardProps = HTMLAttributes<HTMLElement> & {
  children: ReactNode;
  as?: "div" | "section" | "form" | "article";
  /** Extra layout helpers */
  stack?: boolean;
  padded?: boolean;
};

export function Card({
  children,
  as: Tag = "div",
  className = "",
  stack = false,
  padded = true,
  ...rest
}: CardProps) {
  const cls = [
    "ui-card",
    "panel",
    padded ? "" : "ui-card--flush",
    stack ? "stack" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Tag className={cls} {...(rest as HTMLAttributes<HTMLElement>)}>
      {children}
    </Tag>
  );
}

export function CardTitle({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <h2 className={`ui-card-title ${className}`.trim()}>{children}</h2>;
}
