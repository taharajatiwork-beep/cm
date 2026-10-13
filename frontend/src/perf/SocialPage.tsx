import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Badge, Button, Card, Dialog, ErrorMessage, Field, ForbiddenState, Input, Muted, PageHeader, SectionHeader, Segmented, Select, Table, TextArea } from "../components/ui";
import { isForbiddenError } from "../lib/apiError";
import { DateText } from "../components/DateText";
import { useToast } from "../components/ui/Toast";
import { Bi, useBi } from "../i18n";
import { perfApi, toman, type PageRow, type Story } from "./api";
import { FileButton, RelatedLinks } from "./bits";
import { ArrangeBar, hit, ShowMore, useArrange, type SortOption } from "./browse";
import { PageEdit, RowActions, StoryEdit, useRemove } from "./edit";

type Kind = "story" | "post" | "banner";

const KINDS: Array<{ key: Kind; en: string; fa: string }> = [
  { key: "story", en: "Story", fa: "استوری" },
  { key: "post", en: "Post", fa: "پست" },
  { key: "banner", en: "Banner", fa: "بنر" },
];

const PAY: Record<string, string> = {
  requested: "منتظر مالی",
  manager_ok: "منتظر مالی",
  finance_ok: "منتظر مالی",
  paid: "پرداخت شد",
  recorded: "پرداخت شد",
  rejected: "رد شد",
};

const PAGE_CATALOG_SORTS: SortOption<PageRow>[] = [
  { key: "price-desc", label: "گران‌ترین", pick: (row) => row.price_toman, dir: "desc" },
  { key: "price-asc", label: "ارزان‌ترین", pick: (row) => row.price_toman, dir: "asc" },
  { key: "cpl-asc", label: "کمترین هزینهٔ هر ورودی", pick: (row) => row.cpl, dir: "asc" },
  { key: "followers", label: "بیشترین دنبال‌کننده", pick: (row) => row.followers, dir: "desc" },
  { key: "name", label: "اسم", pick: (row) => row.name, dir: "asc" },
];

const PLACE_SORTS: SortOption<Story>[] = [
  { key: "views-desc", label: "بیشترین نمایش", pick: (row) => row.views, dir: "desc" },
  { key: "leads-desc", label: "بیشترین ورودی", pick: (row) => row.leads, dir: "desc" },
  { key: "cost-desc", label: "بیشترین مبلغ", pick: (row) => row.cost_toman, dir: "desc" },
  { key: "cpl-asc", label: "کمترین هزینهٔ هر ورودی", pick: (row) => row.cpl, dir: "asc" },
  { key: "date", label: "جدیدترین تاریخ", pick: (row) => row.published_on || "", dir: "desc" },
  { key: "page", label: "اسم پیج", pick: (row) => row.page, dir: "asc" },
];

