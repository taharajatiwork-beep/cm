import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Badge, Button, Card, EmptyState, ErrorMessage, List, ListItem, LoadingState, PageHeader, SectionHeader, StatCard } from "../components/ui";
import { Bi } from "../i18n";
import { perfApi, toman, type Panel } from "./api";

export function PerfHomePage() {
  const home = useQuery({ queryKey: ["perf", "home"], queryFn: perfApi.home });
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  if (home.isLoading) return <LoadingState />;
  if (home.error) return <ErrorMessage error={home.error instanceof Error ? home.error.message : String(home.error)} />;
  const data = home.data!;
  const low = data.panels.find((panel) => panel.low);
  return (
    <>
      <PageHeader
        title={<Bi en="Performance" fa="پرفورمنس" />}
        description={<Bi en="SMS stays on its page. Social has its own flow. The campaign shows the result." fa="پیامک صفحهٔ خودش را دارد. سوشال فلوی جدا دارد. کمپین نتیجه را نشان می‌دهد." />}
        actions={<Button variant="secondary" to="/perf/sheet"><Bi en="Sheet" fa="شیت" /></Button>}
      />
      <div className="kpi-row kpi-row--3 kpi-row--even">
        <StatCard icon="megaphone" tone="accent" label={<Bi en="Active" fa="کمپین فعال" />} value={toman(data.active_campaigns.length)} hint={campaigns.data ? <Bi en="of all campaigns" fa={`از ${toman(campaigns.data.length)}`} /> : <Bi en="open one" fa="یکی را باز کنید" />} to="/perf/campaigns" />
        <StatCard icon="alert" tone={data.waiting_payments ? "warn" : "ok"} label={<Bi en="Payments" fa="پرداخت" />} value={toman(data.waiting_payments)} hint={<Bi en="waiting" fa="منتظر تأیید" />} to="/perf/money" />
        <StatCard icon="message" tone={low ? "warn" : "neutral"} label={<Bi en="SMS panels" fa="پنل پیامک" />} value={toman(data.panels.length)} hint={low ? low.name : data.panels.map((panel) => panel.name).join(" · ") || <Bi en="none" fa="پنلی نیست" />} to="/perf/sms" />
      </div>
      <Card>
        <SectionHeader icon="check" title={<Bi en="Next" fa="کار بعدی" />} hint={<Bi en="Opening one prepares the draft, the check, the page list, or the insight form. It does not send, book, or pay." fa="باز کردن، متن و چک، چیدن پیج، یا فرم اینسایت را آماده می‌کند. ارسال، قرار و پرداخت همچنان با دکمه است." />} count={data.next.length} />
        {data.next.length ? (
          <List>
            {data.next.map((item) => (
              <ListItem key={item.href + item.title} tone={item.tone === "warn" ? "warn" : undefined}>
                <Link to={item.href}>{item.title}</Link>
                <Badge tone={item.tone === "warn" ? "warn" : ""}>{item.label}</Badge>
              </ListItem>
            ))}
          </List>
        ) : (
          <EmptyState titleEn="Nothing is waiting" titleFa="کار بازی نمانده" bodyEn="Active campaigns have a budget, pages, and a recorded send." bodyFa="کمپین‌های فعال بودجه، پیج و ارسال ثبت‌شده دارند." />
        )}
      </Card>
      <Card>
        <SectionHeader icon="flag" title={<Bi en="Campaigns" fa="کمپین‌ها" />} count={campaigns.data?.length} action={<Button variant="ghost" to="/perf/campaigns"><Bi en="All" fa="همه" /></Button>} />
        {!campaigns.data?.length ? (
          <EmptyState titleEn="No campaign yet" titleFa="هنوز کمپینی نیست" bodyEn="Create one, then SMS and social attach to it." bodyFa="یکی بسازید. پیامک و سوشال به همان وصل می‌شوند." />
        ) : (
          <List>
            {[...campaigns.data].sort((a, b) => (b.cost_toman || 0) - (a.cost_toman || 0)).slice(0, 8).map((row) => (
              <ListItem key={row.id}>
                <Link to={`/perf/campaigns/${row.id}`}>{row.code} — {row.title}</Link>
                <span className="muted">{row.brand} · {toman(row.cost_toman)} · CPL {row.cpl ? toman(row.cpl) : "—"}</span>
              </ListItem>
            ))}
          </List>
        )}
      </Card>
      <div className="grid grid-2">
        {data.panels.map((panel) => (
          <PanelCard key={panel.id} panel={panel} />
        ))}
      </div>
    </>
  );
}

function PanelCard({ panel }: { panel: Panel }) {
  return (
    <Card>
      <SectionHeader
        icon="message"
        title={<Link to="/perf/sms">{panel.name}</Link>}
        hint={panel.sender_line}
        action={panel.low ? <Badge tone="warn"><Bi en="Low" fa="کم" /></Badge> : <Badge tone="ok"><Bi en="Ok" fa="کافی" /></Badge>}
      />
      <p className="perf-balance">
        <span className="kpi-value">{toman(panel.balance_toman)}</span>
        <span className="muted"><Bi en="left" fa="مانده" /></span>
      </p>
      <p className="muted">
        <Bi en="Charged" fa="شارژ تأییدشده" /> {toman(panel.charged_toman || 0)}
        {" · "}
        <Bi en="Spent" fa="مصرف ارسال" /> {toman(panel.spent_toman || 0)}
      </p>
    </Card>
  );
}
