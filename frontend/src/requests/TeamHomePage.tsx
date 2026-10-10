import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Card, EmptyState, ErrorMessage, LoadingState, Muted, PageHeader, SectionHeader } from "../components/ui";
import { Bi } from "../i18n";
import { faNum } from "../fa";
import { ApiError } from "../api";
import { requestsApi, type TeamHome } from "./api";

export function TeamHomePage() {
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
      />
      {data.sections.length > 0 ? (
        <div className="grid grid-2">
          {data.sections.map((section) => (
            <Link key={section.id} to={`/teams/${section.id}`}>
              <Card>
                <strong>{section.name}</strong>
                <Muted><Bi en="Open this section" fa="بخش این تیم" /></Muted>
              </Card>
            </Link>
          ))}
        </div>
      ) : null}
      <Card>
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
                <Link to="/requests">{row.code}</Link> {row.title} <Muted>{row.status}</Muted>
              </li>
            ))}
          </ul>
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
                  {row.team_name} · {row.status} · {faNum(row.progress.done)}/{faNum(row.progress.total)}
                </Muted>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
