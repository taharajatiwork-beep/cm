import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Card, ErrorMessage, Field, Input, LoadingState, Muted, PageHeader, SectionHeader } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { useAuth } from "../auth";
import { Bi } from "../i18n";
import { perfApi, type Connections, type MizitoSnapshot, type SheetLink } from "./api";

const SHEETS: Array<{ key: string; fa: string; en: string }> = [
  { key: "report", fa: "شیت گزارش", en: "Report sheet" },
  { key: "register", fa: "دفتر شماره کمپین", en: "Campaign register" },
  { key: "costs", fa: "شیت هزینه", en: "Cost sheet" },
  { key: "reporter", fa: "ریپورتر", en: "Reporter" },
];

function sheetBadge(live: boolean, link: SheetLink | undefined) {
  if (!link?.configured) return <Badge><Bi en="Not set" fa="تنظیم نشده" /></Badge>;
  if (!live) return <Badge tone="warn"><Bi en="Ready to check" fa="آمادهٔ بررسی" /></Badge>;
  if (link.connected) return <Badge tone="ok"><Bi en="Connected" fa="وصل" /></Badge>;
  return <Badge tone="danger"><Bi en="Failed" fa="باز نشد" /></Badge>;
}

export function ConnectionsPage() {
  const { has } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [live, setLive] = useState(false);
  const [token, setToken] = useState("");
  const [probe, setProbe] = useState<MizitoSnapshot | null>(null);
  const status = useQuery({
    queryKey: ["perf", "connections", live],
    queryFn: () => perfApi.connections(live),
  });

  function save(next: string) {
    perfApi.saveMizito(next).then((result) => {
      setToken("");
      setProbe(null);
      qc.invalidateQueries({ queryKey: ["perf", "connections"] });
      toast(result.saved ? `توکن ذخیره شد${result.hint ? ` (${result.hint})` : ""}` : "توکن پاک شد");
    }).catch((error: Error) => toast(error.message));
  }

  function tryMizito() {
    setProbe(null);
    perfApi.refreshMizito().then((result) => {
      setProbe(result);
      qc.invalidateQueries({ queryKey: ["perf", "mizito"] });
      toast(result.connected ? `${result.open_count} کارت باز در صفحهٔ پول گذاشته شد` : (result.reason || "میزیتو وصل نشد"));
    }).catch((error: Error) => toast(error.message));
  }

  if (status.isLoading) return <LoadingState />;
  if (status.error || !status.data) return <ErrorMessage error={status.error instanceof Error ? status.error.message : "اتصالات خوانده نشد"} />;
  const data: Connections = status.data;

  return (
    <>
      <PageHeader
        title={<Bi en="Connections" fa="اتصالات" />}
        description={<Bi en="Where each outside system stands, and where the Mizito token is saved." fa="وضعیت هر اتصال بیرونی، و جایی که توکن میزیتو ذخیره می‌شود." />}
        actions={
          <Button type="button" variant="secondary" onClick={() => setLive(true)}>
            <Bi en="Check sheets" fa="بررسی شیت‌ها" />
          </Button>
        }
      />

      <Card>
        <SectionHeader
          icon="book"
          title={<Bi en="Google Sheets" fa="گوگل‌شیت" />}
          hint={data.service_account
            ? <Bi en={data.service_account} fa={data.service_account} />
            : <Bi en="The service account file is not set." fa="فایل حساب سرویس تنظیم نشده است." />}
        />
        <div className="form-grid">
          {SHEETS.map((item) => {
            const link = data.sheets[item.key];
            return (
              <div key={item.key}>
                <div className="row">
                  <strong><Bi en={item.en} fa={item.fa} /></strong>
                  {sheetBadge(live, link)}
                </div>
                {link?.title ? <Muted>{link.title}</Muted> : null}
                {live && link?.reason ? <Muted>{link.reason}</Muted> : null}
              </div>
            );
          })}
        </div>
        <Muted>
          <Bi
            en="Checking only reads the sheet title. It does not write rows."
            fa="بررسی فقط عنوان شیت را می‌خواند و ردیفی نمی‌نویسد."
          />
        </Muted>
      </Card>

      <Card>
        <SectionHeader
          icon="briefcase"
          title={<Bi en="Mizito" fa="میزیتو" />}
          hint={data.mizito.saved
            ? <Bi en={`Saved ${data.mizito.hint}`} fa={`ذخیره شده ${data.mizito.hint}`} />
            : <Bi en="No token yet" fa="هنوز توکنی ذخیره نشده" />}
          action={data.mizito.saved ? <Badge tone="ok"><Bi en="Token saved" fa="توکن هست" /></Badge> : <Badge tone="warn"><Bi en="Needs a token" fa="توکن لازم است" /></Badge>}
        />
        <ol className="perf-steps">
          <li>یک بار در <a href="https://office.mizito.ir" target="_blank" rel="noreferrer">office.mizito.ir</a> وارد شوید.</li>
          <li>در همان مرورگر ابزار توسعه را باز کنید (F12) و تب Network را انتخاب کنید.</li>
          <li>صفحه را تازه کنید و یک درخواست به app.mizito.ir را باز کنید.</li>
          <li>در Request Headers مقدار <strong>x-token</strong> را کپی کنید.</li>
          <li>همین‌جا بچسبانید و ذخیره کنید. این توکن روی سرور می‌ماند و از هر سیستم همین پنل کافی است.</li>
        </ol>
        <Muted>رمز عبور میزیتو ذخیره نمی‌شود. وقتی توکن منقضی شد، همین مراحل را تکرار کنید و مقدار تازه را جایگزین کنید.</Muted>
        {has("perf.write") ? (
          <div className="form-grid">
            <Field label={<Bi en="x-token" fa="توکن x-token" />}>
              <Input type="password" autoComplete="off" value={token} placeholder="از هدر درخواست کپی شود" onChange={(event) => setToken(event.target.value)} />
            </Field>
            <div className="row perf-actions">
              <Button type="button" disabled={!token.trim()} onClick={() => save(token)}><Bi en="Save" fa="ذخیره" /></Button>
              {data.mizito.saved ? <Button type="button" variant="secondary" onClick={() => save("")}><Bi en="Clear" fa="پاک کردن" /></Button> : null}
              <Button type="button" variant="secondary" onClick={tryMizito}><Bi en="Try" fa="امتحان اتصال" /></Button>
            </div>
          </div>
        ) : (
          <Muted>ذخیرهٔ توکن با دسترسی نوشتن پرفورمنس ممکن است.</Muted>
        )}
        {probe ? (
          <Muted>
            {probe.connected
              ? `${probe.open_count} کارت باز در ${probe.projects.length} پروژه. `
              : (probe.reason || "وصل نشد")}
            {probe.connected ? <Link to="/perf/money">لیست در صفحهٔ پول است.</Link> : null}
          </Muted>
        ) : null}
      </Card>

      <Card>
        <SectionHeader icon="message" title={<Bi en="SMS panels" fa="پنل‌های پیامک" />} />
        {data.panels.length === 0 ? <Muted>هنوز پنلی ثبت نشده است.</Muted> : (
          <div className="form-grid">
            {data.panels.map((panel) => (
              <div key={panel.code || panel.name} className="row">
                <strong>{panel.name}</strong>
                {panel.ready ? <Badge tone="ok"><Bi en="Login saved" fa="ورود ذخیره شده" /></Badge> : <Badge tone="warn"><Bi en="No API login" fa="ورود API نیست" /></Badge>}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <SectionHeader
          icon="sparkles"
          title={<Bi en="Insight reading" fa="خواندن اینسایت" />}
          action={data.insight.ready ? <Badge tone="ok"><Bi en="Key set" fa="کلید هست" /></Badge> : <Badge tone="warn"><Bi en="No key" fa="کلید نیست" /></Badge>}
        />
        <Muted>{data.insight.provider}</Muted>
      </Card>

      <Card>
        <SectionHeader icon="send" title={<Bi en="Telegram" fa="تلگرام" />} />
        <Link to="/settings"><Bi en="Open settings" fa="تنظیم در صفحهٔ تنظیمات" /></Link>
      </Card>
    </>
  );
}
