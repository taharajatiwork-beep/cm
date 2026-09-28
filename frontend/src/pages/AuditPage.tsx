import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Button, Card, EmptyState, ErrorMessage, Input, PageHeader } from "../components/ui";
import { DateText } from "../components/DateText";
import { Bi, useBi } from "../i18n";

export function AuditPage() {
  const bi = useBi();
  const [action, setAction] = useState("");
  const q = useQuery({
    queryKey: ["audit", action],
    queryFn: () => api.audit.list(action),
  });
  const rows = (q.data ?? []) as Array<Record<string, unknown>>;
  const shown = action ? rows.filter((row) => String(row.action).includes(action)) : rows;

  function download() {
    const header = "action,entity_type,created_at\n";
    const body = shown
      .map((row) => `${row.action},${row.entity_type},${row.created_at}`)
      .join("\n");
    const blob = new Blob([header + body], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "audit.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Audit" fa="ممیزی" />}
        actions={
          <Button variant="secondary" onClick={download}>
            <Bi en="Excel/CSV" fa="خروجی" />
          </Button>
        }
      />
      <Input value={action} onChange={(e) => setAction(e.target.value)} placeholder={bi("Filter action", "فیلتر عمل")} />
      <ErrorMessage error={q.isError ? String((q.error as Error).message) : ""} />
      <Card>
        {shown.length === 0 ? (
          <EmptyState titleEn="No audit rows" titleFa="ردیفی نیست" bodyEn="Nothing matches this filter." bodyFa="چیزی با این فیلتر نیست." />
        ) : (
          shown.map((row) => (
            <div key={String(row.id)} className="row-item">
              <strong>{String(row.action)}</strong>
              <span className="muted">{String(row.entity_type)}</span>
              <DateText value={row.created_at} />
            </div>
          ))
        )}
      </Card>
    </>
  );
}
