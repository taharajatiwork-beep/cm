import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Checkbox, ErrorMessage, Field, Input, Muted, Table } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { Bi } from "../i18n";
import {
  perfApi,
  toman,
  type PishgamArea,
  type PishgamPreviewArea,
  type PishgamPreviewResult,
  type PishgamTargeting,
} from "./api";

const TIER_TONE = { A: "ok", B: "warn", N: "" } as const;

const SMART_DEFAULTS = {
  preview_enabled: true,
  send_enabled: false,
  send_reason: "ارسال قفل است تا تأیید دستی شما. اولین ارسال واقعی با تعداد کم انجام شود.",
  tariffs_rial: { 1: 504, 2: 403, 3: 304 } as Record<number, number>,
  unit_note: "واحد تأیید نشده",
  limits: { max_polygons_per_request: 3, max_edge_km: 2, max_send_recipients: 500, max_balance_percent: 25 },
};

function normalizeSmart(raw: PishgamTargeting["smart"] | undefined) {
  const legacy = raw as { reason?: string } | undefined;
  return {
    ...SMART_DEFAULTS,
    ...raw,
    send_reason: raw?.send_reason ?? legacy?.reason ?? SMART_DEFAULTS.send_reason,
    tariffs_rial: { ...SMART_DEFAULTS.tariffs_rial, ...raw?.tariffs_rial },
    limits: { ...SMART_DEFAULTS.limits, ...raw?.limits },
  };
}

function previewRunning(status: string | undefined) {
  return status === "checking" || status === "creating" || status === "waiting" || status === "refreshing";
}

function progressLabel(preview: PishgamPreviewResult | null | undefined) {
  if (!preview?.progress) return "";
  const p = preview.progress;
  if (p.area_name && p.request_total) {
    return `${p.message || "در حال شمارش"} — ${p.area_name} (${toman((p.request_index ?? 0) + 1)}/${toman(p.request_total)})`;
  }
  return p.message || "";
}

export type TargetingCardProps = {
  smsBody: string;
  pickedKeys?: string[];
  onPickedChange?: (keys: string[]) => void;
  onPreviewChange?: (preview: PishgamPreviewResult | null) => void;
};

