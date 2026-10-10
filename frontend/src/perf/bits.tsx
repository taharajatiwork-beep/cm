import { useId, useRef, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError } from "../api";
import { Badge, Button, Dialog, Icon, SectionHeader } from "../components/ui";
import { Bi, useBi } from "../i18n";
import { mizitoCode, perfApi } from "./api";

/** از یک کمپین به بقیهٔ بخش‌های همان کمپین. بخش فعلی نشان داده نمی‌شود. */
export function RelatedLinks({ id, code, here }: { id: string; code?: string; here?: string }) {
  const items = [
    { key: "campaign", to: `/perf/campaigns/${id}`, label: code ? `کمپین ${code}` : "کمپین" },
    { key: "sms", to: `/perf/sms?campaign=${id}`, label: "پیامک" },
    { key: "social", to: `/perf/social?campaign=${id}`, label: "سوشال" },
    { key: "money", to: `/perf/money?campaign=${id}`, label: "هزینه‌ها" },
    { key: "sheet", to: code ? `/perf/sheet?campaign=${encodeURIComponent(code)}` : "/perf/sheet", label: "شیت" },
  ].filter((item) => item.key !== here);
  return (
    <div className="row">
      {items.map((item) => (
        <Button key={item.key} variant="ghost" to={item.to}>{item.label}</Button>
      ))}
    </div>
  );
}

/** کد کمپین را به صفحهٔ همان کمپین می‌برد. اگر کمپین در پنل نباشد، کد فقط متن می‌ماند. */
export function CampaignCode({ code, id }: { code?: string | null; id?: string | null }) {
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const key = mizitoCode(code);
  const found = id
    ? (campaigns.data ?? []).find((row) => row.id === id)
    : key
      ? (campaigns.data ?? []).find((row) => mizitoCode(row.code) === key)
      : undefined;
  const label = found?.code || code || "";
  if (!label) return <>—</>;
  if (!found) return <>{label}</>;
  return (
    <Link to={`/perf/campaigns/${found.id}`} onClick={(event) => event.stopPropagation()}>
      {label}
    </Link>
  );
}

export function FilePick({
  accept,
  label,
  hint,
  busy,
  onFile,
}: {
  accept: string;
  label: ReactNode;
  hint?: ReactNode;
  busy?: boolean;
  onFile: (file: File) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className="drop-zone" disabled={busy} onClick={() => ref.current?.click()}>
        <Icon name="upload" size={22} />
        <strong>{label}</strong>
        {hint ? <span dir={typeof hint === "string" && hint.trim().startsWith(".") ? "ltr" : undefined}>{hint}</span> : null}
      </button>
      <input
        ref={ref}
        hidden
        type="file"
        accept={accept}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
    </>
  );
}

export function FileButton({
  accept,
  label,
  onFile,
}: {
  accept: string;
  label: ReactNode;
  onFile: (file: File) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <Button type="button" variant="secondary" onClick={() => ref.current?.click()}>
        {label}
      </Button>
      <input
        ref={ref}
        hidden
        type="file"
        accept={accept}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
    </>
  );
}

export type Outcome = { ok: boolean; title: string; detail: string };

/** متن دقیق خطا: کد وضعیت و detail سرور، بدون خلاصه‌کردن. */
export function exactError(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = (error.detail || error.message || "").trim();
    return detail ? `کد ${error.status}: ${detail}` : `کد ${error.status}`;
  }
  if (error instanceof Error && error.message.trim()) return error.message.trim();
  return "خطای ناشناخته";
}

/** نتیجهٔ یک درخواست: موفق یا ناموفق، با توضیح کامل. */
export function OutcomePop({ outcome, onClose }: { outcome: Outcome | null; onClose: () => void }) {
  const bi = useBi();
  const titleId = useId();
  if (!outcome) return null;
  return (
    <Dialog onClose={onClose} className="form-pop" labelledBy={titleId} closeLabel={bi("Close", "بستن")}>
      <SectionHeader
        title={<span id={titleId}>{outcome.title}</span>}
        action={<button type="button" className="kpi-more" onClick={onClose}><Bi en="Close" fa="بستن" /></button>}
      />
      <Badge tone={outcome.ok ? "ok" : "danger"}>{outcome.ok ? "موفق" : "ناموفق"}</Badge>
      <p className="outcome-detail">{outcome.detail}</p>
    </Dialog>
  );
}
