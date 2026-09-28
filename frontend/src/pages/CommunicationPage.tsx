import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Avatar,
  Badge,
  Button,
  ErrorMessage,
  Icon,
  type IconName,
  Input,
  LoadingState,
  PageHeader,
  Select,
} from "../components/ui";
import { Bi, useBi, useLocale } from "../i18n";
import { formatJalaliShort } from "../jalali";
import { buildPersonMap, personName } from "../lib/collaboration";
import { StatusLabel } from "../ux";

type CommSection = "needs_me" | "threads" | "branch" | "campaigns";

type ConvRow = Record<string, unknown> & {
  _lastSender?: string | null;
  _lastText?: string;
  _lastAt?: string;
};

const emptyRows: ConvRow[] = [];
const emptyRecords: Array<Record<string, unknown>> = [];

const sections: Array<{ key: CommSection; en: string; fa: string; icon: IconName }> = [
  { key: "needs_me", en: "Waiting for my reply", fa: "منتظر جواب من", icon: "bell" },
  { key: "threads", en: "All messages", fa: "همه پیام‌ها", icon: "message" },
  { key: "branch", en: "Branch requests", fa: "درخواست‌های شعب", icon: "branch" },
  { key: "campaigns", en: "Ad campaigns", fa: "کمپین‌های تبلیغاتی", icon: "megaphone" },
];

