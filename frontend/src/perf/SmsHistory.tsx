import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Field,
  Input,
  LoadingState,
  Muted,
  SectionHeader,
  Select,
  Table,
  TextArea,
} from "../components/ui";
import { DateText } from "../components/DateText";
import { useToast } from "../components/ui/Toast";
import { Bi } from "../i18n";
import { perfApi, toman, type PanelStatus, type PishgamDelivery, type SmsSend } from "./api";
import { CampaignCode, FilePick } from "./bits";
import { ArrangeBar, ShowMore, useArrange, type SortOption } from "./browse";
import { useLiveConnections, useSavedConnections } from "./connectionsQuery";
import { RowActions, SmsDelivery, SmsEdit, useRemove } from "./edit";

const SEND_SORTS: SortOption<SmsSend>[] = [
  { key: "cost-desc", label: "بیشترین هزینه", pick: (row) => row.cost_toman, dir: "desc" },
  { key: "n-desc", label: "بیشترین گیرنده", pick: (row) => row.recipient_count, dir: "desc" },
  { key: "del-desc", label: "بیشترین تحویل", pick: (row) => row.delivered_count, dir: "desc" },
  { key: "leads-desc", label: "بیشترین ورودی", pick: (row) => row.leads, dir: "desc" },
  { key: "date", label: "جدیدترین ارسال", pick: (row) => row.sent_at || "", dir: "desc" },
  { key: "code", label: "کد کمپین", pick: (row) => row.campaign_code, dir: "asc" },
];

function sendText(body: string): string {
  return body.replace(/\[\[[^\]]+\]\]/g, "").replace(/\s+/g, " ").trim();
}

