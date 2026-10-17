import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, ErrorMessage, LoadingState, Muted, PageHeader, SectionHeader, Table } from "../components/ui";
import { Bi } from "../i18n";
import { perfApi } from "./api";

function usageLines(usage: Record<string, unknown> | null): string[] {
  if (!usage) return [];
  const lines: string[] = [];
  for (const [key, value] of Object.entries(usage)) {
    if (value === null || value === undefined) continue;
    if (typeof value === "object") {
      lines.push(`${key}: ${JSON.stringify(value)}`);
    } else {
      lines.push(`${key}: ${String(value)}`);
    }
  }
  return lines.slice(0, 12);
}

export function VardastPage() {
  const query = useQuery({ queryKey: ["perf", "vardast"], queryFn: () => perfApi.vardast() });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return (
      <>
        <PageHeader
          title={<Bi en="Vardast" fa="وردست" />}
          actions={<Button variant="ghost" to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Button>}
        />
        <ErrorMessage error={query.error} />
      </>
    );
  }

  const data = query.data!;
  if (!data.connected) {
    return (
      <>
        <PageHeader
          title={<Bi en="Vardast" fa="وردست" />}
          actions={<Button variant="ghost" to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Button>}
        />
        <ErrorMessage friendly message={data.reason || "اتصال وردست برقرار نیست."} />
        <Muted>
          <Bi en="Add your Public API key under Connections." fa="کلید Public API را در اتصالات ذخیره کنید." />
          {" "}
          <Link to="/perf/connections">اتصالات</Link>
        </Muted>
      </>
    );
  }

  const usage = usageLines(data.usage);

  return (
    <>
      <PageHeader
        title={<Bi en="Vardast" fa="وردست" />}
        actions={<Button variant="ghost" to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Button>}
      />
      <Card>
        <SectionHeader
          icon="message"
          title={<Bi en="Channels" fa="کانال‌ها" />}
          count={data.channels.length}
        />
        {data.channels.length === 0 ? (
          <Muted><Bi en="No channels returned." fa="کانالی برنگشت." /></Muted>
        ) : (
          <Table
            rows={data.channels}
            rowKey={(row) => row.id || row.name}
            columns={[
              { key: "name", header: "نام", render: (row) => row.name },
              { key: "platform", header: "پلتفرم", className: "cell-nowrap", render: (row) => row.platform || "—" },
              { key: "id", header: "شناسه", className: "hide-sm perf-num", render: (row) => row.id },
            ]}
          />
        )}
      </Card>
      {usage.length > 0 ? (
        <Card>
          <SectionHeader icon="activity" title={<Bi en="Usage" fa="مصرف" />} />
          <ul className="perf-steps">
            {usage.map((line) => (
              <li key={line}><code>{line}</code></li>
            ))}
          </ul>
        </Card>
      ) : null}
      <Muted><Bi en="Read-only — no messages are sent from CM." fa="فقط خواندن — از CM پیامی ارسال نمی‌شود." /></Muted>
    </>
  );
}
