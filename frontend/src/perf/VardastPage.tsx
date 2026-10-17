import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  ErrorMessage,
  Field,
  LoadingState,
  Muted,
  PageHeader,
  SectionHeader,
  Segmented,
  Select,
  Table,
} from "../components/ui";
import { Bi } from "../i18n";
import { perfApi, toman, type VardastContact } from "./api";

type Tab = "overview" | "contacts" | "assistants" | "inbox" | "reports" | "activity";

const USAGE_LABELS: Record<string, string> = {
  total_contacts: "مخاطب",
  contact_credit: "اعتبار مخاطب",
  total_chats: "گفتگو",
  chat_credit: "اعتبار گفتگو",
  all_chat_credit: "سقف گفتگو",
  mode: "حالت",
  next_due_date: "تمدید",
  time_credit: "اعتبار زمانی",
  is_allowed: "مجاز",
};

function usageEntries(usage: Record<string, unknown> | null): Array<{ key: string; label: string; value: string }> {
  if (!usage) return [];
  const skip = new Set(["active_features", "user_id"]);
  return Object.entries(usage)
    .filter(([key, value]) => !skip.has(key) && value !== null && value !== undefined && typeof value !== "object")
    .map(([key, value]) => ({
      key,
      label: USAGE_LABELS[key] || key,
      value: typeof value === "boolean" ? (value ? "بله" : "خیر") : String(value),
    }));
}

