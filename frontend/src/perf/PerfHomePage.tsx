import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Badge, Button, Card, EmptyState, ErrorMessage, ForbiddenState, List, ListItem, LoadingState, MoreMenu, PageHeader, SectionHeader, TitleCode } from "../components/ui";
import { isForbiddenError } from "../lib/apiError";
import { FaText } from "../components/FaText";
import { Bi, useBi } from "../i18n";
import { useAuth } from "../auth";
import { canSeePerfApi } from "../lib/access";
import { perfApi, toman, type Panel } from "./api";

export function PerfHomePage() {
  const bi = useBi();
  const { user, has } = useAuth();
  const accessUser = {
    roleCode: user?.roleCode,
    permissions: user?.permissions ?? [],
    teamId: user?.team_id,
    teamHomeTeamId: user?.team_home_team_id,
  };
  const perfOk = canSeePerfApi(accessUser, has);
  const home = useQuery({ queryKey: ["perf", "home"], queryFn: perfApi.home, enabled: perfOk });
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns, enabled: perfOk });
  if (!perfOk) return <ForbiddenState />;
  if (home.isLoading) return <LoadingState />;
  if (home.error) {
    if (isForbiddenError(home.error)) return <ForbiddenState />;
    return <ErrorMessage error={home.error} />;
  }
  const campaignsForbidden = campaigns.isError && isForbiddenError(campaigns.error);
  const data = home.data!;
  const low = data.panels.find((panel) => panel.low);
  const next = data.next[0];
  return (
    <>
      <PageHeader
        title={<Bi en="Performance" fa="پرفورمنس" />}
        description={<Bi en="SMS stays on its page. Social has its own flow. The campaign shows the result." fa="پیامک صفحهٔ خودش را دارد. سوشال فلوی جدا دارد. کمپین نتیجه را نشان می‌دهد." />}
        actions={
          <>
            {next ? (
              <Button to={next.href}>
                <Bi en="Next gap" fa="کار بعدی" />
              </Button>
            ) : (
              <Button to="/perf/campaigns">
                <Bi en="New campaign" fa="کمپین تازه" />
              </Button>
            )}
            <MoreMenu label={bi("More", "بیشتر")}>
              <Button variant="ghost" to="/perf/sheet">
                <Bi en="Sheet" fa="شیت" />
              </Button>
              <Button variant="ghost" to="/perf/insights">
                <Bi en="Social insights" fa="تحلیل سوشال" />
              </Button>
              <Button variant="ghost" to="/perf/connections">
                <Bi en="Connections" fa="اتصالات" />
              </Button>
            </MoreMenu>
          </>
        }
      />
      {low ? (
        <p className="banner banner-warn">
          <Bi en={`Low SMS balance: ${low.name}`} fa={`اعتبار کم در پنل ${low.name}`} />
        </p>
      ) : null}
      <Card>
        <SectionHeader icon="check" title={<Bi en="Campaign gaps" fa="جاهای ناقص کمپین‌ها" />} hint={<Bi en="Each row opens the campaign or its tool. It does not send, book, or pay." fa="هر ردیف کمپین یا ابزارش را باز می‌کند. ارسال، قرار و پرداخت همچنان با دکمه است." />} count={data.next.length} />
        {data.next.length ? (
          <List>
            {data.next.map((item) => (
              <ListItem key={item.href + item.title} tone={item.tone === "warn" ? "warn" : undefined}>
                <Link to={item.href}><FaText text={item.title} /></Link>
                <Badge tone={item.tone === "warn" ? "warn" : ""}><FaText text={item.label} /></Badge>
              </ListItem>
            ))}
          </List>
        ) : (
          <EmptyState titleEn="Nothing is waiting" titleFa="کار بازی نمانده" bodyEn="Active campaigns have a budget, pages, and a recorded send." bodyFa="کمپین‌های فعال بودجه، پیج و ارسال ثبت‌شده دارند." />
        )}
      </Card>
      <Card>
        <SectionHeader icon="flag" title={<Bi en="Campaigns" fa="کمپین‌ها" />} count={campaigns.data?.length} action={<Button variant="ghost" to="/perf/campaigns"><Bi en="All" fa="همه" /></Button>} />
        {campaignsForbidden ? (
          <ForbiddenState />
        ) : campaigns.isLoading ? (
          <LoadingState />
        ) : campaigns.error ? (
          <ErrorMessage error={campaigns.error} />
        ) : !campaigns.data?.length ? (
          <EmptyState titleEn="No campaign yet" titleFa="هنوز کمپینی نیست" bodyEn="Create one, then SMS and social attach to it." bodyFa="یکی بسازید. پیامک و سوشال به همان وصل می‌شوند." />
        ) : (
          <List>
            {[...campaigns.data].sort((a, b) => (b.cost_toman || 0) - (a.cost_toman || 0)).slice(0, 8).map((row) => (
              <ListItem key={row.id}>
                <Link to={`/perf/campaigns/${row.id}`}><TitleCode title={row.title} code={row.code} /></Link>
                <span className="muted">{row.brand} · {toman(row.cost_toman)} · <Bi en="CPL" fa="هزینه هر ورودی" /> {row.cpl ? toman(row.cpl) : "—"}</span>
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
