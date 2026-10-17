import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Card, ErrorMessage, Field, Input, LoadingState, Muted, PageHeader, SectionHeader } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { DateText } from "../components/DateText";
import { useAuth } from "../auth";
import { Bi } from "../i18n";
import { requestsApi } from "../requests/api";
import { perfApi, toman, type Connections, type SheetLink } from "./api";
import { exactError, OutcomePop, type Outcome } from "./bits";
import { liveConnectionsQuery, savedConnectionsQuery, useLiveConnections, useSavedConnections } from "./connectionsQuery";

const SHEETS: Array<{ key: string; fa: string; en: string; help: string }> = [
  {
    key: "report",
    fa: "شیت گزارش",
    en: "Report sheet",
    help: "خروجی خود پنل: پیامک، سوشال، ورودی، هزینه و گزارش. «بفرست به گوگل‌شیت» همین را از نو می‌نویسد.",
  },
  {
    key: "register",
    fa: "دفتر شماره کمپین",
    en: "Campaign register",
    help: "کمپین‌های بعد از ورود آرشیو به Campaign Number اضافه می‌شوند. ردیف‌های قبلی پاک نمی‌شوند.",
  },
  {
    key: "costs",
    fa: "شیت هزینه",
    en: "Cost sheet",
    help: "هزینه‌های تازه به شیت هزینه و گزارش روزانه اضافه می‌شوند. دفتر قدیمی هزینه دست نمی‌خورد.",
  },
  {
    key: "reporter",
    fa: "ریپورتر",
    en: "Reporter",
    help: "پیامک به تب SMS می‌رود و استوری منتشرشده به Instagram-S، مگر پیج فقط بله/روبیکا باشد.",
  },
];

type Tone = "ok" | "warn" | "danger" | "busy";

function sheetTone(link: SheetLink | undefined, liveReady: boolean, checking: boolean): Tone {
  if (!link?.configured) return "danger";
  if (!liveReady) return checking ? "busy" : "warn";
  return link.connected ? "ok" : "danger";
}

function sheetBadge(link: SheetLink | undefined, liveReady: boolean, checking: boolean) {
  const tone = sheetTone(link, liveReady, checking);
  if (!link?.configured) return <Badge tone="danger"><Bi en="Not set" fa="تنظیم نشده" /></Badge>;
  if (!liveReady) return <Badge tone="warn">{checking ? <Bi en="Checking" fa="در حال بررسی" /> : <Bi en="Not checked" fa="بررسی نشده" />}</Badge>;
  if (tone === "ok") return <Badge tone="ok"><Bi en="Connected" fa="وصل" /></Badge>;
  return <Badge tone="danger"><Bi en="Failed" fa="باز نشد" /></Badge>;
}

function sheetLine(label: string, link: SheetLink | undefined): string {
  if (!link) return `${label}: وضعیتی برنگشت.`;
  if (link.connected) return `${label}: وصل. عنوان شیت «${link.title || "بدون عنوان"}».`;
  return `${label}: وصل نیست. ${link.reason || "دلیلی از سرور نیامد."}`;
}

function StatusLight({ tone, label }: { tone: Tone; label: string }) {
  return (
    <p className="conn-status-line" data-tone={tone}>
      <span className="conn-status-dot" aria-hidden />
      {label}
    </p>
  );
}

