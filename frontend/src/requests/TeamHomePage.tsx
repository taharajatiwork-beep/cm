import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Button, Card, EmptyState, ErrorMessage, LoadingState, Muted, PageHeader, SectionHeader, StatCard } from "../components/ui";
import { Bi } from "../i18n";
import { faNum } from "../fa";
import { ApiError } from "../api";
import { requestStatusLabel } from "./labels";
import { PROJECT_STATUS_LABEL } from "./ProjectsPage";
import { useAuth } from "../auth";
import { requestsApi, type TeamHome } from "./api";

export function TeamHomePage() {
  const { has } = useAuth();
  const canOpenCampaigns = has("campaign.read");
  const { teamId = "" } = useParams();
  const home = useQuery({
    queryKey: ["team-home", teamId],
    queryFn: () => requestsApi.teamHome(teamId),
    enabled: Boolean(teamId),
  });

  if (home.isLoading) return <LoadingState />;
  if (home.error) {
    const message = home.error instanceof ApiError ? home.error.message : String(home.error);
    return <ErrorMessage error={message} />;
  }
  const data = home.data as TeamHome;
  return (
    <>
      <PageHeader
        title={data.team.name}
        description={
          data.shared ? (
            <Bi en="Shared home for this section and its teams." fa="خانهٔ مشترک این بخش و تیم‌های زیرش." />
          ) : (
            <Bi en="This section has no sub-teams." fa="این بخش زیرتیم ندارد." />
          )
        }
        actions={
          data.can_edit && (data.counts?.open_requests ?? data.requests.length) > 0 ? (
            <Button to="/requests">
              <Bi en="Review requests" fa="بررسی درخواست‌ها" />
            </Button>
          ) : undefined
        }
      />
      <div className="kpi-row kpi-row--4">
        {data.can_edit ? (
          <StatCard icon="megaphone" tone="warn" label={<Bi en="Open requests" fa="درخواست باز" />} value={faNum(data.counts?.open_requests ?? data.requests.length)} to="/requests" />
        ) : null}
        <StatCard icon="layers" tone="accent" label={<Bi en="Projects in progress" fa="پروژه در جریان" />} value={faNum(data.counts?.active_projects ?? data.projects.length)} to="/projects" />
        <StatCard icon="flag" tone="ai" label={<Bi en="Active campaigns" fa="کمپین فعال" />} value={faNum(data.counts?.active_campaigns ?? data.campaigns?.length ?? 0)} />
        <StatCard icon="activity" tone="ok" label={<Bi en="Reports" fa="گزارش" />} value={<Bi en="Open" fa="باز کردن" />} to="/reports" />
      </div>
      <Card>
        <SectionHeader title={<Bi en="In this section" fa="کارهای این بخش" />} />
        <div className="row perf-actions">
          <Link to="/projects"><Bi en="Projects" fa="پروژه‌ها" /></Link>
          <Link to="/reports"><Bi en="Reports" fa="گزارش‌ها" /></Link>
        </div>
      </Card>
      {data.can_edit ? <Card>
        <SectionHeader title={<Bi en="Incoming requests" fa="درخواست‌های ورودی" />} count={data.requests.length} />
        {data.requests.length === 0 ? (
          <EmptyState
            titleEn="No requests"
            titleFa="درخواستی نیست"
            bodyEn="Requests assigned to this team will appear here."
            bodyFa="درخواست‌های متصل به این تیم همین‌جا نمایش داده می‌شوند."
          />
        ) : (
          <ul>
            {data.requests.map((row) => (
              <li key={row.id}>
                <Link to={`/requests/${row.id}`}>{row.code}</Link> {row.title} <Muted>{requestStatusLabel(row.status)}</Muted>
              </li>
            ))}
          </ul>
        )}
      </Card> : null}
      <Card>
        <SectionHeader title={<Bi en="Campaigns" fa="کمپین‌ها" />} count={data.campaigns?.length ?? 0} />
        {(data.campaigns ?? []).length === 0 ? (
          <EmptyState
            titleEn="No campaign"
            titleFa="کمپینی نیست"
            bodyEn="Ask the marketing lead to attach campaigns to team projects."
            bodyFa="از سرپرست مارکتینگ بخواهید کمپین به پروژه‌های تیم وصل کند."
          />
        ) : (
          <>
            {!canOpenCampaigns ? (
              <Muted as="p">
                <Bi en="Details live with the marketing lead." fa="جزئیات با سرپرست مارکتینگ است." />
              </Muted>
            ) : null}
            <ul>
              {(data.campaigns ?? []).map((row) => (
                <li key={row.id}>
                  {canOpenCampaigns ? (
                    <Link to={`/perf/campaigns/${row.id}`}>{row.code} — {row.title}</Link>
                  ) : (
                    <span>{row.code} — {row.title}</span>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>
      <Card>
        <SectionHeader title={<Bi en="Projects" fa="پروژه‌ها" />} count={data.projects.length} />
        {data.projects.length === 0 ? (
          <EmptyState
            titleEn="No projects"
            titleFa="پروژه‌ای نیست"
            bodyEn="Projects created from these requests will appear here."
            bodyFa="پروژه‌هایی که از این درخواست‌ها ساخته می‌شوند همین‌جا نمایش داده می‌شوند."
          />
        ) : (
          <ul>
            {data.projects.map((row) => (
              <li key={row.id}>
                {data.own_section ? <Link to={`/projects/${row.id}`}>{row.title}</Link> : row.title}
                {" "}
                <Muted>
                  {row.request_code ? (
                    <>
                      <Bi en="From request" fa="از درخواست" /> <span dir="ltr">{row.request_code}</span> ·{" "}
                    </>
                  ) : null}
                  {row.team_name} · {PROJECT_STATUS_LABEL[row.status] ?? row.status} · {faNum(row.progress.done)}/{faNum(row.progress.total)}
                </Muted>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
