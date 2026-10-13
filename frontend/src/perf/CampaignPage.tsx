import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Donut, LineTrend } from "../components/charts";
import { Badge, Button, Card, ErrorMessage, List, ListItem, LoadingState, MoreMenu, Muted, PageHeader, SectionHeader, Select, StatCard, Table, type Tone } from "../components/ui";
import { DateText } from "../components/DateText";
import { useToast } from "../components/ui/Toast";
import { Bi } from "../i18n";
import { formatJalali } from "../jalali";
import { downloadPerf, leadsLabel, mizitoCode, mizitoStatus, perfApi, toman, type MizitoCard, type Report } from "./api";
import { CampaignBriefSection } from "./Brief";
import { FilePick } from "./bits";
import { ArrangeBar, ShowMore, useArrange, type SortOption } from "./browse";
import { CampaignEdit, RowActions, useRemove } from "./edit";
import { MizitoCardDialog, MizitoOpenButton, type MizitoCardLike } from "./MizitoCardDialog";

export function CampaignPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const remove = useRemove();
  const [editing, setEditing] = useState(false);
  const row = useQuery({ queryKey: ["perf", "campaign", id], queryFn: () => perfApi.campaign(id), enabled: Boolean(id) });
  const leads = useMutation({
    mutationFn: (file: File) => perfApi.importLeads(file),
    onSuccess: (result) => {
      toast(`${result.added} ورودی ثبت شد`);
      qc.invalidateQueries({ queryKey: ["perf"] });
    },
    onError: (error: Error) => toast(error.message),
  });
  if (row.isLoading) return <LoadingState />;
  if (row.error || !row.data) return <ErrorMessage error={row.error instanceof Error ? row.error.message : "کمپین پیدا نشد"} />;
  const data = row.data;
  const report: Report = {
    trend: data.report?.trend ?? [],
    pages: data.report?.pages ?? [],
    channels: data.report?.channels ?? [],
    views: data.report?.views ?? 0,
    leads: data.report?.leads ?? 0,
    cost_toman: data.report?.cost_toman ?? 0,
    cpl: data.report?.cpl ?? 0,
    cpv: data.report?.cpv ?? 0,
    clicks: data.report?.clicks ?? 0,
    starts_on: data.report?.starts_on ?? null,
    ends_on: data.report?.ends_on ?? null,
    notes: data.report?.notes ?? [],
    advice: data.report?.advice,
    budget_toman: data.report?.budget_toman,
    budget_over: data.report?.budget_over,
    budget_warning: data.report?.budget_warning,
    source: data.report?.source,
  };
  const shift = periodShift(report.trend);
  const lines = decisionLines(report, shift);
  const leadRate = report.views > 0 && report.leads > 0 ? (report.leads / report.views) * 100 : null;
  const shownRate = leadRate != null && leadRate >= 0.5 ? leadRate : null;
  const budgetWarn = report.budget_warning || (report.budget_over ? "هزینه از بودجه بیشتر شده است." : "");
  return (
    <div className="perf-report">
      {budgetWarn ? (
        <p className="callout warn" role="status">
          <Badge tone="warn">بودجه</Badge> {budgetWarn}
        </p>
      ) : null}
      <PageHeader
        title={`${data.code} — ${data.title}`}
        description={
          <>
            {data.brand ? <span>{data.brand}</span> : null}
            {data.goal ? <span>{data.brand ? " · " : null}{data.goal}</span> : null}
            {report.starts_on ? (
              <span>
                {data.goal || data.brand ? " · " : null}
                از <CampaignDay value={report.starts_on} />
                {report.ends_on ? <> تا <CampaignDay value={report.ends_on} /></> : null}
              </span>
            ) : data.goal || data.brand ? null : (
              <Bi en="Numbers are calculated from the sheet, then shown here." fa="آمار از روی شیت ساخته می‌شود و اینجا نشان داده می‌شود." />
            )}
          </>
        }
        actions={
          <div className="row no-print">
            <Button variant="secondary" to={`/perf/sms?campaign=${data.id}`}><Bi en="SMS" fa="پیامک" /></Button>
            <MoreMenu label={<Bi en="More" fa="بیشتر" />}>
              {data.project_id ? <Button variant="ghost" to={`/projects/${data.project_id}`}><Bi en="Project" fa="پروژه" /></Button> : null}
              <Button
                variant="ghost"
                onClick={() => {
                  void perfApi.campaignThread(data.id).then((thread) => navigate(`/communication?c=${thread.id}`));
                }}
              >
                <Bi en="Chat" fa="گفتگو" />
              </Button>
              <Button variant="ghost" to={`/perf/social?campaign=${data.id}`}><Bi en="Social" fa="سوشال" /></Button>
              <Button variant="ghost" to={`/perf/money?campaign=${data.id}`}><Bi en="Costs" fa="هزینه‌ها" /></Button>
              <Button variant="ghost" to={`/perf/sheet?campaign=${data.code}`}><Bi en="Sheet" fa="شیت" /></Button>
              <Button type="button" variant="ghost" onClick={() => window.print()}><Bi en="Print" fa="چاپ" /></Button>
            </MoreMenu>
            <RowActions
              onEdit={() => setEditing(true)}
              onDelete={() => void remove(`کمپین ${data.code}`, () => perfApi.deleteCampaign(data.id).then(() => navigate("/perf/campaigns")))}
            />
          </div>
        }
      />
      <CampaignBriefSection campaign={data} brief={data.brief} />
      <div className="kpi-row kpi-row--4 kpi-row--even">
        <StatCard
          icon="activity"
          tone="neutral"
          label={<Bi en="Cost" fa="هزینه" />}
          value={compactToman(report.cost_toman)}
          hint={moneyHint(report.cost_toman, shift?.costPct ?? null, false)}
        />
        <StatCard
          icon="flag"
          tone={shiftTone(shift?.leadsPct ?? null, false)}
          label={<Bi en="Leads" fa="ورودی" />}
          value={leadsLabel(report.leads)}
          hint={shownRate != null ? <>{faPercent(shownRate)} از نمایش‌ها<Shift pct={shift?.leadsPct ?? null} lowerIsBetter={false} /></> : <Shift pct={shift?.leadsPct ?? null} lowerIsBetter={false} />}
        />
        <StatCard
          icon="activity"
          tone={shiftTone(shift?.cplPct ?? null, true)}
          label={<Bi en="CPL" fa="هزینه هر ورودی" />}
          value={compactToman(report.cpl)}
          hint={<>هزینهٔ هر ورودی<Shift pct={shift?.cplPct ?? null} lowerIsBetter /></>}
        />
        <StatCard
          icon="users"
          tone="neutral"
          label={<Bi en="CPV" fa="هزینه هر بازدید" />}
          value={compactToman(report.cpv)}
          hint={<>هزینهٔ هر نمایش · از {toman(report.views)} نمایش</>}
        />
      </div>
      <MizitoCards code={data.code} />
      {lines.length ? (
        <Card>
          <SectionHeader
            icon="alert"
            title={<Bi en="What to do" fa="چه کار شود" />}
            hint={<Bi en="Later days of this range compared with the earlier days." fa="نیمهٔ دوم روزهای دارای داده، نسبت به نیمهٔ اول." />}
          />
          {lines[0] ? <p className="perf-advice">{lines[0]}</p> : null}
          {lines.length > 1 ? (
            <List>
              {lines.slice(1).map((line) => <ListItem key={line}>{line}</ListItem>)}
            </List>
          ) : null}
        </Card>
      ) : null}
      {report.trend.length || report.pages.length || data.budget_toman || report.clicks ? (
        <p className="muted perf-facts">
          {report.trend.length ? <>{toman(report.trend.length)} روز در نمودار</> : null}
          {report.pages.length ? <>{report.trend.length ? " · " : null}{toman(report.pages.length)} پیج</> : null}
          {data.budget_toman ? (
            data.budget_toman > report.cost_toman
              ? <> · بودجه {compactToman(data.budget_toman)} · مانده {compactToman(data.budget_toman - report.cost_toman)}</>
              : <> · بودجه {compactToman(data.budget_toman)} · {compactToman(report.cost_toman - data.budget_toman)} بیش از بودجه</>
          ) : null}
          {report.clicks ? <> · کلیک {toman(report.clicks)}</> : null}
        </p>
      ) : null}
      <div className="perf-chart-grid">
        {METRICS.map((metric) => (
          <Card key={metric.key} className="perf-chart-card">
            <SectionHeader title={metric.title} />
            <TrendChart trend={report.trend} metric={metric.key} title={metric.title} />
          </Card>
        ))}
      </div>
      <Card className="perf-chart-card">
        <SectionHeader title={<Bi en="Spend by channel" fa="سهم هزینه به تفکیک کانال" />} hint={<Bi en="Each slice is that channel's share of spend. The legend also shows cost per lead." fa="هر تکه سهم هزینهٔ همان کانال است. کنار نمودار، هزینهٔ هر ورودی همان کانال هم هست." />} />
        <ChannelShare channels={report.channels} />
      </Card>
      <div className="no-print">
      <BestPages pages={report.pages} campaignId={data.id} />
      </div>
      <Card className="no-print">
        <SectionHeader
          title={<Bi en="Add Didar leads" fa="افزودن ورودی دیدار" />}
          hint={<Bi en="Rows with this campaign code are counted in the lead number above." fa="ردیف‌هایی که کد این کمپین را دارند به عدد ورودی بالا اضافه می‌شوند." />}
          action={
            <Button type="button" variant="secondary" onClick={() => downloadPerf("/perf/excel/template?kind=leads", "leads-template.xlsx")}>
              <Bi en="Blank template" fa="قالب خالی" />
            </Button>
          }
        />
        <FilePick
          accept=".xlsx"
          label={<Bi en="Choose the Didar file" fa="فایل دیدار را انتخاب کنید" />}
          hint=".xlsx"
          busy={leads.isPending}
          onFile={(file) => leads.mutate(file)}
        />
      </Card>
      {editing ? <CampaignEdit row={data} onClose={() => setEditing(false)} /> : null}
    </div>
  );
}

