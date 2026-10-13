import { useId, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { DateText } from "../components/DateText";
import { Badge, Button, Card, Dialog, ErrorMessage, LoadingState, Muted, PageHeader, SectionHeader, Select, Table } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { Bi, useBi } from "../i18n";
import { downloadPerf, leadsLabel, perfApi, toman, type CampaignRow, type Sheet, type SmsSend, type Story } from "./api";
import { CampaignCode, exactError, FilePick, OutcomePop, type Outcome } from "./bits";
import { ArrangeBar, choices, ShowMore, useArrange, type SortOption } from "./browse";
import { CampaignEdit, CostEdit, RowActions, SmsEdit, StoryEdit, useRemove } from "./edit";

export function SheetPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const focus = params.get("campaign") || "";
  const sheet = useQuery({ queryKey: ["perf", "sheet"], queryFn: perfApi.sheet });
  const register = useQuery({ queryKey: ["perf", "register"], queryFn: perfApi.campaignRegister });
  const catalog = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const listedOn = new Map([...(register.data?.rows ?? []), ...(register.data?.legacy ?? [])].map((row) => [row.code, row.when]));
  const byCode = new Map((catalog.data ?? []).map((row) => [row.code, row]));
  const remove = useRemove();
  const [campaignEdit, setCampaignEdit] = useState<CampaignRow | null>(null);
  const [smsEdit, setSmsEdit] = useState<SmsSend | null>(null);
  const [storyEdit, setStoryEdit] = useState<Story | null>(null);
  const [costEdit, setCostEdit] = useState<Sheet["costs"][number] | null>(null);
  const [syncOpen, setSyncOpen] = useState(false);
  const [pushing, setPushing] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  if (sheet.isLoading) return <LoadingState />;
  if (sheet.error || !sheet.data) return <ErrorMessage error={sheet.error instanceof Error ? sheet.error.message : "شیت خوانده نشد"} />;
  const data = sheet.data;
  const campaigns = focus ? data.campaigns.filter((row) => row.code === focus) : data.campaigns;
  const sms = focus ? data.sms.filter((row) => row.campaign_code === focus) : data.sms;
  const stories = focus ? data.stories.filter((row) => row.campaign_code === focus) : data.stories;
  const costs = focus ? data.costs.filter((row) => row.campaign_code === focus) : data.costs;

  function sync() {
    setPushing(true);
    perfApi.syncSheets().then((result) => {
      qc.invalidateQueries({ queryKey: ["perf"] });
      setSyncOpen(false);
      const s = result.sources ?? {};
      const counts = `دفتر کمپین ${toman(s.register ?? 0)} · هزینه ${toman(s.costs ?? 0)} · پیامک ${toman(s.sms ?? 0)} · سوشال ${toman(s.social ?? 0)}`;
      setOutcome({
        ok: result.pushed,
        title: result.pushed ? "ارسال به گوگل‌شیت موفق بود" : "ارسال به گوگل‌شیت ناموفق بود",
        detail: result.pushed
          ? `تب‌های شیت گزارش (پیامک، سوشال، ورودی، هزینه، گزارش) از نو نوشته شد.\nردیف تازه اضافه‌شده — ${counts}${result.reason ? `\n${result.reason}` : ""}${result.spreadsheet_url ? `\nشیت: ${result.spreadsheet_url}` : ""}`
          : (result.reason || "گوگل‌شیت وصل نیست و ارسال انجام نشد. وضعیت اتصال را در صفحهٔ اتصالات ببینید."),
      });
    }).catch((error: unknown) => {
      setPushing(false);
      setOutcome({ ok: false, title: "ارسال به گوگل‌شیت ناموفق بود", detail: exactError(error) });
    });
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Sheet" fa={focus ? `شیت ${focus}` : "شیت"} />}
        description={
          <>
            {data.google_connected
              ? <Bi en="Connected. A campaign goes to the register, a cost to the cost sheet, and SMS or social to the reporter." fa="وصل است. کمپین به دفتر شماره، هزینه به شیت هزینه، و پیامک و سوشال به ریپورتر می‌رود." />
              : <Bi en="Facts go to the sheet. The report is built from that sheet." fa="اطلاعات اول به شیت می‌رود. گزارش از روی همان شیت ساخته و به‌روز می‌شود." />}
            {data.spreadsheet_url ? <> · <a href={data.spreadsheet_url} target="_blank" rel="noreferrer"><Bi en="Open" fa="باز کردن گوگل‌شیت" /></a></> : null}
            {focus ? <> · <Link to="/perf/sheet"><Bi en="All rows" fa="همهٔ ردیف‌ها" /></Link></> : null}
          </>
        }
        actions={
          <div className="row">
            <Button type="button" variant="secondary" onClick={() => downloadPerf("/perf/excel/reporter", "reporter.xlsx")}><Bi en="Excel" fa="اکسل گزارش" /></Button>
            <Button type="button" variant="secondary" onClick={() => downloadPerf("/perf/excel/costs", "cost-tracking.xlsx")}><Bi en="Costs" fa="اکسل هزینه" /></Button>
            <Button type="button" onClick={() => setSyncOpen(true)}><Bi en="Push" fa="بفرست به گوگل‌شیت" /></Button>
          </div>
        }
      />
      <FoundTable
        icon="megaphone"
        title={<Bi en="Campaigns" fa="کمپین" />}
        rows={campaigns}
        rowKey={(row) => row.id}
        sorts={SHEET_CAMPAIGN_SORTS}
        facet={{ all: "همهٔ برندها", value: (row) => row.brand }}
        text={(row) => [row.code, row.title, row.brand]}
        columns={[
          { key: "code", header: "کد", render: (row) => <Link to={`/perf/campaigns/${row.id}`}>{row.code}</Link> },
          { key: "when", header: "تاریخ", className: "cell-nowrap", render: (row) => <CampaignSheetDate when={listedOn.get(row.code)} ready={register.isSuccess} meta={byCode.get(row.code)} /> },
          { key: "title", header: "عنوان", render: (row) => row.title },
          { key: "brand", header: "برند", render: (row) => row.brand },
          { key: "cost", header: "هزینه", render: (row) => toman(row.cost_toman) },
          { key: "leads", header: "ورودی", render: (row) => leadsLabel(row.leads) },
          { key: "cpl", header: "هزینه هر ورودی", render: (row) => toman(row.cpl) },
          {
            key: "actions",
            header: "",
            render: (row) => (
              <RowActions
                onEdit={() => { const full = byCode.get(row.code); if (full) setCampaignEdit(full); }}
                onDelete={() => void remove(`کمپین ${row.code}`, () => perfApi.deleteCampaign(row.id))}
              />
            ),
          },
        ]}
      />
      <FoundTable
        icon="message"
        title={<Bi en="SMS" fa="پیامک" />}
        extra={<Button variant="ghost" to={focus ? `/perf/sms?campaign=${encodeURIComponent(focus)}` : "/perf/sms"}><Bi en="Open" fa="باز کردن" /></Button>}
        rows={sms}
        rowKey={(row) => row.id}
        sorts={SMS_SORTS}
        scope={{ all: "همهٔ ارسال‌ها", cost: "فقط با هزینه", leads: "فقط با ورودی", pick: (row) => ({ cost: row.cost_toman, leads: row.leads }) }}
        text={(row) => [row.campaign_code]}
        columns={[
          { key: "code", header: "کمپین", render: (row) => <CampaignCode code={row.campaign_code} /> },
          { key: "when", header: "تاریخ", className: "cell-nowrap", render: (row) => <IsoDate value={row.sent_at} /> },
          { key: "n", header: "گیرنده", render: (row) => toman(row.recipient_count) },
          { key: "cost", header: "هزینه", render: (row) => toman(row.cost_toman) },
          { key: "del", header: "تحویل", render: (row) => toman(row.delivered_count) },
          { key: "leads", header: "ورودی", render: (row) => toman(row.leads) },
          {
            key: "actions",
            header: "",
            render: (row) => (
              <RowActions
                onEdit={() => setSmsEdit(row)}
                onDelete={() => void remove(`ارسال ${row.campaign_code || ""}`, () => perfApi.deleteSend(row.id))}
              />
            ),
          },
        ]}
      />
      <FoundTable
        icon="layers"
        title={<Bi en="Social" fa="سوشال" />}
        extra={<Button variant="ghost" to={focus && byCode.get(focus) ? `/perf/social?campaign=${byCode.get(focus)?.id}` : "/perf/social"}><Bi en="Social" fa="سوشال" /></Button>}
        rows={stories}
        rowKey={(row) => row.id}
        sorts={STORY_SORTS}
        facet={{ all: "همهٔ انواع", value: (row) => KIND_LABEL[row.kind || "story"] || row.kind || "" }}
        scope={{ all: "همهٔ قرارها", cost: "فقط با هزینه", leads: "فقط با ورودی", pick: (row) => ({ cost: row.cost_toman, leads: row.leads }) }}
        text={(row) => [row.campaign_code, row.page]}
        columns={[
          { key: "code", header: "کمپین", render: (row) => <CampaignCode code={row.campaign_code} /> },
          { key: "when", header: "تاریخ", className: "cell-nowrap", render: (row) => <IsoDate value={row.published_on} /> },
          { key: "page", header: "پیج", render: (row) => row.page },
          { key: "views", header: "نمایش", render: (row) => toman(row.views) },
          { key: "leads", header: "ورودی", render: (row) => toman(row.leads) },
          { key: "cpl", header: "هزینه هر ورودی", render: (row) => toman(row.cpl) },
          {
            key: "actions",
            header: "",
            render: (row) => (
              <RowActions
                onEdit={() => setStoryEdit(row)}
                onDelete={() => void remove(`قرار ${row.page || row.campaign_code || ""}`, () => perfApi.deleteStory(row.id))}
              />
            ),
          },
        ]}
      />
      <FoundTable
        icon="briefcase"
        title={<Bi en="Costs" fa="هزینه" />}
        extra={
          <div className="row">
            {data.google_connected ? <Badge tone="ok">گوگل‌شیت</Badge> : <Badge>شیت پنل</Badge>}
            <Button variant="ghost" to={focus && byCode.get(focus) ? `/perf/money?campaign=${byCode.get(focus)?.id}` : "/perf/money"}><Bi en="Costs" fa="هزینه‌ها" /></Button>
          </div>
        }
        rows={costs}
        rowKey={(row) => String(row.cost_number) + row.campaign_code}
        sorts={COST_SORTS}
        facet={{ all: "همهٔ برندها", value: (row) => row.brand }}
        text={(row) => [row.campaign_code, row.brand, row.detail, row.description, row.kind]}
        columns={[
          { key: "n", header: "شماره", render: (row) => row.cost_number },
          { key: "when", header: "تاریخ", className: "cell-nowrap", render: (row) => <IsoDate value={row.spent_on} /> },
          { key: "code", header: "کمپین", render: (row) => <CampaignCode code={row.campaign_code} /> },
          { key: "brand", header: "برند", render: (row) => row.brand },
          { key: "amount", header: "مبلغ", render: (row) => toman(row.amount_toman) },
          { key: "detail", header: "شرح", render: (row) => row.detail || row.description },
          {
            key: "actions",
            header: "",
            render: (row) => (
              <RowActions
                onEdit={() => setCostEdit(row)}
                onDelete={() => void remove(`هزینه ${row.cost_number}`, () => perfApi.deleteCost(row.id))}
              />
            ),
          },
        ]}
      />
      <Card>
        <SectionHeader icon="upload" title={<Bi en="Bring an old cost file" fa="آوردن فایل هزینهٔ قبلی" />} hint={<Bi en="Rows join this sheet." fa="ردیف‌ها به همین شیت می‌آیند." />} />
        <FilePick
          accept=".xlsx"
          label={<Bi en="Choose the cost file" fa="فایل هزینه" />}
          hint=".xlsx"
          onFile={(file) => {
            perfApi.importCosts(file).then((result) => {
              toast(`${result.added} ردیف به شیت آمد`);
              qc.invalidateQueries({ queryKey: ["perf"] });
            }).catch((error: Error) => toast(error.message));
          }}
        />
      </Card>
      {campaignEdit ? <CampaignEdit row={campaignEdit} onClose={() => setCampaignEdit(null)} /> : null}
      {smsEdit ? <SmsEdit row={smsEdit} onClose={() => setSmsEdit(null)} /> : null}
      {storyEdit ? <StoryEdit row={storyEdit} onClose={() => setStoryEdit(null)} /> : null}
      {costEdit ? <CostEdit row={costEdit} onClose={() => setCostEdit(null)} /> : null}
      {syncOpen ? (
        <SyncPop
          connected={data.google_connected}
          url={data.spreadsheet_url}
          busy={pushing}
          onPush={sync}
          onClose={() => !pushing && setSyncOpen(false)}
        />
      ) : null}
      <OutcomePop outcome={outcome} onClose={() => setOutcome(null)} />
    </>
  );
}

