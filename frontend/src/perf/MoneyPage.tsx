import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth";
import { Badge, Button, Card, Dialog, EmptyState, ErrorMessage, Field, Input, LoadingState, Muted, PageHeader, SectionHeader, Select, Table } from "../components/ui";
import { DELETE_CONFIRM_LABEL, useConfirm } from "../components/ui/ConfirmDialog";
import { DateText } from "../components/DateText";
import { Bi, useBi } from "../i18n";
import { MIZITO_STATUS, mizitoStatus, perfApi, toman, type CampaignRow, type MizitoCard, type MizitoFinance, type MizitoFinanceCard, type Payment } from "./api";
import { CampaignCode, exactError, OutcomePop, RelatedLinks, type Outcome } from "./bits";
import { ArrangeBar, hit, ShowMore, useArrange, type SortOption } from "./browse";
import { MizitoCardDialog, MizitoOpenButton, type MizitoCardLike } from "./MizitoCardDialog";
import { withoutEmptyColumns } from "../lib/columns";
import { hasExpensePay, hasExpenseTeamApprove } from "../lib/permissions";

const KIND: Record<string, string> = {
  panel_charge: "شارژ پنل",
  story: "سوشال",
  other: "سایر",
};

const CENTERS = ["پرفورمنس", "دفتر مرکزی", "شعبه فروش مرزداران", "شعبه فروش ایرانمال", "شعبه فروش کاشانی", "کلیه شعب"];

const STATUS: Record<string, string> = {
  requested: "درخواست — منتظر تأیید مالی",
  manager_ok: "تأیید مدیر — منتظر مالی",
  finance_ok: "منتظر مالی (وضعیت قدیمی)",
  paid: "پرداخت شد — هزینه هنوز در شیت نیامده",
  recorded: "ثبت شد — هزینه در شیت کمپین آمده",
  rejected: "رد شد — دیگر قابل تأیید نیست",
};

function paymentStatus(status: string): string {
  return STATUS[status] || `وضعیت ناشناخته: ${status}`;
}

