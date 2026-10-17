import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button, Card, LoadingState, Muted, SectionHeader } from "../components/ui";
import { Bi } from "../i18n";
import { faNum } from "../fa";
import { perfApi } from "./api";

export function CampaignSocialCard({ campaignId }: { campaignId: string }) {
  const social = useQuery({
    queryKey: ["perf", "campaign", campaignId, "social"],
    queryFn: () => perfApi.campaignSocial(campaignId),
  });

  if (social.isLoading) return <LoadingState block={false} />;
  if (social.isError || !social.data) return null;

  const data = social.data;
  const daily = data.latest_daily;
  const show =
    data.has_links ||
    daily ||
    data.novinhub_accounts.length > 0 ||
    data.vardast_channels.length > 0;

  if (!show && !daily) {
    return (
      <Card className="no-print">
        <SectionHeader icon="activity" title={<Bi en="Social & automation" fa="سوشال و اتوماسیون" />} />
        <Muted as="p">
          <Bi
            en="Link Novin accounts or Vardast channels to this campaign under Social insights."
            fa="در «تحلیل سوشال» اکانت نوین‌هاب یا کانال وردست را به این کمپین وصل کنید."
          />{" "}
          <Link to="/perf/insights"><Bi en="Social insights" fa="تحلیل سوشال" /></Link>
        </Muted>
      </Card>
    );
  }

  return (
    <Card className="no-print">
      <SectionHeader
        icon="activity"
        title={<Bi en="Social & automation" fa="سوشال و اتوماسیون" />}
        action={
          <Button variant="ghost" to="/perf/insights">
            <Bi en="Full insights" fa="تحلیل کامل" />
          </Button>
        }
      />
      {data.novinhub_accounts.length ? (
        <p className="fine">
          <Bi en="Novin Hub" fa="نوین‌هاب" />:{" "}
          {data.novinhub_accounts.map((a) => `${a.page_name || a.account_id}`).join(" · ")}
        </p>
      ) : null}
      {data.vardast_channels.length ? (
        <p className="fine">
          <Bi en="Vardast channels" fa="کانال وردست" />: {faNum(data.vardast_channels.length)}
        </p>
      ) : null}
      {daily ? (
        <p className="muted fine">
          <Bi en={`Latest sync ${daily.day}: ~${daily.comments_open_est} open comments, ~${daily.conversations_open_est} directs`} fa={`آخرین sync ${daily.day}: ~${faNum(daily.comments_open_est)} کامنت باز، ~${faNum(daily.conversations_open_est)} دایرکت`} />
        </p>
      ) : null}
      <div className="toolbar">
        <Button variant="ghost" to="/perf/novinhub"><Bi en="Novin Hub" fa="نوین هاب" /></Button>
        <Button variant="ghost" to="/perf/vardast"><Bi en="Vardast" fa="وردست" /></Button>
        <Button variant="ghost" to={`/ai-lab?kind=social_inbox_review`}><Bi en="AI analysis" fa="تحلیل AI" /></Button>
      </div>
    </Card>
  );
}
