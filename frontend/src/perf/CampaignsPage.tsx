import { useEffect, useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button, Card, Dialog, ErrorMessage, Field, ForbiddenState, Input, LoadingState, Muted, PageHeader, SectionHeader, Segmented, Select, Table } from "../components/ui";
import { isForbiddenError } from "../lib/apiError";
import { DateText } from "../components/DateText";
import { Bi, useBi } from "../i18n";
import { formatJalaliLong, formatJalaliText } from "../jalali";
import { useAuth } from "../auth";
import { canSeePerfApi } from "../lib/access";
import { tabFromParam, withTabParam } from "../lib/tabs";
import { leadsLabel, mizitoStatus, perfApi, toman, triageLabel, type CampaignRow, type MizitoMissing, type MizitoRequest, type MizitoTriageCard, type RegisterRow } from "./api";
import { ArrangeBar, choices, ShowMore, useArrange, type SortOption } from "./browse";
import { CampaignEdit, RowActions, useRemove } from "./edit";
import { CampaignCode, exactError, OutcomePop, type Outcome } from "./bits";
import { MizitoCardDialog, MizitoOpenButton, type MizitoCardLike } from "./MizitoCardDialog";
import { MizitoRequestsBlock } from "./MizitoRequests";
import { mizitoMissingQuery, mizitoRequestsQuery, mizitoTriageQuery } from "./mizitoQueries";

const CAMPAIGN_TABS = ["campaigns", "requests", "missing", "triage"] as const;
type CampaignTab = (typeof CAMPAIGN_TABS)[number];