export function ConnectionsPage() {
  const { has } = useAuth();
  const perfTools = has("perf.read") || has("perf.write");
  const canEditSecrets = has("request.triage") || has("request.manage") || has("org.admin");
  const qc = useQueryClient();
  const [token, setToken] = useState("");
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  // صفحه فقط وضعیت ذخیره‌شده را می‌خواند (بدون کال بیرونی). بررسی زنده فقط با دکمه.
  const saved = useSavedConnections(perfTools);
  const live = useLiveConnections();

  function checkNow() {
    void live.refetch().then((result) => {
      if (!result.data) {
        setOutcome({ ok: false, title: "بررسی اتصال‌ها انجام نشد", detail: exactError(result.error) });
        return;
      }
      const lines = SHEETS.map((item) => sheetLine(item.fa, result.data.sheets[item.key]));
      const mizitoLine = result.data.mizito.connected
        ? `میزیتو: وصل${result.data.mizito.hint ? ` (${result.data.mizito.hint})` : ""}.`
        : `میزیتو: وصل نیست. ${result.data.mizito.reason || "دلیلی از سرور نیامد."}`;
      const ok = SHEETS.every((item) => result.data.sheets[item.key]?.connected) && Boolean(result.data.mizito.connected);
      setOutcome({
        ok,
        title: ok ? "بررسی اتصال‌ها موفق بود" : "بررسی اتصال‌ها ناموفق بود",
        detail: [...lines, mizitoLine].join("\n"),
      });
    });
  }

  // بعد از ذخیرهٔ توکن یا API، نتیجهٔ بررسی زندهٔ قبلی دیگر معتبر نیست: کنار می‌رود و وضعیت ذخیره‌شده دوباره خوانده می‌شود.
  // بررسی زندهٔ تازه خودکار نیست.
  function refreshSaved() {
    qc.removeQueries({ queryKey: liveConnectionsQuery.queryKey, exact: true });
    void qc.invalidateQueries({ queryKey: savedConnectionsQuery.queryKey });
  }

  function save(next: string) {
    perfApi.saveMizito(next).then((result) => {
      setToken("");
      refreshSaved();
      setOutcome({
        ok: true,
        title: result.saved ? "ذخیرهٔ کلید دسترسی موفق بود" : "پاک‌کردن کلید دسترسی موفق بود",
        detail: result.saved
          ? `کلید در دیتابیس این سازمان رمزنگاری شد${result.hint ? ` (${result.hint})` : ""}. نیازی به .env یا دادن دستی توکن نیست — «خواندن کارت‌ها» و همگام‌سازی پروژه‌ها از همین کلید استفاده می‌کنند.`
          : "کلید دسترسی از سرور پاک شد. تا کلید تازه بچسبانید، خواندن میزیتو انجام نمی‌شود.",
      });
    }).catch((error: unknown) => {
      setOutcome({ ok: false, title: "ذخیرهٔ کلید دسترسی ناموفق بود", detail: exactError(error) });
    });
  }

  function syncMizitoProjects() {
    requestsApi.syncMizitoWork(false).then((result) => {
      void qc.invalidateQueries({ queryKey: ["requests", "work-projects"] });
      void qc.invalidateQueries({ queryKey: ["requests", "mizito-kanban"] });
      setOutcome({
        ok: true,
        title: "همگام‌سازی پروژه‌ها از میزیتو",
        detail: `ساخته: ${String(result.created ?? 0)} · به‌روز: ${String(result.updated ?? 0)} · رد شده: ${String(result.skipped ?? 0)}`,
      });
    }).catch((error: unknown) => {
      setOutcome({ ok: false, title: "همگام‌سازی پروژه‌ها ناموفق بود", detail: exactError(error) });
    });
  }

  function tryMizito() {
    perfApi.refreshMizito().then((result) => {
      void qc.invalidateQueries({ queryKey: ["perf", "mizito"] });
      void qc.invalidateQueries({ queryKey: savedConnectionsQuery.queryKey });
      setOutcome({
        ok: result.connected,
        title: result.connected ? "خواندن کارت‌های میزیتو موفق بود" : "خواندن کارت‌های میزیتو ناموفق بود",
        detail: result.connected
          ? `${toman(result.open_count)} کارت فعال از ${toman(result.projects.length)} پروژه خوانده شد و در صفحهٔ هزینه‌ها گذاشته شد. چیزی در میزیتو نوشته نشد.`
          : (result.reason || "میزیتو جواب نداد و دلیلی هم نفرستاد."),
      });
    }).catch((error: unknown) => {
      setOutcome({ ok: false, title: "خواندن کارت‌های میزیتو ناموفق بود", detail: exactError(error) });
    });
  }

  if ((saved.isLoading && live.isLoading) || (!saved.data && !live.data && (saved.isFetching || live.isFetching))) {
    return <LoadingState />;
  }
  if (!saved.data && !live.data) {
    const error = live.error || saved.error;
    return <ErrorMessage error={error ?? "اتصالات خوانده نشد"} />;
  }
  const data: Connections = live.data ?? saved.data!;
  const liveReady = Boolean(live.data);
  const checking = live.isFetching;
  const mizito = data.mizito;
  const checkedAt = live.dataUpdatedAt ? new Date(live.dataUpdatedAt).toISOString() : null;

  return (
    <>
      <PageHeader
        title={<Bi en="My connections" fa="اتصالات من" />}
        description={<Bi en="Saved links and a live check when you press the button." fa="لینک‌های ذخیره‌شده و بررسی زنده با دکمهٔ «بررسی همین حالا»." />}
        actions={
          <Button
            type="button"
            variant="secondary"
            disabled={checking}
            aria-busy={checking}
            onClick={checkNow}
          >
            {checking ? <Bi en="Checking…" fa="در حال بررسی…" /> : <Bi en="Check now" fa="بررسی همین حالا" />}
          </Button>
        }
      />
      {data.sheet_sync && (data.sheet_sync.running || data.sheet_sync.error || data.sheet_sync.result === "error") ? (
        <Card className="stack">
          <SectionHeader
            icon="layers"
            title={<Bi en="Last sheet sync" fa="آخرین همگام‌سازی شیت" />}
            action={data.sheet_sync.running ? <Badge tone="warn"><Bi en="Running" fa="در جریان" /></Badge> : data.sheet_sync.result === "error" ? <Badge tone="danger"><Bi en="Failed" fa="خطا" /></Badge> : null}
          />
          {data.sheet_sync.running ? (
            <Muted as="p">{data.sheet_sync.actor_name || "یک نفر"} در حال به‌روزرسانی شیت است. اگر ۴۰۹ گرفتید همین‌جا می‌بینید و بعداً دوباره «بفرست به گوگل‌شیت» بزنید.</Muted>
          ) : null}
          {data.sheet_sync.error ? <ErrorMessage friendly={false} message={data.sheet_sync.error} /> : null}
          {data.sheet_sync.finished_at ? <Muted>پایان: <DateText value={data.sheet_sync.finished_at} withTime /></Muted> : null}
        </Card>
      ) : null}
      <p className="conn-fresh">
        {checking ? "در حال بررسی زندهٔ همهٔ اتصال‌ها…" : checkedAt ? (
          <>آخرین بررسی زنده: <DateText value={checkedAt} withTime />. خودکار تکرار نمی‌شود؛ برای وضعیت تازه دوباره دکمه را بزنید.</>
        ) : (
          <>در این نشست هنوز بررسی زنده نشده است. شیت‌ها و پنل‌ها «بررسی نشده» هستند و میزیتو آخرین وضعیت ذخیره‌شده را نشان می‌دهد.</>
        )}
      </p>

      <Card>
        <SectionHeader
          icon="book"
          title={<Bi en="Google Sheets" fa="گوگل‌شیت" />}
          action={data.sheets_ready
            ? <Badge tone="ok"><Bi en="File found" fa="فایل حساب سرویس هست" /></Badge>
            : <Badge tone="danger"><Bi en="No credentials" fa="حساب سرویس نیست" /></Badge>}
        />
        <StatusLight
          tone={data.sheets_ready ? (SHEETS.every((item) => data.sheets[item.key]?.connected) ? "ok" : liveReady ? "danger" : "warn") : "danger"}
          label={
            data.sheets_ready
              ? SHEETS.every((item) => data.sheets[item.key]?.connected)
                ? "همهٔ شیت‌های گوگل در آخرین بررسی وصل بودند."
                : liveReady
                  ? "برخی شیت‌ها باز نشدند — جزئیات را در کارت‌های پایین ببینید."
                  : "فایل حساب سرویس هست؛ برای وضعیت زنده «بررسی همین حالا» را بزنید."
              : "فایل حساب سرویس روی سرور نیست — تا تنظیم شود شیت کار نمی‌کند."
          }
        />
        <details className="conn-tech">
          <summary><Bi en="Technical details" fa="جزئیات فنی" /></summary>
          {data.service_account ? (
            <Muted as="p" className="mono ltr-value">{data.service_account}</Muted>
          ) : (
            <ErrorMessage
              friendly={false}
              message="فایل JSON حساب سرویس در مسیر تنظیم‌شده پیدا نشد."
            />
          )}
        </details>
        <div className="conn-grid">
          {SHEETS.map((item) => {
            const link = data.sheets[item.key];
            const tone = sheetTone(link, liveReady, checking);
            return (
              <article key={item.key} className="conn-tile" data-tone={tone}>
                <div className="conn-tile-head">
                  <h3><Bi en={item.en} fa={item.fa} /></h3>
                  {sheetBadge(link, liveReady, checking)}
                </div>
                <p className="conn-help">{item.help}</p>
                {link?.connected && link.title ? <Muted>عنوان: {link.title}</Muted> : null}
                {liveReady && link && !link.connected ? (
                  <ErrorMessage friendly={false} message={link.reason || "شیت باز نشد و دلیلی از سرور نیامد."} />
                ) : null}
              </article>
            );
          })}
        </div>
      </Card>

      {perfTools ? <Card>
        <SectionHeader
          icon="briefcase"
          title={<Bi en="Mizito" fa="میزیتو" />}
          hint={mizito.saved ? <Bi en={`Saved ${mizito.hint}`} fa={`کلید ذخیره شده ${mizito.hint}`} /> : <Bi en="No key yet" fa="هنوز کلیدی ذخیره نشده" />}
          action={checking && !liveReady
            ? <Badge tone="warn"><Bi en="Checking" fa="در حال بررسی" /></Badge>
            : mizito.connected
              ? <Badge tone="ok"><Bi en="Connected" fa="وصل" /></Badge>
              : <Badge tone="danger"><Bi en="Not connected" fa="وصل نیست" /></Badge>}
        />
        <StatusLight
          tone={checking && !liveReady ? "busy" : mizito.connected ? "ok" : "danger"}
          label={
            mizito.connected
              ? `میزیتو وصل است — ${toman(mizito.open_count ?? 0)} کارت فعال در آخرین خواندن.`
              : mizito.saved
                ? "کلید میزیتو ذخیره شده اما آخرین بررسی وصل نبود."
                : "کلید میزیتو ذخیره نشده — از جزئیات فنی بچسبانید."
          }
        />
        <article className="conn-tile" data-tone={checking && !liveReady ? "busy" : mizito.connected ? "ok" : "danger"}>
          <p className="conn-help">
            میزیتو فقط خوانده می‌شود. x-token در دیتابیس همین سرور ذخیره می‌شود. همگام‌سازی پروژه‌ها هر ۱۵ دقیقه در worker سرور انجام می‌شود؛ «همگام‌سازی پروژه‌ها» همان کار را همین حالا اجرا می‌کند.
          </p>
          {mizito.connected ? (
            <Muted>
              {toman(mizito.open_count ?? 0)} کارت فعال در آخرین خواندن کامل
              {mizito.read_at ? <> · <DateText value={mizito.read_at} withTime /></> : null}
              {" · "}
              <Link to="/perf/money">لیست در صفحهٔ هزینه‌ها</Link>
            </Muted>
          ) : (
            <ErrorMessage friendly={false} message={mizito.reason || "وضعیت میزیتو مشخص نیست."} />
          )}
          {mizito.checked_at ? <Muted>آخرین جواب میزیتو: <DateText value={mizito.checked_at} withTime /></Muted> : <Muted>میزیتو هنوز بررسی نشده است.</Muted>}
        </article>
        <details className="conn-tech">
          <summary><Bi en="Technical details" fa="جزئیات فنی" /></summary>
          <ol className="perf-steps">
            <li>یک بار در <a href="https://office.mizito.ir" target="_blank" rel="noreferrer">office.mizito.ir</a> وارد شوید.</li>
            <li>در همان مرورگر ابزار توسعه را باز کنید (F12) و تب Network را انتخاب کنید.</li>
            <li>صفحه را تازه کنید و یک درخواست به app.mizito.ir را باز کنید.</li>
            <li>در Request Headers مقدار <strong>x-token</strong> را کپی کنید.</li>
          </ol>
          {canEditSecrets ? (
            <div className="form-grid">
              <Field label={<Bi en="Connection key" fa="کلید اتصال (x-token)" />}>
                <Input type="password" autoComplete="off" value={token} placeholder="از هدر درخواست کپی شود" onChange={(event) => setToken(event.target.value)} />
              </Field>
              <div className="row perf-actions">
                <Button type="button" disabled={!token.trim()} onClick={() => save(token)}><Bi en="Save" fa="ذخیره" /></Button>
                {mizito.saved ? <Button type="button" variant="secondary" onClick={() => save("")}><Bi en="Clear" fa="پاک کردن" /></Button> : null}
                <Button type="button" variant="secondary" onClick={tryMizito}><Bi en="Read cards" fa="خواندن کارت‌ها" /></Button>
                <Button type="button" variant="secondary" onClick={syncMizitoProjects}><Bi en="Sync projects" fa="همگام‌سازی پروژه‌ها" /></Button>
              </div>
            </div>
          ) : (
            <Muted>ذخیرهٔ کلید فقط برای سرپرست و ادمین است.</Muted>
          )}
        </details>
      </Card> : null}

      {perfTools ? <div className="conn-side">
        <Card>
          <SectionHeader icon="message" title={<Bi en="SMS panels" fa="پنل‌های پیامک" />} />
          <p className="conn-help conn-note">پنلی که آدرس API و کلید اتصالش ذخیره باشد، با «بررسی همین حالا» موجودی‌اش زنده خوانده می‌شود. آی‌اس‌ام‌اس با نام کاربری و رمز وب‌سرویس موجودی زنده می‌خواند؛ اگر ورود سه بار ناموفق باشد پنل ۱۰ دقیقه قفل می‌شود.</p>
          {data.panels.length === 0 ? <Muted>هنوز پنلی ثبت نشده است.</Muted> : (
            <div className="conn-grid">
              {data.panels.map((panel) => (
                <PanelTile key={panel.code || panel.name} panel={panel} writable={canEditSecrets} checking={checking} onSaved={refreshSaved} />
              ))}
            </div>
          )}
        </Card>

        <Card>
          <SectionHeader
            icon="sparkles"
            title={<Bi en="Post stats reading" fa="خواندن آمار پست" />}
            action={data.insight.ready
              ? <Badge tone="ok"><Bi en="Key set" fa="کلید هست" /></Badge>
              : <Badge tone="warn"><Bi en="No key" fa="کلید نیست" /></Badge>}
          />
          <article className="conn-tile" data-tone={data.insight.ready ? "ok" : "warn"}>
            {data.insight.ready ? (
              <p className="conn-help">
                کلید مدل زبانی ({data.insight.provider || "ارائه‌دهنده مشخص نیست"}) در تنظیم سرور هست. خواندن خودکار متن اسکرین‌شات آمار پست از همین کلید استفاده می‌کند.
              </p>
            ) : (
              <ErrorMessage
                friendly={false}
                message={`کلید مدل زبانی خالی است${data.insight.provider ? ` (ارائه‌دهنده: ${data.insight.provider})` : ""}. خواندن خودکار متن اسکرین‌شات آمار پست انجام نمی‌شود.`}
              />
            )}
          </article>
          <SectionHeader icon="send" title={<Bi en="Telegram" fa="تلگرام" />} />
          <article className="conn-tile" data-tone="warn">
            <p className="conn-help">
              ربات تلگرام در این صفحه صدا زده نمی‌شود. کلید دسترسی و چت‌ها در تنظیمات است. اگر ربات خاموش باشد، اعلان به تلگرام نمی‌رسد و خود درخواست در پنل می‌ماند.
            </p>
            <Link to="/settings"><Bi en="Open settings" fa="تنظیم در صفحهٔ تنظیمات" /></Link>
          </article>
        </Card>
      </div> : null}
      <OutcomePop outcome={outcome} onClose={() => setOutcome(null)} />
    </>
  );
}