export function MoneyPage() {
  const [params] = useSearchParams();
  const { has, user } = useAuth();
  const canFinance = hasExpensePay(has);
  const canTeamApprove = hasExpenseTeamApprove(has);
  const qc = useQueryClient();
  const payments = useQuery({ queryKey: ["perf", "payments"], queryFn: perfApi.payments });
  const panels = useQuery({ queryKey: ["perf", "panels"], queryFn: perfApi.panels });
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const [kind, setKind] = useState("panel_charge");
  const pages = useQuery({ queryKey: ["perf", "pages"], queryFn: perfApi.pages, enabled: kind === "story" });
  const [amount, setAmount] = useState("");
  const [beneficiary, setBeneficiary] = useState("");
  const [iban, setIban] = useState("");
  const [panelId, setPanelId] = useState("");
  const [pageId, setPageId] = useState("");
  const [campaignId, setCampaignId] = useState(params.get("campaign") || "");
  const [open, setOpen] = useState(Boolean(params.get("campaign")));
  const [center, setCenter] = useState("پرفورمنس");
  const [campaignQuery, setCampaignQuery] = useState("");
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const bi = useBi();
  const moneyFormTitleId = useId();
  const create = useMutation({
    mutationFn: () =>
      perfApi.createPayment({
        kind,
        amount_toman: amount === "" ? 0 : Number(amount),
        beneficiary,
        iban,
        panel_id: kind === "panel_charge" ? panelId || null : null,
        campaign_id: campaignId || null,
        cost_center: center,
      }),
    onSuccess: (row) => {
      qc.invalidateQueries({ queryKey: ["perf"] });
      setOpen(false);
      setOutcome({
        ok: true,
        title: "ثبت درخواست موفق بود",
        detail: `درخواست ${KIND[row.kind] || row.kind} به مبلغ ${toman(row.amount_toman)} تومان ثبت شد.\nوضعیت: ${paymentStatus(row.status)}`,
      });
    },
    onError: (error: unknown) => setOutcome({ ok: false, title: "ثبت درخواست ناموفق بود", detail: exactError(error) }),
  });
  const act = useMutation({
    mutationFn: ({ id, action, amount }: { id: string; action: string; amount?: number }) => perfApi.advance(id, action, amount),
    onSuccess: (row) => {
      qc.invalidateQueries({ queryKey: ["perf"] });
      setOutcome({
        ok: true,
        title: "اقدام روی درخواست موفق بود",
        detail: `وضعیت الان: ${paymentStatus(row.status)}`,
      });
    },
    onError: (error: unknown) => setOutcome({ ok: false, title: "اقدام روی درخواست ناموفق بود", detail: exactError(error) }),
  });

  return (
    <>
      <PageHeader
        title={<Bi en="Costs" fa="هزینه‌ها" />}
        description={<Bi en="Payment requests for finance to approve." fa="درخواست‌های پرداخت برای تأیید مالی." />}
        actions={
          <div className="row">
            {campaignId ? <RelatedLinks id={campaignId} code={(campaigns.data ?? []).find((row) => row.id === campaignId)?.code} here="money" /> : (
              <Button variant="secondary" to="/perf/sheet"><Bi en="Sheet" fa="شیت" /></Button>
            )}
            <Button variant="secondary" to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Button>
            {has("perf.write") ? <Button type="button" onClick={() => setOpen(true)}><Bi en="New payment request" fa="درخواست پرداخت جدید" /></Button> : null}
          </div>
        }
      />
      {has("perf.write") && open ? (
        <Dialog
          onClose={() => setOpen(false)}
          className="form-pop"
          labelledBy={moneyFormTitleId}
          closeLabel={bi("Close", "بستن")}
          busy={create.isPending}
        >
          <SectionHeader
            icon="briefcase"
            title={<span id={moneyFormTitleId}><Bi en="New request" fa="درخواست تازه" /></span>}
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
              <Input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d]/g, ""))} />
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
                    if (page.price_toman) setAmount(String(page.price_toman));
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
              <Button type="button" disabled={!amount || Number(amount) <= 0 || create.isPending || (kind === "story" && !pageId)} onClick={() => create.mutate()}>
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
        </Dialog>
      ) : null}
      <MizitoList campaigns={campaigns.data ?? []} />
      <MizitoFinanceBlock campaigns={campaigns.data ?? []} />
      {payments.isLoading ? <LoadingState /> : null}
      {payments.error ? <ErrorMessage error={payments.error instanceof Error ? payments.error.message : String(payments.error)} /> : null}
      {payments.data ? (
        payments.data.length === 0 ? (
          <EmptyState
            titleEn="No payment requests yet"
            titleFa="هنوز درخواست پرداختی نیست"
            bodyEn="Panel top-ups and social costs start with a new request."
            bodyFa="شارژ پنل و هزینهٔ سوشال با «درخواست تازه» شروع می‌شود."
          />
        ) : (
          <MoneyTable rows={payments.data} campaigns={campaigns.data ?? []} canFinance={canFinance} canTeamApprove={canTeamApprove} userId={user?.id} onAct={(id, action, amount) => act.mutate({ id, action, amount })} onOutcome={setOutcome} />
        )
      ) : null}
      <OutcomePop outcome={outcome} onClose={() => setOutcome(null)} />
    </>
  );
}