function PageCatalog() {
  const qc = useQueryClient();
  const toast = useToast();
  const pages = useQuery({ queryKey: ["perf", "pages"], queryFn: perfApi.pages });
  const [name, setName] = useState("");
  const [topic, setTopic] = useState("");
  const [contact, setContact] = useState("");
  const [price, setPrice] = useState("");
  const [editId, setEditId] = useState("");
  const [nextPrice, setNextPrice] = useState("");
  const [adding, setAdding] = useState(false);
  const [pricing, setPricing] = useState(false);
  const [priceQuery, setPriceQuery] = useState("");
  const add = useMutation({
    mutationFn: () => perfApi.createPage({ name, topic, contact, price_toman: price === "" ? 0 : Number(price) }),
    onSuccess: () => {
      toast("پیج به فهرست اضافه شد");
      setName("");
      setTopic("");
      setContact("");
      setPrice("");
      qc.invalidateQueries({ queryKey: ["perf", "pages"] });
    },
    onError: (error: Error) => toast(error.message),
  });
  const savePrice = useMutation({
    mutationFn: () => perfApi.updatePage(editId, { price_toman: nextPrice === "" ? 0 : Number(nextPrice) }),
    onSuccess: () => {
      toast("قیمت پیج عوض شد");
      qc.invalidateQueries({ queryKey: ["perf", "pages"] });
    },
    onError: (error: Error) => toast(error.message),
  });
  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState("price");
  const narrowed = (pages.data ?? []).filter((row) => {
    if (scope === "price" && !row.price_toman) return false;
    if (scope === "leads" && row.cpl == null) return false;
    return true;
  });
  const list = useArrange(narrowed, 8, PAGE_CATALOG_SORTS, (row) => [row.name, row.topic, row.contact], scope);
  return (
    <>
      <SectionHeader
        title={<Bi en="Pages" fa="فهرست پیج" />}
        hint={<Bi en="Shared by every campaign." fa="برای همهٔ کمپین‌ها یکی است." />}
        count={list.ordered.length}
        action={
          <div className="perf-head-actions">
            <Button type="button" variant="secondary" onClick={() => setPricing(true)}>
              <Bi en="Change a price" fa="تغییر قیمت" />
            </Button>
            <Button type="button" variant="ghost" onClick={() => setOpen((value) => !value)}>
              {open ? <Bi en="Hide" fa="جمع کردن" /> : <Bi en="Show" fa="نمایش فهرست" />}
            </Button>
            <Button type="button" onClick={() => setAdding(true)}>
              <Bi en="Add a page" fa="افزودن پیج" />
            </Button>
          </div>
        }
      />
      {open ? (
      <ArrangeBar
        query={list.query}
        onQuery={list.setQuery}
        placeholder="اسم پیج یا موضوع"
        sortKey={list.sortKey}
        onSort={list.setSortKey}
        sorts={list.sorts}
        onReset={scope !== "price" || list.searching || list.sortChanged ? () => { setScope("price"); list.resetSort(); } : undefined}
      >
        <Select aria-label="محدوده" value={scope} onChange={(event) => setScope(event.target.value)}>
          <option value="">همهٔ پیج‌ها</option>
          <option value="price">فقط با قیمت</option>
          <option value="leads">فقط با ورودی</option>
        </Select>
      </ArrangeBar>
      ) : <Muted as="p"><Bi en="The list is shared. Priced pages are shown when you open it." fa="فهرست برای همهٔ کمپین‌ها یکی است. با باز کردن، اول پیج‌های قیمت‌دار می‌آید." /></Muted>}
      {open && list.windowed.total ? (
        <PageTable rows={list.windowed.rows} />
      ) : open ? (
        <Muted as="p"><Bi en="No pages yet." fa="پیجی با این فیلتر نیست." /></Muted>
      ) : null}
      {open ? <ShowMore left={list.windowed.left} onMore={list.windowed.grow} /> : null}
      {adding ? (
        <FormPop title={<Bi en="Add a page" fa="افزودن پیج" />} onClose={() => setAdding(false)}>
          <Field label={<Bi en="Name" fa="اسم" />}><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label={<Bi en="Topic" fa="موضوع" />}><Input value={topic} onChange={(e) => setTopic(e.target.value)} /></Field>
          <Field label={<Bi en="Contact" fa="مخاطب" />}><Input value={contact} onChange={(e) => setContact(e.target.value)} /></Field>
          <Field label={<Bi en="Price (toman)" fa="قیمت (تومان)" />}><Input inputMode="numeric" value={price} onChange={(e) => setPrice(e.target.value.replace(/[^\d]/g, ""))} /></Field>
          <Button type="button" disabled={!name.trim() || add.isPending} onClick={() => add.mutate(undefined, { onSuccess: () => setAdding(false) })}>
            <Bi en="Add page" fa="افزودن" />
          </Button>
        </FormPop>
      ) : null}
      {pricing ? (
        <FormPop title={<Bi en="Change a price" fa="تغییر قیمت" />} onClose={() => setPricing(false)}>
          <Field label={<Bi en="Page" fa="پیج" />}>
            <Input value={priceQuery} placeholder="جستجوی پیج" onChange={(event) => setPriceQuery(event.target.value)} />
            <Select value={editId} onChange={(e) => {
              const id = e.target.value;
              setEditId(id);
              const row = (pages.data ?? []).find((item) => item.id === id);
              setNextPrice(row?.price_toman ? String(row.price_toman) : "");
            }}>
              <option value="">—</option>
              {(pages.data ?? []).filter((row) => hit(priceQuery, row.name)).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </Select>
          </Field>
          <Field label={<Bi en="New price" fa="قیمت جدید" />}>
            <Input inputMode="numeric" value={nextPrice} onChange={(e) => setNextPrice(e.target.value.replace(/[^\d]/g, ""))} />
          </Field>
          <Button type="button" variant="secondary" disabled={!editId || savePrice.isPending} onClick={() => savePrice.mutate(undefined, { onSuccess: () => setPricing(false) })}>
            <Bi en="Save price" fa="ذخیره" />
          </Button>
        </FormPop>
      ) : null}
    </>
  );
}

function FormPop({ title, onClose, children }: { title: ReactNode; onClose: () => void; children: ReactNode }) {
  const bi = useBi();
  const titleId = useId();
  return (
    <Dialog onClose={onClose} className="form-pop" labelledBy={titleId} closeLabel={bi("Close", "بستن")}>
      <SectionHeader
        title={<span id={titleId}>{title}</span>}
        action={<button type="button" className="kpi-more" onClick={onClose}><Bi en="Close" fa="بستن" /></button>}
      />
      {children}
    </Dialog>
  );
}

function PageTable({ rows }: { rows: PageRow[] }) {
  const remove = useRemove();
  const [edit, setEdit] = useState<PageRow | null>(null);
  return (
    <>
      <Table
        rows={rows}
        rowKey={(row) => row.id}
        columns={[
          { key: "name", header: "پیج", render: (row) => row.name },
          { key: "topic", header: "موضوع", render: (row) => row.topic || "—" },
          { key: "price", header: "قیمت", className: "perf-num", render: (row) => toman(row.price_toman) },
          { key: "cpl", header: "هر ورودی", className: "perf-num", render: (row) => row.cpl != null ? toman(row.cpl) : "—" },
          { key: "contact", header: "مخاطب", render: (row) => row.contact || "—" },
          {
            key: "actions",
            header: "",
            render: (row) => <RowActions onEdit={() => setEdit(row)} onDelete={() => void remove(`پیج ${row.name}`, () => perfApi.deletePage(row.id))} />,
          },
        ]}
      />
      {edit ? <PageEdit row={edit} onClose={() => setEdit(null)} /> : null}
    </>
  );
}

function CarLines({ rows }: { rows: Array<{ id: string; summary: string; raw_text: string; brand: string }> }) {
  const remove = useRemove();
  return (
    <ul className="perf-cars">
      {rows.map((row) => (
        <li key={row.id}>
          <span>{row.summary || row.raw_text}{row.brand ? ` · ${row.brand}` : ""}</span>
          <button type="button" className="perf-chip-x" onClick={() => void remove(row.summary || "ماشین", () => perfApi.deleteRequest(row.id))} aria-label="حذف">×</button>
        </li>
      ))}
    </ul>
  );
}

function KindPane({ campaignId, kind, label, focus }: { campaignId: string; kind: Kind; label: string; focus?: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const stories = useQuery({ queryKey: ["perf", "stories"], queryFn: perfApi.stories });
  const pages = useQuery({ queryKey: ["perf", "pages"], queryFn: perfApi.pages });
  const [pageId, setPageId] = useState("");
  const [pageQuery, setPageQuery] = useState("");
  const [pay, setPay] = useState("");
  const [adding, setAdding] = useState(false);
  const add = useMutation({
    mutationFn: () => perfApi.createStory({ campaign_id: campaignId, page_id: pageId, kind }),
    onSuccess: (row) => {
      toast(row.payment_id ? "قرار ثبت شد و درخواست پرداخت برای مالی رفت" : "قرار بدون مبلغ ثبت شد");
      setPageId("");
      setAdding(false);
      qc.invalidateQueries({ queryKey: ["perf"] });
    },
    onError: (error: Error) => toast(error.message),
  });
  const owned = (stories.data ?? []).filter((row) => row.campaign_id === campaignId && (row.kind || "story") === kind);
  useEffect(() => {
    if (focus === "insight") setPay("published");
    if (focus === "publish") setPay("waiting");
  }, [focus]);
  const narrowed = owned.filter((row) => {
    if (pay === "published") return row.status === "published";
    if (pay === "waiting") return row.status !== "published";
    return true;
  });
  const list = useArrange(narrowed, 6, PLACE_SORTS, (row) => [row.page, row.payment_status], pay);
  const matched = (pages.data ?? []).filter((row) => (pageQuery ? hit(pageQuery, row.name) : row.price_toman > 0));
  const sliced = matched.slice(0, 40);
  const picked = (pages.data ?? []).find((row) => row.id === pageId);
  const pageOptions = picked && !sliced.some((row) => row.id === picked.id) ? [picked, ...sliced] : sliced;
  return (
    <>
      <ArrangeBar
        query={list.query}
        onQuery={list.setQuery}
        placeholder="جستجو در قرارها"
        sortKey={list.sortKey}
        onSort={list.setSortKey}
        sorts={list.sorts}
        onReset={pay || list.searching || list.sortChanged ? () => { setPay(""); list.resetSort(); } : undefined}
      >
        <Select aria-label="وضعیت" value={pay} onChange={(event) => setPay(event.target.value)}>
          <option value="">همه</option>
          <option value="published">منتشر شده</option>
          <option value="waiting">هنوز منتشر نشده</option>
        </Select>
        <Button type="button" onClick={() => setAdding(true)}>قرار {label}</Button>
      </ArrangeBar>
      {owned.length === 0 ? (
        <Muted as="p">{`هنوز ${label}ی برای این کمپین نیست.`}</Muted>
      ) : list.windowed.total === 0 ? (
        <Muted as="p">{`با این فیلتر ${label}ی نیست.`}</Muted>
      ) : (
        <PlacementTable rows={list.windowed.rows} focus={focus} candidates={owned} />
      )}
      <ShowMore left={list.windowed.left} onMore={list.windowed.grow} />
      {adding ? (
        <FormPop title={`قرار ${label}`} onClose={() => setAdding(false)}>
          <Field label={<Bi en="Page" fa="پیج" />}>
            <Input value={pageQuery} placeholder="جستجوی پیج" onChange={(event) => setPageQuery(event.target.value)} />
            <Select value={pageId} onChange={(e) => setPageId(e.target.value)}>
              <option value="">—</option>
              {pageOptions.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} · {toman(row.price_toman)}
                  {row.cpl != null ? ` · هر ورودی ${toman(row.cpl)}` : ""}
                </option>
              ))}
            </Select>
            {matched.length > pageOptions.length ? <Muted as="p">{toman(matched.length - pageOptions.length)} پیج دیگر؛ اسم را جستجو کنید.</Muted> : null}
          </Field>
          <Button type="button" disabled={!pageId || add.isPending} onClick={() => add.mutate()}>
            ثبت
          </Button>
        </FormPop>
      ) : null}
    </>
  );
}

