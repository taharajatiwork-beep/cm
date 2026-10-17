import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Badge, Button, Card, ErrorMessage, LoadingState, Muted, PageHeader, SectionHeader, Segmented, Table } from "../components/ui";
import { Bi } from "../i18n";
import { perfApi, toman } from "./api";

type Tab = "accounts" | "comments" | "directs" | "automation";

function loginBadge(required: boolean) {
  if (required) {
    return <Badge tone="danger"><Bi en="Reconnect needed" fa="اتصال قطع" /></Badge>;
  }
  return <Badge tone="ok"><Bi en="Connected" fa="وصل" /></Badge>;
}

export function NovinHubPage() {
  const [tab, setTab] = useState<Tab>("automation");
  const home = useQuery({ queryKey: ["perf", "novinhub"], queryFn: () => perfApi.novinhub() });
  const automation = useQuery({
    queryKey: ["perf", "novinhub", "automation"],
    queryFn: () => perfApi.novinhubAutomation(),
    enabled: tab === "automation",
  });
  const comments = useQuery({
    queryKey: ["perf", "novinhub", "comments"],
    queryFn: () => perfApi.novinhubComments(40),
    enabled: tab === "comments",
  });
  const conversations = useQuery({
    queryKey: ["perf", "novinhub", "conversations"],
    queryFn: () => perfApi.novinhubConversations(40),
    enabled: tab === "directs",
  });

  if (home.isLoading) return <LoadingState />;
  if (home.isError) {
    return (
      <>
        <PageHeader title={<Bi en="Novin Hub" fa="نوین هاب" />} actions={<Button variant="ghost" to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Button>} />
        <ErrorMessage error={home.error} />
      </>
    );
  }

  const data = home.data!;
  if (!data.connected) {
    return (
      <>
        <PageHeader title={<Bi en="Novin Hub" fa="نوین هاب" />} actions={<Button variant="ghost" to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Button>} />
        <ErrorMessage friendly message={data.reason || "اتصال نوین‌هاب برقرار نیست."} />
        <Muted><Link to="/perf/connections">اتصالات</Link></Muted>
      </>
    );
  }

  const disconnected = data.accounts.filter((row) => row.login_required).length;

  return (
    <>
      <PageHeader title={<Bi en="Novin Hub" fa="نوین هاب" />} actions={<Button variant="ghost" to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Button>} />
      <Segmented<Tab>
        value={tab}
        onChange={setTab}
        items={[
          { key: "automation", label: <Bi en="Automation" fa="اتوماسیون" /> },
          { key: "accounts", label: <Bi en="Accounts" fa="اکانت‌ها" />, count: data.accounts.length },
          { key: "comments", label: <Bi en="Comments" fa="کامنت‌ها" /> },
          { key: "directs", label: <Bi en="Directs" fa="دایرکت‌ها" /> },
        ]}
      />
      {disconnected > 0 ? (
        <Card>
          <Muted><Bi en={`${disconnected} account(s) need reconnect.`} fa={`${disconnected} اکانت باید در نوین‌هاب دوباره وصل شود.`} /></Muted>
        </Card>
      ) : null}

      {tab === "automation" ? (
        automation.isLoading ? <LoadingState /> : (
          <div className="fill-row">
            <Card>
              <SectionHeader icon="message" title={<Bi en="Latest comments" fa="آخرین کامنت‌ها" />} />
              {automation.data?.comments.ok === false ? <ErrorMessage friendly={false} message={automation.data.comments.reason} /> : null}
              {automation.data?.comments.ok ? (
                <Muted>
                  {toman(automation.data.comments.total ?? automation.data.comments.items.length)} مورد (صفحهٔ اول)
                </Muted>
              ) : null}
              {automation.data?.comments.items?.length ? (
                <Table
                  rows={automation.data.comments.items}
                  rowKey={(row) => row.id}
                  columns={[
                    { key: "account", header: "اکانت", render: (row) => row.account_name || row.account_id },
                    { key: "text", header: "متن", render: (row) => row.text },
                    { key: "date", header: "زمان", className: "hide-sm cell-nowrap", render: (row) => row.date },
                  ]}
                />
              ) : automation.data?.comments.ok ? <Muted>کامنتی در صفحهٔ اول نیست.</Muted> : null}
            </Card>
            <Card>
              <SectionHeader icon="message" title={<Bi en="Latest directs" fa="آخرین دایرکت‌ها" />} />
              {automation.data?.conversations.ok === false ? <ErrorMessage friendly={false} message={automation.data.conversations.reason} /> : null}
              {automation.data?.conversations.ok ? (
                <Muted>
                  {toman(automation.data.conversations.total ?? automation.data.conversations.items.length)} مورد (صفحهٔ اول)
                </Muted>
              ) : null}
              {automation.data?.conversations.items?.length ? (
                <Table
                  rows={automation.data.conversations.items}
                  rowKey={(row) => row.id}
                  columns={[
                    { key: "account", header: "اکانت", render: (row) => row.account_name || row.account_id },
                    { key: "msg", header: "آخرین پیام", render: (row) => row.last_message },
                    { key: "date", header: "زمان", className: "hide-sm cell-nowrap", render: (row) => row.update_date },
                  ]}
                />
              ) : automation.data?.conversations.ok ? <Muted>مکالمه‌ای در صفحهٔ اول نیست.</Muted> : null}
            </Card>
          </div>
        )
      ) : null}

      {tab === "accounts" ? (
        <Card>
          <SectionHeader icon="message" title={<Bi en="Accounts" fa="اکانت‌ها" />} count={data.accounts.length} />
          <Table
            rows={data.accounts}
            rowKey={(row) => row.id || row.name}
            columns={[
              { key: "name", header: "نام", render: (row) => row.name },
              { key: "type", header: "نوع", className: "cell-nowrap", render: (row) => row.type || "—" },
              { key: "login", header: "اتصال", render: (row) => loginBadge(row.login_required) },
              { key: "automation", header: "پاسخ هوشمند", className: "hide-sm", render: (row) => row.automation_status || "—" },
            ]}
          />
        </Card>
      ) : null}

      {tab === "comments" ? (
        <Card>
          <SectionHeader icon="message" title={<Bi en="Comments" fa="کامنت‌ها" />} />
          {comments.isLoading ? <LoadingState /> : null}
          {comments.data && !comments.data.ok ? <ErrorMessage friendly={false} message={comments.data.reason} /> : null}
          {comments.data?.ok ? (
            <Table
              rows={comments.data.items}
              rowKey={(row) => row.id}
              columns={[
                { key: "account", header: "اکانت", render: (row) => row.account_name || row.account_id },
                { key: "text", header: "متن", render: (row) => row.text },
                { key: "social", header: "شبکه", className: "hide-sm", render: (row) => row.social || "—" },
                { key: "date", header: "زمان", className: "hide-sm", render: (row) => row.date },
              ]}
            />
          ) : null}
        </Card>
      ) : null}

      {tab === "directs" ? (
        <Card>
          <SectionHeader icon="message" title={<Bi en="Conversations" fa="مکالمه‌ها" />} />
          {conversations.isLoading ? <LoadingState /> : null}
          {conversations.data && !conversations.data.ok ? <ErrorMessage friendly={false} message={conversations.data.reason} /> : null}
          {conversations.data?.ok ? (
            <Table
              rows={conversations.data.items}
              rowKey={(row) => row.id}
              columns={[
                { key: "account", header: "اکانت", render: (row) => row.account_name || row.account_id },
                { key: "msg", header: "آخرین پیام", render: (row) => row.last_message },
                { key: "date", header: "زمان", className: "hide-sm", render: (row) => row.update_date },
              ]}
            />
          ) : null}
        </Card>
      ) : null}

      <Muted><Bi en="Read-only automation — no POST to Novin Hub from CM." fa="اتوماسیون فقط‌خواندنی — CM به نوین‌هاب POST نمی‌زند." /></Muted>
    </>
  );
}
