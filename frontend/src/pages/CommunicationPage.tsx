import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Avatar,
  Badge,
  Button,
  Dialog,
  ErrorMessage,
  Icon,
  type IconName,
  Input,
  LoadingState,
  MoreMenu,
  PageHeader,
  Select,
  TextArea,
} from "../components/ui";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { Bi, useBi, useLocale } from "../i18n";
import { faDigits, faNum } from "../fa";
import { formatJalaliShort } from "../jalali";
import { buildPersonMap, personName } from "../lib/collaboration";
import { messageDisplayText, parseMessageMedia } from "../lib/messageMedia";
import { queryKeys } from "../lib/queryKeys";
import { perfApi } from "../perf/api";
import { campaignFromText } from "../perf/fromMessage";
import { StatusLabel } from "../ux";

type CommSection = "needs_me" | "threads" | "branch" | "campaigns";

type ConvRow = Record<string, unknown>;

const emptyRows: ConvRow[] = [];
const emptyRecords: Array<Record<string, unknown>> = [];

const sections: Array<{ key: CommSection; en: string; fa: string; icon: IconName }> = [
  { key: "needs_me", en: "Waiting for my reply", fa: "منتظر جواب من", icon: "bell" },
  { key: "threads", en: "All messages", fa: "همه پیام‌ها", icon: "message" },
  { key: "branch", en: "Branch requests", fa: "درخواست‌های شعب", icon: "branch" },
  { key: "campaigns", en: "Conversation topic", fa: "موضوع گفتگو", icon: "megaphone" },
];

function shortTime(v: unknown): string {
  if (!v) return "";
  const d = new Date(String(v));
  if (Number.isNaN(d.getTime())) return "";
  const today = d.toDateString() === new Date().toDateString();
  if (today) {
    return faDigits(`${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`);
  }
  return formatJalaliShort(d) ?? "";
}

