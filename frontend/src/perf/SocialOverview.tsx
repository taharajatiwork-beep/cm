import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button, Card, ErrorMessage, LoadingState, SectionHeader, StatCard } from "../components/ui";
import { Bi } from "../i18n";
import { faNum } from "../fa";
import { perfApi, type SocialOverviewSnapshot } from "./api";

function statusRows(map: Record<string, number> | undefined): string {
  if (!map) return "—";
  const entries = Object.entries(map).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return "—";
  return entries.slice(0, 4).map(([k, v]) => `${k}: ${faNum(v)}`).join(" · ");
}

export function SocialOverviewPanel({
  refreshToken = 0,
  showAiLink = true,
  compact = false,
}: {
  refreshToken?: number;
  showAiLink?: boolean;
  compact?: boolean;
}) {
  const overview = useQuery({
    queryKey: ["perf", "social", "overview", refreshToken],
    queryFn: () => perfApi.socialOverview(refreshToken > 0),
  });

  if (overview.isLoading) return <LoadingState />;
  if (overview.isError) return <ErrorMessage error={overview.error} />;

  const data = overview.data as SocialOverviewSnapshot;
  const nh = data.novinhub;
  const vd = data.vardast;

  return (
    <Card>
      <SectionHeader
        icon="activity"
        title={<Bi en="Social & automation" fa="سوشال و اتوماسیون" />}
        hint={
          <Bi
            en={data.cached ? `Cached · ${data.rollup_at ?? ""}` : `Refreshed · ${data.rollup_at ?? ""}`}
            fa={data.cached ? `از cache · ${data.rollup_at ?? ""}` : `تازه · ${data.rollup_at ?? ""}`}
          />
        }
        action={
          <div className="toolbar">
            {showAiLink ? (
              <Button variant="ghost" to="/ai-lab?kind=social_inbox_review">
                <Bi en="Analyze in AI Lab" fa="تحلیل در AI Lab" />
              </Button>
            ) : null}
            {!compact ? (
              <Button variant="ghost" to="/perf/insights">
                <Bi en="Full report" fa="گزارش کامل" />
              </Button>
            ) : null}
          </div>
        }
      />
      <div className="kpi-grid">
        <StatCard
          icon="message"
          label={<Bi en="Open comments (est.)" fa="کامنت باز (تخمین)" />}
          value={nh?.connected ? faNum(nh.comments_open_est ?? 0) : "—"}
          hint={statusRows(nh?.comments_by_status)}
          tone={nh?.comments_open_est && nh.comments_open_est >= 5 ? "warn" : "neutral"}
          to="/perf/novinhub"
        />
        <StatCard
          icon="chat"
          label={<Bi en="Open directs (est.)" fa="دایرکت باز (تخمین)" />}
          value={nh?.connected ? faNum(nh.conversations_open_est ?? 0) : "—"}
          hint={statusRows(nh?.conversations_by_status)}
          tone={nh?.conversations_open_est && nh.conversations_open_est >= 5 ? "warn" : "neutral"}
          to="/perf/novinhub"
        />
        <StatCard
          icon="sparkles"
          label={<Bi en="Vardast chat credit" fa="اعتبار گفتگو وردست" />}
          value={
            vd?.connected && vd.usage?.chat_credit != null ? faNum(vd.usage.chat_credit) : "—"
          }
          hint={
            vd?.channel_count
              ? <Bi en={`${vd.channel_count} channels`} fa={`${faNum(vd.channel_count)} کانال`} />
              : vd?.reason
          }
          tone={vd?.low_chat_credit ? "warn" : "ok"}
          to="/perf/vardast"
        />
        <StatCard
          icon="plug"
          label={<Bi en="Novin accounts" fa="اکانت نوین‌هاب" />}
          value={nh?.connected ? faNum(nh.account_count ?? 0) : "—"}
          hint={
            nh?.accounts_needing_login
              ? <Bi en={`${nh.accounts_needing_login} need reconnect`} fa={`${faNum(nh.accounts_needing_login)} نیاز به اتصال`} />
              : <Bi en="Assistants" fa="دستیارها" />
          }
          tone={nh?.accounts_needing_login ? "danger" : "neutral"}
          to="/perf/connections"
        />
      </div>
      {!compact && (nh?.comment_snippets?.length || nh?.direct_snippets?.length) ? (
        <div className="fill-row" style={{ marginTop: "1rem" }}>
          {nh.comment_snippets?.length ? (
            <div>
              <h4 className="fine muted"><Bi en="Recent comment themes" fa="نمونهٔ کامنت‌ها" /></h4>
              <ul className="plain-list">
                {nh.comment_snippets.map((row, i) => (
                  <li key={i}>
                    <span className="muted">{row.account}</span> — {row.snippet}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {nh.direct_snippets?.length ? (
            <div>
              <h4 className="fine muted"><Bi en="Recent direct themes" fa="نمونهٔ دایرکت‌ها" /></h4>
              <ul className="plain-list">
                {nh.direct_snippets.map((row, i) => (
                  <li key={i}>
                    <span className="muted">{row.account}</span> — {row.snippet}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
      {!nh?.connected && !vd?.connected ? (
        <p className="muted fine">
          <Bi en="Connect Novin Hub or Vardast under Connections." fa="از اتصالات نوین‌هاب یا وردست را وصل کنید." />{" "}
          <Link to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Link>
        </p>
      ) : null}
    </Card>
  );
}
