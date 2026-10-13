import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import {
  Badge,
  Button,
  Card,
  ErrorMessage,
  Field,
  Icon,
  type IconName,
  Input,
  LoadingState,
  Muted,
  PageHeader,
  SectionHeader,
  TextArea,
} from "../components/ui";
import { useAuth } from "../auth";
import { Bi, useBi } from "../i18n";

type Mode = "ask" | "communication" | "inventory" | "sales" | "purchase" | "divar";

const MODE_META: Record<Mode, { icon: IconName; descEn: string; descFa: string }> = {
  ask: {
    icon: "sparkles",
    descEn: "Ask about the records you are allowed to see",
    descFa: "درباره همان اطلاعاتی بپرسید که در بخش خودتان می‌بینید",
  },
  communication: {
    icon: "users",
    descEn: "Write who should do what — it becomes a project with to-dos",
    descFa: "بنویسید چه کسی چه کند؛ خودش به پروژه و کارها تبدیل می‌شود",
  },
  inventory: {
    icon: "car",
    descEn: "Find cars that have been in stock too long",
    descFa: "پیدا کردن خودروهایی که زیادی مانده‌اند",
  },
  sales: {
    icon: "flag",
    descEn: "Find customers nobody has called back",
    descFa: "پیدا کردن مشتری‌هایی که کسی پیگیرشان نبوده",
  },
  purchase: {
    icon: "briefcase",
    descEn: "Find good cars to buy",
    descFa: "پیدا کردن خودروهای مناسب برای خرید",
  },
  divar: {
    icon: "megaphone",
    descEn: "Draft Divar ads for you to check and publish",
    descFa: "نوشتن پیش‌نویس آگهی دیوار تا شما بررسی و منتشر کنید",
  },
};

type ChatMsg = {
  id: string;
  role: "user" | "assistant";
  text: string;
  answerMode?: string;
  sources?: Array<{ entity_type: string; title: string; entity_id: string }>;
};

const modes: Array<{
  key: Mode;
  en: string;
  fa: string;
}> = [
  { key: "ask", en: "Ask a question", fa: "سؤال بپرس" },
  { key: "communication", en: "Split work", fa: "تقسیم کار" },
  { key: "inventory", en: "Slow-moving cars", fa: "خودروهای مانده" },
  { key: "sales", en: "Customer follow-up", fa: "پیگیری مشتری‌ها" },
  { key: "purchase", en: "Buying opportunities", fa: "فرصت‌های خرید" },
  { key: "divar", en: "Divar ads", fa: "آگهی دیوار" },
];

const ASK_STARTERS = [
  { en: "What is the status of Camry #124?", fa: "وضعیت کمری #124 چیست؟" },
  { en: "What are our listing rules?", fa: "قوانین ثبت آگهی ما چیست؟" },
  { en: "Is Elantra 2021 in stock?", fa: "النترا ۲۰۲۱ موجود داریم؟" },
];

function modeVisible(key: Mode, has: (perm: string) => boolean): boolean {
  if (key === "ask") return true;
  if (key === "communication") return has("work_item.write");
  if (key === "inventory") return has("inventory.read");
  if (key === "sales" || key === "purchase") return has("customer.read");
  if (key === "divar") return has("campaign.write");
  return false;
}