export function CommunicationPage() {
  const { user, roleHint, has } = useAuth();
  const bi = useBi();
  const { locale } = useLocale();
  const streamEnd = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recordChunksRef = useRef<Blob[]>([]);
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [making, setMaking] = useState("");

  const [section, setSection] = useState<CommSection>("needs_me");
  const selected = params.get("c");
  const [showArchived, setShowArchived] = useState(false);
  const [showCompose, setShowCompose] = useState(false);
  const [topic, setTopic] = useState("");
  const [withIds, setWithIds] = useState<string[]>([]);
  const [linkCampaignId, setLinkCampaignId] = useState("");
  const [linkWorkId, setLinkWorkId] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [sendError, setSendError] = useState("");
  const [sending, setSending] = useState(false);
  const [recording, setRecording] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [addingTo, setAddingTo] = useState<string | null>(null);
  const [addUserId, setAddUserId] = useState("");
  // پیش‌پر کردن compose از URL — «گفتگو دربارهٔ ...» از صفحهٔ خودرو/مشتری/پرونده
  const [prefill, setPrefill] = useState({ vehicle: "", case: "", customer: "" });

  /** Keep the URL shareable: /communication?c=<id> reopens the same thread. */
  const openConv = useCallback(
    (id: string) => {
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("c", id);
        return next;
      });
      setSendError("");
    },
    [setParams, setSendError],
  );

  const board = useQuery({
    queryKey: queryKeys.communication(user?.id, showArchived),
    refetchInterval: 30_000,
    queryFn: async () => {
      const people = await api.people.list().catch(() => []);
      const convs = await api.conversations.list({ archived: showArchived || undefined });
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
      return {
        people,
        peopleMap: buildPersonMap(people),
        rows: convs,
        campaigns,
        branchCases,
        sharedWork,
      };
    },
  });

  const rows = board.data?.rows ?? emptyRows;
  const allCampaigns = board.data?.campaigns ?? emptyRecords;
  const campaigns =
    roleHint === "admin"
      ? allCampaigns
      : allCampaigns.filter((camp) => rows.some((row) => String(row.campaign_id) === String(camp.id)));
  const branchCases = board.data?.branchCases ?? emptyRecords;
  const people = board.data?.people ?? emptyRecords;
  const peopleMap = board.data?.peopleMap ?? buildPersonMap([]);
  const sharedWork = board.data?.sharedWork ?? emptyRecords;
  const loading = board.isLoading;

  /** Open thread messages poll every 10s; the list itself every 30s. */
  const thread = useQuery({
    queryKey: queryKeys.conversationMessages(selected ?? ""),
    enabled: Boolean(selected),
    refetchInterval: 10_000,
    queryFn: () => api.conversations.messages(selected ?? ""),
  });
  const messages = thread.data ?? emptyRecords;

  const refreshBoard = useCallback(() => {
    void qc.invalidateQueries({ queryKey: queryKeys.communicationRoot });
  }, [qc]);

  useEffect(() => {
    streamEnd.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  // ?new=1&topic=...&vehicle=...&case=...&customer=... → compose باز و پیش‌پر می‌شود
  useEffect(() => {
    if (params.get("new") !== "1") return;
    setShowCompose(true);
    setTopic(params.get("topic") ?? "");
    const peopleRaw = params.get("people");
    if (peopleRaw) {
      setWithIds(peopleRaw.split(",").map((id) => id.trim()).filter(Boolean));
    }
    setPrefill({
      vehicle: params.get("vehicle") ?? "",
      case: params.get("case") ?? "",
      customer: params.get("customer") ?? "",
    });
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const key of ["new", "topic", "vehicle", "case", "customer", "people"]) next.delete(key);
        return next;
      },
      { replace: true },
    );
    // فقط در اولین ورود به صفحه اجرا شود
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const needsMe = useCallback((c: ConvRow) => Boolean(c.needs_reply), []);

  const counts = useMemo(
    () => ({
      needs_me: rows.filter(needsMe).length,
      threads: rows.length,
      branch: branchCases.length,
      campaigns: campaigns.length,
    }),
    [rows, branchCases, campaigns, needsMe],
  );

  const visibleRows = useMemo(() => {
    const sorted = [...rows].sort((a, b) =>
      String(b.last_message_at || b.created_at || "").localeCompare(
        String(a.last_message_at || a.created_at || ""),
      ),
    );
    return section === "needs_me" ? sorted.filter(needsMe) : sorted;
  }, [section, rows, needsMe]);

  const send = useMutation({
    mutationFn: (body: { id: string; text: string }) =>
      api.conversations.postMessage(body.id, body.text),
    onSuccess: () => {
      setText("");
      setSendError("");
      void qc.invalidateQueries({ queryKey: queryKeys.conversationMessages(selected ?? "") });
      refreshBoard();
    },
    onError: (err) => setSendError(String((err as Error).message)),
  });

  const sendMedia = useMutation({
    mutationFn: (body: { id: string; file: File; messageType?: string }) =>
      api.conversations.postMedia(body.id, body.file, body.messageType),
    onSuccess: () => {
      setSendError("");
      void qc.invalidateQueries({ queryKey: queryKeys.conversationMessages(selected ?? "") });
      refreshBoard();
    },
    onError: (err) => setSendError(String((err as Error).message)),
  });

  async function onPickFile(file: File | null) {
    if (!selected || !file || sendMedia.isPending || uploading) return;
    const audio = file.type.startsWith("audio/");
    const image = file.type.startsWith("image/");
    const messageType = audio ? "VOICE" : image ? "IMAGE" : "DOCUMENT";
    setUploading(true);
    try {
      await sendMedia.mutateAsync({ id: selected, file, messageType });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function toggleVoiceRecord() {
    if (!selected) return;
    if (recording && recorderRef.current) {
      recorderRef.current.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setSendError(bi("Voice recording is not supported in this browser.", "ضبط صدا در این مرورگر پشتیبانی نمی‌شود."));
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType: mime });
      recordChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) recordChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        setRecording(false);
        recorderRef.current = null;
        const blob = new Blob(recordChunksRef.current, { type: mime });
        if (!blob.size) return;
        const file = new File([blob], `voice-${Date.now()}.webm`, { type: mime });
        void onPickFile(file);
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (err) {
      setSendError(String((err as Error).message));
    }
  }

  useEffect(() => {
    return () => {
      recorderRef.current?.stop();
    };
  }, []);

  async function onSend(e: FormEvent) {
    e.preventDefault();
    if (!selected || !text.trim() || send.isPending) return;
    setSending(true);
    try {
      await send.mutateAsync({ id: selected, text: text.trim() });
    } finally {
      setSending(false);
    }
  }

  function onReplyKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter" || e.shiftKey) return;
    e.preventDefault();
    const form = e.currentTarget.form;
    if (form) form.requestSubmit();
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
        vehicle_id: prefill.vehicle || undefined,
        case_id: prefill.case || undefined,
        customer_id: prefill.customer || undefined,
      });
      setTopic("");
      setWithIds([]);
      setLinkCampaignId("");
      setLinkWorkId("");
      setPrefill({ vehicle: "", case: "", customer: "" });
      setShowCompose(false);
      setSection("threads");
      refreshBoard();
      openConv(String(c.id));
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  function campaignTitle(id: unknown) {
    const c = campaigns.find((x) => String(x.id) === String(id));
    return c ? String(c.title) : null;
  }

  function workTitle(id: unknown) {
    const w = sharedWork.find((x) => String(x.id) === String(id));
    return w ? String(w.title) : null;
  }

  async function archiveCurrent() {
    if (!selected) return;
    const ok = await confirm(
      bi("Archive this conversation?", "این گفتگو بایگانی شود؟"),
      bi("It moves out of the list; you can restore it later.", "از فهرست خارج می‌شود؛ بعداً می‌توانید برگردانید."),
      bi("Archive", "بایگانی"),
    );
    if (!ok) return;
    try {
      await api.conversations.archive(selected);
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete("c");
        return next;
      });
      toast(bi("Archived", "بایگانی شد"));
      refreshBoard();
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  async function unarchive(row: ConvRow) {
    try {
      await api.conversations.unarchive(String(row.id));
      toast(bi("Restored from archive", "از بایگانی برگردانده شد"));
      refreshBoard();
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  async function addParticipant() {
    if (!selected || !addUserId) return;
    try {
      await api.conversations.addParticipant(selected, addUserId);
      setAddUserId("");
      setAddingTo(null);
      toast(bi("Added to the conversation", "به گفتگو اضافه شد"));
      refreshBoard();
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  const roleLine =
    roleHint === "admin"
      ? bi(
          "You see every chat and the rest of the company’s information.",
          "همهٔ گفتگوها و بقیهٔ اطلاعات شرکت را می‌بینید.",
        )
      : bi(
          "Only chats you are in. A project or campaign thread shows up here after you are added.",
          "فقط چت‌هایی که خودتان داخلشان هستید. گفتگوی پروژه یا کمپین وقتی دیده می‌شود که به آن اضافه شده باشید.",
        );

  const visibleSections = sections.filter((s) => {
    if (s.key === "branch")
      return (roleHint === "manager" || roleHint === "admin" || branchCases.length > 0) && has("case.read");
    if (s.key === "campaigns") return has("campaign.read") && campaigns.length > 0;
    return true;
  });

  const navActive: CommSection | "archive" = showArchived ? "archive" : section;

  function selectNav(key: CommSection | "archive") {
    if (key === "archive") {
      setShowArchived(true);
      setSection("threads");
      return;
    }
    setShowArchived(false);
    setSection(key);
  }

  const current = rows.find((r) => String(r.id) === selected) ?? null;
  async function makeCampaign(id: string, source: string) {
    const brief = source.trim();
    if (!brief || making) return;
    setMaking(id);
    try {
      const row = await perfApi.createCampaign(campaignFromText(brief));
      toast("کمپین از همین درخواست ساخته شد");
      navigate(`/perf/campaigns/${row.id}`);
    } catch (err) {
      toast(String((err as Error).message));
      setMaking("");
    }
  }

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
              {c.project_id ? (
                <Button variant="ghost" to={`/projects/${String(c.project_id)}`}>
                  <Bi en="Open project" fa="باز کردن پروژه" />
                </Button>
              ) : null}
              {has("perf.write") ? (
                <Button
                  type="button"
                  variant="secondary"
                  className="btn-sm"
                  disabled={making === String(c.id)}
                  onClick={() => void makeCampaign(String(c.id), String(c.subject || ""))}
                >
                  <Bi en="Make a campaign" fa="کمپین کن" />
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
              if (first) openConv(String(first.id));
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
              {showArchived ? (
                <Bi en="Nothing in the archive." fa="چیزی در بایگانی نیست." />
              ) : section === "needs_me" ? (
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
      const sender = c.last_sender_id ? personName(peopleMap, c.last_sender_id) : "";
      const lastAt = c.last_message_at || c.created_at;
      return (
        <button
          key={String(c.id)}
          type="button"
          className={`thread-row${selected === String(c.id) ? " active" : ""}${waiting ? " needs" : ""}`}
          onClick={() => openConv(String(c.id))}
        >
          <Avatar name={sender || String(c.topic || "?")} size={30} />
          <div className="thread-row-body">
            <div className="thread-row-top">
              <span className="thread-row-title">{String(c.topic || withWhom(c) || c.id)}</span>
              <span className="muted fine">
                {shortTime(lastAt)}
              </span>
            </div>
            {c.last_message_text ? (
              <span className="thread-row-preview">
                {sender ? `${sender}: ` : ""}
                {messageDisplayText(String(c.last_message_text)) ||
                  (parseMessageMedia(String(c.last_message_text))
                    ? bi("Attachment", "پیوست")
                    : String(c.last_message_text))}
              </span>
            ) : null}
            {Boolean(waiting || c.project_id || c.pm_campaign_id) && (
              <div className="thread-row-tags">
                {waiting ? (
                  <Badge tone="warn">
                    <Bi en="Reply" fa="پاسخ" />
                  </Badge>
                ) : null}
                {c.project_id ? (
                  <Link
                    className="thread-row-link"
                    to={`/projects/${String(c.project_id)}`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Icon name="layers" size={11} />
                    {bi("Project", "پروژه")}
                  </Link>
                ) : null}
                {c.pm_campaign_id ? (
                  <Link
                    className="thread-row-link"
                    to={`/perf/campaigns/${String(c.pm_campaign_id)}`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Icon name="megaphone" size={11} />
                    {bi("Campaign", "کمپین")}
                  </Link>
                ) : null}
              </div>
            )}
          </div>
          {showArchived ? (
            <span
              className="row-lead"
              role="button"
              tabIndex={0}
              aria-label={bi("Restore conversation", "بازگرداندن گفتگو")}
              onClick={(e) => {
                e.stopPropagation();
                void unarchive(c);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.stopPropagation();
                  void unarchive(c);
                }
              }}
            >
              <Icon name="arrow" size={14} />
            </span>
          ) : null}
        </button>
      );
    });
  }

  const candidates = people.filter((p) => {
    const id = String(p.id);
    if (id === String(user?.id)) return false;
    const ids = Array.isArray(current?.participant_ids)
      ? (current.participant_ids as Array<unknown>).map(String)
      : [];
    return !ids.includes(id);
  });

  return (
    <>
      <PageHeader title={<Bi en="Messages" fa="پیام‌ها" />} description={roleLine} />
      <ErrorMessage
        error={error || sendError || (board.isError ? String((board.error as Error).message) : "")}
      />

      <div className="inbox">
        <section className="inbox-list">
          <div className="inbox-list-head">
            <nav className="inbox-sections" aria-label={bi("Message sections", "بخش‌های پیام")}>
              {visibleSections.map((s) => {
                const active = navActive === s.key;
                const count = counts[s.key];
                const attention = s.key === "needs_me" && counts.needs_me > 0;
                return (
                  <button
                    key={s.key}
                    type="button"
                    className={`inbox-section${active ? " active" : ""}`}
                    aria-current={active ? "true" : undefined}
                    onClick={() => selectNav(s.key)}
                  >
                    <span className="inbox-section-label">
                      <Icon name={s.icon} size={15} />
                      <span>{bi(s.en, s.fa)}</span>
                    </span>
                    {typeof count === "number" ? (
                      <span className={attention ? "inbox-section-count attention" : "inbox-section-count"}>
                        {faNum(count)}
                      </span>
                    ) : null}
                  </button>
                );
              })}
              <button
                type="button"
                className={`inbox-section${navActive === "archive" ? " active" : ""}`}
                aria-current={navActive === "archive" ? "true" : undefined}
                onClick={() => selectNav("archive")}
              >
                <span className="inbox-section-label">
                  <Icon name="clock" size={15} />
                  <span>{bi("Archive", "بایگانی")}</span>
                </span>
              </button>
            </nav>
            <Button
              variant="primary"
              className="btn-sm inbox-new-msg"
              onClick={() => setShowCompose(true)}
            >
              <Icon name="plus" size={13} />
              <Bi en="New message" fa="پیام جدید" />
            </Button>
          </div>
          {showCompose ? (
            <Dialog onClose={() => setShowCompose(false)} className="form-pop" labelledBy="compose-title" closeLabel={bi("Close", "بستن")}>
            <form className="compose-pop" onSubmit={create}>
              <h3 id="compose-title" className="sr-only"><Bi en="New message" fa="پیام جدید" /></h3>
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
                      <Select
                        value={linkCampaignId}
                        onChange={(e) => setLinkCampaignId(e.target.value)}
                      >
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
            </Dialog>
          ) : null}
          <div className="inbox-scroll">{renderList()}</div>
        </section>

        <section className="inbox-thread">
          {selected && !current && (loading || thread.isLoading) ? (
            <LoadingState />
          ) : !selected || (!current && !messages.length) ? (
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
                  <h2>{String(current?.topic || bi("Conversation", "گفتگو"))}</h2>
                  <span className="muted">{current ? withWhom(current) : ""}</span>
                </div>
                <div className="row">
                  {current?.campaign_id ? (
                    <Badge>
                      <Icon name="megaphone" size={10} />
                      {campaignTitle(current.campaign_id)}
                    </Badge>
                  ) : null}
                  {current?.work_item_id && has("work_item.read") ? (
                    <Button
                      variant="secondary"
                      className="btn-sm"
                      to={`/work-items/${String(current.work_item_id)}`}
                    >
                      <Icon name="layers" size={13} />
                      {workTitle(current.work_item_id) || bi("Related project", "پروژه مرتبط")}
                    </Button>
                  ) : null}
                  <MoreMenu label={bi("More", "بیشتر")}>
                    {showArchived && current ? (
                      <Button variant="ghost" className="btn-sm" onClick={() => void unarchive(current)}>
                        <Bi en="Restore" fa="برگرداندن" />
                      </Button>
                    ) : (
                      <Button variant="ghost" className="btn-sm" onClick={() => void archiveCurrent()}>
                        <Bi en="Archive" fa="بایگانی" />
                      </Button>
                    )}
                    <Button variant="ghost" className="btn-sm" onClick={() => setAddingTo(addingTo ? null : selected)}>
                      <Icon name="plus" size={13} />
                      <Bi en="Add person" fa="افزودن نفر" />
                    </Button>
                  </MoreMenu>
                </div>
              </header>

              {addingTo === selected ? (
                <div className="compose-pop">
                  <div className="compose-people">
                    <span className="muted">
                      <Bi en="Add to this conversation" fa="افزودن به این گفتگو" />
                    </span>
                    <Select value={addUserId} onChange={(e) => setAddUserId(e.target.value)}>
                      <option value="">{bi("Choose a person", "یک نفر را انتخاب کنید")}</option>
                      {candidates.map((p) => (
                        <option key={String(p.id)} value={String(p.id)}>
                          {String(p.full_name)}
                        </option>
                      ))}
                    </Select>
                    <Button
                      className="btn-sm"
                      disabled={!addUserId}
                      onClick={() => void addParticipant()}
                    >
                      <Bi en="Add" fa="افزودن" />
                    </Button>
                  </div>
                </div>
              ) : null}

              <div className="msg-stream">
                {thread.isLoading ? (
                  <LoadingState />
                ) : messages.length === 0 ? (
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
                            <span>{shortTime(m.created_at)}</span>
                          </div>
                          <MessageBody text={String(m.text ?? "")} messageType={String(m.message_type ?? "")} />
                          {has("perf.write") && String(m.text || "").trim() ? (
                            <div className="msg-actions">
                              <Button
                                type="button"
                                variant="ghost"
                                className="btn-sm"
                                disabled={making === String(m.id)}
                                onClick={() => void makeCampaign(String(m.id), String(m.text))}
                              >
                                <Bi en="Make a campaign" fa="کمپین کن" />
                              </Button>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={streamEnd} />
              </div>

              <form className="reply-bar" onSubmit={onSend}>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="sr-only"
                  accept="image/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx"
                  onChange={(e) => void onPickFile(e.target.files?.[0] ?? null)}
                />
                <Button
                  type="button"
                  variant="ghost"
                  className="btn-sm"
                  disabled={!selected || uploading || sendMedia.isPending}
                  onClick={() => fileInputRef.current?.click()}
                  aria-label={bi("Attach file", "پیوست فایل")}
                >
                  <Icon name="paperclip" size={14} />
                </Button>
                <Button
                  type="button"
                  variant={recording ? "secondary" : "ghost"}
                  className="btn-sm"
                  disabled={!selected || uploading || sendMedia.isPending}
                  onClick={() => void toggleVoiceRecord()}
                  aria-label={bi("Voice message", "پیام صوتی")}
                >
                  <Icon name="upload" size={14} />
                </Button>
                <TextArea
                  rows={1}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={onReplyKeyDown}
                  placeholder={bi(
                    "Write a reply… (Enter to send, Shift+Enter for a new line)",
                    "پاسخ بنویسید… (Enter برای ارسال، Shift+Enter برای خط جدید)",
                  )}
                />
                <Button type="submit" disabled={!text.trim() || sending || uploading || recording}>
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

function MessageBody({ text, messageType }: { text: string; messageType: string }) {
  const media = parseMessageMedia(text);
  if (!media) return <div>{text}</div>;
  const upper = messageType.toUpperCase();
  const audio =
    upper === "VOICE" || /\.(webm|ogg|mp3|m4a|wav)$/i.test(media.filename) || media.filename.startsWith("voice-");
  if (upper === "IMAGE" || (!audio && /\.(png|jpe?g|gif|webp)$/i.test(media.filename))) {
    return (
      <a href={media.url} target="_blank" rel="noreferrer">
        <img className="msg-media-img" src={media.url} alt={media.filename} />
      </a>
    );
  }
  if (audio) {
    return <audio className="msg-media-audio" controls preload="metadata" src={media.url} />;
  }
  return (
    <a className="msg-media-file" href={media.url} download={media.filename}>
      <Bi en="Download" fa="دانلود" /> {media.filename}
    </a>
  );
}