function MizitoCards({ code }: { code: string }) {
  const mizito = useQuery({ queryKey: ["perf", "mizito"], queryFn: perfApi.mizito });
  const [openCard, setOpenCard] = useState<MizitoCardLike | null>(null);
  if (mizito.isLoading) return <LoadingState block={false} />;
  const key = mizitoCode(code);
  const cards = (mizito.data?.cards ?? [])
    .filter((card) => key && mizitoCode(card.code) === key)
    .sort((a, b) => Number(a.active === false) - Number(b.active === false) || (b.modified_at || "").localeCompare(a.modified_at || ""));
  return (
    <Card>
      <SectionHeader
        icon="briefcase"
        title={<Bi en="Mizito" fa="میزیتو" />}
        count={cards.length || undefined}
        hint={<Bi en="Mizito cards whose title has this campaign code: active first, then most recently changed. Read-only." fa="کارت‌های میزیتو که کد این کمپین در عنوانشان است؛ اول فعال‌ها، بعد تازه‌ترها. فقط خواندنی." />}
        action={<Button variant="secondary" to="/perf/money"><Bi en="All cards" fa="همه در هزینه‌ها" /></Button>}
      />
      {cards.length === 0 ? (
        <Muted as="p">
          {mizito.data?.read_at
            ? `کارتی با کد ${code} در میزیتو پیدا نشد.`
            : "هنوز از میزیتو خوانده نشده؛ در صفحهٔ هزینه‌ها «به‌روز از میزیتو» را بزنید."}
        </Muted>
      ) : (
        <Table
          rows={cards}
          rowKey={(card: MizitoCard) => card.id || `${card.project}|${card.board}|${card.title}`}
          onRowClick={(card: MizitoCard) => setOpenCard(card)}
          columns={[
            { key: "project", header: "پروژه", className: "hide-sm", render: (card: MizitoCard) => card.project },
            { key: "board", header: "برد", render: (card: MizitoCard) => card.board || "—" },
            {
              key: "status",
              header: "وضعیت",
              render: (card: MizitoCard) => (
                <>
                  {mizitoStatus(card)}
                  {card.completed ? <span className="muted"> · تکمیل‌شده</span> : null}
                </>
              ),
            },
            { key: "title", header: "کارت", render: (card: MizitoCard) => <MizitoOpenButton title={card.title} onOpen={() => setOpenCard(card)} /> },
            {
              key: "checklist",
              header: "چک‌لیست",
              render: (card: MizitoCard) => (card.checklist_total ? `${toman(card.checklist_done ?? 0)} از ${toman(card.checklist_total)}` : "—"),
            },
            { key: "modified", header: "آخرین تغییر", render: (card: MizitoCard) => (card.modified_at ? <DateText value={card.modified_at} /> : "—") },
            { key: "people", header: "مسئول", className: "hide-sm", render: (card: MizitoCard) => (card.assignees?.length ? toman(card.assignees.length) : "—") },
          ]}
        />
      )}
      {openCard ? <MizitoCardDialog card={openCard} onClose={() => setOpenCard(null)} /> : null}
    </Card>
  );
}

