/**
 * نمودارهای سبک SVG/CSS — بدون وابستگی خارجی.
 * برای تب‌های «تحلیل‌ها» و «مانیتورینگ» صفحهٔ مدیریت.
 * اگر یک نقطه `items` داشته باشد، نگه داشتن روی آن همان رکوردها را با لینک نشان می‌دهد.
 */
import { useState, type MouseEvent } from "react";
import { Link } from "react-router-dom";
import { formatJalali } from "../jalali";

export type ChartPoint = {
  title: string;
  href: string | null;
  detail?: string;
};

const DONUT_COLORS = [
  "var(--accent)",
  "var(--ok)",
  "var(--warn)",
  "var(--danger)",
  "#8b5cf6",
  "#64748b",
];

function PointPop({ items, series }: { items: ChartPoint[]; series?: string }) {
  if (items.length === 0) return null;
  return (
    <span className="chart-tip-pop">
      {series ? <span className="chart-tip-series">{series}</span> : null}
      {items.map((item) =>
        item.href ? (
          <Link key={`${item.href}-${item.title}`} to={item.href} className="chart-tip-link">
            {item.title}
          </Link>
        ) : (
          <span key={item.title}>{item.title}</span>
        ),
      )}
    </span>
  );
}

/** نوارهای افقی — مناسب تفکیک‌ها (اولویت، وضعیت، نوع و…). RTL-دوست. */
export function HBars({
  data,
  color = "var(--accent)",
  format,
}: {
  data: Array<{ label: string; value: number; items?: ChartPoint[] }>;
  color?: string;
  format?: (v: number) => string;
}) {
  if (data.length === 0) {
    return <div className="chart-empty muted">—</div>;
  }
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="chart-hbars">
      {data.map((d) => (
        <div
          key={d.label}
          className={d.items && d.items.length > 0 ? "chart-hbar-row chart-tip" : "chart-hbar-row"}
          tabIndex={d.items && d.items.length > 0 ? 0 : undefined}
          title={d.items && d.items.length > 0 ? undefined : `${d.label}: ${d.value}`}
        >
          {d.items && d.items.length > 0 ? <PointPop items={d.items} /> : null}
          <span className="chart-hbar-label">{d.label}</span>
          <span className="chart-hbar-track">
            <span
              className="chart-hbar-fill"
              style={{
                width: `${Math.max((d.value / max) * 100, d.value > 0 ? 2 : 0)}%`,
                background: color,
              }}
            />
          </span>
          <span className="chart-hbar-value">{format ? format(d.value) : d.value}</span>
        </div>
      ))}
    </div>
  );
}

/** نمودار ستونی گروهی — هر برچسب چند ستون هم‌خانواده دارد. */
export function GroupedBars({
  data,
  legend,
  colors = ["var(--accent)", "var(--ok)"],
  height = 150,
}: {
  data: Array<{ label: string; values: number[]; items?: ChartPoint[][] }>;
  legend?: string[];
  colors?: string[];
  height?: number;
}) {
  if (data.length === 0) {
    return <div className="chart-empty muted">—</div>;
  }
  const max = Math.max(1, ...data.flatMap((d) => d.values));
  return (
    <div className="chart-grouped" style={{ height }}>
      {legend && legend.length > 0 ? (
        <div className="chart-legend">
          {legend.map((item, i) => (
            <span key={item} className="chart-legend-item">
              <i style={{ background: colors[i] ?? "var(--accent)" }} />
              {item}
            </span>
          ))}
        </div>
      ) : null}
      <div className="chart-grouped-rows">
        {data.map((d) => {
          const groups = (d.items ?? []).map((rows, i) => ({
            series: legend?.[i],
            rows,
          })).filter((group) => group.rows.length > 0);
          return (
          <div
            key={d.label}
            className={groups.length > 0 ? "chart-col chart-tip" : "chart-col"}
            tabIndex={groups.length > 0 ? 0 : undefined}
          >
            {groups.length > 0 ? (
              <span className="chart-tip-pop">
                {groups.map((group) => (
                  <span key={group.series ?? "all"} className="chart-tip-group">
                    {group.series ? <span className="chart-tip-series">{group.series}</span> : null}
                    {group.rows.map((item) =>
                      item.href ? (
                        <Link key={`${item.href}-${item.title}`} to={item.href} className="chart-tip-link">
                          {item.title}
                        </Link>
                      ) : (
                        <span key={item.title}>{item.title}</span>
                      ),
                    )}
                  </span>
                ))}
              </span>
            ) : null}
            <span className="chart-group">
              {d.values.map((v, i) => (
                <span
                  key={i}
                  className="chart-bar"
                  title={`${d.label} · ${v}`}
                  style={{
                    height: `${v > 0 ? Math.max((v / max) * 100, 3) : 0}%`,
                    background: colors[i] ?? "var(--accent)",
                  }}
                />
              ))}
            </span>
            <span className="chart-col-label mono">{d.label}</span>
          </div>
          );
        })}
      </div>
    </div>
  );
}

