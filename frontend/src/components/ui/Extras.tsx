import { useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Icon, type IconName } from "./Icon";

export type Tone = "neutral" | "accent" | "ok" | "warn" | "danger" | "ai";

export function StatCard({
  icon,
  label,
  value,
  hint,
  tone = "neutral",
  to,
}: {
  icon: IconName;
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  to?: string;
}) {
  const body = (
    <>
      <span className={`kpi-icon tone-${tone}`}>
        <Icon name={icon} size={16} />
      </span>
      <span className="kpi-text">
        <span className="kpi-label">{label}</span>
        <span className="kpi-value">{value}</span>
        {hint ? <span className="kpi-hint">{hint}</span> : null}
      </span>
    </>
  );
  return to ? (
    <Link className="kpi kpi--link" to={to}>
      {body}
    </Link>
  ) : (
    <div className="kpi">{body}</div>
  );
}

export function Segmented<K extends string>({
  value,
  onChange,
  items,
}: {
  value: K;
  onChange: (k: K) => void;
  items: Array<{ key: K; label: ReactNode; count?: number; icon?: IconName }>;
}) {
  return (
    <div className="segmented" role="tablist">
      {items.map((it) => (
        <button
          key={it.key}
          type="button"
          role="tab"
          aria-selected={value === it.key}
          className={value === it.key ? "seg active" : "seg"}
          onClick={() => onChange(it.key)}
        >
          {it.icon ? <Icon name={it.icon} size={14} /> : null}
          <span>{it.label}</span>
          {typeof it.count === "number" ? <span className="seg-count">{it.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Sheet({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="sheet-root" role="dialog" aria-modal>
      <div className="sheet-backdrop" onClick={onClose} />
      <aside className="sheet">
        <header className="sheet-head">
          <h2>{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="close">
            <Icon name="x" />
          </button>
        </header>
        <div className="sheet-body">{children}</div>
        {footer ? <footer className="sheet-foot">{footer}</footer> : null}
      </aside>
    </div>
  );
}

export function Avatar({ name, size = 28 }: { name: string; size?: number }) {
  const initials =
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((p) => p[0])
      .join("")
      .toUpperCase() || "?";
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  const hue = hash % 360;
  return (
    <span
      className="avatar"
      style={{
        width: size,
        height: size,
        fontSize: Math.round(size * 0.4),
        background: `hsl(${hue} 55% 92%)`,
        color: `hsl(${hue} 45% 32%)`,
      }}
      aria-hidden
    >
      {initials}
    </span>
  );
}

export function SectionHeader({
  title,
  count,
  action,
  icon,
}: {
  title: ReactNode;
  count?: number;
  action?: ReactNode;
  icon?: IconName;
}) {
  return (
    <div className="section-head">
      <h2>
        {icon ? <Icon name={icon} size={15} /> : null}
        {title}
        {typeof count === "number" ? <span className="section-count">{count}</span> : null}
      </h2>
      {action ? <div className="section-action">{action}</div> : null}
    </div>
  );
}

export function IconButton({
  icon,
  label,
  onClick,
  type = "button",
}: {
  icon: IconName;
  label: string;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  return (
    <button type={type} className="icon-btn" onClick={onClick} aria-label={label} title={label}>
      <Icon name={icon} />
    </button>
  );
}