type ReportPage = Report["pages"][number];
type TrendPoint = Report["trend"][number];
type Metric = "cost" | "leads" | "cpl";

const METRICS: Array<{ key: Metric; label: string; title: string }> = [
  { key: "cost", label: "هزینه", title: "هزینه در این بازه" },
  { key: "leads", label: "ورودی", title: "ورودی در این بازه" },
  { key: "cpl", label: "هزینه هر ورودی", title: "هزینهٔ هر ورودی در این بازه" },
];

const PAGE_SORTS: SortOption<ReportPage>[] = [
  { key: "cpl-asc", label: "کمترین هزینهٔ هر ورودی", pick: (row) => row.cpl, dir: "asc" },
  { key: "cpl-desc", label: "بیشترین هزینهٔ هر ورودی", pick: (row) => row.cpl, dir: "desc" },
  { key: "leads-desc", label: "بیشترین ورودی", pick: (row) => row.leads, dir: "desc" },
  { key: "views-desc", label: "بیشترین نمایش", pick: (row) => row.views, dir: "desc" },
  { key: "cost-desc", label: "بیشترین هزینه", pick: (row) => row.cost, dir: "desc" },
  { key: "name", label: "اسم", pick: (row) => row.name, dir: "asc" },
];

function CampaignDay({ value }: { value: string }) {
  if (!value) return <>—</>;
  if (/^\d{4}-\d{2}-\d{2}/.test(value)) return <DateText value={value} />;
  return <>{value}</>;
}