export function CampaignsPage() {
  const bi = useBi();
  const { user, has } = useAuth();
  const accessUser = {
    roleCode: user?.roleCode,
    permissions: user?.permissions ?? [],
    teamId: user?.team_id,
    teamHomeTeamId: user?.team_home_team_id,
  };
  const perfOk = canSeePerfApi(accessUser, has);
  // تب در URL است (?tab=) تا با رفرش و دکمهٔ بازگشت بماند و بشود لینکش را فرستاد. تب کمپین‌ها پیش‌فرض است.
  const [params, setParams] = useSearchParams();
  const tab = tabFromParam(params.get("tab"), CAMPAIGN_TABS, "campaigns");
  const pickTab = (next: CampaignTab) => setParams((current) => withTabParam(current, next, "campaigns"), { replace: true });
  const rows = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns, enabled: perfOk });
  // شمارهٔ تب‌ها از همان کش محتوای تب‌ها؛ همه از دیتابیس پنل، بدون کال به میزیتو
  const requests = useQuery({ ...mizitoRequestsQuery("new"), enabled: perfOk });
  const missing = useQuery({ ...mizitoMissingQuery, enabled: perfOk });
  const triage = useQuery({ ...mizitoTriageQuery(null), enabled: perfOk });
  const undecided = (requests.data?.counts.new ?? 0) + (requests.data?.counts.duplicate ?? 0);
  const register = useQuery({ queryKey: ["perf", "register"], queryFn: perfApi.campaignRegister, enabled: perfOk });
  const listedOn = new Map([...(register.data?.rows ?? []), ...(register.data?.legacy ?? [])].map((row) => [row.code, row.when]));
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<MizitoRequest | null>(null);
  const [preset, setPreset] = useState<CampaignPreset | null>(null);
  const [book, setBook] = useState(false);
  const [brand, setBrand] = useState("");
  const [channel, setChannel] = useState("");
  const [scope, setScope] = useState("");
  const brands = choices(rows.data ?? [], (row) => row.brand);
  const narrowed = (rows.data ?? []).filter((row) => {
    if (brand && row.brand !== brand) return false;
    if (channel === "sms" && !row.channels.includes("sms")) return false;
    if (channel === "social" && !row.channels.includes("ig_story")) return false;
    if (scope === "cost" && !(row.cost_toman || 0)) return false;
    if (scope === "leads" && !(row.leads || 0)) return false;
    return true;
  });
  const list = useArrange(narrowed, 12, CAMPAIGN_SORTS, (row) => [row.code, row.title, row.brand, listedOn.get(row.code), formatJalaliText(listedOn.get(row.code))], `${brand}|${channel}|${scope}`);
  const filtered = list.ordered;

  // محتوای تب کمپین‌ها (همان جدول قبلی). متغیر است نه کامپوننت تو در تو تا فیلتر و جستجو با هر رندر از نو ساخته نشوند.
  const campaignsForbidden = rows.isError && isForbiddenError(rows.error);

  const campaignsTab = (
    <>
      {campaignsForbidden ? <ForbiddenState /> : null}
      {!campaignsForbidden && rows.isLoading ? <LoadingState /> : null}
      {!campaignsForbidden && rows.error ? (
        <ErrorMessage error={rows.error instanceof Error ? rows.error.message : String(rows.error)} />
      ) : null}
      {!campaignsForbidden && rows.data ? (
        <Card>
          <SectionHeader icon="megaphone" title={<Bi en="All campaigns" fa="همهٔ کمپین‌ها" />} count={filtered.length} />
          <ArrangeBar
            query={list.query}
            onQuery={list.setQuery}
            placeholder="کد، عنوان یا برند"
            sortKey={list.sortKey}
            onSort={list.setSortKey}
            sorts={list.sorts}
            onReset={brand || channel || scope || list.searching || list.sortChanged ? () => { setBrand(""); setChannel(""); setScope(""); list.resetSort(); } : undefined}
          >
            <Select aria-label="برند" value={brand} onChange={(event) => setBrand(event.target.value)}>
              <option value="">همهٔ برندها</option>
              {brands.map((item) => <option key={item} value={item}>{item}</option>)}
            </Select>
            <Select aria-label="کانال" value={channel} onChange={(event) => setChannel(event.target.value)}>
              <option value="">همهٔ کانال‌ها</option>
              <option value="sms">پیامک</option>
              <option value="social">سوشال</option>
            </Select>
            <Select aria-label="محدوده" value={scope} onChange={(event) => setScope(event.target.value)}>
              <option value="">همهٔ ردیف‌ها</option>
              <option value="cost">فقط با هزینه</option>
              <option value="leads">فقط با ورودی</option>
            </Select>
          </ArrangeBar>
          {list.windowed.total === 0 ? <Muted as="p">با این فیلتر کمپینی نیست.</Muted> : <CampaignTable rows={list.windowed.rows} listedOn={listedOn} datesReady={register.isSuccess} />}
          <ShowMore left={list.windowed.left} onMore={list.windowed.grow} />
        </Card>
      ) : null}
    </>
  );

  if (!perfOk) return <ForbiddenState />;

  return (
    <>
      <PageHeader
        title={<Bi en="Performance campaigns" fa="کمپین پرفورمنس" />}
        description={<Bi en="Each row is one perf campaign (not a conversation topic). SMS and social stay inside it." fa="هر ردیف یک کمپین پرفورمنس است (نه «موضوع گفتگو» در پیام‌ها). پیامک و سوشال داخل همان می‌مانند." />}
        actions={
          <div className="row">
            <Button type="button" variant="secondary" onClick={() => setBook(true)}>
              <Bi en="Number book" fa="دفتر شماره" />
            </Button>
            <Button type="button" onClick={() => setOpen(true)}>
              <Bi en="New campaign" fa="کمپین تازه" />
            </Button>
          </div>
        }
      />
      <Segmented<CampaignTab>
        idBase="campaigns"
        ariaLabel={bi("Campaign sections", "بخش‌های صفحهٔ کمپین‌ها")}
        value={tab}
        onChange={pickTab}
        items={[
          { key: "campaigns", label: <Bi en="Campaign list" fa="فهرست کمپین" />, count: rows.data?.length },
          {
            key: "requests",
            label: <Bi en="Mizito ads" fa="درخواست تبلیغ (میزیتو)" />,
            count: requests.data ? undecided : undefined,
            attention: undecided > 0,
            attentionLabel: bi("undecided Mizito requests", "درخواست میزیتو تصمیم‌نگرفته"),
          },
          { key: "missing", label: <Bi en="Missing codes" fa="کدهای جاافتاده" />, count: missing.data?.codes.length },
          { key: "triage", label: <Bi en="Needs attention" fa="رسیدگی" />, count: triage.data?.read_at ? triage.data.total : undefined },
        ]}
      />
      {CAMPAIGN_TABS.map((key) => (
        <div key={key} role="tabpanel" id={`campaigns-panel-${key}`} aria-labelledby={`campaigns-tab-${key}`} className="campaign-tabpanel" hidden={tab !== key}>
          {tab !== key ? null : key === "requests" ? (
            <MizitoRequestsBlock onCreate={setDraft} />
          ) : key === "missing" ? (
            <MizitoMissingCodes onCreate={setPreset} />
          ) : key === "triage" ? (
            <MizitoTriage />
          ) : (
            campaignsTab
          )}
        </div>
      ))}
      {book ? <RegisterPop onClose={() => setBook(false)} /> : null}
      {open ? <NewCampaignPop onClose={() => setOpen(false)} /> : null}
      {draft ? <NewCampaignPop draft={draft} onClose={() => setDraft(null)} /> : null}
      {preset ? <NewCampaignPop preset={preset} onClose={() => setPreset(null)} /> : null}
    </>
  );
}

