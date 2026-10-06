import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth";
import { Badge, Button, Card, ErrorMessage, Field, Input, LoadingState, Muted, PageHeader, SectionHeader, Select, Table } from "../components/ui";
import { DateText } from "../components/DateText";
import { useToast } from "../components/ui/Toast";
import { Bi } from "../i18n";
import { perfApi, toman, type CampaignRow, type MizitoCard, type Payment } from "./api";
import { ArrangeBar, hit, ShowMore, useArrange, type SortOption } from "./browse";
import { useRemove } from "./edit";

const KIND: Record<string, string> = {
  panel_charge: "شارژ پنل",
  story: "سوشال",
  other: "سایر",
};

const CENTERS = ["پرفورمنس", "دفتر مرکزی", "شعبه فروش مرزداران", "شعبه فروش ایرانمال", "شعبه فروش کاشانی", "کلیه شعب"];

const STATUS: Record<string, string> = {
  requested: "درخواست",
  manager_ok: "تأیید مدیر",
  finance_ok: "تأیید مالی",
  paid: "پرداخت شد",
  recorded: "ثبت شد",
  rejected: "رد شد",
};

export function MoneyPage() {
  const [params] = useSearchParams();
  const { has, user } = useAuth();
  const canFinance = !!user?.permissions.includes("price.write");
  const qc = useQueryClient();
  const toast = useToast();
  const payments = useQuery({ queryKey: ["perf", "payments"], queryFn: perfApi.payments });
  const panels = useQuery({ queryKey: ["perf", "panels"], queryFn: perfApi.panels });
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const [kind, setKind] = useState("panel_charge");
  const pages = useQuery({ queryKey: ["perf", "pages"], queryFn: perfApi.pages, enabled: kind === "story" });
  const [amount, setAmount] = useState(0);
  const [beneficiary, setBeneficiary] = useState("");
  const [iban, setIban] = useState("");
  const [panelId, setPanelId] = useState("");
  const [pageId, setPageId] = useState("");
  const [campaignId, setCampaignId] = useState(params.get("campaign") || "");
  const [open, setOpen] = useState(Boolean(params.get("campaign")));
  const [center, setCenter] = useState("پرفورمنس");
  const [campaignQuery, setCampaignQuery] = useState("");
  const create = useMutation({
    mutationFn: () =>
      perfApi.createPayment({
        kind,
        amount_toman: amount,
        beneficiary,
        iban,
        panel_id: kind === "panel_charge" ? panelId || null : null,
        campaign_id: campaignId || null,
        cost_center: center,
      }),
    onSuccess: () => {
      toast("درخواست ثبت شد");
      qc.invalidateQueries({ queryKey: ["perf"] });
    },
    onError: (error: Error) => toast(error.message),
  });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) => perfApi.advance(id, action),
    onSuccess: () => {
      toast("پرداخت ثبت شد");
      qc.invalidateQueries({ queryKey: ["perf"] });
    },
    onError: (error: Error) => toast(error.message),
  });

  return (
    <>
      <PageHeader
        title={<Bi en="Money" fa="پول" />}
        description={<Bi en="Panel top-ups and social costs are requested here. Finance approves and pays here." fa="شارژ پنل و هزینهٔ سوشال همین‌جا درخواست می‌شود. مالی همین‌جا تأیید و پرداخت می‌کند." />}
        actions={
          <div className="row">
            <Button variant="secondary" to="/perf/sheet"><Bi en="Sheet" fa="شیت" /></Button>
            <Button variant="secondary" to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Button>
            {has("perf.write") ? <Button type="button" onClick={() => setOpen((value) => !value)}><Bi en="New request" fa="درخواست تازه" /></Button> : null}
          </div>
        }
      />
      {has("perf.write") && open ? (
        <Card>
          <SectionHeader
            icon="briefcase"
            title={<Bi en="New request" fa="درخواست تازه" />}
            hint={<Bi en="Finance pays this request here. A panel top-up increases the balance. A social cost enters the campaign." fa="مالی همین درخواست را همین‌جا پرداخت می‌کند. شارژ پنل مانده را زیاد می‌کند و هزینهٔ سوشال در کمپین می‌آید." />}
          />
          <div className="form-grid">
            <Field label={<Bi en="Type" fa="نوع" />}>
              <Select value={kind} onChange={(e) => {
                const next = e.target.value;
                if (next !== "panel_charge") setPanelId("");
                if (next !== "story") setPageId("");
                setKind(next);
              }}>
                <option value="panel_charge">شارژ پنل</option>
                <option value="story">سوشال</option>
                <option value="other">سایر</option>
              </Select>
            </Field>
            <Field label={<Bi en="Amount (toman)" fa="مبلغ (تومان)" />}>
              <Input type="number" value={amount} onChange={(e) => setAmount(Number(e.target.value))} />
            </Field>
            {kind === "panel_charge" ? (
              <Field label={<Bi en="Panel" fa="پنل" />}>
                <Select value={panelId} onChange={(e) => {
                  const id = e.target.value;
                  setPanelId(id);
                  const panel = (panels.data ?? []).find((row) => row.id === id);
                  if (panel) setBeneficiary(panel.name);
                }}>
                  <option value="">—</option>
                  {(panels.data ?? []).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                </Select>
              </Field>
            ) : null}
            {kind === "story" ? (
              <Field label={<Bi en="Page" fa="پیج" />}>
                <Select value={pageId} onChange={(e) => {
                  const id = e.target.value;
                  setPageId(id);
                  const page = (pages.data ?? []).find((row) => row.id === id);
                  if (page) {
                    setBeneficiary(page.name);
                    if (page.price_toman) setAmount(page.price_toman);
                  }
                }}>
                  <option value="">—</option>
                  {(pages.data ?? []).map((row) => (
                    <option key={row.id} value={row.id}>{row.name} · {toman(row.price_toman)}</option>
                  ))}
                </Select>
              </Field>
            ) : null}
            <Field label={<Bi en="Campaign" fa="کمپین" />}>
              <Input value={campaignQuery} placeholder="جستجوی کد" onChange={(event) => setCampaignQuery(event.target.value)} />
              <Select value={campaignId} onChange={(e) => setCampaignId(e.target.value)}>
                <option value="">—</option>
                {(campaigns.data ?? []).filter((row) => row.id === campaignId || hit(campaignQuery, row.code, row.title)).map((row) => <option key={row.id} value={row.id}>{row.code}</option>)}
              </Select>
            </Field>
            <div className="span-all perf-actions">
              <Button type="button" disabled={amount <= 0 || create.isPending || (kind === "story" && !pageId)} onClick={() => create.mutate()}>
                <Bi en="Request" fa="ثبت درخواست" />
              </Button>
              <Button variant="ghost" to="/perf/sheet"><Bi en="It lands on the sheet" fa="روی شیت دیده می‌شود" /></Button>
            </div>
            <details className="span-all">
              <summary className="muted"><Bi en="Beneficiary and IBAN" fa="ذی‌نفع و شبا" /></summary>
              <div className="form-grid">
                <Field label={<Bi en="Beneficiary" fa="ذی‌نفع" />}><Input value={beneficiary} onChange={(e) => setBeneficiary(e.target.value)} /></Field>
                <Field label={<Bi en="IBAN" fa="شبا" />}><Input value={iban} onChange={(e) => setIban(e.target.value)} /></Field>
                <Field label={<Bi en="Cost center" fa="مرکز هزینه" />}>
                  <Select value={center} onChange={(e) => setCenter(e.target.value)}>
                    {CENTERS.map((item) => <option key={item} value={item}>{item}</option>)}
                  </Select>
                </Field>
              </div>
            </details>
          </div>
        </Card>
      ) : null}
      <MizitoList campaigns={campaigns.data ?? []} />
      {payments.isLoading ? <LoadingState /> : null}
      {payments.error ? <ErrorMessage error={payments.error instanceof Error ? payments.error.message : String(payments.error)} /> : null}
      {payments.data ? (
        <MoneyTable rows={payments.data} campaigns={campaigns.data ?? []} canFinance={canFinance} userId={user?.id} onAct={(id, action) => act.mutate({ id, action })} />
      ) : null}
    </>
  );
}