function formatCompact(value: number): string {
  const rounded = value >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  return new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 }).format(rounded);
}

function compactToman(value: number | null | undefined): string {
  if (value == null) return "—";
  const amount = Math.round(value);
  const abs = Math.abs(amount);
  if (abs >= 1_000_000_000) return `${formatCompact(abs / 1_000_000_000)} میلیارد`;
  if (abs >= 10_000_000) return `${formatCompact(abs / 1_000_000)} میلیون`;
  return toman(amount);
}

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function faPercent(value: number): string {
  return `${new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 }).format(value)}٪`;
}

function moneyHint(value: number, pct: number | null, lowerIsBetter: boolean): ReactNode {
  return (
    <>
      {value >= 1_000_000 ? `${toman(value)} تومان` : "تومان"}
      <Shift pct={pct} lowerIsBetter={lowerIsBetter} />
    </>
  );
}

function Shift({ pct, lowerIsBetter }: { pct: number | null; lowerIsBetter: boolean }) {
  if (pct == null || Math.abs(pct) < 2) return null;
  const better = lowerIsBetter ? pct < 0 : pct > 0;
  return (
    <span className={better ? "perf-delta is-better" : "perf-delta is-worse"}>
      {" "}{pct > 0 ? "↑" : "↓"} {toman(Math.abs(pct))}٪ نیمهٔ دوم
    </span>
  );
}

function shiftTone(pct: number | null, lowerIsBetter: boolean): Tone {
  if (pct == null || Math.abs(pct) < 8) return "neutral";
  const better = lowerIsBetter ? pct < 0 : pct > 0;
  return better ? "ok" : "warn";
}