const SOURCE_LINES = [
  "تب‌های شیت گزارش خود پنل (پیامک، سوشال، ورودی، هزینه، گزارش) از نو نوشته می‌شود.",
  "ردیف‌های تازه به شیت‌های منبع اضافه می‌شود: دفتر شمارهٔ کمپین، شیت هزینه، پیامک ریپورتر، استوری اینستاگرام. ردیف‌های قبلی پاک نمی‌شوند.",
  "بعد از ارسال، آمار همین صفحه از روی شیت گوگل خوانده می‌شود.",
  "اگر گوگل وصل نباشد ارسال کامل انجام نمی‌شود و دلیلش در پنجرهٔ نتیجه نوشته می‌شود.",
];

function SyncPop({
  connected,
  url,
  busy,
  onPush,
  onClose,
}: {
  connected: boolean;
  url?: string;
  busy: boolean;
  onPush: () => void;
  onClose: () => void;
}) {
  const bi = useBi();
  const titleId = useId();
  return (
    <Dialog onClose={onClose} className="form-pop" labelledBy={titleId} closeLabel={bi("Close", "بستن")} busy={busy}>
        <SectionHeader
          icon="upload"
          title={<span id={titleId}><Bi en="Push to Google Sheets" fa="بفرست به گوگل‌شیت" /></span>}
          action={<button type="button" className="kpi-more" onClick={onClose}><Bi en="Close" fa="بستن" /></button>}
        />
        {connected ? (
          <p className="conn-note">
            گوگل وصل است
            {url ? <> · <a href={url} target="_blank" rel="noreferrer">باز کردن شیت</a></> : null}
            . با زدن دکمهٔ زیر ارسال شروع می‌شود و نتیجه در پنجرهٔ «موفق یا ناموفق» با جزئیات نشان داده می‌شود.
          </p>
        ) : (
          <ErrorMessage
            friendly={false}
            message="گوگل‌شیت وصل نیست. ارسال روی شیت گوگل انجام نمی‌شود؛ دلیل دقیق در پنجرهٔ نتیجه می‌آید. وضعیت را در صفحهٔ اتصالات چک کنید."
          />
        )}
        <ul className="sync-steps">
          {SOURCE_LINES.map((line) => <li key={line}>{line}</li>)}
        </ul>
        <div className="row perf-actions">
          <Button type="button" onClick={onPush} disabled={busy}>
            {busy ? <Bi en="Sending…" fa="در حال ارسال…" /> : <Bi en="Send now" fa="همین حالا بفرست" />}
          </Button>
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>
            <Bi en="Cancel" fa="بی‌خیال" />
          </Button>
        </div>
    </Dialog>
  );
}