const TRIAGE_FLAGS = ["no_code", "stuck", "no_assignee", "overdue"];
const TRIAGE_DAYS = [7, 14, 30, 60, 90];

function MizitoTriage() {
  const [days, setDays] = useState<number | null>(null);
  const [all, setAll] = useState(false);
  const [openCard, setOpenCard] = useState<{ card: MizitoCardLike; flags: string[] } | null>(null);
  const triage = useQuery(mizitoTriageQuery(days));
  const data = triage.data;
  if (triage.isLoading) return <LoadingState />;
  if (triage.error) return <ErrorMessage error={triage.error instanceof Error ? triage.error.message : String(triage.error)} />;
  if (!data || !data.read_at) {
    return (
      <Card>
        <SectionHeader icon="alert" title={<Bi en="Cards that need attention" fa="کارت‌هایی که رسیدگی می‌خواهند" />} />
        <Muted as="p">هنوز از میزیتو خوانده نشده است. بعد از «به‌روز از میزیتو» در صفحهٔ هزینه‌ها، کارت‌های نیازمند رسیدگی اینجا می‌آیند.</Muted>
      </Card>
    );
  }
  const shown = all ? data.cards : data.cards.slice(0, 8);
  const open = (row: MizitoTriageCard) => setOpenCard({
    card: { id: row.id, title: row.title, project: row.project, board: row.board, status: row.status, code: row.code, modified_at: row.modified_at, deadline: row.deadline },
    flags: row.flags,
  });
  const choices = TRIAGE_DAYS.includes(data.days) ? TRIAGE_DAYS : [...TRIAGE_DAYS, data.days].sort((a, b) => a - b);
  return (
    <Card>
      <SectionHeader
        icon="alert"
        title={<Bi en="Cards that need attention" fa="کارت‌هایی که رسیدگی می‌خواهند" />}
        count={data.total}
        hint={<Bi en="Active Mizito cards from the last read: no campaign code (performance and campaign projects only), no change for a long time, no assignee, or past deadline. Most flags first." fa="کارت‌های فعال میزیتو از آخرین خواندن: بدون کد (فقط پرفورمنس و کمپین)، مدت زیاد بدون تغییر، بدون مسئول یا مهلت گذشته. بیشترین پرچم اول، بعد قدیمی‌ترین." />}
        action={
          <Select aria-label="روز بدون تغییر" value={String(data.days)} onChange={(event) => { setDays(Number(event.target.value)); setAll(false); }}>
            {choices.map((item) => <option key={item} value={item}>{toman(item)} روز</option>)}
          </Select>
        }
      />
      <p className="muted">
        {TRIAGE_FLAGS.map((flag, index) => (
          <span key={flag}>{index ? " · " : null}{triageLabel(flag, data.days)}: {toman(data.counts[flag] ?? 0)}</span>
        ))}
        {` · از ${toman(data.checked)} کارت فعال`}
      </p>
      {data.cards.length === 0 ? <Muted as="p">کارت فعالی پرچم ندارد.</Muted> : (
        <Table
          rows={shown}
          rowKey={(row: MizitoTriageCard) => row.id || `${row.project}|${row.board}|${row.title}`}
          onRowClick={open}
          columns={[
            { key: "code", header: "کمپین", className: "cell-nowrap", render: (row: MizitoTriageCard) => <CampaignCode code={row.code} /> },
            { key: "title", header: "کارت", render: (row: MizitoTriageCard) => <MizitoOpenButton title={row.title} onOpen={() => open(row)} /> },
            {
              key: "flags",
              header: "پرچم",
              render: (row: MizitoTriageCard) => (
                <span className="perf-chips">
                  {row.flags.map((flag) => <span key={flag} className="perf-chip">{triageLabel(flag, data.days)}</span>)}
                </span>
              ),
            },
            { key: "idle", header: "روز بدون تغییر", className: "cell-nowrap", render: (row: MizitoTriageCard) => (row.days_since_change != null ? toman(row.days_since_change) : "—") },
            { key: "project", header: "پروژه", className: "hide-sm", render: (row: MizitoTriageCard) => row.project || "—" },
            { key: "board", header: "برد", className: "hide-sm", render: (row: MizitoTriageCard) => row.board || "—" },
          ]}
        />
      )}
      <ShowMore left={data.cards.length - shown.length} onMore={() => setAll(true)} />
      {openCard ? <MizitoCardDialog card={openCard.card} flags={openCard.flags} onClose={() => setOpenCard(null)} /> : null}
    </Card>
  );
}