function periodShift(trend: TrendPoint[]) {
  const rows = trend.filter((point) => point.cost || point.leads);
  if (rows.length < 4) return null;
  const mid = Math.floor(rows.length / 2);
  const sum = (part: TrendPoint[]) => part.reduce((acc, point) => ({ cost: acc.cost + point.cost, leads: acc.leads + point.leads }), { cost: 0, leads: 0 });
  const early = sum(rows.slice(0, mid));
  const late = sum(rows.slice(mid));
  const pct = (now: number, then: number) => (then > 0 ? Math.round(((now - then) / then) * 100) : null);
  const cpl = (part: { cost: number; leads: number }) => (part.leads > 0 ? part.cost / part.leads : null);
  const earlyCpl = cpl(early);
  const lateCpl = cpl(late);
  return {
    costPct: pct(late.cost, early.cost),
    leadsPct: pct(late.leads, early.leads),
    cplPct: earlyCpl && lateCpl ? Math.round(((lateCpl - earlyCpl) / earlyCpl) * 100) : null,
  };
}

function decisionLines(report: Report, shift: ReturnType<typeof periodShift>): string[] {
  const lines: string[] = [];
  if (report.advice) lines.push(report.advice);
  if (shift?.cplPct != null && Math.abs(shift.cplPct) >= 10) {
    lines.push(shift.cplPct > 0
      ? `هزینهٔ هر ورودی در نیمهٔ دوم این بازه ${toman(shift.cplPct)}٪ بیشتر از نیمهٔ اول است.`
      : `هزینهٔ هر ورودی در نیمهٔ دوم این بازه ${toman(Math.abs(shift.cplPct))}٪ کمتر از نیمهٔ اول است.`);
  }
  if (shift?.costPct != null && shift.costPct >= 15 && (shift.leadsPct == null || shift.leadsPct <= 0)) {
    lines.push("هزینه در نیمهٔ دوم بیشتر شده، ولی ورودی بیشتر نشده.");
  }
  for (const channel of report.channels) {
    if (channel.cost > 0 && !channel.leads) lines.push(`کانال ${channel.label} هزینه دارد و ورودی ثبت‌شده ندارد.`);
  }
  const priced = report.pages.filter((page) => page.cpl != null);
  const mid = median(priced.map((page) => page.cpl || 0));
  if (priced.length >= 4 && mid) {
    const worst = [...priced].sort((a, b) => (b.cpl || 0) - (a.cpl || 0))[0];
    if (worst?.cpl != null && worst.cpl > mid * 1.25) {
      lines.push(`پیج ${worst.name} از میانهٔ پیج‌ها گران‌تر تمام شده: ${compactToman(worst.cpl)} در برابر ${compactToman(mid)}.`);
    }
  }
  for (const note of report.notes) {
    if (!lines.some((line) => line.includes(note) || note.includes(line))) lines.push(note);
  }
  return lines.slice(0, 4);
}

function dayDetail(point: TrendPoint): string {
  const cpl = point.cost && point.leads ? Math.round(point.cost / point.leads) : null;
  const date = (formatJalali(point.day) || point.day).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);
  return [
    date,
    `هزینه ${compactToman(point.cost)}`,
    `ورودی ${leadsLabel(point.leads)}`,
    cpl != null ? `هزینه هر ورودی ${compactToman(cpl)}` : "",
  ].filter(Boolean).join(" · ");
}

function TrendChart({ trend, metric, title }: { trend: TrendPoint[]; metric: Metric; title: string }) {
  const points = trend.flatMap((point) => {
    const detail = dayDetail(point);
    if (metric === "cpl") {
      if (!point.cost || !point.leads) return [];
      return [{ label: point.day, value: Math.round(point.cost / point.leads), detail }];
    }
    return [{ label: point.day, value: metric === "cost" ? point.cost : point.leads, detail }];
  });
  if (!points.length) return <Muted><Bi en="Not enough points for this metric." fa="برای این معیار نقطهٔ کافی نیست." /></Muted>;
  return <LineTrend points={points} label={title} format={metric === "leads" ? toman : compactToman} />;
}