function PlacementTable({ rows, readonly, focus, candidates }: { rows: Story[]; readonly?: boolean; focus?: string; candidates?: Story[] }) {
  const remove = useRemove();
  const [numbers, setNumbers] = useState<Story | null>(null);
  const [edit, setEdit] = useState<Story | null>(null);
  const opened = useRef("");
  useEffect(() => {
    if (readonly || !focus || opened.current === focus) return;
    const pool = candidates?.length ? candidates : rows;
    const row = focus === "insight"
      ? pool.find((item) => item.status === "published" && !item.views && !item.leads)
      : focus === "publish"
        ? pool.find((item) => item.status !== "published")
        : undefined;
    if (!row) return;
    opened.current = focus;
    setNumbers(row);
  }, [readonly, focus, candidates, rows]);
  return (
    <>
      <Table
        rows={rows}
        rowKey={(row) => row.id}
        columns={[
          { key: "page", header: "پیج", render: (row) => row.page || "—" },
          { key: "when", header: "تاریخ", className: "cell-nowrap", render: (row) => row.published_on ? <DateText value={row.published_on} /> : "—" },
          { key: "cost", header: "مبلغ", className: "perf-num", render: (row) => toman(row.cost_toman) },
          { key: "views", header: "نمایش", className: "perf-num", render: (row) => toman(row.views) },
          { key: "leads", header: "ورودی", className: "perf-num", render: (row) => toman(row.leads) },
          { key: "cpl", header: "هر ورودی", className: "perf-num", render: (row) => toman(row.cpl) },
          {
            key: "status",
            header: "وضعیت",
            render: (row) => row.status === "published"
              ? <Badge tone="ok">منتشر شده</Badge>
              : <Badge tone="warn">{row.payment_status ? (PAY[row.payment_status] || "وضعیت نامشخص") : "قرار"}</Badge>,
          },
          {
            key: "actions",
            header: "",
            className: "col-actions",
            render: (row) => (
              <div className="row-actions">
                {readonly ? null : (
                  <Button type="button" variant="secondary" className="btn-sm" onClick={() => setNumbers(row)}>
                    {row.status === "published" ? "اصلاح عددها" : "منتشر شد"}
                  </Button>
                )}
                <RowActions onEdit={() => setEdit(row)} onDelete={() => void remove(`قرار ${row.page || ""}`, () => perfApi.deleteStory(row.id))} />
              </div>
            ),
          },
        ]}
      />
      {numbers && !readonly ? <NumbersPop row={numbers} onClose={() => setNumbers(null)} /> : null}
      {edit ? <StoryEdit row={edit} onClose={() => setEdit(null)} /> : null}
    </>
  );
}