const KIND_LABEL: Record<string, string> = { story: "استوری", post: "پست", banner: "بنر" };

function campaignOrder(code: string): number {
  const legacy = /-(\d+)$/.exec(code);
  if (legacy) return Number(legacy[1]);
  const current = /(\d+)$/.exec(code);
  return current ? Number(current[1]) : 0;
}

function CampaignSheetDate({ when, ready, meta }: { when: string | undefined; ready: boolean; meta: CampaignRow | undefined }) {
  if (!ready) return <>—</>;
  if (when) return <>{when}</>;
  if (meta?.starts_on) return <DateText value={meta.starts_on} />;
  if (when === undefined && meta?.created_at) return <DateText value={meta.created_at} />;
  return <>—</>;
}

function IsoDate({ value }: { value: string | null | undefined }) {
  if (!value) return <>—</>;
  return <DateText value={value} />;
}

const SHEET_CAMPAIGN_SORTS: SortOption<Sheet["campaigns"][number]>[] = [
  { key: "new", label: "جدیدترین", pick: (row) => campaignOrder(row.code), dir: "desc" },
  { key: "old", label: "قدیمی‌ترین", pick: (row) => campaignOrder(row.code), dir: "asc" },
  { key: "cost-desc", label: "بیشترین هزینه", pick: (row) => row.cost_toman || 0, dir: "desc" },
  { key: "cost-asc", label: "کمترین هزینه", pick: (row) => row.cost_toman || 0, dir: "asc" },
  { key: "leads-desc", label: "بیشترین ورودی", pick: (row) => row.leads || 0, dir: "desc" },
  { key: "cpl-asc", label: "کمترین هزینهٔ هر ورودی", pick: (row) => row.cpl, dir: "asc" },
  { key: "code", label: "کد", pick: (row) => row.code, dir: "asc" },
];