function ChannelShare({ channels }: { channels: Report["channels"] }) {
  const rows = channels.filter((item) => item.cost > 0);
  if (!rows.length) return <Muted><Bi en="No spend recorded yet." fa="هنوز هزینه‌ای ثبت نشده." /></Muted>;
  const total = rows.reduce((sum, item) => sum + item.cost, 0);
  return (
    <Donut
      size={168}
      centerLabel={compactToman(total)}
      caption="جمع هزینه"
      data={rows.map((item) => {
        const share = total ? Math.round((item.cost / total) * 100) : 0;
        const cpl = item.leads ? Math.round(item.cost / item.leads) : null;
        return { label: `${item.label} · ${toman(share)}٪${cpl != null ? ` · ${compactToman(cpl)}` : ""}`, value: item.cost };
      })}
      format={(value) => compactToman(value)}
    />
  );
}

function pageBand(page: ReportPage, avg: number | null): "better" | "worse" | "empty" | "flat" {
  if (page.cost > 0 && !page.leads) return "empty";
  if (page.cpl == null || avg == null || avg <= 0) return "flat";
  const gap = (page.cpl - avg) / avg;
  if (gap <= -0.08) return "better";
  if (gap >= 0.08) return "worse";
  return "flat";
}

function PageStatus({ page, avg }: { page: ReportPage; avg: number | null }) {
  const band = pageBand(page, avg);
  if (band === "empty") return <span className="perf-delta is-worse">ورودی ندارد</span>;
  if (page.cpl == null || avg == null || avg <= 0 || band === "flat") return <>—</>;
  const pct = Math.round((Math.abs(page.cpl - avg) / avg) * 100);
  if (band === "better") return <span className="perf-delta is-better">↓ {toman(pct)}٪ بهتر از میانه</span>;
  return <span className="perf-delta is-worse">↑ {toman(pct)}٪ بدتر از میانه</span>;
}

function BestPages({ pages, campaignId }: { pages: ReportPage[]; campaignId: string }) {
  const [band, setBand] = useState("all");
  const priced = pages.filter((page) => page.cpl != null);
  const avg = median(priced.map((page) => page.cpl || 0));
  const pool = pages.filter((page) => band === "all" || pageBand(page, avg) === band);
  const list = useArrange(pool, 8, PAGE_SORTS, (item) => [item.name], band);
  return (
    <Card>
      <SectionHeader
        title={<Bi en="Social pages" fa="پیج‌های سوشال" />}
        count={list.ordered.length}
        hint={avg != null ? <>میانهٔ هزینهٔ هر ورودی {compactToman(avg)}</> : undefined}
      />
      <ArrangeBar
        query={list.query}
        onQuery={list.setQuery}
        placeholder="اسم پیج"
        sortKey={list.sortKey}
        onSort={list.setSortKey}
        sorts={list.sorts}
        onReset={list.searching || list.sortChanged || band !== "all" ? () => { list.resetSort(); setBand("all"); } : undefined}
      >
        <Select aria-label="وضعیت" value={band} onChange={(event) => setBand(event.target.value)}>
          <option value="all">همهٔ وضعیت‌ها</option>
          <option value="better">بهتر از میانه</option>
          <option value="worse">بدتر از میانه</option>
          <option value="empty">بدون ورودی</option>
        </Select>
      </ArrangeBar>
      {pages.length === 0 ? <Muted as="p">هنوز پیجی در گزارش نیست.</Muted> : list.windowed.total === 0 ? <Muted as="p">پیجی با این فیلتر نیست.</Muted> : (
        <Table
          rows={list.windowed.rows}
          rowKey={(item) => item.name}
          columns={[
            { key: "name", header: "پیج", render: (item) => <Link to={`/perf/social?campaign=${campaignId}`}>{item.name}</Link> },
            { key: "cost", header: "هزینه", className: "perf-num", render: (item) => compactToman(item.cost) },
            { key: "views", header: "نمایش", className: "perf-num hide-sm", render: (item) => toman(item.views) },
            { key: "leads", header: "ورودی", className: "perf-num", render: (item) => leadsLabel(item.leads) },
            { key: "cpl", header: "هزینه هر ورودی", className: "perf-num", render: (item) => compactToman(item.cpl) },
            { key: "status", header: "وضعیت", render: (item) => <PageStatus page={item} avg={avg} /> },
          ]}
        />
      )}
      <ShowMore left={list.windowed.left} onMore={list.windowed.grow} />
    </Card>
  );
}