function shortTime(v: unknown, locale: "en" | "fa" = "en"): string {
  if (!v) return "";
  const d = new Date(String(v));
  if (Number.isNaN(d.getTime())) return "";
  const today = d.toDateString() === new Date().toDateString();
  if (today)
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (locale === "fa") {
    return formatJalaliShort(d) ?? "";
  }
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function CommunicationPage() {
  const { user, roleHint, has } = useAuth();
  const bi = useBi();
  const { locale } = useLocale();
  const streamEnd = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();
  const [section, setSection] = useState<CommSection>("needs_me");
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<Array<Record<string, unknown>>>([]);
  const [showCompose, setShowCompose] = useState(false);
  const [topic, setTopic] = useState("");
  const [withIds, setWithIds] = useState<string[]>([]);
  const [linkCampaignId, setLinkCampaignId] = useState("");
  const [linkWorkId, setLinkWorkId] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  async function enrichConversations(list: Array<Record<string, unknown>>): Promise<ConvRow[]> {
    const enriched: ConvRow[] = [];
    for (const c of list.slice(0, 40)) {
      try {
        const msgs = await api.conversations.messages(String(c.id));
        const last = msgs[msgs.length - 1];
        enriched.push({
          ...c,
          _lastSender: last ? String(last.sender_id || "") : null,
          _lastText: last ? String(last.text) : "",
          _lastAt: last ? String(last.created_at) : "",
        });
      } catch {
        enriched.push({ ...c });
      }
    }
    return enriched;
  }

  const board = useQuery({
    queryKey: ["communication-board", user?.id],
    queryFn: async () => {
      const people = await api.people.list().catch(() => []);
      const peopleMap = buildPersonMap(people);
      const convs = await api.conversations.list();
      const rows = await enrichConversations(convs);
      const campaigns = has("campaign.read") ? await api.campaigns.list() : [];
      const branchCases = has("case.read")
        ? (await api.cases.list({ type: "BRANCH_REQUEST" })).filter(
            (c) => c.status !== "COMPLETED" && c.status !== "CANCELLED",
          )
        : [];
      const sharedWork = has("work_item.read")
        ? (await api.workItems.list()).filter(
            (w) => w.status !== "COMPLETED" && w.status !== "CANCELLED",
          )
        : [];
      return { people, peopleMap, rows, campaigns, branchCases, sharedWork };
    },
  });
  const rows = board.data?.rows ?? emptyRows;
  const campaigns = board.data?.campaigns ?? emptyRecords;
  const branchCases = board.data?.branchCases ?? emptyRecords;
  const people = board.data?.people ?? emptyRecords;
  const peopleMap = board.data?.peopleMap ?? buildPersonMap([]);
  const sharedWork = board.data?.sharedWork ?? emptyRecords;
  const loading = board.isLoading;

  async function refresh() {
    await qc.invalidateQueries({ queryKey: ["communication-board"] });
  }

  useEffect(() => {
    streamEnd.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const needsMe = (c: ConvRow) =>
    Boolean(c._lastSender && user?.id && String(c._lastSender) !== String(user.id));

  const counts = useMemo(
    () => ({
      needs_me: rows.filter(needsMe).length,
      threads: rows.length,
      branch: branchCases.length,
      campaigns: campaigns.length,
    }),
    [rows, branchCases, campaigns, user?.id],
  );

  const visibleRows = useMemo(() => {
    const sorted = [...rows].sort((a, b) =>
      String(b._lastAt || "").localeCompare(String(a._lastAt || "")),
    );
    return section === "needs_me" ? sorted.filter(needsMe) : sorted;
  }, [section, rows, user?.id]);

  async function openConv(id: string) {
    setSelected(id);
    setMessages(await api.conversations.messages(id));
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!user?.id) return;
    setError("");
    try {
      if (withIds.length === 0) {
        setError(bi("Choose who this message is for.", "بگویید این پیام برای چه کسی است."));
        return;
      }
      const c = await api.conversations.create({
        topic: topic || bi("New conversation", "گفتگوی جدید"),
        participant_ids: [user.id, ...withIds],
        channel: "WEB",
        campaign_id: linkCampaignId || undefined,
        work_item_id: linkWorkId || undefined,
      });
      setTopic("");
      setWithIds([]);
      setLinkCampaignId("");
      setLinkWorkId("");
      setShowCompose(false);
      setSection("threads");
      await refresh();
      await openConv(String(c.id));
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!selected || !text.trim()) return;
    await api.conversations.postMessage(selected, text.trim());
    setText("");
    setMessages(await api.conversations.messages(selected));
    await refresh();
  }

  function campaignTitle(id: unknown) {
    const c = campaigns.find((x) => String(x.id) === String(id));
    return c ? String(c.title) : null;
  }

  function workTitle(id: unknown) {
    const w = sharedWork.find((x) => String(x.id) === String(id));
    return w ? String(w.title) : null;
  }

  const roleLine = bi(
    "Talk with colleagues. Start with “Waiting for my reply”, pick a message on the list and answer it.",
    "گفتگو با همکاران. از «منتظر جواب من» شروع کنید، یک پیام را از فهرست انتخاب کنید و جواب بدهید.",
  );

  const visibleSections = sections.filter((s) => {
    if (s.key === "branch")
      return (roleHint === "manager" || roleHint === "admin" || branchCases.length > 0) && has("case.read");
    if (s.key === "campaigns") return has("campaign.read") && campaigns.length > 0;
    return true;
  });

  const current = rows.find((r) => String(r.id) === selected);
  const currentSection = sections.find((s) => s.key === section)!;

  function withWhom(row: ConvRow): string {
    const ids = Array.isArray(row.participant_ids) ? row.participant_ids.map(String) : [];
    return ids
      .filter((id) => id !== String(user?.id))
      .map((id) => personName(peopleMap, id))
      .filter(Boolean)
      .join(locale === "fa" ? "، " : ", ");
  }

  function renderList() {
    if (loading) return <LoadingState />;

    if (section === "branch") {
      if (branchCases.length === 0) {
        return (
          <div className="pane-empty">
            <Bi en="No open branch requests." fa="درخواست باز شعبه‌ای نیست." />
          </div>
        );
      }
      return branchCases.map((c) => (
        <div key={String(c.id)} className="thread-row">
          <span className="row-lead">
            <Icon name="branch" />
          </span>
          <div className="thread-row-body">
            <span className="thread-row-title">{String(c.subject)}</span>
            <span className="thread-row-preview">
              {bi("Owner", "مسئول")}: {personName(peopleMap, c.owner_id)}
            </span>
            <div className="thread-row-tags">
              <StatusLabel status={String(c.status)} />
              {c.work_item_id ? (
                <Button variant="ghost" to={`/work-items/${String(c.work_item_id)}`}>
                  <Bi en="Open project" fa="باز کردن پروژه" />
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      ));
    }

    if (section === "campaigns") {
      if (campaigns.length === 0) {
        return (
          <div className="pane-empty">
            <Bi en="No campaigns yet." fa="هنوز کمپینی نیست." />
          </div>
        );
      }
      return campaigns.map((camp) => {
        const threads = rows.filter((r) => String(r.campaign_id) === String(camp.id));
        return (
          <button
            key={String(camp.id)}
            type="button"
            className="thread-row"
            onClick={() => {
              setLinkCampaignId(String(camp.id));
              const first = threads[0];
              if (first) void openConv(String(first.id));
              else setShowCompose(true);
            }}
          >
            <span className="row-lead">
              <Icon name="megaphone" />
            </span>
            <div className="thread-row-body">
              <span className="thread-row-title">{String(camp.title)}</span>
              <div className="thread-row-tags">
                <StatusLabel status={String(camp.status)} />
                <Badge>
                  {threads.length} <Bi en="messages" fa="گفتگو" />
                </Badge>
              </div>
            </div>
          </button>
        );
      });
    }

    if (visibleRows.length === 0) {
      return (
        <div className="pane-empty">
          <div>
            <Icon name="message" size={22} />
            <div>
              {section === "needs_me" ? (
                <Bi en="No one is waiting on you." fa="کسی منتظر پاسخ شما نیست." />
              ) : (
                <Bi en="No conversations here yet." fa="هنوز گفتگویی اینجا نیست." />
              )}
            </div>
          </div>
        </div>
      );
    }

    return visibleRows.map((c) => {
      const waiting = needsMe(c);
      const sender = c._lastSender ? personName(peopleMap, c._lastSender) : "";
      return (
        <button
          key={String(c.id)}
          type="button"
          className={`thread-row${selected === String(c.id) ? " active" : ""}${waiting ? " needs" : ""}`}
          onClick={() => void openConv(String(c.id))}
        >
          <Avatar name={sender || String(c.topic || "?")} size={30} />
          <div className="thread-row-body">
            <div className="thread-row-top">
              <span className="thread-row-title">{String(c.topic || withWhom(c) || c.id)}</span>
              <span className="muted" style={{ fontSize: "0.7rem" }}>
                {shortTime(c._lastAt, locale)}
              </span>
            </div>
            {c._lastText ? (
              <span className="thread-row-preview">
                {sender ? `${sender}: ` : ""}
                {String(c._lastText)}
              </span>
            ) : null}
            {Boolean(waiting || c.work_item_id || c.campaign_id) && (
              <div className="thread-row-tags">
                {waiting ? (
                  <Badge tone="warn">
                    <Bi en="Reply" fa="پاسخ" />
                  </Badge>
                ) : null}
                {c.work_item_id ? (
                  <Badge>
                    <Icon name="layers" size={10} />
                    {workTitle(c.work_item_id) || bi("Project", "پروژه")}
                  </Badge>
                ) : null}
                {c.campaign_id ? (
                  <Badge>
                    <Icon name="megaphone" size={10} />
                    {campaignTitle(c.campaign_id) || bi("Campaign", "کمپین")}
                  </Badge>
                ) : null}
              </div>
            )}
          </div>
        </button>
      );
    });
  }

  return (
    <>
      <PageHeader title={<Bi en="Messages" fa="پیام‌ها" />} description={roleLine} />
      <ErrorMessage error={error || (board.isError ? String((board.error as Error).message) : "")} />

      <div className="inbox">
        <nav className="inbox-nav">
          {visibleSections.map((s) => (
            <button
              key={s.key}
              type="button"
              className={`inbox-nav-item${section === s.key ? " active" : ""}${
                s.key === "needs_me" && counts.needs_me > 0 ? " is-hot" : ""
              }`}
              onClick={() => {
                setSection(s.key);
                setSelected(null);
                setMessages([]);
              }}
            >
              <Icon name={s.icon} />
              <span>
                <Bi en={s.en} fa={s.fa} />
              </span>
              <span className="inbox-count">{counts[s.key]}</span>
            </button>
          ))}
        </nav>

        <section className="inbox-list">
          <div className="inbox-list-head">
            <h2>
              <Bi en={currentSection.en} fa={currentSection.fa} />
            </h2>
            <Button
              variant={showCompose ? "secondary" : "primary"}
              className="btn-sm"
              onClick={() => setShowCompose((v) => !v)}
            >
              <Icon name={showCompose ? "x" : "plus"} size={13} />
              <Bi en="New message" fa="پیام جدید" />
            </Button>
          </div>
          {showCompose && (
            <form className="compose-pop" onSubmit={create}>
              <Input
                autoFocus
                placeholder={bi("What is it about?", "درباره چیست؟")}
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />
              <div className="compose-people">
                <span className="muted">
                  <Bi en="With" fa="با" />
                </span>
                {people
                  .filter((person) => String(person.id) !== String(user?.id))
                  .map((person) => {
                    const id = String(person.id);
                    const on = withIds.includes(id);
                    return (
                      <label key={id} className={`chip${on ? " active" : ""}`}>
                        <input
                          type="checkbox"
                          checked={on}
                          onChange={() =>
                            setWithIds((cur) => (on ? cur.filter((x) => x !== id) : [...cur, id]))
                          }
                        />
                        {String(person.full_name)}
                      </label>
                    );
                  })}
              </div>
              {(sharedWork.length > 0 || (has("campaign.read") && campaigns.length > 0)) && (
                <details className="advanced">
                  <summary>
                    <Bi en="Attach to a project (optional)" fa="وصل به یک پروژه (اختیاری)" />
                  </summary>
                  <div className="advanced-body">
                    {sharedWork.length > 0 && (
                      <Select value={linkWorkId} onChange={(e) => setLinkWorkId(e.target.value)}>
                        <option value="">{bi("No project", "بدون پروژه")}</option>
                        {sharedWork.slice(0, 20).map((w) => (
                          <option key={String(w.id)} value={String(w.id)}>
                            {String(w.title)}
                          </option>
                        ))}
                      </Select>
                    )}
                    {has("campaign.read") && campaigns.length > 0 && (
                      <Select value={linkCampaignId} onChange={(e) => setLinkCampaignId(e.target.value)}>
                        <option value="">{bi("No campaign", "بدون کمپین")}</option>
                        {campaigns.map((camp) => (
                          <option key={String(camp.id)} value={String(camp.id)}>
                            {String(camp.title)}
                          </option>
                        ))}
                      </Select>
                    )}
                  </div>
                </details>
              )}
              <div className="row">
                <Button type="submit" className="btn-sm">
                  <Bi en="Start" fa="شروع گفتگو" />
                </Button>
              </div>
            </form>
          )}
          <div className="inbox-scroll">{renderList()}</div>
        </section>

        <section className="inbox-thread">
          {!selected || !current ? (
            <div className="pane-empty">
              <div>
                <Icon name="message" size={26} />
                <div>
                  <strong>
                    <Bi en="Choose a message from the list" fa="یک پیام را از فهرست انتخاب کنید" />
                  </strong>
                </div>
                <div className="muted">
                  <Bi
                    en="Or press “New message” to start one."
                    fa="یا برای شروع گفتگو، «پیام جدید» را بزنید."
                  />
                </div>
              </div>
            </div>
          ) : (
            <>
              <header className="inbox-thread-head">
                <div>
                  <h2>{String(current.topic || bi("Conversation", "گفتگو"))}</h2>
                  <span className="muted">{withWhom(current)}</span>
                </div>
                <div className="row">
                  <Button
                    variant="ghost"
                    className="btn-sm"
                    onClick={() => {
                      void api.conversations.archive(selected).then(() => {
                        setSelected(null);
                        setMessages([]);
                        return refresh();
                      });
                    }}
                  >
                    <Bi en="Archive" fa="بایگانی" />
                  </Button>
                  {current.campaign_id ? (
                    <Badge>
                      <Icon name="megaphone" size={10} />
                      {campaignTitle(current.campaign_id)}
                    </Badge>
                  ) : null}
                  {current.work_item_id ? (
                    <Button
                      variant="secondary"
                      className="btn-sm"
                      to={`/work-items/${String(current.work_item_id)}`}
                    >
                      <Icon name="layers" size={13} />
                      {workTitle(current.work_item_id) || bi("Related project", "پروژه مرتبط")}
                    </Button>
                  ) : null}
                </div>
              </header>
              <div className="msg-stream">
                {messages.length === 0 ? (
                  <div className="pane-empty">
                    <Bi en="No messages yet — say hello." fa="هنوز پیامی نیست — شروع کنید." />
                  </div>
                ) : (
                  messages.map((m) => {
                    const mine = String(m.sender_id) === String(user?.id);
                    const who = personName(peopleMap, m.sender_id);
                    return (
                      <div key={String(m.id)} className={`msg${mine ? " mine" : ""}`}>
                        <Avatar name={who} size={28} />
                        <div className="msg-body">
                          <div className="msg-who">
                            <strong>{mine ? bi("You", "شما") : who}</strong>
                            <span>{shortTime(m.created_at, locale)}</span>
                          </div>
                          <div>{String(m.text)}</div>
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={streamEnd} />
              </div>
              <form className="reply-bar" onSubmit={send}>
                <Input
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder={bi("Write a reply…", "پاسخ بنویسید…")}
                />
                <Button type="submit" disabled={!text.trim()}>
                  <Icon name="send" size={14} />
                  <Bi en="Send" fa="ارسال" />
                </Button>
              </form>
            </>
          )}
        </section>
      </div>
    </>
  );
}