type MissingRow = MizitoMissing["codes"][number];

type CampaignPreset = { code: string; title: string; tag: string };

function tagOf(code: string): string {
  return (/^[A-Za-z]+/.exec(code)?.[0] || "S").toUpperCase();
}

function MizitoMissingCodes({ onCreate }: { onCreate: (preset: CampaignPreset) => void }) {
  const missing = useQuery(mizitoMissingQuery);
  const [all, setAll] = useState(false);
  const [openCard, setOpenCard] = useState<MizitoCardLike | null>(null);
  const rows = missing.data?.codes ?? [];
  if (missing.isLoading) return <LoadingState />;
  if (missing.error) return <ErrorMessage error={missing.error instanceof Error ? missing.error.message : String(missing.error)} />;
  if (!rows.length) {
    return (
      <Card>
        <SectionHeader icon="briefcase" title={<Bi en="In Mizito, not in the panel" fa="در میزیتو هست، در پنل نیست" />} />
        <Muted as="p">
          {missing.data?.read_at ? "هر کد کمپینی که در کارت‌های میزیتو هست، در پنل هم کمپین دارد." : "هنوز از میزیتو خوانده نشده است؛ کدهای جاافتاده بعد از اولین خواندن اینجا می‌آیند."}
        </Muted>
      </Card>
    );
  }
  const shown = all ? rows : rows.slice(0, 8);
  return (
    <Card>
      <SectionHeader
        icon="briefcase"
        title={<Bi en="In Mizito, not in the panel" fa="در میزیتو هست، در پنل نیست" />}
        count={rows.length}
        hint={<Bi en="Campaign codes in Mizito card titles with no campaign here. From the last Mizito read; nothing is created automatically." fa="کدهای کمپین که در عنوان کارت‌های میزیتو هستند ولی کمپینی با آن کد در پنل نیست. از آخرین خواندن میزیتو؛ چیزی خودکار ساخته نمی‌شود." />}
      />
      <Table
        rows={shown}
        rowKey={(row: MissingRow) => row.code}
        onRowClick={(row: MissingRow) => setOpenCard(row)}
        columns={[
          { key: "code", header: "کد", className: "cell-nowrap", render: (row: MissingRow) => row.code },
          { key: "title", header: "کارت", render: (row: MissingRow) => <MizitoOpenButton title={row.title} onOpen={() => setOpenCard(row)} /> },
          { key: "project", header: "پروژه", className: "hide-sm", render: (row: MissingRow) => row.project || "—" },
          {
            key: "status",
            header: "وضعیت",
            render: (row: MissingRow) => (
              <>
                {mizitoStatus(row)}
                {row.completed ? <span className="muted"> · تکمیل‌شده</span> : null}
              </>
            ),
          },
          { key: "cards", header: "کارت‌ها", className: "hide-sm", render: (row: MissingRow) => toman(row.cards) },
          { key: "modified", header: "آخرین تغییر", className: "cell-nowrap", render: (row: MissingRow) => (row.modified_at ? <DateText value={row.modified_at} /> : "—") },
          {
            key: "make",
            header: "",
            render: (row: MissingRow) => (
              <Button
                type="button"
                className="btn-sm"
                onClick={(event) => {
                  event.stopPropagation();
                  onCreate({ code: row.code, title: row.title, tag: tagOf(row.code) });
                }}
              >
                ساخت در پنل
              </Button>
            ),
          },
        ]}
      />
      <ShowMore left={rows.length - shown.length} onMore={() => setAll(true)} />
      {openCard ? <MizitoCardDialog card={openCard} onClose={() => setOpenCard(null)} /> : null}
    </Card>
  );
}