const SMS_SORTS: SortOption<Sheet["sms"][number]>[] = [
  { key: "new", label: "جدیدترین", pick: (row) => row.sent_at || "", dir: "desc" },
  { key: "old", label: "قدیمی‌ترین", pick: (row) => row.sent_at || "", dir: "asc" },
  { key: "cost-desc", label: "بیشترین هزینه", pick: (row) => row.cost_toman, dir: "desc" },
  { key: "n-desc", label: "بیشترین گیرنده", pick: (row) => row.recipient_count, dir: "desc" },
  { key: "del-desc", label: "بیشترین تحویل", pick: (row) => row.delivered_count, dir: "desc" },
  { key: "leads-desc", label: "بیشترین ورودی", pick: (row) => row.leads, dir: "desc" },
  { key: "code", label: "کد کمپین", pick: (row) => row.campaign_code, dir: "asc" },
];

const STORY_SORTS: SortOption<Sheet["stories"][number]>[] = [
  { key: "new", label: "جدیدترین", pick: (row) => row.published_on || "", dir: "desc" },
  { key: "old", label: "قدیمی‌ترین", pick: (row) => row.published_on || "", dir: "asc" },
  { key: "views-desc", label: "بیشترین نمایش", pick: (row) => row.views, dir: "desc" },
  { key: "leads-desc", label: "بیشترین ورودی", pick: (row) => row.leads, dir: "desc" },
  { key: "cost-desc", label: "بیشترین هزینه", pick: (row) => row.cost_toman, dir: "desc" },
  { key: "cpl-asc", label: "کمترین هزینهٔ هر ورودی", pick: (row) => row.cpl, dir: "asc" },
];