export function AgentPage() {
  const bi = useBi();
  const { has } = useAuth();
  const chatEnd = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<Mode>("ask");
  const [message, setMessage] = useState("");
  const [autoCreate, setAutoCreate] = useState(true);
  const [minDays, setMinDays] = useState(30);
  const [staleDays, setStaleDays] = useState(3);
  const [chat, setChat] = useState<ChatMsg[]>(() => {
    try {
      const raw = localStorage.getItem("cm_agent_chat");
      if (raw) return JSON.parse(raw) as ChatMsg[];
    } catch {
      /* ignore */
    }
    return [
      {
        id: "welcome",
        role: "assistant",
        text: "سلام! سؤال را بپرسید. منابع پاسخ کنار هر جواب نشان داده می‌شود.",
      },
    ];
  });
  const [commResult, setCommResult] = useState<Awaited<ReturnType<typeof api.agent>> | null>(null);
  const [invResult, setInvResult] = useState<Awaited<
    ReturnType<typeof api.inventoryAgent>
  > | null>(null);
  const [salesResult, setSalesResult] = useState<Awaited<
    ReturnType<typeof api.salesAgent>
  > | null>(null);
  const [purchaseResult, setPurchaseResult] = useState<Awaited<
    ReturnType<typeof api.purchaseAgent>
  > | null>(null);
  const [divarResult, setDivarResult] = useState<Awaited<
    ReturnType<typeof api.divarAgent>
  > | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [params, setParams] = useSearchParams();
  const urlAsked = useRef(false);
  const visibleModes = modes.filter((m) => modeVisible(m.key, has));
  const canCreate =
    mode === "divar" ? has("task.write") : mode === "ask" ? false : has("case.write");

  useEffect(() => {
    if (!modeVisible(mode, has)) setMode("ask");
  }, [mode, has]);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    localStorage.setItem("cm_agent_chat", JSON.stringify(chat.slice(-40)));
  }, [chat, busy]);

  useEffect(() => {
    const q = params.get("q");
    if (q && !urlAsked.current) {
      urlAsked.current = true;
      setParams({}, { replace: true });
      void askChat(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function askChat(q: string) {
    const text = q.trim();
    if (!text) return;
    setBusy(true);
    setError("");
    const userMsg: ChatMsg = { id: `u-${Date.now()}`, role: "user", text };
    setChat((prev) => [...prev, userMsg]);
    setMessage("");
    try {
      const res = await api.rag.ask(text);
      setChat((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: res.answer || bi("No answer.", "جوابی نبود."),
          answerMode: res.answer_mode,
          sources: (res.hits || []).slice(0, 5).map((h) => ({
            entity_type: h.entity_type,
            title: h.title,
            entity_id: h.entity_id,
          })),
        },
      ]);
    } catch (err) {
      setError(String((err as Error).message));
      setChat((prev) => [
        ...prev,
        {
          id: `e-${Date.now()}`,
          role: "assistant",
          text: bi("Could not answer that request.", "نتوانست به این درخواست جواب بدهد."),
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function run(e: FormEvent) {
    e.preventDefault();
    if (mode === "ask") {
      await askChat(message);
      return;
    }
    setBusy(true);
    setError("");
    setCommResult(null);
    setInvResult(null);
    setSalesResult(null);
    setPurchaseResult(null);
    setDivarResult(null);
    try {
      if (mode === "communication") {
        setCommResult(await api.agent(message));
      } else if (mode === "inventory") {
        setInvResult(
          await api.inventoryAgent({
            message: message || undefined,
            min_days: minDays,
            auto_create: canCreate && autoCreate,
          }),
        );
      } else if (mode === "sales") {
        setSalesResult(
          await api.salesAgent({
            message: message || undefined,
            stale_days: staleDays,
            auto_create: canCreate && autoCreate,
          }),
        );
      } else if (mode === "purchase") {
        setPurchaseResult(
          await api.purchaseAgent({
            message: message || undefined,
            stale_days: staleDays,
            auto_create: canCreate && autoCreate,
          }),
        );
      } else {
        setDivarResult(
          await api.divarAgent({
            message: message || undefined,
            auto_create: canCreate && autoCreate,
          }),
        );
      }
    } catch (err) {
      setError(String((err as Error).message));
    } finally {
      setBusy(false);
    }
  }

  function selectMode(k: Mode) {
    setMode(k);
    if (k === "ask") setMessage("");
    else if (k === "communication") {
      setMessage(
        bi(
          "For Camry #124, Reza follows up customers and Sara does marketing.",
          "برای این کمری، رضا مشتری رو پیگیری کنه و سارا تبلیغات رو انجام بده.",
        ),
      );
    } else setMessage("");
  }

  function onComposerKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy) void askChat(message);
    }
  }

  const runLabel =
    mode === "inventory"
      ? bi("Find slow-moving cars", "پیدا کن")
      : mode === "sales"
        ? bi("Find customers to call", "پیدا کن")
        : mode === "purchase"
          ? bi("Find opportunities", "پیدا کن")
          : mode === "divar"
            ? bi("Write the ads", "آگهی‌ها را بنویس")
            : bi("Create project & to-dos", "ساخت پروژه و کارها");

  function sourceHref(etype: string, id: string): string | null {
    if (etype === "vehicle") return `/vehicles/${id}`;
    if (etype === "work_item") return `/projects`;
    if (etype === "document") return `/knowledge`;
    if (etype === "case") return `/`;
    return null;
  }

  const sourceLabel: Record<string, [string, string]> = {
    vehicle: ["Car", "خودرو"],
    work_item: ["Project", "پروژه"],
    document: ["Guide", "راهنما"],
    case: ["Follow-up", "پیگیری"],
    user: ["Colleague", "همکار"],
    message: ["Message", "پیام"],
  };

  function ResultCard({
    extra,
    message: msg,
    workItemId,
  }: {
    extra?: ReactNode;
    message: string;
    workItemId?: string | null;
  }) {
    return (
      <Card className="result-card">
        <div className="row">
          <strong>
            <Bi en="Result" fa="نتیجه" />
          </strong>
          {extra}
          {workItemId ? (
            <Button variant="secondary" className="btn-sm" to="/projects">
              <Icon name="layers" size={13} />
              <Bi en="Open the new project" fa="دیدن پروژه ساخته‌شده" />
            </Button>
          ) : null}
        </div>
        <pre className="result-pre">{msg}</pre>
      </Card>
    );
  }

  const autoCreateLabel =
    mode === "divar"
      ? bi("Also create a to-do to review the drafts", "برای بررسی پیش‌نویس‌ها یک کار هم بساز")
      : bi("Also create to-dos for what’s found", "برای موارد پیدا شده خودکار کار بساز");

  const curMeta = MODE_META[mode];
  const curMode = visibleModes.find((m) => m.key === mode) ?? modes[0];

  return (
    <>
      <PageHeader
        title={<Bi en="Assistant" fa="دستیار" />}
        description={
          <Bi
            en="Ask about your own area. The assistant only uses the parts you are allowed to see."
            fa="درباره حوزهٔ خودتان بپرسید. دستیار فقط همان بخش‌هایی را می‌بیند که اجازه دارید."
          />
        }
      />

      <div className="agent-layout">
        <div>
          {mode === "ask" ? (
            <Card className="chat-panel">
              <div className="chat-thread">
                {chat.map((m) => (
                  <div key={m.id} className={`chat-bubble chat-bubble--${m.role}`}>
                    <div className="chat-bubble-text">{m.text}</div>
                    {m.answerMode ? (
                      <div className="chat-mode-tag">
                        <Badge tone={m.answerMode === "llm" ? "ok" : ""}>
                          <Icon name={m.answerMode === "llm" ? "sparkles" : "search"} size={10} />
                          {m.answerMode === "llm"
                            ? bi("Answered from your records", "پاسخ از روی اطلاعات شما")
                            : bi("Search results", "نتیجه جستجو")}
                        </Badge>
                      </div>
                    ) : null}
                    {m.sources && m.sources.length > 0 ? (
                      <div className="chat-sources">
                        <Muted>
                          <Bi en="Based on" fa="بر اساس" />
                        </Muted>
                        <ul>
                          {m.sources.map((s) => {
                            const href = sourceHref(s.entity_type, s.entity_id);
                            const [en, fa] = sourceLabel[s.entity_type] || [s.entity_type, s.entity_type];
                            const label = `${bi(en, fa)} · ${s.title}`;
                            return (
                              <li key={`${s.entity_type}-${s.entity_id}`}>
                                {href ? (
                                  <Button variant="ghost" to={href}>
                                    {label}
                                  </Button>
                                ) : (
                                  <span>{label}</span>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                ))}
                {busy ? (
                  <div className="chat-bubble chat-bubble--assistant">
                    <LoadingState block={false} labelEn="Thinking…" labelFa="در حال بررسی…" />
                  </div>
                ) : null}
                <div ref={chatEnd} />
              </div>

              <form className="chat-composer" onSubmit={run}>
                {chat.length <= 1 && (
                  <div className="chat-starters">
                    {ASK_STARTERS.map((s) => (
                      <button
                        key={s.en}
                        type="button"
                        className="chip"
                        disabled={busy}
                        onClick={() => void askChat(bi(s.en, s.fa))}
                      >
                        {bi(s.en, s.fa)}
                      </button>
                    ))}
                  </div>
                )}
                <ErrorMessage error={error} />
                <div className="chat-input-row">
                  <TextArea
                    rows={1}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={onComposerKey}
                    placeholder={bi(
                      "Type your question… (press Enter to send)",
                      "سؤالتان را بنویسید… (با Enter ارسال می‌شود)",
                    )}
                  />
                  <Button type="submit" disabled={busy || !message.trim()}>
                    <Icon name="send" size={14} />
                    <Bi en="Ask" fa="بپرس" />
                  </Button>
                </div>
              </form>
            </Card>
          ) : (
            <div className="stack stack--roomy">
              <Card as="form" className="agent-run" onSubmit={run}>
                <SectionHeader icon={curMeta.icon} title={<Bi en={curMode.en} fa={curMode.fa} />} />
                <Muted>{bi(curMeta.descEn, curMeta.descFa)}</Muted>
                <Field
                  label={
                    mode === "communication" ? (
                      <Bi en="Describe who should do what" fa="بنویسید چه کسی چه کاری کند" />
                    ) : (
                      <Bi en="Extra instructions (optional)" fa="توضیح اضافه (اختیاری)" />
                    )
                  }
                >
                  <TextArea
                    rows={mode === "communication" ? 3 : 2}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                  />
                </Field>
                {mode !== "communication" && (
                  <details className="advanced">
                    <summary>
                      <Bi en="Settings" fa="تنظیمات" />
                      <span className="muted">
                        <Bi en="(optional)" fa="(اختیاری)" />
                      </span>
                    </summary>
                  <div className="agent-params advanced-body">
                    {mode === "inventory" && (
                      <Field label={<Bi en="In stock longer than (days)" fa="بیشتر از چند روز مانده باشد" />}>
                        <Input
                          type="number"
                          min={0}
                          value={minDays}
                          onChange={(e) => setMinDays(Number(e.target.value))}
                        />
                      </Field>
                    )}
                    {(mode === "sales" || mode === "purchase") && (
                      <Field label={<Bi en="No contact for (days)" fa="چند روز بی‌پیگیری مانده باشد" />}>
                        <Input
                          type="number"
                          min={0}
                          value={staleDays}
                          onChange={(e) => setStaleDays(Number(e.target.value))}
                        />
                      </Field>
                    )}
                    {canCreate ? (
                      <label className="check-row check-row--tall">
                        <input
                          type="checkbox"
                          checked={autoCreate}
                          onChange={(e) => setAutoCreate(e.target.checked)}
                        />
                        {autoCreateLabel}
                      </label>
                    ) : null}
                  </div>
                  </details>
                )}
                <ErrorMessage error={error} />
                <div className="compose-actions">
                  <Button type="submit" disabled={busy}>
                    <Icon name={curMeta.icon} size={14} />
                    {busy ? bi("Running…", "در حال اجرا…") : runLabel}
                  </Button>
                </div>
              </Card>

              {commResult && (
                <ResultCard
                  message={commResult.message}
                  workItemId={commResult.work_item_id}
                />
              )}
              {invResult && (
                <ResultCard
                  extra={
                    <Badge>
                      {bi("opportunities", "فرصت‌ها")}: {invResult.opportunities_found}
                    </Badge>
                  }
                  message={invResult.message}
                  workItemId={invResult.work_item_ids?.[0]}
                />
              )}
              {salesResult && (
                <ResultCard
                  extra={
                    <Badge>
                      {bi("follow-ups", "پیگیری‌ها")}: {salesResult.follow_ups_found}
                    </Badge>
                  }
                  message={salesResult.message}
                  workItemId={salesResult.work_item_ids?.[0]}
                />
              )}
              {purchaseResult && (
                <ResultCard
                  extra={
                    <Badge>
                      {bi("opportunities", "فرصت‌ها")}: {purchaseResult.opportunities_found}
                    </Badge>
                  }
                  message={purchaseResult.message}
                  workItemId={purchaseResult.work_item_ids?.[0]}
                />
              )}
              {divarResult && (
                <ResultCard
                  extra={
                    <Badge>
                      {bi("prepared", "آماده‌شده")}: {divarResult.listings_prepared}
                    </Badge>
                  }
                  message={divarResult.message}
                  workItemId={divarResult.work_item_ids?.[0]}
                />
              )}
            </div>
          )}
        </div>

        <aside className="side-stack">
          <Card>
            <SectionHeader title={<Bi en="What can I help with?" fa="چه کمکی از دستیار برمی‌آید؟" />} />
            <div className="mode-list">
              {visibleModes.map((m) => {
                const meta = MODE_META[m.key];
                return (
                  <button
                    key={m.key}
                    type="button"
                    className={`mode-item${mode === m.key ? " active" : ""}`}
                    onClick={() => selectMode(m.key)}
                  >
                    <span className="row-lead">
                      <Icon name={meta.icon} size={14} />
                    </span>
                    <span>
                      <strong>
                        <Bi en={m.en} fa={m.fa} />
                      </strong>
                      <span className="muted">{bi(meta.descEn, meta.descFa)}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </Card>
        </aside>
      </div>
    </>
  );
}

