import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  List,
  ListItem,
  Muted,
  PageHeader,
} from "../components/ui";
import { Bi, LangSwitch, useBi } from "../i18n";
import { queryKeys } from "../lib/queryKeys";

type Section = "org" | "knowledge" | "language" | "telegram";

type TgStatus = {
  linked: boolean;
  provider: string;
  bot_username: string | null;
  username: string | null;
  disabled: boolean;
  notify_prefs: Record<string, boolean> | null;
  quiet_start_hour: number | null;
  quiet_end_hour: number | null;
  digest_enabled: boolean;
  deep_link_template: string | null;
};

const DEFAULT_PREFS: Record<string, boolean> = {
  task_assigned: true,
  message: true,
  sla: true,
  task_done: true,
  branch: true,
};

export function SettingsPage() {
  const bi = useBi();
  const [section, setSection] = useState<Section>("telegram");
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);

  const branchesQuery = useQuery({ queryKey: queryKeys.branches, queryFn: () => api.branches.list() });
  const teamsQuery = useQuery({ queryKey: queryKeys.teams, queryFn: () => api.teams.list() });
  const deptsQuery = useQuery({ queryKey: queryKeys.departments, queryFn: () => api.departments.list() });
  const docsQuery = useQuery({ queryKey: queryKeys.knowledge, queryFn: () => api.knowledge.list() });
  const membersQuery = useQuery({
    queryKey: queryKeys.teamMembers(String(selectedTeam ?? "")),
    enabled: Boolean(selectedTeam),
    queryFn: () => api.teams.members(String(selectedTeam)),
  });
  const branches = branchesQuery.data ?? [];
  const teams = teamsQuery.data ?? [];
  const depts = deptsQuery.data ?? [];
  const docs = docsQuery.data ?? [];
  const members = membersQuery.data ?? [];
  const [deepLink, setDeepLink] = useState<string | null>(null);
  const [linkCode, setLinkCode] = useState<string | null>(null);
  const [tgBusy, setTgBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const tgQuery = useQuery({
    queryKey: queryKeys.telegramStatus,
    queryFn: () => api.telegram.status(),
  });
  const tg: TgStatus | null = tgQuery.data ?? null;
  const tgError = actionError || (tgQuery.isError ? String((tgQuery.error as Error).message) : "");
  const [prefs, setPrefs] = useState(DEFAULT_PREFS);
  const [digest, setDigest] = useState(true);
  const [quietStart, setQuietStart] = useState("");
  const [quietEnd, setQuietEnd] = useState("");

  useEffect(() => {
    const st = tgQuery.data;
    if (!st) return;
    // Mirror the server state into the form, without clobbering typing.
    setPrefs({ ...DEFAULT_PREFS, ...(st.notify_prefs || {}) });
    setDigest(st.digest_enabled);
    setQuietStart(st.quiet_start_hour != null ? String(st.quiet_start_hour) : "");
    setQuietEnd(st.quiet_end_hour != null ? String(st.quiet_end_hour) : "");
  }, [tgQuery.data]);

  function refreshTg() {
    setActionError("");
    return tgQuery.refetch();
  }

  function openTeam(id: string) {
    setSelectedTeam(id);
  }

  async function connectTelegram() {
    setTgBusy(true);
    setActionError("");
    try {
      const res = await api.telegram.linkCode();
      setLinkCode(res.link_code);
      setDeepLink(res.deep_link);
      if (res.deep_link) {
        window.open(res.deep_link, "_blank", "noopener,noreferrer");
      }
      // Poll status a few times
      for (let i = 0; i < 8; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const st = await api.telegram.status();
        if (st.linked) {
          setDeepLink(null);
          setLinkCode(null);
          await tgQuery.refetch();
          break;
        }
      }
    } catch (e) {
      setActionError(String((e as Error).message));
    } finally {
      setTgBusy(false);
    }
  }

  async function disconnectTelegram() {
    setTgBusy(true);
    setActionError("");
    try {
      await api.telegram.unlink();
      setDeepLink(null);
      setLinkCode(null);
      await refreshTg();
    } catch (e) {
      setActionError(String((e as Error).message));
    } finally {
      setTgBusy(false);
    }
  }

  async function saveTgPrefs() {
    setTgBusy(true);
    setActionError("");
    try {
      const qs = quietStart === "" ? null : Number(quietStart);
      const qe = quietEnd === "" ? null : Number(quietEnd);
      await api.telegram.updatePrefs({
        notify_prefs: prefs,
        digest_enabled: digest,
        clear_quiet: qs == null || qe == null,
        quiet_start_hour: qs ?? undefined,
        quiet_end_hour: qe ?? undefined,
      });
      await refreshTg();
    } catch (e) {
      setActionError(String((e as Error).message));
    } finally {
      setTgBusy(false);
    }
  }

  const qrUrl =
    deepLink != null
      ? `https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(deepLink)}`
      : null;

  return (
    <>
      <PageHeader
        title={<Bi en="Settings" fa="تنظیمات" />}
        description={
          <Bi
            en="Change the language, connect Telegram, and see how the company is organised."
            fa="تغییر زبان، اتصال تلگرام، و دیدن ساختار شرکت."
          />
        }
      />
      <TotpCard />

      <div className="tab-row">
        {(
          [
            ["telegram", bi("Telegram", "تلگرام")],
            ["language", bi("Language", "زبان")],
            ["org", bi("Branches & teams", "شعب و تیم‌ها")],
            ["knowledge", bi("Rules & guides", "قوانین و راهنماها")],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={section === key ? "tab active" : "tab"}
            onClick={() => setSection(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {section === "telegram" && (
        <div className="stack" style={{ gap: "var(--space-4)", maxWidth: "36rem" }}>
          <Card stack>
            <CardTitle>
              <Bi en="Connect Telegram" fa="اتصال تلگرام" />
            </CardTitle>
            <p className="help-text" style={{ margin: 0 }}>
              <Bi
                en="Get work alerts on your phone, mark to-dos done, and reply — without opening the website."
                fa="اعلان کارها را روی گوشی بگیرید، کار را انجام‌شده بزنید و جواب بدهید — بدون باز کردن سایت."
              />
            </p>
            {tgError ? <p className="danger-text">{tgError}</p> : null}
            {tg?.linked ? (
              <>
                <p>
                  <Badge tone="ok">
                    <Bi en="Connected" fa="متصل" />
                  </Badge>{" "}
                  {tg.username ? (
                    <Muted>@{tg.username}</Muted>
                  ) : (
                    <Muted>
                      <Bi en="linked" fa="وصل شده" />
                    </Muted>
                  )}
                </p>
                <Button variant="secondary" disabled={tgBusy} onClick={() => void disconnectTelegram()}>
                  <Bi en="Disconnect" fa="قطع اتصال" />
                </Button>
              </>
            ) : (
              <>
                <Button disabled={tgBusy} onClick={() => void connectTelegram()}>
                  {tgBusy
                    ? bi("Waiting…", "در انتظار…")
                    : bi("Open in Telegram", "باز کردن در تلگرام")}
                </Button>
                {deepLink && (
                  <div className="stack" style={{ gap: "var(--space-2)" }}>
                    <Muted>
                      <Bi
                        en="If the app did not open, scan this code with your phone:"
                        fa="اگر برنامه باز نشد، این کد را با گوشی اسکن کنید:"
                      />
                    </Muted>
                    {qrUrl ? (
                      <img src={qrUrl} alt="QR" width={160} height={160} style={{ borderRadius: 8 }} />
                    ) : null}
                    <a href={deepLink} target="_blank" rel="noreferrer">
                      {deepLink}
                    </a>
                    {linkCode ? (
                      <Muted>
                        <Bi en="Or send in the bot:" fa="یا در بات بفرستید:" />{" "}
                        <code>/link {linkCode}</code>
                      </Muted>
                    ) : null}
                  </div>
                )}
                {!deepLink && !tgBusy && (
                  <Muted>
                    <Bi
                      en="If the bot username is not configured yet, you will get a one-time code to paste in Telegram."
                      fa="اگر نام بات هنوز تنظیم نشده باشد، یک کد یک‌بارمصرف برای چسباندن در تلگرام می‌گیرید."
                    />
                  </Muted>
                )}
              </>
            )}
          </Card>

          {tg?.linked && (
            <Card stack>
              <CardTitle>
                <Bi en="Notification settings" fa="تنظیمات اعلان" />
              </CardTitle>
              <details className="advanced" open>
                <summary>
                  <Bi en="What to send (optional)" fa="چه چیزهایی بیاید (اختیاری)" />
                </summary>
                <div className="advanced-body">
                  {(
                    [
                      ["task_assigned", bi("New to-dos", "کار جدید")],
                      ["message", bi("New messages", "پیام جدید")],
                      ["sla", bi("Deadlines", "مهلت‌ها")],
                      ["task_done", bi("When my to-dos are finished", "وقتی کار من تمام شد")],
                      ["branch", bi("Branch requests", "درخواست شعبه")],
                    ] as const
                  ).map(([key, label]) => (
                    <label key={key} className="check-row">
                      <input
                        type="checkbox"
                        checked={Boolean(prefs[key])}
                        onChange={(e) => setPrefs((p) => ({ ...p, [key]: e.target.checked }))}
                      />
                      {label}
                    </label>
                  ))}
                  <label className="check-row">
                    <input type="checkbox" checked={digest} onChange={(e) => setDigest(e.target.checked)} />
                    <Bi en="Morning summary" fa="خلاصه صبحگاهی" />
                  </label>
                  <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
                    <label>
                      <Muted>
                        <Bi en="Quiet from (hour UTC)" fa="سکوت از ساعت (UTC)" />
                      </Muted>
                      <input
                        className="control"
                        type="number"
                        min={0}
                        max={23}
                        value={quietStart}
                        onChange={(e) => setQuietStart(e.target.value)}
                        placeholder="22"
                        style={{ width: "4.5rem" }}
                      />
                    </label>
                    <label>
                      <Muted>
                        <Bi en="until" fa="تا" />
                      </Muted>
                      <input
                        className="control"
                        type="number"
                        min={0}
                        max={23}
                        value={quietEnd}
                        onChange={(e) => setQuietEnd(e.target.value)}
                        placeholder="8"
                        style={{ width: "4.5rem" }}
                      />
                    </label>
                  </div>
                  <Button className="btn-sm" disabled={tgBusy} onClick={() => void saveTgPrefs()}>
                    <Bi en="Save" fa="ذخیره" />
                  </Button>
                </div>
              </details>
            </Card>
          )}
        </div>
      )}

      {section === "org" && (
        <div className="grid grid-2">
          <Card>
            <CardTitle>
              <Bi en="Branches" fa="شعب" />
            </CardTitle>
            {branches.length === 0 ? (
              <Muted>—</Muted>
            ) : (
              <ul>
                {branches.map((b) => (
                  <li key={String(b.id)}>
                    {String(b.name)} <Badge>{String(b.code)}</Badge>
                  </li>
                ))}
              </ul>
            )}
            <CardTitle>
              <Bi en="Departments" fa="بخش‌ها" />
            </CardTitle>
            <ul>
              {depts.map((d) => (
                <li key={String(d.id)}>{String(d.name)}</li>
              ))}
            </ul>
            <details className="advanced">
              <summary>
                <Bi en="Advanced tools" fa="ابزارهای پیشرفته" />
              </summary>
              <div className="advanced-body">
                <Button variant="ghost" to="/cases">
                  <Bi en="All follow-ups (full list)" fa="همه پیگیری‌ها (فهرست کامل)" />
                </Button>
              </div>
            </details>
          </Card>
          <Card>
            <CardTitle>
              <Bi en="Teams" fa="تیم‌ها" />
            </CardTitle>
            <List>
              {teams.map((t) => (
                <ListItem key={String(t.id)}>
                  <span>{String(t.name)}</span>
                  <Button variant="secondary" type="button" onClick={() => void openTeam(String(t.id))}>
                    <Bi en="Members" fa="اعضا" />
                  </Button>
                </ListItem>
              ))}
            </List>
            {selectedTeam && (
              <div style={{ marginTop: "1rem" }}>
                <strong>
                  <Bi en="Members" fa="اعضا" />
                </strong>
                <ul>
                  {members.map((m) => (
                    <li key={String(m.id)}>{String(m.full_name)}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        </div>
      )}

      {section === "knowledge" && (
        <Card>
          <p>
            <Bi
              en="Company rules and guides. Colleagues can search them and the assistant uses them in its answers."
              fa="قوانین و راهنماهای شرکت. همکاران می‌توانند جستجویشان کنند و دستیار در جواب‌ها از آن‌ها استفاده می‌کند."
            />
          </p>
          {docs.length === 0 ? (
            <EmptyState
              titleEn="No guides yet"
              titleFa="هنوز راهنمایی نیست"
              bodyEn="Add your company rules when ready."
              bodyFa="هر وقت آماده بودید، قوانین شرکت را اضافه کنید."
              action={
                <Button variant="secondary" to="/knowledge">
                  <Bi en="Go to Rules & guides" fa="رفتن به قوانین و راهنماها" />
                </Button>
              }
            />
          ) : (
            <ul>
              {docs.map((d) => (
                <li key={String(d.id)}>{String(d.title)}</li>
              ))}
            </ul>
          )}
          <Button variant="secondary" to="/knowledge">
            <Bi en="Manage rules & guides" fa="مدیریت قوانین و راهنماها" />
          </Button>
        </Card>
      )}

      {section === "language" && (
        <Card>
          <EmptyState
            titleEn="Display language"
            titleFa="زبان نمایش"
            bodyEn="Switch the interface between English and Persian."
            bodyFa="رابط را بین انگلیسی و فارسی عوض کنید."
            action={<LangSwitch />}
          />
        </Card>
      )}

      <details className="advanced" style={{ marginTop: "1rem" }}>
        <summary>
          <Bi en="Test accounts (for trying the system)" fa="حساب‌های آزمایشی (برای امتحان سیستم)" />
        </summary>
        <div className="advanced-body">
          <ul className="muted" style={{ margin: 0, paddingInlineStart: "1.2rem" }}>
            <li>ali@autoco.example — {bi("Manager", "مدیر")}</li>
            <li>reza@autoco.example — {bi("Seller", "فروشنده")}</li>
            <li>sara@autoco.example — {bi("Marketing", "بازاریابی")}</li>
            <li>maryam@autoco.example — {bi("Mashhad branch", "شعبه مشهد")}</li>
          </ul>
          <p className="muted" style={{ margin: 0 }}>
            {bi("Password for all:", "رمز همه:")} <code>password</code>
          </p>
        </div>
      </details>
    </>
  );
}

function TotpCard() {
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [otpauth, setOtpauth] = useState("");
  return (
    <Card>
      <h2>
        <Bi en="Two-factor login" fa="ورود دو مرحله‌ای" />
      </h2>
      <Button
        variant="secondary"
        onClick={() => {
          void api.totp.setup().then((row) => {
            setSecret(row.secret);
            setOtpauth(row.otpauth);
          });
        }}
      >
        <Bi en="Show QR secret" fa="نمایش رمز" />
      </Button>
      {otpauth ? (
        <img
          alt="totp"
          src={`https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(otpauth)}`}
        />
      ) : null}
      {secret ? <p className="mono">{secret}</p> : null}
      <input className="control" value={code} onChange={(e) => setCode(e.target.value)} />
      <Button onClick={() => void api.totp.enable(code)}>
        <Bi en="Enable" fa="فعال‌سازی" />
      </Button>
    </Card>
  );
}
