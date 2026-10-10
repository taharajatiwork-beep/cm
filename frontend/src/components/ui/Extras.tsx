import { useId, useRef, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { faNum } from "../../fa";
import { nextTabIndex } from "../../lib/tabs";
import { Dialog } from "./Dialog";
import { Icon, type IconName } from "./Icon";

export type Tone = "neutral" | "accent" | "ok" | "warn" | "danger" | "ai";

export function StatCard({
  icon,
  label,
  value,
  hint,
  tone = "neutral",
  to,
  onClick,
  onMore,
  moreLabel,
}: {
  icon: IconName;
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  to?: string;
  onClick?: () => void;
  onMore?: () => void;
  moreLabel?: ReactNode;
}) {
  const body = (
    <>
      <span className="kpi-main">
        <span className={`kpi-icon tone-${tone}`}>
          <Icon name={icon} size={16} />
        </span>
        <span className="kpi-text">
          <span className="kpi-label">{label}</span>
          <span className="kpi-value">{typeof value === "number" ? faNum(value) : value}</span>
          {hint ? <span className="kpi-hint">{hint}</span> : null}
        </span>
      </span>
      {onMore ? (
        <button type="button" className="kpi-more" onClick={onMore}>
          {moreLabel}
        </button>
      ) : null}
    </>
  );
  const className = onMore ? "kpi kpi--stack" : "kpi";
  if (to) {
    return (
      <Link className={`${className} kpi--link`} to={to}>
        {body}
      </Link>
    );
  }
  if (onClick) {
    return (
      <button type="button" className={`${className} kpi--link`} onClick={onClick}>
        {body}
      </button>
    );
  }
  return <div className={className}>{body}</div>;
}

/**
 * تب/فیلتر کوچک. با idBase تب واقعی است: هر دکمه id و aria-controls به پنل
 * `${idBase}-panel-${key}` دارد، فقط تب فعال در ترتیب Tab است و فلش‌ها/Home/End جابه‌جا می‌کنند.
 * attention شمارهٔ تب را پررنگ می‌کند (مثلاً درخواست تصمیم‌نگرفته) و attentionLabel برای صفحه‌خوان است.
 */
export function Segmented<K extends string>({
  value,
  onChange,
  items,
  ariaLabel,
  idBase,
}: {
  value: K;
  onChange: (k: K) => void;
  items: Array<{ key: K; label: ReactNode; count?: number; icon?: IconName; attention?: boolean; attentionLabel?: string }>;
  ariaLabel?: string;
  idBase?: string;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (!idBase) return;
    const current = refs.current.findIndex((node) => node === document.activeElement);
    const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
    const next = nextTabIndex(current < 0 ? items.findIndex((it) => it.key === value) : current, items.length, event.key, rtl);
    if (next === null) return;
    event.preventDefault();
    onChange(items[next].key);
    refs.current[next]?.focus();
  }
  return (
    <div className="segmented" role="tablist" aria-label={ariaLabel} onKeyDown={idBase ? onKeyDown : undefined}>
      {items.map((it, index) => (
        <button
          key={it.key}
          ref={(node) => {
            refs.current[index] = node;
          }}
          type="button"
          role="tab"
          id={idBase ? `${idBase}-tab-${it.key}` : undefined}
          aria-controls={idBase ? `${idBase}-panel-${it.key}` : undefined}
          tabIndex={idBase ? (value === it.key ? 0 : -1) : undefined}
          aria-selected={value === it.key}
          className={value === it.key ? "seg active" : "seg"}
          onClick={() => onChange(it.key)}
        >
          {it.icon ? <Icon name={it.icon} size={14} /> : null}
          <span>{it.label}</span>
          {typeof it.count === "number" ? (
            <span className={it.attention ? "seg-count seg-count-attn" : "seg-count"}>{faNum(it.count)}</span>
          ) : null}
          {it.attention && it.attentionLabel ? <span className="seg-sr">{it.attentionLabel}</span> : null}
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
  const titleId = useId();
  if (!open) return null;
  return (
    <Dialog onClose={onClose} layout="sheet" as="aside" labelledBy={titleId}>
      <header className="sheet-head">
        <h2 id={titleId}>{title}</h2>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="بستن">
          <Icon name="x" />
        </button>
      </header>
      <div className="sheet-body">{children}</div>
      {footer ? <footer className="sheet-foot">{footer}</footer> : null}
    </Dialog>
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
  hint,
}: {
  title: ReactNode;
  count?: number;
  action?: ReactNode;
  icon?: IconName;
  /** یک خط توضیح: این بخش چیست و کاربر با آن چه کند. */
  hint?: ReactNode;
}) {
  return (
    <div className="section-head">
      <div className="section-head-main">
        <h2>
          {icon ? <Icon name={icon} size={15} /> : null}
          {title}
          {typeof count === "number" ? <span className="section-count">{faNum(count)}</span> : null}
        </h2>
        {hint ? <p className="section-hint">{hint}</p> : null}
      </div>
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