export function VardastPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [channelId, setChannelId] = useState("");
  const [contactId, setContactId] = useState("");
  const [reportChannelId, setReportChannelId] = useState("");

  const home = useQuery({ queryKey: ["perf", "vardast"], queryFn: () => perfApi.vardast() });
  const contacts = useQuery({
    queryKey: ["perf", "vardast", "contacts", channelId],
    queryFn: () => perfApi.vardastContacts(channelId ? { channel_ids: channelId, size: 50 } : { size: 50 }),
    enabled: tab === "contacts" || tab === "inbox",
  });
  const assistants = useQuery({
    queryKey: ["perf", "vardast", "assistants"],
    queryFn: () => perfApi.vardastAssistants(),
    enabled: tab === "assistants" || tab === "inbox",
  });
  const messages = useQuery({
    queryKey: ["perf", "vardast", "messages", channelId, contactId],
    queryFn: () => perfApi.vardastMessages(channelId, contactId),
    enabled: tab === "inbox" && Boolean(channelId && contactId),
  });
  const activity = useQuery({
    queryKey: ["perf", "vardast", "usage-activity"],
    queryFn: () => perfApi.vardastUsageActivity(),
    enabled: tab === "activity",
  });
  const reportContacts = useQuery({
    queryKey: ["perf", "vardast", "channel-contacts", reportChannelId],
    queryFn: () => perfApi.vardastChannelContacts(reportChannelId),
    enabled: tab === "reports" && Boolean(reportChannelId),
  });

  const contactOptions = useMemo(() => {
    const rows = contacts.data?.items ?? [];
    return channelId ? rows.filter((row) => row.channel_id === channelId || !row.channel_id) : rows;
  }, [contacts.data?.items, channelId]);

  if (home.isLoading) return <LoadingState />;
  if (home.isError) {
    return (
      <>
        <PageHeader title={<Bi en="Vardast" fa="وردست" />} actions={<Button variant="ghost" to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Button>} />
        <ErrorMessage error={home.error} />
      </>
    );
  }

  const data = home.data!;
  if (!data.connected) {
    return (
      <>
        <PageHeader title={<Bi en="Vardast" fa="وردست" />} actions={<Button variant="ghost" to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Button>} />
        <ErrorMessage friendly message={data.reason || "اتصال وردست برقرار نیست."} />
        <Muted><Link to="/perf/connections">اتصالات</Link></Muted>
      </>
    );
  }

  const usage = usageEntries(data.usage);

  return (
    <>
      <PageHeader title={<Bi en="Vardast" fa="وردست" />} actions={<Button variant="ghost" to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Button>} />
      <Segmented<Tab>
        value={tab}
        onChange={setTab}
        items={[
          { key: "overview", label: <Bi en="Overview" fa="خلاصه" /> },
          { key: "contacts", label: <Bi en="Contacts" fa="مخاطبین" /> },
          { key: "assistants", label: <Bi en="Assistants" fa="دستیارها" /> },
          { key: "inbox", label: <Bi en="Monitor" fa="مانیتور" /> },
          { key: "reports", label: <Bi en="Reports" fa="گزارش" /> },
          { key: "activity", label: <Bi en="Activity" fa="فعالیت" /> },
        ]}
      />

      {tab === "overview" ? (
        <div className="fill-row">
          <Card>
            <SectionHeader icon="message" title={<Bi en="Channels" fa="کانال‌ها" />} count={data.channels.length} />
            <Table
              rows={data.channels}
              rowKey={(row) => row.id || row.name}
              columns={[
                { key: "name", header: "نام", render: (row) => row.name },
                { key: "platform", header: "پلتفرم", className: "cell-nowrap", render: (row) => row.platform || "—" },
                { key: "id", header: "شناسه", className: "hide-sm perf-num", render: (row) => row.id },
              ]}
            />
          </Card>
          {usage.length > 0 ? (
            <Card>
              <SectionHeader icon="activity" title={<Bi en="Usage" fa="مصرف" />} />
              <div className="grid-2">
                {usage.map((row) => (
                  <div key={row.key} className="conn-tile">
                    <Muted>{row.label}</Muted>
                    <strong className="perf-num">
                      {(() => {
                        const n = Number(row.value);
                        if (!Number.isNaN(n) && (row.key.includes("credit") || row.key.startsWith("total_"))) return toman(n);
                        return row.value;
                      })()}
                    </strong>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}
        </div>
      ) : null}

      {tab === "contacts" ? (
        <Card>
          <SectionHeader icon="users" title={<Bi en="Contacts" fa="مخاطبین" />} count={contacts.data?.items.length} />
          {contacts.isLoading ? <LoadingState /> : null}
          {contacts.data && !contacts.data.ok ? <ErrorMessage friendly={false} message={contacts.data.reason} /> : null}
          {contacts.data?.ok ? (
            <Table
              rows={contacts.data.items}
              rowKey={(row) => row.id}
              columns={[
                { key: "name", header: "نام", render: (row: VardastContact) => row.name },
                { key: "platform", header: "پلتفرم", className: "cell-nowrap", render: (row) => row.platform || "—" },
                { key: "channel", header: "کانال", className: "hide-sm perf-num", render: (row) => row.channel_id || "—" },
              ]}
            />
          ) : null}
        </Card>
      ) : null}

      {tab === "assistants" ? (
        <Card>
          <SectionHeader icon="sparkles" title={<Bi en="Assistants" fa="دستیارها" />} count={assistants.data?.items.length} />
          {assistants.isLoading ? <LoadingState /> : null}
          {assistants.data && !assistants.data.ok ? <ErrorMessage friendly={false} message={assistants.data.reason} /> : null}
          {assistants.data?.ok ? (
            <Table
              rows={assistants.data.items}
              rowKey={(row) => row.id}
              columns={[
                { key: "name", header: "نام", render: (row) => row.name },
                { key: "channel", header: "کانال", className: "perf-num", render: (row) => row.channel_id || "—" },
              ]}
            />
          ) : null}
        </Card>
      ) : null}

      {tab === "inbox" ? (
        <Card>
          <SectionHeader icon="message" title={<Bi en="Conversation monitor" fa="مانیتور گفتگو" />} />
          <div className="form-grid">
            <Field label="کانال">
              <Select value={channelId} onChange={(event) => { setChannelId(event.target.value); setContactId(""); }}>
                <option value="">انتخاب کانال</option>
                {data.channels.map((ch) => (
                  <option key={ch.id} value={ch.id}>{ch.name} ({ch.platform})</option>
                ))}
              </Select>
            </Field>
            <Field label="مخاطب">
              <Select value={contactId} onChange={(event) => setContactId(event.target.value)} disabled={!channelId}>
                <option value="">انتخاب مخاطب</option>
                {contactOptions.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </Select>
            </Field>
          </div>
          {messages.isLoading ? <LoadingState /> : null}
          {messages.data && !messages.data.ok ? <ErrorMessage friendly={false} message={messages.data.reason} /> : null}
          {messages.data?.ok ? (
            <Table
              rows={messages.data.items}
              rowKey={(row) => row.id || `${row.created_at}-${row.text.slice(0, 20)}`}
              columns={[
                { key: "role", header: "نقش", className: "cell-nowrap", render: (row) => row.role || "—" },
                { key: "text", header: "متن", render: (row) => row.text },
                { key: "at", header: "زمان", className: "hide-sm cell-nowrap", render: (row) => row.created_at || "—" },
              ]}
            />
          ) : null}
        </Card>
      ) : null}

      {tab === "reports" ? (
        <Card>
          <SectionHeader icon="activity" title={<Bi en="Channel contacts (report)" fa="مخاطبین کانال (گزارش)" />} />
          <Field label="کانال">
            <Select value={reportChannelId} onChange={(event) => setReportChannelId(event.target.value)}>
              <option value="">انتخاب کانال</option>
              {data.channels.map((ch) => (
                <option key={ch.id} value={ch.id}>{ch.name}</option>
              ))}
            </Select>
          </Field>
          {reportContacts.isLoading ? <LoadingState /> : null}
          {reportContacts.data && !reportContacts.data.ok ? <ErrorMessage friendly={false} message={reportContacts.data.reason} /> : null}
          {reportContacts.data?.ok ? (
            <Table
              rows={reportContacts.data.items}
              rowKey={(row) => row.id}
              columns={[
                { key: "name", header: "نام", render: (row) => row.name },
                { key: "phone", header: "تلفن", render: (row) => row.phone || "—" },
              ]}
            />
          ) : null}
        </Card>
      ) : null}

      {tab === "activity" ? (
        <Card>
          <SectionHeader icon="activity" title={<Bi en="Usage activity" fa="فعالیت مصرف" />} />
          {activity.isLoading ? <LoadingState /> : null}
          {activity.data && !activity.data.ok ? <ErrorMessage friendly={false} message={activity.data.reason} /> : null}
          {activity.data?.ok && activity.data.items.length === 0 ? <Muted>رکوردی برنگشت.</Muted> : null}
          {activity.data?.ok && activity.data.items.length > 0 ? (
            <ul className="perf-steps">
              {activity.data.items.slice(0, 20).map((row, index) => (
                <li key={index}><code>{JSON.stringify(row)}</code></li>
              ))}
            </ul>
          ) : null}
        </Card>
      ) : null}

      <Muted><Bi en="Read-only automation — CM sends no POST to Vardast." fa="اتوماسیون فقط‌خواندنی — CM به وردست POST نمی‌زند." /></Muted>
    </>
  );
}
