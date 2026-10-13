import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api";
import { Button, Card, ErrorMessage, Muted, SectionHeader } from "./ui";
import { useToast } from "./ui/Toast";
import { Bi, useBi } from "../i18n";

type Target = {
  key: string;
  env: string;
  updated: boolean;
  error?: string;
  tabs?: string[];
};

type SyncResult = {
  ok: boolean;
  targets: Target[];
  skipped: Array<{ key: string; env: string; reason: string }>;
};

const LABELS: Record<string, [string, string]> = {
  performance: ["Sotoudeh", "ستوده"],
  cost_tracking: ["Cost tracking", "هزینه‌ها"],
  register_campaign: ["Campaigns", "کمپین‌ها"],
  reporter: ["Reporter", "گزارش"],
};

function label(key: string, bi: (en: string, fa: string) => string): string {
  const pair = LABELS[key];
  return pair ? bi(pair[0], pair[1]) : key;
}

export function SheetsSyncCard({ embedded = false }: { embedded?: boolean } = {}) {
  const bi = useBi();
  const toast = useToast();
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const status = useQuery({ queryKey: ["sheets", "status"], queryFn: () => api.perfSheets.status() });
  const running = Boolean(status.data?.running);
  const sync = useMutation({
    mutationFn: () => api.perfSheets.sync(),
    onSuccess: (data: SyncResult) => {
      const updated = data.targets.filter((row) => row.updated).map((row) => label(row.key, bi));
      const failed = data.targets.filter((row) => row.error);
      const skipped = data.skipped.map((row) => row.reason);
      const parts: string[] = [];
      if (updated.length) {
        parts.push(bi(`Updated ${updated.join(", ")}`, `به‌روز شد: ${updated.join("، ")}`));
      }
      if (skipped.length) parts.push(skipped.join(" "));
      if (failed.length) {
        parts.push(failed.map((row) => `${row.env}: ${row.error}`).join(" "));
      }
      const text = parts.join(" · ") || bi("Google Sheets updated", "گوگل‌شیت به‌روز شد");
      if (!data.ok || failed.length) {
        setNotice("");
        setError(text);
        toast(bi("Google Sheets sync failed", "به‌روزرسانی گوگل‌شیت ناموفق بود"));
        return;
      }
      setError("");
      setNotice(text);
      toast(bi("Google Sheets updated", "گوگل‌شیت به‌روز شد"));
    },
    onError: (err: unknown) => {
      const text = err instanceof ApiError ? err.message : String(err);
      setNotice("");
      setError(text);
      toast(bi("Google Sheets sync failed", "به‌روزرسانی گوگل‌شیت ناموفق بود"));
    },
  });

  const body = (
    <>
      {embedded ? (
        <div className="record-actions">
          <Button onClick={() => sync.mutate()} disabled={sync.isPending || running}>
            {sync.isPending ? (
              <Bi en="Updating…" fa="در حال به‌روزرسانی…" />
            ) : (
              <Bi en="Update Google Sheets" fa="به‌روزرسانی گوگل‌شیت" />
            )}
          </Button>
        </div>
      ) : (
        <SectionHeader
          title={<Bi en="Google Sheets" fa="گوگل‌شیت" />}
          action={
            <Button onClick={() => sync.mutate()} disabled={sync.isPending || running}>
              {sync.isPending ? (
                <Bi en="Updating…" fa="در حال به‌روزرسانی…" />
              ) : (
                <Bi en="Update Google Sheets" fa="به‌روزرسانی گوگل‌شیت" />
              )}
            </Button>
          }
        />
      )}
      <Muted>
        {running ? (
          <Bi en={`${status.data?.actor_name || "Someone"} is updating the sheet`} fa={`${status.data?.actor_name || "یک همکار"} در حال به‌روزرسانی است`} />
        ) : status.data?.finished_at ? (
          <Bi en={`Last update by ${status.data.actor_name || "—"}`} fa={`آخرین به‌روزرسانی: ${status.data.actor_name || "—"} · ${status.data.result || ""}`} />
        ) : (
          <Bi
            en="After you change posts, prices, customers, or campaigns, push them to the Sotoudeh sheet and the cost, campaign, and report workbooks."
            fa="بعد از تغییر پست، قیمت، مشتری یا کمپین، شیت ستوده و شیت‌های هزینه، کمپین و گزارش را به‌روز کنید."
          />
        )}
      </Muted>
      {notice ? <p className="fine">{notice}</p> : null}
      <ErrorMessage error={error} friendly={false} />
    </>
  );
  if (embedded) return <div className="stack">{body}</div>;
  return <Card>{body}</Card>;
}