/** دونات SVG با راهنما — سهم هر بخش از کل. */
export function Donut({
  data,
  size = 140,
  centerLabel,
  caption,
  format,
}: {
  data: Array<{ label: string; value: number; items?: ChartPoint[] }>;
  size?: number;
  centerLabel?: string;
  caption?: string;
  format?: (v: number) => string;
}) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  const radius = 15.9155;
  let acc = 0;
  return (
    <div className="chart-donut-wrap">
      <div className="chart-donut-ring" style={{ width: size, height: size }}>
        <svg viewBox="0 0 42 42" width={size} height={size} role="img" aria-label="donut chart">
          <circle cx="21" cy="21" r={radius} fill="none" stroke="var(--line)" strokeWidth="6" />
          {total > 0
            ? data.map((d, i) => {
                const pct = (d.value / total) * 100;
                const dash = `${pct} ${100 - pct}`;
                const offset = 25 - acc;
                acc += pct;
                return (
                  <circle
                    key={d.label}
                    cx="21"
                    cy="21"
                    r={radius}
                    fill="none"
                    stroke={DONUT_COLORS[i % DONUT_COLORS.length]}
                    strokeWidth="6"
                    strokeDasharray={dash}
                    strokeDashoffset={offset}
                  >
                    <title>{`${d.label}: ${d.value}`}</title>
                  </circle>
                );
              })
            : null}
        </svg>
        <span className="chart-donut-center">
          {centerLabel ?? total.toLocaleString()}
          {caption ? <small>{caption}</small> : null}
        </span>
      </div>
      <ul className="chart-donut-legend">
        {data.map((d, i) => (
          <li
            key={d.label}
            className={d.items && d.items.length > 0 ? "chart-tip" : undefined}
            tabIndex={d.items && d.items.length > 0 ? 0 : undefined}
          >
            {d.items && d.items.length > 0 ? <PointPop items={d.items} /> : null}
            <i style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
            <span>{d.label}</span>
            <b>{format ? format(d.value) : d.value}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** روند روزانه با SVG. بدون کتابخانهٔ نمودار. */
export function LineTrend({
  points,
  format,
  label,
}: {
  points: Array<{ label: string; value: number; detail?: string }>;
  format?: (value: number) => string;
  label?: string;
}) {
  const [active, setActive] = useState<number | null>(null);
  if (points.length === 0) return null;
  const width = 720;
  const height = 240;
  const padL = 12;
  const padR = 108;
  const padT = 16;
  const padB = 32;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  const max = Math.max(...points.map((point) => point.value), 1);
  const text = (value: number) => faDigits(format ? format(value) : String(Math.round(value)));
  const ticks = [max, max / 2, 0];
  const step = points.length === 1 ? 0 : innerW / (points.length - 1);
  const markEvery = Math.max(1, Math.ceil(points.length / 6));
  const coords = points.map((point, index) => {
    const x = padL + index * step;
    const y = padT + innerH - (point.value / max) * innerH;
    return { x, y, ...point, index };
  });
  const d = coords.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const area = `${d} L ${coords[coords.length - 1].x.toFixed(1)} ${(padT + innerH).toFixed(1)} L ${coords[0].x.toFixed(1)} ${(padT + innerH).toFixed(1)} Z`;
  const chosen = active != null ? coords[active] : null;
  const tip = chosen ? (chosen.detail || `${faDigits(formatJalali(chosen.label) || axisLabel(chosen.label))}: ${text(chosen.value)}`) : "";
  return (
    <div className="chart-line-wrap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="chart-line"
        role="img"
        aria-label={label}
        onMouseLeave={() => setActive(null)}
        onMouseMove={(event) => setActive(nearest(coords, event, width, height))}
        onClick={(event) => setActive(nearest(coords, event, width, height))}
      >
        {ticks.map((tick) => {
          const y = padT + innerH - (tick / max) * innerH;
          return (
            <g key={tick}>
              <line x1={padL} x2={padL + innerW} y1={y} y2={y} stroke="var(--line)" strokeWidth="1" />
              <text x={padL + innerW + 8} y={y + 4} fontSize="11" fill="currentColor">{text(tick)}</text>
            </g>
          );
        })}
        <path d={area} fill="var(--accent)" opacity="0.12" />
        <path d={d} fill="none" stroke="var(--accent)" strokeWidth="2.5" />
        {chosen ? <line x1={chosen.x} x2={chosen.x} y1={padT} y2={padT + innerH} stroke="var(--accent)" strokeDasharray="3 3" strokeWidth="1" /> : null}
        {coords.map((point) => {
          const showLabel = point.index % markEvery === 0 || point.index === coords.length - 1;
          return (
            <g key={`${point.index}-${point.label}`}>
              <circle
                cx={point.x}
                cy={point.y}
                r={point.index === active ? 5 : 3.5}
                fill="var(--accent)"
                stroke="var(--surface, #fff)"
                strokeWidth="1.5"
              >
                <title>{point.detail || `${faDigits(formatJalali(point.label) || axisLabel(point.label))}: ${text(point.value)}`}</title>
              </circle>
              <circle cx={point.x} cy={point.y} r="14" fill="transparent" />
              {showLabel ? (
                <text
                  x={point.x}
                  y={height - 8}
                  textAnchor={point.index === 0 ? "start" : point.index === coords.length - 1 ? "end" : "middle"}
                  fontSize="11"
                  fill="currentColor"
                >
                  {faDigits(axisLabel(point.label))}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      {tip ? <p className="chart-line-tip">{tip}</p> : <p className="chart-line-tip muted">روی نقطه نگه دارید</p>}
    </div>
  );
}

function nearest(
  coords: Array<{ x: number; y: number; index: number }>,
  event: MouseEvent<SVGSVGElement>,
  width: number,
  height: number,
): number | null {
  const rect = event.currentTarget.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const x = ((event.clientX - rect.left) / rect.width) * width;
  const y = ((event.clientY - rect.top) / rect.height) * height;
  let best = 0;
  let bestDist = Infinity;
  coords.forEach((point) => {
    const dist = (point.x - x) ** 2 + (point.y - y) ** 2;
    if (dist < bestDist) {
      bestDist = dist;
      best = point.index;
    }
  });
  return bestDist < 36 * 36 ? best : null;
}

function faDigits(text: string): string {
  return text.replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);
}

function axisLabel(label: string): string {
  const full = formatJalali(label);
  if (!full) return label.length > 5 ? label.slice(5) : label;
  const parts = full.split("/");
  return parts.length === 3 ? `${parts[1]}/${parts[2]}` : full;
}