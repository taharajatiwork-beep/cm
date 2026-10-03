/**
 * نمودارهای سبک SVG/CSS — بدون وابستگی خارجی.
 * برای تب‌های «تحلیل‌ها» و «مانیتورینگ» صفحهٔ مدیریت.
 */

const DONUT_COLORS = [
  "var(--accent)",
  "var(--ok)",
  "var(--warn)",
  "var(--danger)",
  "#8b5cf6",
  "#64748b",
];

/** نوارهای افقی — مناسب تفکیک‌ها (اولویت، وضعیت، نوع و…). RTL-دوست. */
export function HBars({
  data,
  color = "var(--accent)",
  format,
}: {
  data: Array<{ label: string; value: number }>;
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
        <div key={d.label} className="chart-hbar-row" title={`${d.label}: ${d.value}`}>
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
  data: Array<{ label: string; values: number[] }>;
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
        {data.map((d) => (
          <div key={d.label} className="chart-col">
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
        ))}
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
  data: Array<{ label: string; value: number }>;
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
          <li key={d.label}>
            <i style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
            <span className="mono">{d.label}</span>
            <b>{format ? format(d.value) : d.value}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}