function NumbersPop({ row, onClose }: { row: Story; onClose: () => void }) {
  const bi = useBi();
  const titleId = useId();
  return (
    <Dialog onClose={onClose} className="form-pop" labelledBy={titleId} closeLabel={bi("Close", "بستن")}>
      <SectionHeader
        icon="check"
        title={<span id={titleId}>{row.page || "پیج"}</span>}
        action={<button type="button" className="kpi-more" onClick={onClose}><Bi en="Close" fa="بستن" /></button>}
      />
      <Publish row={row} onDone={onClose} />
    </Dialog>
  );
}

function Publish({ row, onDone }: { row: Story; onDone?: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [day, setDay] = useState(row.published_on || "");
  const [views, setViews] = useState(row.views ? String(row.views) : "");
  const [leads, setLeads] = useState(row.leads ? String(row.leads) : "");
  const save = useMutation({
    mutationFn: () =>
      perfApi.publishStory(row.id, {
        published_on: day || null,
        views: views === "" ? null : Number(views),
        leads: leads === "" ? null : Number(leads),
      }),
    onSuccess: () => {
      toast(row.status === "published" ? "عددها ذخیره شد" : "منتشر شد");
      qc.invalidateQueries({ queryKey: ["perf"] });
      onDone?.();
    },
    onError: (error: Error) => toast(error.message),
  });
  return (
    <div className="form-grid">
      <Field label={<Bi en="Date" fa="تاریخ" />}><Input type="date" value={day} onChange={(e) => setDay(e.target.value)} /></Field>
      <Field label={<Bi en="Views" fa="نمایش" />}><Input type="number" value={views} onChange={(e) => setViews(e.target.value)} /></Field>
      <Field label={<Bi en="Leads" fa="ورودی" />}><Input type="number" value={leads} onChange={(e) => setLeads(e.target.value)} /></Field>
      <div className="perf-actions">
        <Button type="button" variant="secondary" disabled={save.isPending} onClick={() => save.mutate()}>
          {row.status === "published" ? "ذخیره" : "منتشر شد"}
        </Button>
        {row.status === "published" ? (
          <FileButton
            accept=".xlsx,image/*"
            label={<Bi en="Read file" fa="خواندن فایل" />}
            onFile={(file) => {
              perfApi.insight(row.id, file).then((result) => {
                toast(result.ok ? (result.source === "file" ? "عددها از فایل خوانده شد" : "عددها از تصویر خوانده شد") : (result.reason || "عدد خوانده نشد"));
                if (result.ok) qc.invalidateQueries({ queryKey: ["perf"] });
              }).catch((error: Error) => toast(error.message));
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

export function SocialFlowPage() {
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("campaign") || "";
  const step = params.get("step") || "";
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const campaignsForbidden = campaigns.isError && isForbiddenError(campaigns.error);
  const campaign = (campaigns.data ?? []).find((row) => row.id === fromUrl || row.code === fromUrl);
  const campaignId = campaign?.id || "";
  const [query, setQuery] = useState("");
  if (campaignsForbidden) {
    return (
      <div className="perf-social">
        <PageHeader
          title={<Bi en="Social" fa="سوشال" />}
          description={
            <Bi
              en="The manager lists the cars. Performance sets a budget. Pages and cost follow from that budget."
              fa="مدیر ماشین‌ها را می‌دهد. بودجه را اینجا می‌گذارید. پیج و هزینه از همان بودجه درمی‌آید."
            />
          }
        />
        <ForbiddenState />
      </div>
    );
  }
  return (
    <div className="perf-social">
      <PageHeader
        title={<Bi en="Social" fa="سوشال" />}
        description={<Bi en="The manager lists the cars. Performance sets a budget. Pages and cost follow from that budget." fa="مدیر ماشین‌ها را می‌دهد. بودجه را اینجا می‌گذارید. پیج و هزینه از همان بودجه درمی‌آید." />}
        actions={campaign ? <RelatedLinks id={campaign.id} code={campaign.code} here="social" /> : null}
      />
      <ErrorMessage error={campaigns.isError ? campaigns.error : null} />
      <Card>
        <div className="perf-pick">
          <Field label={<Bi en="Find" fa="جستجو" />}>
            <Input value={query} placeholder="کد یا عنوان" onChange={(event) => setQuery(event.target.value)} />
          </Field>
          <Field label={<Bi en="Campaign" fa="کمپین" />}>
            <Select
              value={campaignId}
              onChange={(event) => {
                const next = event.target.value;
                setParams(next ? { campaign: next } : {}, { replace: true });
              }}
            >
              <option value="">—</option>
              {(campaigns.data ?? []).filter((row) => row.id === campaignId || hit(query, row.code, row.title)).map((row) => (
                <option key={row.id} value={row.id}>{row.code} — {row.title}</option>
              ))}
            </Select>
          </Field>
        </div>
      </Card>
      {campaign ? <SocialSteps campaignId={campaign.id} budgetToman={campaign.budget_toman} step={step} /> : (
        <Muted as="p"><Bi en="Pick the campaign these cars belong to." fa="اول کمپینی را انتخاب کنید که این ماشین‌ها برای آن هستند." /></Muted>
      )}
    </div>
  );
}

function SocialSteps({ campaignId, budgetToman, step }: { campaignId: string; budgetToman: number | null; step?: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const requests = useQuery({ queryKey: ["perf", "requests"], queryFn: perfApi.requests });
  const stories = useQuery({ queryKey: ["perf", "stories"], queryFn: perfApi.stories });
  const [cars, setCars] = useState("");
  const [budget, setBudget] = useState(budgetToman ? String(budgetToman) : "");
  const [kind, setKind] = useState<Kind>("story");
  const label = KINDS.find((item) => item.key === kind)!;
  useEffect(() => {
    setBudget(budgetToman ? String(budgetToman) : "");
  }, [campaignId, budgetToman]);
  const mine = (requests.data ?? []).filter((row) => row.campaign_id === campaignId);
  const saveCars = useMutation({
    mutationFn: async () => {
      const lines = cars.split(/\n+/).map((line) => line.trim()).filter(Boolean);
      for (const line of lines) await perfApi.createRequest(line, campaignId);
      return lines.length;
    },
    onSuccess: (count) => {
      toast(`${toman(count)} ماشین ثبت شد`);
      setCars("");
      qc.invalidateQueries({ queryKey: ["perf", "requests"] });
    },
    onError: (error: Error) => toast(error.message),
  });
  const suggest = useMutation({
    mutationFn: () => perfApi.suggest(Number(budget) || 0),
    onError: (error: Error) => toast(error.message),
  });
  const saveBudget = useMutation({
    mutationFn: () => perfApi.patchCampaign(campaignId, { budget_toman: Number(budget) || 0 }),
    onSuccess: () => {
      toast("بودجه ذخیره شد");
      qc.invalidateQueries({ queryKey: ["perf", "campaigns"] });
      if ((Number(budget) || 0) > 0) suggest.mutate();
    },
    onError: (error: Error) => toast(error.message),
  });
  const laidOut = useRef("");
  useEffect(() => {
    const amount = budgetToman || 0;
    if (!stories.data || amount <= 0 || laidOut.current === campaignId) return;
    const booked = stories.data.some((row) => row.campaign_id === campaignId);
    if (booked) return;
    laidOut.current = campaignId;
    suggest.mutate();
  }, [campaignId, budgetToman, stories.data, suggest]);
  const book = useMutation({
    mutationFn: async () => {
      const pages = suggest.data?.pages ?? [];
      const taken = new Set(
        (stories.data ?? [])
          .filter((row) => row.campaign_id === campaignId && (row.kind || "story") === kind)
          .map((row) => row.page),
      );
      let added = 0;
      for (const page of pages) {
        if (taken.has(page.name)) continue;
        await perfApi.createStory({ campaign_id: campaignId, page_id: page.id, kind });
        added += 1;
      }
      await Promise.all(mine.filter((row) => row.status === "new").map((row) => perfApi.patchRequest(row.id, { status: "planned" })));
      return added;
    },
    onSuccess: (added) => {
      toast(added ? `${toman(added)} قرار ثبت شد و برای هر کدام درخواست پرداخت رفت` : "این پیج‌ها از قبل قرار دارند");
      qc.invalidateQueries({ queryKey: ["perf"] });
    },
    onError: (error: Error) => toast(error.message),
  });
  const picked = suggest.data?.pages ?? [];
  const spend = picked.reduce((sum, row) => sum + (row.price_toman || 0), 0);
  const amount = Number(budget) || 0;
  return (
    <div className="perf-social-flow">
      <div className="perf-social-top">
        <Card>
          <SectionHeader
            title={<Bi en="1. Cars" fa="۱. ماشین‌ها" />}
            hint={<Bi en="One car per line, as the manager sent them." fa="هر خط یک ماشین، همان‌طور که مدیر فرستاده." />}
            count={mine.length}
          />
          <Field label={<Bi en="List" fa="لیست" />}>
            <TextArea value={cars} rows={4} placeholder={"تیگو ۸\nلاماری ایما"} onChange={(event) => setCars(event.target.value)} />
          </Field>
          <div className="perf-actions">
            <Button type="button" disabled={!cars.trim() || saveCars.isPending} onClick={() => saveCars.mutate()}>
              <Bi en="Save the list" fa="ثبت لیست" />
            </Button>
          </div>
          {mine.length ? <CarLines rows={mine} /> : null}
        </Card>
        <Card>
          <SectionHeader
            title={<Bi en="2. Budget" fa="۲. بودجه" />}
            hint={<Bi en="This is the toman cap for the pages below." fa="سقف تومان برای پیج‌های پایین است." />}
          />
          <div className="perf-plan perf-plan-cap">
            <Field label={<Bi en="Budget (toman)" fa="بودجه (تومان)" />}>
              <Input type="number" value={budget} placeholder="۰" onChange={(event) => setBudget(event.target.value)} />
            </Field>
            <Button type="button" variant="secondary" disabled={amount <= 0 || saveBudget.isPending} onClick={() => saveBudget.mutate()}>
              <Bi en="Save budget" fa="ذخیره بودجه" />
            </Button>
          </div>
        </Card>
      </div>
      <Card>
        <SectionHeader
          title={<Bi en="3. Pages and cost" fa="۳. پیج و هزینه" />}
          hint={<Bi en="Pages are filled from the cheapest cost per lead until the budget runs out. Booking each page asks finance to pay." fa="پیج‌ها از ارزان‌ترین هزینهٔ هر ورودی تا تمام شدن بودجه چیده می‌شوند. ثبت هر پیج برای مالی درخواست پرداخت می‌سازد." />}
        />
        <Segmented
          value={kind}
          onChange={setKind}
          items={KINDS.map((item) => ({ key: item.key, label: <Bi en={item.en} fa={item.fa} /> }))}
        />
        <div className="perf-actions">
          <Button type="button" disabled={amount <= 0 || suggest.isPending} onClick={() => suggest.mutate()}>
            <Bi en="Lay out the pages" fa="چیدن پیج‌ها" />
          </Button>
          {picked.length ? (
            <Button type="button" variant="secondary" disabled={book.isPending} onClick={() => book.mutate()}>
              <Bi en="Book these pages" fa="ثبت این قرارها" />
            </Button>
          ) : null}
        </div>
        {suggest.data ? (
          picked.length ? (
            <>
              <p className="muted perf-readout">{toman(picked.length)} پیج · جمع {toman(spend)} تومان · باقی‌مانده {toman(suggest.data.remaining_toman)}</p>
              <ul className="perf-suggest-list">
                {picked.map((row) => (
                  <li key={row.id}>
                    <b>{row.name}</b>
                    <span className="perf-num">{toman(row.price_toman)}</span>
                    <span className="muted">{row.cpl != null ? `هر ورودی ${toman(row.cpl)}` : "بدون ورودی"}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : <Muted as="p"><Bi en="Nothing fits this budget." fa="با این بودجه پیجی جا نمی‌شود." /></Muted>
        ) : null}
      </Card>
      <Card>
        <SectionHeader title={`${label.fa}‌های این کمپین`} hint={<Bi en="Publish and post stats stay here." fa="انتشار و آمار پست همین‌جا ثبت می‌شود." />} />
        <KindPane campaignId={campaignId} kind={kind} label={label.fa} focus={step} />
      </Card>
      <Card>
        <PageCatalog />
      </Card>
    </div>
  );
}