function RegisterPop({ onClose }: { onClose: () => void }) {
  const bi = useBi();
  const book = useQuery({ queryKey: ["perf", "register"], queryFn: perfApi.campaignRegister });
  const [which, setWhich] = useState<"rows" | "legacy">("rows");
  const [brand, setBrand] = useState("");
  const titleId = useId();
  const source = book.data?.[which] ?? [];
  const brands = choices(source, (row) => row.brand);
  const narrowed = source.filter((row) => !brand || row.brand === brand);
  const list = useArrange(narrowed, 12, REGISTER_SORTS, (row) => [row.code, row.title, row.brand, row.when], `${which}|${brand}`);
  return (
    <Dialog onClose={onClose} labelledBy={titleId} closeLabel={bi("Close", "بستن")}>
        <SectionHeader
          title={<span id={titleId}><Bi en="Number book" fa="دفتر شماره" /></span>}
          action={<button type="button" className="kpi-more" onClick={onClose}><Bi en="Close" fa="بستن" /></button>}
        />
        <div className="segmented" role="group">
          <button type="button" className={which === "rows" ? "seg active" : "seg"} onClick={() => setWhich("rows")}>فعلی</button>
          <button type="button" className={which === "legacy" ? "seg active" : "seg"} onClick={() => setWhich("legacy")}>قدیمی</button>
        </div>
        <ArrangeBar
          query={list.query}
          onQuery={list.setQuery}
          placeholder="کد یا موضوع"
          sortKey={list.sortKey}
          onSort={list.setSortKey}
          sorts={list.sorts}
          onReset={brand || list.searching || list.sortChanged ? () => { setBrand(""); list.resetSort(); } : undefined}
        >
          <Select aria-label="برند" value={brand} onChange={(event) => setBrand(event.target.value)}>
            <option value="">همهٔ برندها</option>
            {brands.map((item) => <option key={item} value={item}>{item}</option>)}
          </Select>
        </ArrangeBar>
        {list.windowed.total === 0 ? <Muted as="p">با این فیلتر کدی نیست.</Muted> : <RegisterTable rows={list.windowed.rows} />}
        <ShowMore left={list.windowed.left} onMore={list.windowed.grow} />
    </Dialog>
  );
}

const CHANNEL_LABEL: Record<string, string> = {
  sms: "پیامک",
  ig_story: "سوشال",
  lbs: "پیامک منطقه‌ای",
  divar: "دیوار",
  google: "گوگل",
  native: "همسان و ویدیو",
  banner: "بنر",
  influencer: "بلاگر",
  landing: "لندینگ",
};

const CAMPAIGN_SORTS: SortOption<CampaignRow>[] = [
  { key: "new", label: "جدیدترین", pick: (row) => campaignOrder(row.code), dir: "desc" },
  { key: "old", label: "قدیمی‌ترین", pick: (row) => campaignOrder(row.code), dir: "asc" },
  { key: "cost-desc", label: "بیشترین هزینه", pick: (row) => row.cost_toman || 0, dir: "desc" },
  { key: "cost-asc", label: "کمترین هزینه", pick: (row) => row.cost_toman || 0, dir: "asc" },
  { key: "leads-desc", label: "بیشترین ورودی", pick: (row) => row.leads || 0, dir: "desc" },
  { key: "cpl-asc", label: "کمترین هزینهٔ هر ورودی", pick: (row) => row.cpl, dir: "asc" },
  { key: "code", label: "کد", pick: (row) => row.code, dir: "asc" },
  { key: "title", label: "عنوان", pick: (row) => row.title, dir: "asc" },
];

const REGISTER_SORTS: SortOption<RegisterRow>[] = [
  { key: "seq-desc", label: "جدیدترین شماره", pick: (row) => row.seq, dir: "desc" },
  { key: "seq-asc", label: "قدیمی‌ترین شماره", pick: (row) => row.seq, dir: "asc" },
  { key: "code", label: "کد", pick: (row) => row.code, dir: "asc" },
  { key: "when", label: "تاریخ", pick: (row) => row.when, dir: "desc" },
];

function RegisterTable({ rows }: { rows: RegisterRow[] }) {
  return (
    <Table
      rows={rows}
      rowKey={(row) => row.code}
      columns={[
        { key: "code", header: "کد", render: (row: RegisterRow) => row.code },
        { key: "title", header: "موضوع", render: (row) => row.title || "—" },
        { key: "brand", header: "برند", render: (row) => row.brand || row.tag },
        { key: "when", header: "تاریخ", className: "cell-nowrap", render: (row) => formatJalaliText(row.when) || "—" },
      ]}
    />
  );
}