const COST_SORTS: SortOption<Sheet["costs"][number]>[] = [
  { key: "new", label: "جدیدترین", pick: (row) => row.spent_on || "", dir: "desc" },
  { key: "old", label: "قدیمی‌ترین", pick: (row) => row.spent_on || "", dir: "asc" },
  { key: "amount-desc", label: "بیشترین مبلغ", pick: (row) => row.amount_toman, dir: "desc" },
  { key: "amount-asc", label: "کمترین مبلغ", pick: (row) => row.amount_toman, dir: "asc" },
  { key: "number", label: "شماره", pick: (row) => row.cost_number, dir: "desc" },
  { key: "code", label: "کد کمپین", pick: (row) => row.campaign_code, dir: "asc" },
];

function FoundTable<T>({
  icon,
  title,
  extra,
  rows,
  rowKey,
  text,
  columns,
  sorts,
  facet,
  scope,
}: {
  icon: "megaphone" | "message" | "layers" | "briefcase";
  title: ReactNode;
  extra?: ReactNode;
  rows: T[];
  rowKey: (row: T) => string;
  text: (row: T) => Array<string | number | null | undefined>;
  columns: Array<{ key: string; header: string; className?: string; render: (row: T) => ReactNode }>;
  sorts: SortOption<T>[];
  facet?: { all: string; value: (row: T) => string };
  scope?: { all: string; cost: string; leads: string; pick: (row: T) => { cost?: number | null; leads?: number | null } };
}) {
  const [facetValue, setFacetValue] = useState("");
  const [scopeValue, setScopeValue] = useState("");
  const options = facet ? choices(rows, facet.value) : [];
  const narrowed = rows.filter((row) => {
    if (facet && facetValue && facet.value(row) !== facetValue) return false;
    if (scopeValue === "cost" && !(scope?.pick(row).cost || 0)) return false;
    if (scopeValue === "leads" && !(scope?.pick(row).leads || 0)) return false;
    return true;
  });
  const list = useArrange(narrowed, 10, sorts, text, `${facetValue}|${scopeValue}`);
  const dirty = Boolean(facetValue || scopeValue || list.searching || list.sortChanged);
  return (
    <Card>
      <SectionHeader icon={icon} title={title} count={list.ordered.length} action={extra} />
      <ArrangeBar
        query={list.query}
        onQuery={list.setQuery}
        placeholder="جستجو"
        sortKey={list.sortKey}
        onSort={list.setSortKey}
        sorts={list.sorts}
        onReset={dirty ? () => { setFacetValue(""); setScopeValue(""); list.resetSort(); } : undefined}
      >
        {facet ? (
          <Select aria-label={facet.all} value={facetValue} onChange={(event) => setFacetValue(event.target.value)}>
            <option value="">{facet.all}</option>
            {options.map((item) => <option key={item} value={item}>{item}</option>)}
          </Select>
        ) : null}
        {scope ? (
          <Select aria-label={scope.all} value={scopeValue} onChange={(event) => setScopeValue(event.target.value)}>
            <option value="">{scope.all}</option>
            <option value="cost">{scope.cost}</option>
            <option value="leads">{scope.leads}</option>
          </Select>
        ) : null}
      </ArrangeBar>
      {list.windowed.total === 0 ? <Muted as="p">با این فیلتر ردیفی نیست.</Muted> : <Table rows={list.windowed.rows} rowKey={rowKey} columns={columns} />}
      <ShowMore left={list.windowed.left} onMore={list.windowed.grow} />
    </Card>
  );
}