type PanelRow = Connections["panels"][number];

function panelTone(panel: PanelRow): Tone {
  if (panel.live) return panel.live.ok ? "ok" : "danger";
  return panel.ready ? "warn" : "danger";
}

function PanelTile({ panel, writable, checking, onSaved }: { panel: PanelRow; writable: boolean; checking: boolean; onSaved: () => void }) {
  const toast = useToast();
  const panelsDetail = useQuery({ queryKey: ["perf", "panels"], queryFn: perfApi.panels });
  const detail = panelsDetail.data?.find((row) => row.id === panel.id);
  const [base, setBase] = useState(panel.api_base || "");
  const [token, setToken] = useState("");
  const [username, setUsername] = useState("");
  const [secret, setSecret] = useState("");
  const [sender, setSender] = useState("");
  const [busy, setBusy] = useState(false);
  const tone = panelTone(panel);
  const canProbe = Boolean((panel.api_base || "").trim() && panel.has_token);
  useEffect(() => {
    if (!detail) return;
    setUsername(detail.api_username || "");
    setSender(detail.sender_line || "");
  }, [detail?.id, detail?.api_username, detail?.sender_line]);
  function save() {
    setBusy(true);
    const payload: Record<string, string> = {};
    if (base.trim()) payload.api_base = base.trim();
    if (token.trim()) payload.api_token = token.trim();
    perfApi.updatePanel(panel.id, payload)
      .then(() => {
        toast("اتصال پنل ذخیره شد؛ با «بررسی همین حالا» زنده خوانده می‌شود");
        setToken("");
        onSaved();
      })
      .catch((error: Error) => toast(error.message))
      .finally(() => setBusy(false));
  }
  function saveSmsLogin() {
    if (!detail) return;
    setBusy(true);
    const payload: Record<string, string> = { api_username: username, sender_line: sender };
    if (secret.trim()) payload.api_secret = secret.trim();
    perfApi.updatePanel(detail.id, payload)
      .then(() => {
        toast(secret.trim() || detail.has_secret ? "اتصال آی‌اس‌ام‌اس ذخیره شد" : "نام کاربری ذخیره شد. رمز وب‌سرویس هنوز خالی است.");
        setSecret("");
        void panelsDetail.refetch();
        onSaved();
      })
      .catch((error: Error) => toast(error.message))
      .finally(() => setBusy(false));
  }
  function saveSenderLine() {
    if (!detail) return;
    setBusy(true);
    perfApi.updatePanel(detail.id, { sender_line: sender })
      .then(() => {
        toast("خط ارسال ذخیره شد");
        void panelsDetail.refetch();
        onSaved();
      })
      .catch((error: Error) => toast(error.message))
      .finally(() => setBusy(false));
  }
  return (
    <article className="conn-tile" data-tone={tone}>
      <div className="conn-tile-head">
        <h3>{panel.name}</h3>
        {panel.live ? (
          panel.live.ok
            ? <Badge tone="ok"><Bi en="Live OK" fa="وصل" /></Badge>
            : <Badge tone="danger"><Bi en="Live failed" fa="باز نشد" /></Badge>
        ) : panel.ready ? (
          <Badge tone="warn">{checking ? <Bi en="Checking" fa="در حال بررسی" /> : <Bi en="Not checked" fa="بررسی نشده" />}</Badge>
        ) : (
          <Badge tone="danger"><Bi en="No API login" fa="ورود API نیست" /></Badge>
        )}
      </div>
      {panel.live ? (
        panel.live.ok ? (
          <>
            <p className="conn-help">موجودی زنده: {panel.live.balance || "پاسخ بدون عدد"} </p>
            {panel.live.lines && panel.live.lines.length > 0 ? (
              <Muted>خطوط: <span dir="ltr">{panel.live.lines.join(" · ")}</span></Muted>
            ) : null}
          </>
        ) : (
          <ErrorMessage friendly={false} message={panel.live.reason || "کال زنده به پنل انجام نشد."} />
        )
      ) : (
        <p className="conn-help">
          {panel.detail}
          {panel.ready && !canProbe ? " آدرس API یا کلید پنل خالی است؛ با ذخیرهٔ آن‌ها موجودی زنده خوانده می‌شود." : ""}
        </p>
      )}
      {writable ? (
        <div className="panel-probe-form">
          {panel.code === "pishgam" || panel.code === "isms" ? null : (
            <>
              <Input placeholder="آدرس API پنل (مثل https://api.example.ir)" value={base} onChange={(event) => setBase(event.target.value)} />
              <Input type="password" autoComplete="off" placeholder={panel.has_token ? "کلید ذخیره شده" : "کلید API"} value={token} onChange={(event) => setToken(event.target.value)} />
              <Button type="button" variant="secondary" disabled={busy || (!base.trim() && !token.trim())} onClick={save}>
                <Bi en="Save API" fa="ذخیره API" />
              </Button>
            </>
          )}
          {panel.code === "isms" && detail ? (
            <>
              <Field label={<Bi en="Username" fa="نام کاربری آی‌اس‌ام‌اس" />}>
                <Input value={username} onChange={(event) => setUsername(event.target.value)} />
              </Field>
              <Field label={<Bi en="API password" fa="رمز وب‌سرویس" />}>
                <Input type="password" autoComplete="off" value={secret} placeholder={detail.has_secret ? "رمز ذخیره شده" : ""} onChange={(event) => setSecret(event.target.value)} />
              </Field>
              <Field label={<Bi en="Sender line" fa="خط ارسال" />}>
                <Input value={sender} onChange={(event) => setSender(event.target.value)} />
              </Field>
              <Button type="button" variant="secondary" disabled={busy} onClick={saveSmsLogin}>
                <Bi en="Save iSMS login" fa="ذخیرهٔ ورود آی‌اس‌ام‌اس" />
              </Button>
            </>
          ) : null}
          {panel.code === "pishgam" && detail ? (
            <>
              <Field label={<Bi en="Sender line" fa="خط ارسال" />}>
                <Input dir="ltr" value={sender} placeholder="مثل 5000302137682" onChange={(event) => setSender(event.target.value)} />
              </Field>
              <Button type="button" variant="secondary" disabled={busy} onClick={saveSenderLine}>
                <Bi en="Save sender line" fa="ذخیرهٔ خط ارسال" />
              </Button>
            </>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