function ChannelChips({ channels }: { channels: string[] }) {
  const shown = channels.slice(0, 3);
  const rest = channels.length - shown.length;
  if (!shown.length) return <>—</>;
  return (
    <span className="perf-chips">
      {shown.map((item) => <span key={item} className="perf-chip">{CHANNEL_LABEL[item] || item}</span>)}
      {rest > 0 ? <span className="muted" dir="ltr">+{toman(rest)}</span> : null}
    </span>
  );
}

function campaignOrder(code: string): number {
  const legacy = /-(\d+)$/.exec(code);
  if (legacy) return Number(legacy[1]);
  const current = /(\d+)$/.exec(code);
  return current ? Number(current[1]) : 0;
}

/**
 * ستون تاریخ همیشه یک شکل دارد: «۱۳ مهر ۱۴۰۵».
 * تاریخ دفتر شماره (متن شیت، معمولاً بی‌سال مثل «31 شهریور») هم به همین شکل درمی‌آید؛
 * سالی که در شیت نیست حدس زده نمی‌شود.
 */
function CampaignDate({ row, when, ready }: { row: CampaignRow; when: string | undefined; ready: boolean }) {
  if (!ready) return <>—</>;
  if (when) return <>{formatJalaliText(when)}</>;
  if (row.starts_on) return <>{formatJalaliLong(row.starts_on) ?? "—"}</>;
  if (when === undefined && row.created_at) return <>{formatJalaliLong(row.created_at) ?? "—"}</>;
  return <>—</>;
}

function CampaignTable({ rows, listedOn, datesReady }: { rows: CampaignRow[]; listedOn: Map<string, string>; datesReady: boolean }) {
  const navigate = useNavigate();
  const remove = useRemove();
  const [edit, setEdit] = useState<CampaignRow | null>(null);
  return (
    <>
    <Table
      rows={rows}
      rowKey={(row) => row.id}
      onRowClick={(row) => navigate(`/perf/campaigns/${row.id}`)}
      columns={[
        { key: "code", header: "کد", className: "cell-nowrap", render: (row: CampaignRow) => <Link to={`/perf/campaigns/${row.id}`}>{row.code}</Link> },
        { key: "title", header: "عنوان", render: (row) => <span className="cell-clamp">{row.title}</span> },
        { key: "when", header: "تاریخ", className: "cell-nowrap", render: (row) => <CampaignDate row={row} when={listedOn.get(row.code)} ready={datesReady} /> },
        { key: "brand", header: "برند", className: "hide-sm cell-nowrap", render: (row) => row.brand },
        { key: "channels", header: "کانال", className: "hide-sm", render: (row) => <ChannelChips channels={row.channels} /> },
        { key: "cost", header: "هزینه", render: (row) => toman(row.cost_toman) },
        { key: "leads", header: "ورودی", render: (row) => leadsLabel(row.leads) },
        { key: "cpl", header: "هزینه هر ورودی", className: "hide-sm", render: (row) => toman(row.cpl) },
        {
          key: "actions",
          header: "",
          className: "col-actions",
          render: (row) => (
            <RowActions
              onEdit={() => setEdit(row)}
              onDelete={() => void remove(`کمپین ${row.code}`, () => perfApi.deleteCampaign(row.id))}
            />
          ),
        },
      ]}
    />
    {edit ? <CampaignEdit row={edit} onClose={() => setEdit(null)} /> : null}
    </>
  );
}

const PANEL_CHANNELS = ["sms", "ig_story"];