function MizitoList({ campaigns }: { campaigns: CampaignRow[] }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [openCard, setOpenCard] = useState<MizitoCardLike | null>(null);
  const list = useQuery({ queryKey: ["perf", "mizito"], queryFn: perfApi.mizito });
  const byCode = new Map(campaigns.map((row) => [row.code, row.id]));

  function refresh() {
    setBusy(true);
    perfApi.refreshMizito().then((result) => {
      qc.setQueryData(["perf", "mizito"], result);
      qc.invalidateQueries({ queryKey: ["perf", "mizito", "missing"] });
      qc.invalidateQueries({ queryKey: ["perf", "mizito", "finance"] });
      qc.invalidateQueries({ queryKey: ["perf", "mizito", "triage"] });
      setOutcome({
        ok: result.connected,
        title: result.connected ? "به‌روزرسانی میزیتو موفق بود" : "به‌روزرسانی میزیتو ناموفق بود",
        detail: result.connected
          ? `${toman(result.open_count)} کارت فعال خوانده شد. چیزی در میزیتو نوشته نشد.`
          : (result.reason || "میزیتو جواب نداد و دلیلی هم نفرستاد."),
      });
    }).catch((error: unknown) => {
      setOutcome({ ok: false, title: "به‌روزرسانی میزیتو ناموفق بود", detail: exactError(error) });
    }).finally(() => setBusy(false));
  }

  const data = list.data;
  const all = data?.cards ?? [];
  const cards = showAll ? all : all.filter((row) => row.active !== false);
  const shown = cards.slice(0, 300);
  const total = data?.total_count ?? all.length;
  // ستونی که در همهٔ ردیف‌ها خالی است نشان داده نمی‌شود. در موبایل فقط کارت، وضعیت و آخرین تغییر می‌ماند (hide-sm).
  const mizitoColumns = withoutEmptyColumns<MizitoCard>([
    { key: "project", header: "پروژه", className: "hide-sm", render: (row: MizitoCard) => row.project },
    { key: "board", header: "برد", className: "hide-sm", render: (row: MizitoCard) => row.board || "—" },
    {
      key: "status",
      header: "وضعیت",
      render: (row: MizitoCard) => {
        const label = mizitoStatus(row);
        return row.completed ? `${label} · تکمیل‌شده` : label;
      },
    },
    { key: "title", header: "کارت", render: (row: MizitoCard) => <MizitoOpenButton title={row.title} onOpen={() => setOpenCard(row)} /> },
    {
      key: "checklist",
      header: "چک‌لیست",
      className: "hide-sm",
      render: (row: MizitoCard) => (row.checklist_total ? `${row.checklist_done ?? 0} از ${row.checklist_total}` : "—"),
    },
    {
      key: "modified",
      header: "آخرین تغییر",
      className: "cell-nowrap",
      render: (row: MizitoCard) => (row.modified_at ? <DateText value={row.modified_at} /> : "—"),
    },
    {
      key: "code",
      header: "کمپین",
      className: "hide-sm cell-nowrap",
      render: (row: MizitoCard) => {
        const id = row.code ? byCode.get(row.code) : undefined;
        if (!row.code) return "—";
        return id ? <Link to={`/perf/campaigns/${id}`} onClick={(event) => event.stopPropagation()}>{row.code}</Link> : row.code;
      },
    },
  ], shown, {
    project: (row) => Boolean(row.project),
    board: (row) => Boolean(row.board),
    checklist: (row) => Boolean(row.checklist_total),
    modified: (row) => Boolean(row.modified_at),
    code: (row) => Boolean(row.code),
  });
  return (
    <Card>
      <SectionHeader
        icon="briefcase"
        title={<Bi en="Mizito cards" fa="کارت‌های میزیتو" />}
        count={data?.connected ? data.open_count : undefined}
        hint={<Bi en="Cards of the marketing projects, each with a status from its board. Only active cards show unless you pick Show all. Refresh replaces this list and does not create a payment." fa="کارت‌های پروژه‌های مارکتینگ، هر کدام با وضعیتی از روی بردش. پیش‌فرض فقط کارت‌های فعال؛ تکمیل‌شده، پرداخت‌شده، تمام‌شده، کنسل، متوقف و اطلاعیه با «نمایش همه» می‌آیند. به‌روز کردن همین لیست را عوض می‌کند و درخواست پرداخت نمی‌سازد." />}
        action={
          <div className="row">
            <Button type="button" variant="secondary" onClick={() => setShowAll(!showAll)}>
              {showAll ? <Bi en="Active only" fa="فقط فعال‌ها" /> : <Bi en={`Show all (${total})`} fa={`نمایش همه (${total})`} />}
            </Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={refresh}><Bi en="Refresh from Mizito" fa="به‌روز از میزیتو" /></Button>
          </div>
        }
      />
      {list.isLoading ? <LoadingState /> : null}
      {data && !data.connected ? <Muted>{data.reason || "هنوز خوانده نشده است"}</Muted> : null}
      {data?.read_at ? <Muted>آخرین خواندن: <DateText value={data.read_at} withTime /></Muted> : null}
      {all.length > 0 && cards.length === 0 ? <Muted>کارت فعالی نیست.</Muted> : null}
      {shown.length > 0 ? (
        <Table
          rows={shown}
          rowKey={(row: MizitoCard) => row.id || `${row.project}|${row.board}|${row.title}`}
          onRowClick={(row: MizitoCard) => setOpenCard(row)}
          columns={mizitoColumns}
        />
      ) : null}
      {cards.length > shown.length ? <Muted>{shown.length} از {cards.length} کارت نشان داده شده است.</Muted> : null}
      {openCard ? <MizitoCardDialog card={openCard} onClose={() => setOpenCard(null)} /> : null}
      <OutcomePop outcome={outcome} onClose={() => setOutcome(null)} />
    </Card>
  );
}

