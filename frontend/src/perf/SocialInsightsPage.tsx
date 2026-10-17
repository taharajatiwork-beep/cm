import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, ErrorMessage, Muted, PageHeader, SectionHeader, StatCard, Table } from "../components/ui";
import { Bi } from "../i18n";
import { faNum } from "../fa";
import { formatJalaliDateTime } from "../jalali";
import { perfApi } from "./api";
import { SocialLinksEditor } from "./SocialLinksEditor";
import { SocialOverviewPanel } from "./SocialOverview";

function isoDaysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function SocialInsightsPage() {
  const qc = useQueryClient();
  const [refreshKey, setRefreshKey] = useState(0);
  const reportFrom = isoDaysAgo(6);
  const reportTo = todayIso();

  const overview = useQuery({
    queryKey: ["perf", "social", "overview", refreshKey],
    queryFn: () => perfApi.socialOverview(refreshKey > 0),
  });

  const report = useQuery({
    queryKey: ["perf", "social", "report", reportFrom, reportTo],
    queryFn: () => perfApi.socialReport(reportFrom, reportTo),
  });

  const syncMut = useMutation({
    mutationFn: () => perfApi.socialSync(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["perf", "social"] });
      setRefreshKey((k) => k + 1);
    },
  });

  const nh = overview.data?.novinhub;
  const vd = overview.data?.vardast;

  const novinhub = useQuery({ queryKey: ["perf", "novinhub"], queryFn: perfApi.novinhub });
  const novinhubAccountOptions = useMemo(
    () =>
      (novinhub.data?.accounts ?? []).map((row) => ({
        id: row.id,
        name: row.name || row.id,
      })),
    [novinhub.data?.accounts],
  );
  const vardastChannelOptions = useMemo(
    () =>
      (vd?.channels ?? []).map((row) => ({
        id: row.id,
        name: row.name || row.id,
      })),
    [vd?.channels],
  );

  const cur = report.data?.current;
  const prev = report.data?.previous_period;

  return (
    <>
      <PageHeader
        title={<Bi en="Social insights" fa="تحلیل سوشال" />}
        description={
          <Bi
            en="KPIs and 7-day trend from periodic hub updates. Drill down on Novin Hub / Vardast pages."
            fa="شاخص و روند ۷ روزه از به‌روزرسانی دوره‌ای. جزئیات در صفحات نوین‌هاب و وردست."
          />
        }
        actions={
          <>
            <Button variant="ghost" to="/perf/novinhub"><Bi en="Novin Hub" fa="نوین هاب" /></Button>
            <Button variant="ghost" to="/perf/vardast"><Bi en="Vardast" fa="وردست" /></Button>
            <Button type="button" onClick={() => syncMut.mutate()} disabled={syncMut.isPending}>
              <Bi en="Sync now" fa="همگام‌سازی الان" />
            </Button>
            <Button type="button" onClick={() => setRefreshKey((k) => k + 1)}>
              <Bi en="Refresh data" fa="تازه‌سازی داده" />
            </Button>
          </>
        }
      />
      {overview.data?.last_sync_at ? (
        <Muted>
          <Bi
            en={`Last sync: ${overview.data.last_sync_at}`}
            fa={`آخرین همگام‌سازی: ${formatJalaliDateTime(overview.data.last_sync_at)}`}
          />
        </Muted>
      ) : null}
      {syncMut.error ? <ErrorMessage error={syncMut.error} /> : null}

      <SocialOverviewPanel refreshToken={refreshKey} showAiLink />

      <Card>
        <SectionHeader
          icon="activity"
          title={<Bi en="7-day trend" fa="روند ۷ روزه" />}
          hint={<Bi en={`${reportFrom} → ${reportTo}`} fa={`${reportFrom} → ${reportTo}`} />}
        />
        {report.isLoading ? (
          <p className="muted fine"><Bi en="Loading…" fa="بارگذاری…" /></p>
        ) : report.error ? (
          <ErrorMessage error={report.error} />
        ) : !report.data?.days.length ? (
          <p className="muted fine">
            <Bi
              en="No daily history yet — run Sync now or wait for the next scheduled sync."
              fa="هنوز تاریخچهٔ روزانه نیست — «همگام‌سازی الان» بزنید یا همگام‌سازی بعدی را صبر کنید."
            />
          </p>
        ) : (
          <>
            <div className="kpi-grid">
              <StatCard
                icon="message"
                label={<Bi en="Avg open comments" fa="میانگین کامنت باز" />}
                value={cur?.avg_comments_open != null ? faNum(cur.avg_comments_open) : "—"}
                hint={
                  prev?.avg_comments_open != null
                    ? <Bi en={`Prev period: ${prev.avg_comments_open}`} fa={`بازه قبل: ${prev.avg_comments_open}`} />
                    : undefined
                }
              />
              <StatCard
                icon="chat"
                label={<Bi en="Avg open directs" fa="میانگین دایرکت باز" />}
                value={cur?.avg_conversations_open != null ? faNum(cur.avg_conversations_open) : "—"}
                hint={
                  prev?.avg_conversations_open != null
                    ? <Bi en={`Prev period: ${prev.avg_conversations_open}`} fa={`بازه قبل: ${prev.avg_conversations_open}`} />
                    : undefined
                }
              />
              <StatCard
                icon="calendar"
                label={<Bi en="Days with data" fa="روز با داده" />}
                value={faNum(cur?.days_with_data ?? 0)}
              />
            </div>
            <Table
              rows={report.data.days}
              rowKey={(row) => row.day}
              columns={[
                { key: "day", header: <Bi en="Day" fa="روز" />, render: (row) => row.day },
                { key: "c", header: <Bi en="Comments open" fa="کامنت باز" />, render: (row) => faNum(row.comments_open_est) },
                { key: "d", header: <Bi en="Directs open" fa="دایرکت باز" />, render: (row) => faNum(row.conversations_open_est) },
                {
                  key: "cr",
                  header: <Bi en="Vardast credit" fa="اعتبار وردست" />,
                  render: (row) => (row.vardast_chat_credit != null ? faNum(row.vardast_chat_credit) : "—"),
                },
              ]}
            />
          </>
        )}
      </Card>

      <SocialLinksEditor
        novinhubAccountOptions={novinhubAccountOptions}
        vardastChannelOptions={vardastChannelOptions}
      />

      <div className="fill-row">
        <Card>
          <SectionHeader icon="message" title={<Bi en="Comments by account" fa="کامنت به تفکیک اکانت" />} />
          {nh?.comments_by_account?.length ? (
            <Table
              rows={nh.comments_by_account}
              rowKey={(row) => row.account}
              columns={[
                { key: "account", header: <Bi en="Account" fa="اکانت" />, render: (row) => row.account },
                { key: "count", header: <Bi en="In sample" fa="در نمونه" />, render: (row) => faNum(row.count) },
              ]}
            />
          ) : (
            <p className="muted fine"><Bi en="No sample yet." fa="هنوز نمونه‌ای نیست." /></p>
          )}
        </Card>
        <Card>
          <SectionHeader icon="chat" title={<Bi en="Directs by account" fa="دایرکت به تفکیک اکانت" />} />
          {nh?.conversations_by_account?.length ? (
            <Table
              rows={nh.conversations_by_account}
              rowKey={(row) => row.account}
              columns={[
                { key: "account", header: <Bi en="Account" fa="اکانت" />, render: (row) => row.account },
                { key: "count", header: <Bi en="In sample" fa="در نمونه" />, render: (row) => faNum(row.count) },
              ]}
            />
          ) : (
            <p className="muted fine"><Bi en="No sample yet." fa="هنوز نمونه‌ای نیست." /></p>
          )}
        </Card>
      </div>

      <Card>
        <SectionHeader icon="sparkles" title={<Bi en="Vardast channels" fa="کانال‌های وردست" />} count={vd?.channels?.length} />
        {vd?.channels?.length ? (
          <Table
            rows={vd.channels}
            rowKey={(row) => row.id || row.name}
            columns={[
              { key: "name", header: <Bi en="Name" fa="نام" />, render: (row) => row.name },
              { key: "platform", header: <Bi en="Platform" fa="پلتفرم" />, render: (row) => row.platform || "—" },
            ]}
          />
        ) : (
          <p className="muted fine"><Bi en="Connect Vardast or refresh data." fa="وردست را در اتصالات وصل کنید یا «تازه‌سازی داده» بزنید." /></p>
        )}
      </Card>
    </>
  );
}