/** فرم «کمپین تازه». با draft از درخواست میزیتو پر می‌شود و با تایید همان درخواست کمپین را می‌سازد. */
function NewCampaignPop({ onClose, draft, preset }: { onClose: () => void; draft?: MizitoRequest; preset?: CampaignPreset }) {
  const bi = useBi();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [madeId, setMadeId] = useState<string | null>(null);
  const book = useQuery({ queryKey: ["perf", "register"], queryFn: perfApi.campaignRegister });
  const hint = draft?.suggested;
  const [title, setTitle] = useState(preset?.title || hint?.title || "");
  const [tag, setTag] = useState(preset?.tag || hint?.tag || "S");
  const [brand, setBrand] = useState(hint?.brand || "ترکیبی");
  const [channels, setChannels] = useState<string[]>(() => {
    const picked = (hint?.channels ?? []).filter((item) => PANEL_CHANNELS.includes(item));
    return picked.length ? picked : ["sms"];
  });
  const titleId = useId();
  const create = useMutation({
    mutationFn: () =>
      draft
        ? perfApi.approveMizitoRequest(draft.id, { title, brand, tag, channels }).then((result) => result.campaign)
        : perfApi.createCampaign({ code: preset?.code || "", title, brand, tag, channels, status: "active" }),
    onSuccess: (row) => {
      qc.invalidateQueries({ queryKey: ["perf"] });
      setMadeId(row.id);
      setOutcome({
        ok: true,
        title: "ساخت کمپین موفق بود",
        detail: `کمپین ${row.code} ساخته شد.\nوضعیت: ${row.status === "active" ? "فعال" : row.status}.\nبا بستن این پنجره به صفحهٔ همان کمپین می‌روید.`,
      });
    },
    onError: (error: unknown) => setOutcome({ ok: false, title: "ساخت کمپین ناموفق بود", detail: exactError(error) }),
  });

  function toggle(channel: string) {
    setChannels((current) =>
      current.includes(channel) ? current.filter((item) => item !== channel) : [...current, channel],
    );
  }

  useEffect(() => {
    if (!preset) return;
    const found = book.data?.tags.find((item) => item.tag === preset.tag);
    if (found) setBrand(found.brand);
  }, [book.data, preset]);

  return (
    <>
      <Dialog
        onClose={onClose}
        className="form-pop"
        labelledBy={titleId}
        closeLabel={bi("Close", "بستن")}
        busy={create.isPending}
        as="form"
        onSubmit={(event) => {
          event.preventDefault();
          if (title.trim() && channels.length) create.mutate();
        }}
      >
        <SectionHeader
          icon="plus"
          title={
            <span id={titleId}>
              {preset ? <Bi en="Campaign from a Mizito code" fa="کمپین با کد میزیتو" /> : draft ? <Bi en="Campaign from a Mizito request" fa="کمپین از درخواست میزیتو" /> : <Bi en="New campaign" fa="کمپین تازه" />}
            </span>
          }
          action={<button type="button" className="kpi-more" onClick={onClose}><Bi en="Close" fa="بستن" /></button>}
        />
        {draft?.excerpt ? <p className="mizito-request-excerpt">{draft.excerpt}</p> : null}
        <Field label={<Bi en="Title" fa="عنوان" />}>
          <Input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label={<Bi en="Brand letter" fa="حرف برند" />}>
          <Select
            value={tag}
            disabled={Boolean(preset)}
            onChange={(event) => {
              const next = event.target.value;
              setTag(next);
              const found = book.data?.tags.find((item) => item.tag === next);
              if (found) setBrand(found.brand);
            }}
          >
            {((book.data?.tags ?? [{ tag: "S", brand: "ترکیبی" }]).some((item) => item.tag === tag)
              ? (book.data?.tags ?? [{ tag: "S", brand: "ترکیبی" }])
              : [{ tag, brand: tag }, ...(book.data?.tags ?? [])]
            ).map((item) => (
              <option key={item.tag} value={item.tag}>{item.tag} — {item.brand}</option>
            ))}
          </Select>
        </Field>
        <Muted as="p">{preset ? `با همین کد ${preset.code} ساخته می‌شود.` : `کد بعدی ${tag}${book.data?.next ?? ""}`}</Muted>
        <Field label={<Bi en="Brand" fa="برند" />}>
          <Input value={brand} onChange={(e) => setBrand(e.target.value)} />
        </Field>
        <div className="segmented" role="group">
          <button type="button" className={channels.includes("sms") ? "seg active" : "seg"} onClick={() => toggle("sms")}>
            <Bi en="SMS" fa="پیامک" />
          </button>
          <button type="button" className={channels.includes("ig_story") ? "seg active" : "seg"} onClick={() => toggle("ig_story")}>
            <Bi en="Social" fa="سوشال" />
          </button>
        </div>
        <Button type="submit" disabled={!title.trim() || channels.length === 0 || create.isPending}>
          <Bi en="Create" fa="ساخت کمپین" />
        </Button>
      </Dialog>
      <OutcomePop
        outcome={outcome}
        onClose={() => {
          setOutcome(null);
          if (madeId) navigate(`/perf/campaigns/${madeId}`);
        }}
      />
    </>
  );
}