const FINANCE_ORDER = ["waiting_approval", "waiting_payment", "paid", "not_in_cost_tracking"];

function MizitoFinanceBlock({ campaigns }: { campaigns: CampaignRow[] }) {
  const finance = useQuery({ queryKey: ["perf", "mizito", "finance"], queryFn: perfApi.mizitoFinance });
  const data = finance.data;
  if (!data || !data.read_at) return null;
  return (
    <Card>
      <SectionHeader
        icon="briefcase"
        title={<Bi en="Mizito payments and cost tracking" fa="پرداخت‌های میزیتو و پیگیری هزینه" />}
        hint={<Bi en="Finance project cards from the last Mizito read next to the panel's cost-tracking rows. Matching is by campaign code only and is a suggestion; nothing is recorded automatically." fa="کارت‌های پروژهٔ مالی از آخرین خواندن میزیتو، کنار ردیف‌های پیگیری هزینه پنل. تطبیق فقط با کد کمپین و پیشنهادی است؛ چیزی خودکار ثبت نمی‌شود." />}
      />
      <p className="muted">
        {FINANCE_ORDER.map((status, index) => {
          const count = data.counts[status] ?? { total: 0, open: 0 };
          return (
            <span key={status}>
              {index ? " · " : null}
              {MIZITO_STATUS[status]}: {toman(count.total)}
              {count.open !== count.total ? ` (${toman(count.open)} باز)` : null}
            </span>
          );
        })}
      </p>
      <h4><Bi en="Not yet in cost tracking" fa="ثبت‌نشده در پیگیری هزینه" /> ({toman(data.to_register_count)})</h4>
      {data.to_register.length ? <FinanceCards rows={data.to_register} /> : <Muted as="p">کارت بازی در ستون «ثبت نشده در پیگیری هزینه» نیست.</Muted>}
      <h4><Bi en="Paid in Mizito, no cost-tracking row" fa="پرداخت‌شده در میزیتو، بدون ردیف پیگیری هزینه" /> ({toman(data.paid_without_cost_count)})</h4>
      {data.paid_without_cost.length ? <FinanceCards rows={data.paid_without_cost} /> : <Muted as="p">همهٔ کارت‌های پرداخت‌شده کد هم‌خوان در پیگیری هزینه دارند.</Muted>}
      {data.paid_suggested_count ? <Muted as="p">{toman(data.paid_suggested_count)} کارت پرداخت‌شده کد هم‌خوان در پیگیری هزینه دارد (پیشنهادی، بدون بررسی مبلغ).</Muted> : null}
      <h4><Bi en="Tracked in Mizito, no finance card" fa="در میزیتو هست، کارت مالی ندارد" /> ({toman(data.panel_without_card_count ?? 0)})</h4>
      {(data.panel_without_card ?? []).length ? <PanelCosts rows={data.panel_without_card ?? []} campaigns={campaigns} /> : <Muted as="p">هر کمپینی که در میزیتو کارت دارد، اگر هزینه‌ای در پنل داشته باشد کارت مالی هم دارد.</Muted>}
    </Card>
  );
}