function RecordedSends({ rows, missing }: { rows: SmsSend[]; missing?: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const remove = useRemove();
  const [edit, setEdit] = useState<SmsSend | null>(null);
  const [delivery, setDelivery] = useState<SmsSend | null>(null);
  const start = missing ? "open" : "linked";
  const [scope, setScope] = useState(start);
  const narrowed = rows.filter((row) => {
    if (scope === "delivered") return row.delivered_count > 0;
    if (scope === "open") return row.recipient_count > 0 && !row.delivered_count;
    if (scope === "linked") return Boolean(row.campaign_code);
    if (scope === "loose") return !row.campaign_code;
    return true;
  });
  const list = useArrange(narrowed, 12, SEND_SORTS, (row) => [row.campaign_code, row.body, row.recipient_count], scope);
  const dirty = scope !== start || list.searching || list.sortChanged;
  return (
    <Card>
      <SectionHeader icon="clock" title={<Bi en="Recorded sends" fa="ارسال‌های ثبت‌شده" />} count={list.ordered.length} />
      <FilePick
        accept=".xlsx"
        label={<Bi en="Drop the panel report" fa="گزارش پنل را بیندازید" />}
        hint={<Bi en="Matched by date or recipient count. Successful delivery counts; waiting does not." fa="با تاریخ یا تعداد گیرنده جور می‌شود. دریافت موفق شمرده می‌شود و منتظر گزارش نه." />}
        onFile={(file) => {
          perfApi.matchDelivery(file).then((result) => {
            toast(`${result.campaign_code || "ارسال"}: ${toman(result.delivered_count)} تحویل`);
            qc.invalidateQueries({ queryKey: ["perf", "sends"] });
          }).catch((error: Error) => toast(error.message));
        }}
      />
      <ArrangeBar
        query={list.query}
        onQuery={list.setQuery}
        placeholder="کد کمپین یا متن"
        sortKey={list.sortKey}
        onSort={list.setSortKey}
        sorts={list.sorts}
        onReset={dirty ? () => { setScope(start); list.resetSort(); } : undefined}
      >
        <Select aria-label="تحویل" value={scope} onChange={(event) => setScope(event.target.value)}>
          <option value="">همهٔ ارسال‌ها</option>
          <option value="linked">فقط با کمپین</option>
          <option value="open">بدون تحویل</option>
          <option value="loose">بدون کمپین</option>
          <option value="delivered">فقط تحویل‌شده</option>
        </Select>
      </ArrangeBar>
      {list.windowed.total === 0 ? <Muted as="p">ارسالی با این فیلتر نیست.</Muted> : (
        <Table
          rows={list.windowed.rows}
          rowKey={(row) => row.id}
          columns={[
            { key: "code", header: "کمپین", className: "cell-nowrap", render: (row: SmsSend) => <CampaignCode code={row.campaign_code} /> },
            { key: "when", header: "تاریخ", render: (row) => row.sent_at ? <DateText value={row.sent_at} /> : "—" },
            { key: "panel", header: "پنل", render: (row) => row.panel_name || "—" },
            { key: "body", header: "متن", render: (row) => <span className="cell-clamp">{sendText(row.body) || "—"}</span> },
            { key: "n", header: "گیرنده", render: (row) => toman(row.recipient_count) },
            { key: "cost", header: "هزینه", render: (row) => toman(row.cost_toman) },
            { key: "del", header: "تحویل", render: (row) => toman(row.delivered_count) },
            { key: "leads", header: "ورودی", render: (row) => toman(row.leads) },
            {
              key: "actions",
              header: "",
              render: (row) => (
                <RowActions
                  onDelivery={() => setDelivery(row)}
                  onEdit={() => setEdit(row)}
                  onDelete={() => void remove(`ارسال ${row.campaign_code || ""}`, () => perfApi.deleteSend(row.id))}
                />
              ),
            },
          ]}
        />
      )}
      <ShowMore left={list.windowed.left} onMore={list.windowed.grow} />
      {edit ? <SmsEdit row={edit} onClose={() => setEdit(null)} /> : null}
      {delivery ? <SmsDelivery row={delivery} onClose={() => setDelivery(null)} /> : null}
    </Card>
  );
}

const PISHGAM_WEB = "https://sms.pishgamrayan.com";

const POSTAL_SECTIONS = [
  { page: "sendZonePostalCode", title: "ارسال منطقه‌ای", hint: "کدپستی و منطقه در پنل پیشگام" },
  { page: "sendSmsFromMap", title: "ارسال از نقشه", hint: "محدوده روی نقشه" },
  { page: "sendSmartSMS", title: "مکان‌محور", hint: "ساکنین محدوده (پنل)" },
];

export function pishgamPageUrl(page: string, body: string, sender: string): string {
  const params = new URLSearchParams();
  if (body.trim()) params.set("smsBody", body.trim());
  if (sender.trim()) params.set("senderNumber", sender.trim());
  const query = params.toString();
  return `${PISHGAM_WEB}/${page}${query ? `?${query}` : ""}`;
}

export function PishgamPostalAudience({ body, senderLine }: { body: string; senderLine: string }) {
  const toast = useToast();
  async function copyText() {
    if (!body.trim()) {
      toast("متن خالی است.");
      return;
    }
    try {
      await navigator.clipboard.writeText(body.trim());
      toast("متن کپی شد.");
    } catch {
      toast("کپی نشد؛ متن را دستی انتخاب کنید.");
    }
  }
  function open(page: string, title: string) {
    window.open(pishgamPageUrl(page, body, senderLine), "_blank", "noopener,noreferrer");
    toast(`${title} در پیشگام باز شد.`);
  }
  return (
    <div className="sms-flow-postal">
      <Muted as="p">
        <Bi
          en="Regional postal send is only in the Pishgam web panel. Copy the message from step 1 and continue there."
          fa="ارسال منطقه‌ای کدپستی فقط در پنل وب پیشگام است. متن را از قدم ۱ کپی کنید و ادامه را آنجا بزنید."
        />
      </Muted>
      <div className="perf-actions">
        <Button type="button" variant="secondary" onClick={() => void copyText()}>
          <Bi en="Copy text" fa="کپی متن" />
        </Button>
      </div>
      <div className="conn-grid">
        {POSTAL_SECTIONS.map((section) => (
          <article key={section.page} className="conn-tile">
            <h3>{section.title}</h3>
            <p className="conn-help">{section.hint}</p>
            <Button type="button" onClick={() => open(section.page, section.title)}>
              <Bi en="Open in Pishgam" fa="ادامه در پیشگام" />
            </Button>
          </article>
        ))}
      </div>
    </div>
  );
}

function PishgamDeliveryCard({
  panelId,
  onDone,
}: {
  panelId: string;
  onDone: (result: PishgamDelivery) => void;
}) {
  const toast = useToast();
  const [messageId, setMessageId] = useState("");
  const [recipients, setRecipients] = useState("");
  const delivery = useMutation({
    mutationFn: () => {
      const numbers = recipients.split(/[\s,،]+/).map((item) => item.trim()).filter(Boolean);
      return perfApi.pishgamDelivery({ panel_id: panelId, message_id: Number(messageId), recipients: numbers });
    },
    onSuccess: onDone,
    onError: (error: Error) => toast(error.message),
  });
  return (
    <Card>
      <SectionHeader
        icon="clock"
        title={<Bi en="Delivery status" fa="بررسی وضعیت تحویل" />}
        hint={<Bi en="Enter the send id from the Pishgam panel (Outbox) and up to 100 recipients. Read-only." fa="شناسهٔ ارسال را از صف ارسال پنل پیشگام بردارید و حداکثر ۱۰۰ گیرنده بنویسید. فقط خواندن." />}
      />
      <div className="form-grid">
        <Field label={<Bi en="Send id" fa="شناسهٔ ارسال" />}>
          <Input type="number" value={messageId} placeholder="مثلاً ۱۲۳۴۵۶" onChange={(e) => setMessageId(e.target.value)} />
        </Field>
        <Field className="span-all" label={<Bi en="Recipients" fa="شمارهٔ گیرنده‌ها" />}>
          <TextArea value={recipients} rows={3} placeholder="هر شماره یک خط یا با ویرگول. حداکثر ۱۰۰ شماره." onChange={(e) => setRecipients(e.target.value)} />
        </Field>
        <div className="span-all perf-actions">
          <Button
            type="button"
            disabled={!panelId || !messageId.trim() || !recipients.trim() || delivery.isPending}
            onClick={() => delivery.mutate()}
          >
            {delivery.isPending ? <Bi en="Checking" fa="در حال بررسی…" /> : <Bi en="Check delivery" fa="بررسی وضعیت" />}
          </Button>
        </div>
      </div>
      {delivery.data ? (
        delivery.data.ok ? (
          <Table
            rows={delivery.data.rows}
            rowKey={(row) => row.to_number || row.text}
            columns={[
              { key: "number", header: "شماره", className: "cell-nowrap", render: (row: PishgamDelivery["rows"][number]) => <span dir="ltr">{row.to_number}</span> },
              { key: "text", header: "وضعیت", render: (row) => row.text || "—" },
            ]}
          />
        ) : (
          <ErrorMessage friendly={false} message={delivery.data.reason} />
        )
      ) : null}
    </Card>
  );
}

export function SmsHistoryTab({ missing }: { missing?: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const saved = useSavedConnections();
  const live = useLiveConnections();
  const checking = live.isFetching;
  const sends = useQuery({ queryKey: ["perf", "sends"], queryFn: perfApi.sends });
  const panel: PanelStatus | undefined = ((live.data ?? saved.data)?.panels ?? []).find((row) => row.code === "pishgam");
  const pishgamSends = (sends.data ?? []).filter((row) => (row.panel_name || "").includes("پیشگام"));
  return (
    <>
      {sends.isLoading ? <LoadingState /> : null}
      {sends.data ? (
        sends.data.length === 0 ? (
          <EmptyState
            titleEn="No send recorded yet"
            titleFa="هنوز ارسالی ثبت نشده"
            bodyEn="After you send, save a record in the send step or import delivery from the panel report."
            bodyFa="بعد از ارسال، در قدم «ارسال» سابقه را ثبت کنید یا تحویل را از گزارش پنل وارد کنید."
          />
        ) : (
          <RecordedSends rows={sends.data} missing={missing} />
        )
      ) : null}
      <Card>
        <SectionHeader
          icon="message"
          title={<Bi en="Pishgam live status" fa="پیشگام — وضعیت زنده" />}
          hint={<Bi en="Balance and lines load when you press Check now." fa="موجودی و خطوط با «بررسی همین حالا» زنده خوانده می‌شود." />}
          action={
            <div className="row">
              {checking
                ? <Badge tone="warn"><Bi en="Checking" fa="در حال بررسی" /></Badge>
                : !panel?.live
                  ? <Badge tone="warn"><Bi en="Not checked" fa="بررسی نشده" /></Badge>
                  : panel.live.ok
                    ? <Badge tone="ok"><Bi en="Connected" fa="وصل" /></Badge>
                    : <Badge tone="danger"><Bi en="Not connected" fa="وصل نیست" /></Badge>}
              <Button type="button" variant="secondary" disabled={checking} aria-busy={checking} onClick={() => void live.refetch()}>
                {checking ? <Bi en="Checking…" fa="در حال بررسی…" /> : <Bi en="Check now" fa="بررسی همین حالا" />}
              </Button>
            </div>
          }
        />
        {live.dataUpdatedAt && !checking ? (
          <Muted as="p">آخرین بررسی زنده: <DateText value={new Date(live.dataUpdatedAt).toISOString()} withTime /></Muted>
        ) : null}
        {live.error && !checking ? (
          <ErrorMessage friendly={false} message={live.error instanceof Error ? live.error.message : "بررسی زنده انجام نشد."} />
        ) : null}
        {!panel || !panel.live ? (
          <Muted as="p">{checking ? "در حال بررسی زنده…" : "برای خواندن موجودی «بررسی همین حالا» را بزنید."}</Muted>
        ) : panel.live.ok ? (
          <div className="form-grid">
            <Field label={<Bi en="Balance" fa="موجودی" />}>
              <Input readOnly value={panel.live.balance || "—"} />
            </Field>
            <Field label={<Bi en="Sender lines" fa="خطوط ارسال" />}>
              <Input readOnly dir="ltr" value={(panel.live.lines ?? []).join(" ، ") || "—"} />
            </Field>
          </div>
        ) : (
          <ErrorMessage friendly={false} message={panel.live.reason || "کال زنده به پنل انجام نشد."} />
        )}
      </Card>
      <Card>
        <SectionHeader icon="sparkles" title={<Bi en="Send analytics" fa="تحلیل ارسال‌ها" />} count={pishgamSends.length} />
        {pishgamSends.length === 0 ? (
          <Muted as="p">هنوز ارسالی از پیشگام ثبت نشده است.</Muted>
        ) : (
          <>
            <div className="form-grid">
              <Field label={<Bi en="Sends" fa="ارسال‌ها" />}><Input readOnly value={toman(pishgamSends.length)} /></Field>
              <Field label={<Bi en="Recipients" fa="گیرنده" />}><Input readOnly value={toman(pishgamSends.reduce((s, r) => s + (r.recipient_count || 0), 0))} /></Field>
              <Field label={<Bi en="Cost (toman)" fa="هزینه (تومان)" />}><Input readOnly value={toman(pishgamSends.reduce((s, r) => s + (r.cost_toman || 0), 0))} /></Field>
              <Field label={<Bi en="Delivered" fa="تحویل" />}><Input readOnly value={toman(pishgamSends.reduce((s, r) => s + (r.delivered_count || 0), 0))} /></Field>
            </div>
            <Table
              rows={pishgamSends.slice(0, 8)}
              rowKey={(row) => row.id}
              columns={[
                { key: "code", header: "کمپین", className: "cell-nowrap", render: (row: SmsSend) => <CampaignCode code={row.campaign_code} /> },
                { key: "when", header: "تاریخ", render: (row) => row.sent_at ? <DateText value={row.sent_at} /> : "—" },
                { key: "n", header: "گیرنده", render: (row) => toman(row.recipient_count) },
                { key: "cost", header: "هزینه", render: (row) => toman(row.cost_toman) },
                { key: "del", header: "تحویل", render: (row) => toman(row.delivered_count) },
              ]}
            />
          </>
        )}
      </Card>
      <PishgamDeliveryCard
        panelId={panel?.id || ""}
        onDone={(result) => {
          toast(`${toman(result.delivered_count)} رسیده به گوشی از ${toman(result.rows.length)} شماره`);
          void qc.invalidateQueries({ queryKey: ["perf", "sends"] });
        }}
      />
    </>
  );
}