export function TargetingCard({ smsBody, pickedKeys, onPickedChange, onPreviewChange }: TargetingCardProps) {
  const toast = useToast();
  const qc = useQueryClient();
  const [picked, setPicked] = useState<string[]>(pickedKeys ?? []);
  const [operators, setOperators] = useState<number[]>([1, 2]);
  const [residenceEnabled, setResidenceEnabled] = useState(true);
  const [startDatetime, setStartDatetime] = useState("");
  const [endDatetime, setEndDatetime] = useState("");

  useEffect(() => {
    if (pickedKeys) setPicked(pickedKeys);
  }, [pickedKeys]);

  const view = useQuery({
    queryKey: ["perf", "pishgam-targeting"],
    queryFn: perfApi.pishgamTargeting,
    refetchInterval: (query) => {
      const preview = query.state.data?.preview;
      return preview && previewRunning(preview.status) ? 5000 : false;
    },
  });

  const sync = useMutation({
    mutationFn: perfApi.syncPishgamTargeting,
    onSuccess: (saved) => {
      toast(`مرجع خوانده شد: ${toman(saved.provinces)} استان، ${toman(saved.cities)} شهر`);
      void qc.invalidateQueries({ queryKey: ["perf", "pishgam-targeting"] });
    },
    onError: (error: Error) => toast(error.message),
  });

  const count = useMutation({
    mutationFn: (force: boolean) =>
      perfApi.previewPishgamAudience({
        keys: picked,
        operators,
        residence_enabled: residenceEnabled,
        start_datetime: startDatetime || null,
        end_datetime: endDatetime || null,
        sms_body: smsBody,
        links_allowed: false,
        force_refresh: force,
      }),
    onSuccess: (result) => {
      if (result.from_cache) toast("نتیجهٔ ذخیره‌شده (کش) نشان داده شد.");
      else if (result.started) toast("بررسی و شمارش شروع شد؛ حدود ۲–۳ دقیقه طول می‌کشد.");
      void qc.invalidateQueries({ queryKey: ["perf", "pishgam-targeting"] });
    },
    onError: (error: Error) => toast(error.message),
  });

  const data = view.data;
  const smart = useMemo(() => (data ? normalizeSmart(data.smart) : SMART_DEFAULTS), [data]);
  const previewData: PishgamPreviewResult | null | undefined = data?.preview;
  const hasPick = picked.length > 0;
  const running = previewRunning(previewData?.status);
  const done = previewData?.status === "done";

  useEffect(() => {
    onPreviewChange?.(done ? previewData ?? null : previewData?.status === "error" ? previewData : null);
  }, [previewData, done, onPreviewChange]);

  const plan = useMemo(() => {
    if (!data || !picked.length) return { fragments: 0, batches: 0 };
    const fragments = data.areas
      .filter((row) => picked.includes(row.key))
      .reduce((sum, row) => sum + (row.fragment_count || 1), 0);
    return { fragments, batches: Math.ceil(fragments / smart.limits.max_polygons_per_request) };
  }, [data, picked, smart.limits.max_polygons_per_request]);

  function setPickedBoth(next: string[]) {
    setPicked(next);
    onPickedChange?.(next);
  }

  function toggle(key: string) {
    setPickedBoth(picked.includes(key) ? picked.filter((item) => item !== key) : [...picked, key]);
  }

  function toggleOperator(code: number) {
    setOperators((current) => (current.includes(code) ? current.filter((item) => item !== code) : [...current, code].sort()));
  }

  const estimateLines = previewData?.estimates?.lines ?? [];

  return (
    <div className="sms-flow-target">
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
        <Muted as="p">
          <Bi en="Smart polygon audience. Create is free; only send costs." fa="مخاطب هوشمند با پلیگان. ساخت مخاطب رایگان است؛ فقط ارسال هزینه دارد." />
        </Muted>
        <Button type="button" variant="secondary" disabled={sync.isPending} onClick={() => sync.mutate()}>
          {sync.isPending ? <Bi en="Syncing…" fa="در حال خواندن…" /> : <Bi en="Sync reference" fa="مرجع API" />}
        </Button>
      </div>
      {view.error ? (
        <ErrorMessage friendly={false} message={view.error instanceof Error ? view.error.message : "هدف‌گیری خوانده نشد."} />
      ) : null}
      {data ? (
        <>
          <div className="meta-row">
            <span className="meta-chip">محله: <span className="perf-num">{toman(picked.length)}</span></span>
            <span className="meta-chip">تکه: <span className="perf-num">{toman(plan.fragments)}</span></span>
            <span className="meta-chip">Create (حداکثر ۳ تکه): <span className="perf-num">{toman(plan.batches)}</span></span>
            <span className="meta-chip">مرجع: <span className="perf-num">{toman(data.refs.provinces)}</span> استان</span>
          </div>

          <section className="sms-flow-target-panel" aria-labelledby="target-areas-title">
            <h3 className="perf-zone-title" id="target-areas-title">محله‌ها</h3>
            <div className="sms-flow-target-table-wrap">
              <Table
                className="sms-flow-target-table"
                rows={data.areas}
                rowKey={(row) => row.key}
                onRowClick={(row) => toggle(row.key)}
                isRowActive={(row) => picked.includes(row.key)}
                columns={[
                  {
                    key: "pick",
                    header: "",
                    className: "cell-check",
                    render: (row: PishgamArea) => (
                      <input
                        type="checkbox"
                        className="sms-flow-target-check"
                        aria-label={row.name_fa}
                        checked={picked.includes(row.key)}
                        onChange={() => toggle(row.key)}
                        onClick={(event) => event.stopPropagation()}
                      />
                    ),
                  },
                  { key: "name", header: "محله", render: (row) => row.name_fa },
                  {
                    key: "tier",
                    header: "سطح",
                    className: "cell-nowrap",
                    render: (row: PishgamArea) => <Badge tone={TIER_TONE[row.tier as keyof typeof TIER_TONE] || ""}>{row.tier}</Badge>,
                  },
                  {
                    key: "frag",
                    header: "تکه",
                    className: "cell-nowrap",
                    render: (row) => <span className="perf-num">{toman(row.fragment_count || 1)}</span>,
                  },
                  {
                    key: "state",
                    header: "نقشه",
                    className: "cell-nowrap",
                    render: (row) => (row.verified ? <Badge tone="ok">تأیید</Badge> : <Badge tone="warn">تقریبی</Badge>),
                  },
                ]}
              />
            </div>
          </section>

          <section className="sms-flow-target-panel sms-flow-target-conditions" aria-labelledby="target-conditions-title">
            <h3 className="perf-zone-title" id="target-conditions-title">شرایط شمارش</h3>
            <div className="form-grid sms-flow-target-conditions-grid">
              <Field className="span-all" label={<Bi en="Operators" fa="اپراتور" />}>
                <div className="choice-grid" role="group" aria-label="اپراتور">
                  {[
                    { code: 1, label: "همراه اول" },
                    { code: 2, label: "ایرانسل" },
                    { code: 3, label: "رایتل" },
                  ].map((item) => (
                    <Checkbox
                      key={item.code}
                      label={item.label}
                      checked={operators.includes(item.code)}
                      onChange={() => toggleOperator(item.code)}
                    />
                  ))}
                </div>
              </Field>
              <Field label={<Bi en="Residence" fa="ساکن" />}>
                <Checkbox
                  className="check-row--tall"
                  label="فقط ساکن محله"
                  checked={residenceEnabled}
                  onChange={(event) => setResidenceEnabled(event.target.checked)}
                />
              </Field>
              <Field label={<Bi en="From (Jalali)" fa="شروع بازه" />}>
                <Input
                  dir="ltr"
                  placeholder="خالی = ۱۱ ساعت گذشته"
                  value={startDatetime}
                  onChange={(event) => setStartDatetime(event.target.value)}
                />
              </Field>
              <Field label={<Bi en="To (Jalali)" fa="پایان بازه" />}>
                <Input
                  dir="ltr"
                  placeholder="خالی = امروز ۰۸:۰۰"
                  value={endDatetime}
                  onChange={(event) => setEndDatetime(event.target.value)}
                />
              </Field>
            </div>
            <Muted as="p" className="sms-flow-target-conditions-hint">
              <Bi en="Jalali date/time; leave blank for Pishgam defaults." fa="تاریخ و ساعت شمسی؛ فیلد خالی = پیش‌فرض پیشگام." />
            </Muted>
          </section>

          <div className="sms-flow-target-bar">
            <div className="perf-actions">
              <Button
                type="button"
                disabled={!hasPick || !operators.length || !smsBody.trim() || running || count.isPending}
                aria-busy={running || count.isPending}
                onClick={() => count.mutate(false)}
              >
                {running ? <Bi en="Counting…" fa="در حال شمارش…" /> : <Bi en="Check & count" fa="بررسی و شمارش" />}
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={!hasPick || running || count.isPending}
                onClick={() => count.mutate(true)}
              >
                <Bi en="Recount" fa="شمارش دوباره" />
              </Button>
            </div>
            {running ? (
              <div className="sms-flow-progress" role="status">
                <div className="sms-flow-progress-bar" aria-hidden />
                <Muted as="p">{progressLabel(previewData)}</Muted>
              </div>
            ) : null}
          </div>

          {previewData?.status === "error" && previewData.error ? (
            <ErrorMessage friendly={false} message={previewData.error.message} />
          ) : null}

          {done && previewData ? (
            <>
              <section className="perf-zone" aria-labelledby="target-by-area">
                <h3 className="perf-zone-title" id="target-by-area">به تفکیک محله</h3>
                <Table
                  rows={previewData.areas ?? []}
                  rowKey={(row: PishgamPreviewArea) => row.key}
                  columns={[
                    { key: "name", header: "محله", render: (row) => row.name_fa },
                    { key: "frag", header: "تکه", render: (row) => toman(row.fragment_count || 1) },
                    { key: "total", header: "جمع", render: (row) => <span className="perf-num">{toman(row.total_count)}</span> },
                    {
                      key: "ops",
                      header: "اپراتور",
                      render: (row) =>
                        (row.recipients ?? [])
                          .map((r) => `${r.operator_name}: ${toman(r.count)}`)
                          .join(" · ") || "—",
                    },
                    {
                      key: "req",
                      header: "درخواست",
                      render: (row) =>
                        (row.requests ?? [])
                          .map((r) => toman(r.smart_sms_request_id))
                          .join("، ") || "—",
                    },
                  ]}
                />
              </section>

              <section className="perf-zone" aria-labelledby="target-by-op">
                <h3 className="perf-zone-title" id="target-by-op">به تفکیک اپراتور</h3>
                <div className="meta-row">
                  <span className="meta-chip">موجودی: <span className="perf-num">{toman(previewData.credit)}</span> ریال</span>
                  {previewData.from_cache ? <Badge tone="warn">از کش</Badge> : null}
                  {previewData.counted_at ? <span className="meta-chip">زمان شمارش: {previewData.counted_at}</span> : null}
                </div>
                <Table
                  rows={estimateLines.length ? estimateLines : previewData.recipients}
                  rowKey={(row) => String(row.operator)}
                  columns={[
                    { key: "op", header: "اپراتور", render: (row) => row.operator_name },
                    { key: "count", header: "تعداد", render: (row) => <span className="perf-num">{toman(row.count)}</span> },
                    { key: "price", header: "قیمت پارت (پیشگام)", render: (row) => <span className="perf-num">{toman(row.persian_price)}</span> },
                    {
                      key: "tariff",
                      header: "تعرفه",
                      render: (row) => (
                        <span className="perf-num">
                          {toman(row.tariff_rial ?? smart.tariffs_rial[row.operator] ?? 0)}
                        </span>
                      ),
                    },
                    {
                      key: "est",
                      header: `برآورد (${toman(previewData.estimates?.sms_parts ?? 1)} پارت)`,
                      render: (row) => (
                        <span className="perf-num">{toman(row.tariff_one_part_total ?? row.api_one_part_total ?? 0)}</span>
                      ),
                    },
                    {
                      key: "afford",
                      header: "حداکثر ارسال",
                      render: (row) => {
                        const n = previewData.affordability_one_part?.[row.operator_name];
                        return n != null ? <span className="perf-num">{toman(n)}</span> : "—";
                      },
                    },
                  ]}
                />
                <Muted as="p">
                  {smart.unit_note} — تعرفه جمع: <span className="perf-num">{toman(previewData.estimates?.tariff_total ?? 0)}</span>
                  {" · "}
                  قیمت پیشگام: <span className="perf-num">{toman(previewData.estimates?.api_total ?? 0)}</span>
                </Muted>
              </section>

              {(previewData.smart_lines?.length ?? 0) > 0 ? (
                <details className="perf-fold">
                  <summary>خطوط ارسال هوشمند</summary>
                  <ul className="perf-steps">
                    {previewData.smart_lines!.map((line) => (
                      <li key={`${line.operator}-${line.number}`}>
                        {line.operator_name}: <span dir="ltr">{line.number}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