function PanelCosts({
  rows,
  campaigns,
}: {
  rows: NonNullable<MizitoFinance["panel_without_card"]>;
  campaigns: CampaignRow[];
}) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, 8);
  const byCode = new Map(campaigns.map((row) => [row.code, row.id]));
  return (
    <>
      <Table
        rows={shown}
        rowKey={(row) => `${row.cost_number}-${row.campaign_code}`}
        columns={[
          { key: "number", header: "شماره", className: "cell-nowrap", render: (row) => `#${toman(row.cost_number)}` },
          {
            key: "code",
            header: "کمپین",
            className: "cell-nowrap",
            render: (row) => {
              const id = byCode.get(row.campaign_code);
              return id ? <Link to={`/perf/campaigns/${id}`}>{row.campaign_code}</Link> : row.campaign_code;
            },
          },
          { key: "amount", header: "مبلغ", render: (row) => (row.amount_toman == null ? "—" : toman(row.amount_toman)) },
          { key: "kind", header: "نوع", render: (row) => row.kind || "—" },
          { key: "description", header: "شرح", render: (row) => row.description || "—" },
        ]}
      />
      <ShowMore left={rows.length - shown.length} onMore={() => setAll(true)} />
    </>
  );
}

const FINANCE_MATCH: Record<string, string> = {
  suggested: "پیشنهاد",
  no_cost_row: "کد در پیگیری هزینه نیست",
  no_code: "بدون کد کمپین",
};

function FinanceCards({ rows }: { rows: MizitoFinanceCard[] }) {
  const [all, setAll] = useState(false);
  const [openCard, setOpenCard] = useState<MizitoCardLike | null>(null);
  const shown = all ? rows : rows.slice(0, 8);
  return (
    <>
      <Table
        rows={shown}
        rowKey={(row: MizitoFinanceCard) => row.id || row.title}
        onRowClick={(row: MizitoFinanceCard) => setOpenCard(row)}
        columns={[
          { key: "title", header: "کارت", render: (row: MizitoFinanceCard) => <MizitoOpenButton title={row.title} onOpen={() => setOpenCard(row)} /> },
          {
            key: "code",
            header: "کد",
            className: "cell-nowrap",
            render: (row: MizitoFinanceCard) => (row.code ? <><CampaignCode code={row.code} />{row.code_source === "notes" ? <span className="muted"> (از یادداشت)</span> : null}</> : "—"),
          },
          {
            key: "match",
            header: "پیگیری هزینه",
            render: (row: MizitoFinanceCard) => (row.match === "suggested"
              ? `${FINANCE_MATCH.suggested}: ${row.suggested_costs.map((number) => `#${toman(number)}`).join("، ")}`
              : FINANCE_MATCH[row.match] || "—"),
          },
          {
            key: "modified",
            header: "آخرین تغییر",
            className: "cell-nowrap",
            render: (row: MizitoFinanceCard) => (
              <>
                {row.modified_at ? <DateText value={row.modified_at} /> : "—"}
                {row.completed ? <span className="muted"> · تکمیل‌شده</span> : null}
              </>
            ),
          },
        ]}
      />
      <ShowMore left={rows.length - shown.length} onMore={() => setAll(true)} />
      {openCard ? <MizitoCardDialog card={openCard} onClose={() => setOpenCard(null)} /> : null}
    </>
  );
}

const PAYMENT_SORTS: SortOption<Payment>[] = [
  { key: "amount-desc", label: "بیشترین مبلغ", pick: (row) => row.amount_toman, dir: "desc" },
  { key: "amount-asc", label: "کمترین مبلغ", pick: (row) => row.amount_toman, dir: "asc" },
  { key: "who", label: "ذی‌نفع", pick: (row) => row.beneficiary, dir: "asc" },
  { key: "status", label: "وضعیت", pick: (row) => STATUS[row.status] || row.status, dir: "asc" },
];

function paymentLinked(row: Payment): boolean {
  return Boolean(row.project_id || row.request_id);
}

function canFinancePay(row: Payment): boolean {
  if (row.status === "finance_ok") return true;
  if (paymentLinked(row)) return row.status === "manager_ok";
  return row.status === "requested" || row.status === "manager_ok";
}

