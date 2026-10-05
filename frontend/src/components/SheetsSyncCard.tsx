import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
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

export function SheetsSyncCard() {
  const bi = useBi();
  const toast = useToast();
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

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

  return (
    <Card>
      <SectionHeader
        title={<Bi en="Google Sheets" fa="گوگل‌شیت" />}
        action={
          <Button onClick={() => sync.mutate()} disabled={sync.isPending}>
            {sync.isPending ? (
              <Bi en="Updating…" fa="در حال به‌روزرسانی…" />
            ) : (
              <Bi en="Update Google Sheets" fa="به‌روزرسانی گوگل‌شیت" />
            )}
          </Button>
        }
      />
      <Muted>
        <Bi
          en="After you change posts, prices, customers, or campaigns, push them to the Sotoudeh sheet and the cost, campaign, and report workbooks."
          fa="بعد از تغییر پست، قیمت، مشتری یا کمپین، شیت ستوده و شیت‌های هزینه، کمپین و گزارش را به‌روز کنید."
        />
      </Muted>
      {notice ? <p className="fine">{notice}</p> : null}
      <ErrorMessage error={error} friendly={false} />
    </Card>
  );
}
