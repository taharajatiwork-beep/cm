import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Button, Card, ErrorMessage, Field, Input, LoadingState, Muted, PageHeader, SectionHeader, Select, Table } from "../components/ui";
import { DateText } from "../components/DateText";
import { useToast } from "../components/ui/Toast";
import { Bi, useBi } from "../i18n";
import { leadsLabel, perfApi, toman, type CampaignRow, type RegisterRow } from "./api";
import { ArrangeBar, choices, ShowMore, useArrange, type SortOption } from "./browse";
import { CampaignEdit, RowActions, useRemove } from "./edit";

export function CampaignsPage() {
  const rows = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const register = useQuery({ queryKey: ["perf", "register"], queryFn: perfApi.campaignRegister });
  const listedOn = new Map([...(register.data?.rows ?? []), ...(register.data?.legacy ?? [])].map((row) => [row.code, row.when]));
  const [open, setOpen] = useState(false);
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
  const list = useArrange(narrowed, 12, CAMPAIGN_SORTS, (row) => [row.code, row.title, row.brand, listedOn.get(row.code)], `${brand}|${channel}|${scope}`);
  const filtered = list.ordered;

  return (
    <>
      <PageHeader
        title={<Bi en="Campaigns" fa="کمپین‌ها" />}
        description={<Bi en="Each row is one campaign. SMS and social stay inside it." fa="هر ردیف یک کمپین است. پیامک و سوشال داخل همان می‌مانند." />}
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
      {rows.isLoading ? <LoadingState /> : null}
      {rows.error ? <ErrorMessage error={rows.error instanceof Error ? rows.error.message : String(rows.error)} /> : null}
      {rows.data ? (
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
      {book ? <RegisterPop onClose={() => setBook(false)} /> : null}
      {open ? <NewCampaignPop onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function RegisterPop({ onClose }: { onClose: () => void }) {
  const bi = useBi();
  const book = useQuery({ queryKey: ["perf", "register"], queryFn: perfApi.campaignRegister });
  const [which, setWhich] = useState<"rows" | "legacy">("rows");
  const [brand, setBrand] = useState("");
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const source = book.data?.[which] ?? [];
  const brands = choices(source, (row) => row.brand);
  const narrowed = source.filter((row) => !brand || row.brand === brand);
  const list = useArrange(narrowed, 12, REGISTER_SORTS, (row) => [row.code, row.title, row.brand, row.when], `${which}|${brand}`);
  return (
    <div className="detail-pop" role="dialog" aria-modal="true">
      <button type="button" className="detail-pop-backdrop" onClick={onClose} aria-label={bi("Close", "بستن")} />
      <div className="detail-pop-card">
        <SectionHeader
          title={<Bi en="Number book" fa="دفتر شماره" />}
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
      </div>
    </div>
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
        { key: "when", header: "تاریخ", render: (row) => row.when || "—" },
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

function CampaignDate({ row, when, ready }: { row: CampaignRow; when: string | undefined; ready: boolean }) {
  if (!ready) return <>—</>;
  if (when) return <>{when}</>;
  if (row.starts_on) return <DateText value={row.starts_on} />;
  if (when === undefined && row.created_at) return <DateText value={row.created_at} />;
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
        { key: "cpl", header: "CPL", className: "hide-sm", render: (row) => toman(row.cpl) },
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

function NewCampaignPop({ onClose }: { onClose: () => void }) {
  const bi = useBi();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const book = useQuery({ queryKey: ["perf", "register"], queryFn: perfApi.campaignRegister });
  const [title, setTitle] = useState("");
  const [tag, setTag] = useState("S");
  const [brand, setBrand] = useState("ترکیبی");
  const [channels, setChannels] = useState<string[]>(["sms"]);
  const create = useMutation({
    mutationFn: () => perfApi.createCampaign({ title, brand, tag, channels, status: "active" }),
    onSuccess: (row) => {
      toast("کمپین ساخته شد");
      qc.invalidateQueries({ queryKey: ["perf"] });
      navigate(`/perf/campaigns/${row.id}`);
    },
    onError: (error: Error) => toast(error.message),
  });

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function toggle(channel: string) {
    setChannels((current) =>
      current.includes(channel) ? current.filter((item) => item !== channel) : [...current, channel],
    );
  }

  return (
    <div className="detail-pop form-pop" role="dialog" aria-modal="true" aria-labelledby="new-campaign-title">
      <button type="button" className="detail-pop-backdrop" onClick={onClose} aria-label={bi("Close", "بستن")} />
      <form
        className="detail-pop-card"
        onSubmit={(event) => {
          event.preventDefault();
          if (title.trim() && channels.length) create.mutate();
        }}
      >
        <SectionHeader
          icon="plus"
          title={<span id="new-campaign-title"><Bi en="New campaign" fa="کمپین تازه" /></span>}
          action={<button type="button" className="kpi-more" onClick={onClose}><Bi en="Close" fa="بستن" /></button>}
        />
        <Field label={<Bi en="Title" fa="عنوان" />}>
          <Input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label={<Bi en="Brand letter" fa="حرف برند" />}>
          <Select
            value={tag}
            onChange={(event) => {
              const next = event.target.value;
              setTag(next);
              const found = book.data?.tags.find((item) => item.tag === next);
              if (found) setBrand(found.brand);
            }}
          >
            {(book.data?.tags ?? [{ tag: "S", brand: "ترکیبی" }]).map((item) => (
              <option key={item.tag} value={item.tag}>{item.tag} — {item.brand}</option>
            ))}
          </Select>
        </Field>
        <Muted as="p">کد بعدی {tag}{book.data?.next ?? ""}</Muted>
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
      </form>
    </div>
  );
}