function MoneyTable({
  rows,
  campaigns,
  canFinance,
  canTeamApprove,
  userId,
  onAct,
  onOutcome,
}: {
  rows: Payment[];
  campaigns: CampaignRow[];
  canFinance: boolean;
  canTeamApprove: boolean;
  userId?: string;
  onAct: (id: string, action: string, amount?: number) => void;
  onOutcome: (outcome: Outcome) => void;
}) {
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const narrowed = rows.filter((row) => (status === "" || row.status === status) && (kind === "" || row.kind === kind));
  const statuses = [...new Set(rows.map((row) => row.status))];
  const kinds = [...new Set(rows.map((row) => row.kind))];
  const list = useArrange(narrowed, 12, PAYMENT_SORTS, (row) => [KIND[row.kind], row.beneficiary, STATUS[row.status], row.amount_toman, row.note], `${status}|${kind}`);
  return (
    <Card>
      <SectionHeader icon="briefcase" title={<Bi en="Payment requests" fa="درخواست‌های پرداخت" />} count={list.ordered.length} />
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
            { key: "kind", header: "نوع", render: (row: Payment) => KIND[row.kind] || row.kind },
            { key: "campaign", header: "کمپین", render: (row) => <CampaignCode id={row.campaign_id} code={campaigns.find((item) => item.id === row.campaign_id)?.code} /> },
            { key: "amount", header: "مبلغ", render: (row) => toman(row.amount_toman) },
            { key: "who", header: "ذی‌نفع", render: (row) => row.beneficiary },
            { key: "by", header: "درخواست‌کننده", render: (row) => row.requester_name || "—" },
            { key: "when", header: "تاریخ", render: (row) => row.created_at ? <DateText value={row.created_at} /> : "—" },
            { key: "status", header: "وضعیت", render: (row) => <Badge tone={row.status === "rejected" ? "danger" : row.status === "paid" || row.status === "recorded" ? "ok" : "warn"}>{paymentStatus(row.status)}</Badge> },
            {
              key: "actions",
              header: "",
              render: (row) => (
                <div className="row">
                  {row.status === "requested" && paymentLinked(row) && canTeamApprove && userId !== row.requester_id ? (
                    <Button type="button" variant="secondary" onClick={() => onAct(row.id, "manager")}>
                      تأیید سرپرست تیم
                    </Button>
                  ) : null}
                  {canFinancePay(row) && canFinance && userId !== row.requester_id ? (
                    <Button type="button" onClick={() => onAct(row.id, "finance", row.amount_toman)}>تأیید و پرداخت</Button>
                  ) : null}
                  {row.status === "requested" && userId === row.requester_id ? (
                    <AmountEdit id={row.id} amount={row.amount_toman} onOutcome={onOutcome} />
                  ) : null}
                  {row.status !== "recorded" && row.status !== "paid" ? (
                    <Button
                      type="button"
                      variant="danger-quiet"
                      className="btn-sm"
                      onClick={() => {
                        void confirm("حذف", `${KIND[row.kind] || "درخواست"} حذف شود؟`, DELETE_CONFIRM_LABEL, { danger: true }).then(async (ok) => {
                          if (!ok) return;
                          try {
                            await perfApi.deletePayment(row.id);
                            await qc.invalidateQueries({ queryKey: ["perf"] });
                            onOutcome({
                              ok: true,
                              title: "حذف درخواست موفق بود",
                              detail: "درخواست از فهرست برداشته شد.",
                            });
                          } catch (error) {
                            onOutcome({ ok: false, title: "حذف درخواست ناموفق بود", detail: exactError(error) });
                          }
                        });
                      }}
                    >
                      حذف
                    </Button>
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

function AmountEdit({ id, amount, onOutcome }: { id: string; amount: number; onOutcome: (outcome: Outcome) => void }) {
  const qc = useQueryClient();
  const [value, setValue] = useState(amount);
  return (
    <span className="row">
      <Input type="number" value={value} onChange={(e) => setValue(Number(e.target.value))} />
      <Button
        type="button"
        variant="secondary"
        disabled={value <= 0 || value === amount}
        onClick={() => {
          perfApi.patchPayment(id, { amount_toman: value }).then((row) => {
            qc.invalidateQueries({ queryKey: ["perf"] });
            onOutcome({
              ok: true,
              title: "تغییر مبلغ موفق بود",
              detail: `مبلغ جدید ${toman(row.amount_toman)} تومان است.\nوضعیت: ${paymentStatus(row.status)}`,
            });
          }).catch((error: unknown) => onOutcome({ ok: false, title: "تغییر مبلغ ناموفق بود", detail: exactError(error) }));
        }}
      >
        ذخیره
      </Button>
    </span>
  );
}