function MizitoList({ campaigns }: { campaigns: CampaignRow[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const list = useQuery({ queryKey: ["perf", "mizito"], queryFn: perfApi.mizito });
  const byCode = new Map(campaigns.map((row) => [row.code, row.id]));

  function refresh() {
    setBusy(true);
    perfApi.refreshMizito().then((result) => {
      qc.setQueryData(["perf", "mizito"], result);
      toast(result.connected ? `${result.open_count} کارت باز خوانده شد` : (result.reason || "میزیتو خوانده نشد"));
    }).catch((error: Error) => toast(error.message)).finally(() => setBusy(false));
  }

  const data = list.data;
  const cards = data?.cards ?? [];
  return (
    <Card>
      <SectionHeader
        icon="briefcase"
        title={<Bi en="Mizito cards" fa="کارت‌های میزیتو" />}
        count={data?.connected ? data.open_count : undefined}
        hint={<Bi en="Open cards still on a working board. Paid, cancelled and notice boards stay out. Refresh replaces this list and does not create a payment." fa="کارت‌هایی که هنوز روی برد کار هستند. پرداخت‌شده، کنسل و اطلاعیه نمی‌آیند. به‌روز کردن همین لیست را عوض می‌کند و درخواست پرداخت نمی‌سازد." />}
        action={<Button type="button" variant="secondary" disabled={busy} onClick={refresh}><Bi en="Refresh from Mizito" fa="به‌روز از میزیتو" /></Button>}
      />
      {list.isLoading ? <LoadingState /> : null}
      {data && !data.connected ? <Muted>{data.reason || "هنوز خوانده نشده است"}</Muted> : null}
      {data?.read_at ? <Muted>آخرین خواندن: <DateText value={data.read_at} withTime /></Muted> : null}
      {cards.length > 0 ? (
        <Table
          rows={cards}
          rowKey={(row: MizitoCard) => `${row.project}|${row.board}|${row.title}`}
          columns={[
            { key: "project", header: "پروژه", render: (row: MizitoCard) => row.project },
            { key: "board", header: "برد", render: (row: MizitoCard) => row.board || "—" },
            { key: "title", header: "کارت", render: (row: MizitoCard) => row.title },
            {
              key: "code",
              header: "کمپین",
              render: (row: MizitoCard) => {
                const id = row.code ? byCode.get(row.code) : undefined;
                if (!row.code) return "—";
                return id ? <Link to={`/perf/campaigns/${id}`}>{row.code}</Link> : row.code;
              },
            },
          ]}
        />
      ) : null}
    </Card>
  );
}

const PAYMENT_SORTS: SortOption<Payment>[] = [
  { key: "amount-desc", label: "بیشترین مبلغ", pick: (row) => row.amount_toman, dir: "desc" },
  { key: "amount-asc", label: "کمترین مبلغ", pick: (row) => row.amount_toman, dir: "asc" },
  { key: "who", label: "ذی‌نفع", pick: (row) => row.beneficiary, dir: "asc" },
  { key: "status", label: "وضعیت", pick: (row) => STATUS[row.status] || row.status, dir: "asc" },
];

function MoneyTable({
  rows,
  campaigns,
  canFinance,
  userId,
  onAct,
}: {
  rows: Payment[];
  campaigns: CampaignRow[];
  canFinance: boolean;
  userId?: string;
  onAct: (id: string, action: string) => void;
}) {
  const remove = useRemove();
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const narrowed = rows.filter((row) => (status === "" || row.status === status) && (kind === "" || row.kind === kind));
  const statuses = [...new Set(rows.map((row) => row.status))];
  const kinds = [...new Set(rows.map((row) => row.kind))];
  const list = useArrange(narrowed, 12, PAYMENT_SORTS, (row) => [KIND[row.kind], row.beneficiary, STATUS[row.status], row.amount_toman, row.note], `${status}|${kind}`);
  return (
    <Card>
      <SectionHeader icon="briefcase" title={<Bi en="Requests" fa="درخواست‌ها" />} count={list.ordered.length} />
      <ArrangeBar
        query={list.query}
        onQuery={list.setQuery}
        placeholder="ذی‌نفع یا نوع"
        sortKey={list.sortKey}
        onSort={list.setSortKey}
        sorts={list.sorts}
        onReset={status || kind || list.searching || list.sortChanged ? () => { setStatus(""); setKind(""); list.resetSort(); } : undefined}
      >
        {statuses.length > 1 ? (
          <Select aria-label="وضعیت" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">همهٔ وضعیت‌ها</option>
            {statuses.map((key) => <option key={key} value={key}>{STATUS[key] || key}</option>)}
          </Select>
        ) : null}
        {kinds.length > 1 ? (
          <Select aria-label="نوع" value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="">همهٔ نوع‌ها</option>
            {kinds.map((key) => <option key={key} value={key}>{KIND[key] || key}</option>)}
          </Select>
        ) : null}
      </ArrangeBar>
      {list.windowed.total === 0 ? <Muted as="p">با این فیلتر درخواستی نیست.</Muted> : (
        <Table
          rows={list.windowed.rows}
          rowKey={(row) => row.id}
          columns={[
            { key: "kind", header: "نوع", render: (row: Payment) => row.campaign_id ? <Link to={`/perf/campaigns/${row.campaign_id}`}>{KIND[row.kind] || row.kind}</Link> : (KIND[row.kind] || row.kind) },
            { key: "campaign", header: "کمپین", render: (row) => campaigns.find((item) => item.id === row.campaign_id)?.code || "—" },
            { key: "amount", header: "مبلغ", render: (row) => toman(row.amount_toman) },
            { key: "who", header: "ذی‌نفع", render: (row) => row.beneficiary },
            { key: "by", header: "درخواست‌کننده", render: (row) => row.requester_name || "—" },
            { key: "when", header: "تاریخ", render: (row) => row.created_at ? <DateText value={row.created_at} /> : "—" },
            { key: "status", header: "وضعیت", render: (row) => <Badge tone={row.status === "rejected" ? "danger" : row.status === "paid" || row.status === "recorded" ? "ok" : "warn"}>{STATUS[row.status] || row.status}</Badge> },
            {
              key: "actions",
              header: "",
              render: (row) => (
                <div className="row">
                  {["requested", "manager_ok", "finance_ok"].includes(row.status) && canFinance && userId !== row.requester_id ? (
                    <Button type="button" onClick={() => onAct(row.id, "finance")}>تأیید و پرداخت</Button>
                  ) : null}
                  {row.status === "requested" && userId === row.requester_id ? (
                    <AmountEdit id={row.id} amount={row.amount_toman} />
                  ) : null}
                  {row.status !== "recorded" && row.status !== "paid" ? (
                    <Button type="button" variant="danger" className="btn-sm" onClick={() => void remove(KIND[row.kind] || "درخواست", () => perfApi.deletePayment(row.id))}>حذف</Button>
                  ) : null}
                </div>
              ),
            },
          ]}
        />
      )}
      <ShowMore left={list.windowed.left} onMore={list.windowed.grow} />
    </Card>
  );
}

function AmountEdit({ id, amount }: { id: string; amount: number }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [value, setValue] = useState(amount);
  return (
    <span className="row">
      <Input type="number" value={value} onChange={(e) => setValue(Number(e.target.value))} />
      <Button
        type="button"
        variant="secondary"
        disabled={value <= 0 || value === amount}
        onClick={() => {
          perfApi.patchPayment(id, { amount_toman: value }).then(() => {
            toast("مبلغ عوض شد");
            qc.invalidateQueries({ queryKey: ["perf"] });
          }).catch((error: Error) => toast(error.message));
        }}
      >
        ذخیره
      </Button>
    </span>
  );
}
