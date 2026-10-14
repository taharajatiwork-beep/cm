import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Badge,
  Button,
  Card,
  Field,
  ForbiddenState,
  Input,
  Muted,
  PageHeader,
  SectionHeader,
  Segmented,
  Select,
  Table,
  TextArea,
  TitleCode,
} from "../components/ui";
import { isForbiddenError } from "../lib/apiError";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { Bi } from "../i18n";
import { downloadPerf, perfApi, toman, type PishgamPreviewResult, type RecipientList } from "./api";
import { FilePick, RelatedLinks } from "./bits";
import { useRemove } from "./edit";
import { TargetingCard } from "./TargetingCard";
import { PishgamPostalAudience, SmsHistoryTab, pishgamPageUrl } from "./SmsHistory";

type MainTab = "new" | "history";
type FlowStep = "message" | "audience" | "send";
type AudienceKind = "list" | "smart" | "postal" | "isms";

function visibleCampaigns(rows: Array<{ id: string; code: string; title: string }> | undefined, query: string, selected: string) {
  const q = query.trim().toLowerCase();
  return (rows ?? []).filter((row) => row.id === selected || !q || row.code.toLowerCase().includes(q) || row.title.toLowerCase().includes(q));
}

export function smsShape(text: string) {
  const persian = text.length === 0 || /[\u0600-\u06FF]/.test(text) || /[^\u0000-\u007F]/.test(text);
  const units = Array.from(text).reduce((sum, ch) => sum + ((ch.codePointAt(0) || 0) > 0xffff ? 2 : 1), 0);
  const single = persian ? 70 : 160;
  const part = persian ? 67 : 153;
  const pages = units === 0 ? 0 : units <= single ? 1 : Math.ceil(units / part);
  const capacity = pages <= 1 ? single : part * pages;
  return { chars: units, pages, room: capacity - units, language: persian ? "فارسی" : "انگلیسی" };
}

function Meter({ text, recipients, tariff }: { text: string; recipients: number; tariff: number }) {
  const shape = smsShape(text);
  const cost = shape.pages * Math.max(0, recipients) * Math.max(0, tariff);
  return (
    <p className="muted perf-meter">
      {toman(shape.chars)} نویسه {shape.language} · {toman(shape.pages || 0)} صفحه
      {shape.pages <= 1 ? ` · ${toman(shape.room)} نویسه تا دو برابر شدن هزینه` : ` · هزینه ${toman(shape.pages)} برابر یک صفحه`}
      {cost ? ` · حدود ${toman(cost)} تومان` : ""}
    </p>
  );
}

export function SmsPage() {
  const toast = useToast();
  const [params] = useSearchParams();
  const fromUrl = params.get("campaign") || "";
  const stepParam = params.get("step") || "";
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const campaignsForbidden = campaigns.isError && isForbiddenError(campaigns.error);
  const fromLink = (campaigns.data ?? []).find((row) => row.id === fromUrl || row.code === fromUrl)?.id || "";
  const [campaignId, setCampaignId] = useState(fromUrl.length > 8 ? fromUrl : "");
  const [mainTab, setMainTab] = useState<MainTab>(stepParam === "delivery" ? "history" : "new");
  const [flowStep, setFlowStep] = useState<FlowStep>("message");
  const [body, setBody] = useState("ستوده\nلغو11");
  const [audienceKind, setAudienceKind] = useState<AudienceKind>("list");
  const [listId, setListId] = useState("");
  const [panelId, setPanelId] = useState("");
  const [serviceMobiles, setServiceMobiles] = useState("");
  const [messageId, setMessageId] = useState("");
  const [smartPreview, setSmartPreview] = useState<PishgamPreviewResult | null>(null);
  const [smartKeys, setSmartKeys] = useState<string[]>([]);

  useEffect(() => {
    if (fromLink) setCampaignId((current) => current || fromLink);
  }, [fromLink]);

  const picked = (campaigns.data ?? []).find((row) => row.id === campaignId);
  const panels = useQuery({ queryKey: ["perf", "panels"], queryFn: perfApi.panels });
  const lists = useQuery({ queryKey: ["perf", "lists"], queryFn: perfApi.lists });
  const panel = (panels.data ?? []).find((item) => item.id === panelId);
  const listRow = (lists.data ?? []).find((row) => row.id === listId);
  const sender = panel?.sender_line || "";

  useEffect(() => {
    if (!panelId && panels.data?.length === 1) setPanelId(panels.data[0].id);
  }, [panelId, panels.data]);

  const recipientCount = useMemo(() => {
    if (audienceKind === "list") return listRow?.final_count ?? 0;
    if (audienceKind === "smart" && smartPreview?.status === "done") {
      return smartPreview.estimates?.total_count ?? smartPreview.recipients?.reduce((s, r) => s + r.count, 0) ?? 0;
    }
    if (audienceKind === "isms") {
      return serviceMobiles.split(/[\s,،]+/).map((item) => item.trim()).filter(Boolean).length;
    }
    return 0;
  }, [audienceKind, listRow, smartPreview, serviceMobiles]);

  const shape = smsShape(body);
  const hasCancel = body.includes("لغو11") || body.includes("لغو 11");

  const missingItems = useMemo(() => {
    const items: Array<{ label: string; step: FlowStep }> = [];
    if (!body.trim()) items.push({ label: "متن خالی است", step: "message" });
    if (!hasCancel) items.push({ label: "«لغو۱۱» در متن نیست", step: "message" });
    if (!campaignId) items.push({ label: "کمپین انتخاب نشده", step: "message" });
    if (audienceKind === "list" && !listId) items.push({ label: "لیست انتخاب نشده", step: "audience" });
    if (audienceKind === "smart" && smartPreview?.status !== "done") items.push({ label: "شمارش محله انجام نشده", step: "audience" });
    if (audienceKind === "isms" && recipientCount === 0) items.push({ label: "شمارهٔ خدماتی نیست", step: "audience" });
    if (!panelId) items.push({ label: "پنل انتخاب نشده", step: "send" });
    return items;
  }, [body, hasCancel, campaignId, audienceKind, listId, smartPreview, recipientCount, panelId]);

  if (campaignsForbidden) {
    return (
      <>
        <PageHeader
          title={<Bi en="SMS" fa="پیامک" />}
          description={<Bi en="One flow: message, audience, send — with a live summary." fa="یک جریان: پیام، مخاطب، ارسال — با خلاصهٔ همیشه در دسترس." />}
        />
        <ForbiddenState />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={<Bi en="SMS" fa="پیامک" />}
        description={<Bi en="One flow: message, audience, send — with a live summary." fa="یک جریان: پیام، مخاطب، ارسال — با خلاصهٔ همیشه در دسترس." />}
        actions={
          <div className="row">
            <Button variant="secondary" onClick={() => void perfApi.smsPull().then((row) => toast(row.note))}>
              <Bi en="Read from panel" fa="خواندن از پنل" />
            </Button>
            {picked ? <RelatedLinks id={picked.id} code={picked.code} here="sms" /> : null}
          </div>
        }
      />
      <Segmented
        value={mainTab}
        onChange={setMainTab}
        items={[
          { key: "new", label: <Bi en="New send" fa="ارسال جدید" /> },
          { key: "history", label: <Bi en="History & reports" fa="سابقه و گزارش" /> },
        ]}
      />
      {mainTab === "history" ? (
        <SmsHistoryTab missing={stepParam === "delivery"} />
      ) : (
        <div className="sms-flow">
          <div className="sms-flow-main">
            <FlowStepNav step={flowStep} onStep={setFlowStep} />
            {flowStep === "message" ? (
              <MessageStep campaignId={campaignId} onCampaign={setCampaignId} body={body} onBody={setBody} />
            ) : null}
            {flowStep === "audience" ? (
              <AudienceStep
                kind={audienceKind}
                onKind={setAudienceKind}
                campaignId={campaignId}
                listId={listId}
                onListId={setListId}
                body={body}
                smartKeys={smartKeys}
                onSmartKeys={setSmartKeys}
                onSmartPreview={setSmartPreview}
                serviceMobiles={serviceMobiles}
                onServiceMobiles={setServiceMobiles}
                senderLine={sender}
              />
            ) : null}
            {flowStep === "send" ? (
              <SendStep
                campaignId={campaignId}
                body={body}
                panelId={panelId}
                onPanelId={setPanelId}
                audienceKind={audienceKind}
                listId={listId}
                recipientCount={recipientCount}
                serviceMobiles={serviceMobiles}
                onServiceMobiles={setServiceMobiles}
                messageId={messageId}
                onMessageId={setMessageId}
                smartPreview={smartPreview}
              />
            ) : null}
          </div>
          <aside className="sms-flow-summary">
            <SmsSummary
              campaign={picked}
              shape={shape}
              hasCancel={hasCancel}
              audienceKind={audienceKind}
              recipientCount={recipientCount}
              smartPreview={smartPreview}
              missing={missingItems}
              onJump={setFlowStep}
            />
          </aside>
        </div>
      )}
    </>
  );
}

function FlowStepNav({ step, onStep }: { step: FlowStep; onStep: (s: FlowStep) => void }) {
  const items: Array<{ key: FlowStep; label: string }> = [
    { key: "message", label: "۱ پیام" },
    { key: "audience", label: "۲ مخاطب" },
    { key: "send", label: "۳ ارسال" },
  ];
  return (
    <nav className="sms-flow-steps" aria-label="قدم‌ها">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className={item.key === step ? "sms-flow-step is-active" : "sms-flow-step"}
          onClick={() => onStep(item.key)}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}

function MessageStep({
  campaignId,
  onCampaign,
  body,
  onBody,
}: {
  campaignId: string;
  onCampaign: (id: string) => void;
  body: string;
  onBody: (text: string) => void;
}) {
  const toast = useToast();
  const panels = useQuery({ queryKey: ["perf", "panels"], queryFn: perfApi.panels });
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const requests = useQuery({ queryKey: ["perf", "requests"], queryFn: perfApi.requests });
  const lists = useQuery({ queryKey: ["perf", "lists"], queryFn: perfApi.lists });
  const [campaignQuery, setCampaignQuery] = useState("");
  const [brand, setBrand] = useState("");
  const [cars, setCars] = useState("");
  const [offer, setOffer] = useState("تحویل فوری");
  const [phone, setPhone] = useState("021-47677777");
  const [link, setLink] = useState("");
  const [recipients, setRecipients] = useState("");
  const textRef = useRef("");
  const drafted = useRef("");
  const campaign = campaigns.data?.find((row) => row.id === campaignId);
  const check = useMutation({
    mutationFn: (payload: { text: string; brand: string; recipients: number; panel_id?: string }) => perfApi.checkSms(payload),
  });
  const runCheck = check.mutate;
  useEffect(() => {
    textRef.current = body;
  }, [body]);
  const draft = useMutation({
    mutationFn: (payload: Record<string, string>) => perfApi.draftSms(payload),
    onSuccess: (data, variables) => {
      if (!data.messages.length) {
        if (!variables.quiet) toast("نمونه‌ای ساخته نشد");
        return;
      }
      if (variables.quiet === "1") {
        const first = data.messages.find((item) => item.kind === "ad1")?.text || data.messages[0]?.text || "";
        if (first && !textRef.current.trim()) onBody(first);
        return;
      }
      toast("سه نمونه پایین آماده است؛ یکی را بزنید تا در متن بنشیند.");
    },
    onError: (error: Error) => toast(error.message),
  });
  useEffect(() => {
    if (!body.trim()) return;
    const handle = window.setTimeout(() => {
      runCheck({ text: body, brand, recipients: recipients === "" ? 0 : Number(recipients), panel_id: panels.data?.[0]?.id });
    }, 400);
    return () => window.clearTimeout(handle);
  }, [body, brand, recipients, panels.data, runCheck]);
  useEffect(() => {
    if (!campaign || !requests.isFetched || !lists.isFetched || drafted.current === campaign.id) return;
    drafted.current = campaign.id;
    if (textRef.current.trim()) return;
    const names = (requests.data ?? [])
      .filter((row) => row.campaign_id === campaign.id)
      .map((row) => (row.summary || row.raw_text).trim())
      .filter(Boolean);
    const carLine = names.join("، ") || campaign.title;
    const linked = (lists.data ?? []).find((row) => row.campaign_id === campaign.id);
    setBrand(campaign.brand || "");
    setCars(carLine);
    if (linked) setRecipients(String(linked.final_count));
    draft.mutate({
      quiet: "1",
      brand: campaign.brand || "",
      cars: carLine,
      offer: "تحویل فوری",
      phone: "021-47677777",
      link: "",
      campaign_code: campaign.code,
    });
  }, [campaign, requests.isFetched, requests.data, lists.isFetched, lists.data, draft, onBody]);

  return (
    <Card>
      <SectionHeader
        icon="message"
        title={<Bi en="Message" fa="پیام" />}
        hint={
          <Bi
            en="Persian stays one page through 70 characters. Character 71 doubles the price."
            fa="فارسی تا ۷۰ نویسه یک صفحه است. نویسهٔ ۷۱ هزینه را دو برابر می‌کند؛ نمونهٔ دوصفحه‌ای جداست."
          />
        }
      />
      <div className="form-grid">
        <Field className="span-2" label={<Bi en="Campaign" fa="کمپین" />}>
          <Input value={campaignQuery} placeholder="جستجوی کد یا عنوان" onChange={(event) => setCampaignQuery(event.target.value)} />
          <Select value={campaignId} onChange={(e) => onCampaign(e.target.value)}>
            <option value="">—</option>
            {visibleCampaigns(campaigns.data, campaignQuery, campaignId).map((row) => (
              <option key={row.id} value={row.id}>{row.code} — {row.title}</option>
            ))}
          </Select>
        </Field>
        <Field className="span-all" label={<Bi en="Message" fa="متن" />}>
          <TextArea value={body} onChange={(e) => onBody(e.target.value)} rows={6} />
          <Meter text={body} recipients={recipients === "" ? 0 : Number(recipients)} tariff={panels.data?.[0]?.tariff_toman || 0} />
          {check.data || check.isPending || check.isError ? (
            <div className="perf-check perf-check--inline">
              {check.isPending ? <Muted as="p">در حال چک قوانین…</Muted> : null}
              {check.isError ? (
                <Muted as="p">{check.error instanceof Error ? check.error.message : "چک قوانین انجام نشد."}</Muted>
              ) : null}
              {check.data ? (
                <>
                  <Badge tone={check.data.ok ? "ok" : "warn"}>
                    {toman(check.data.pages)} صفحه، {toman(check.data.chars)} نویسه
                    {check.data.estimated_cost_toman ? `، حدود ${toman(check.data.estimated_cost_toman)} تومان` : ""}
                  </Badge>
                  {check.data.issues.map((issue) => (
                    <Muted key={issue} as="p">{issue}</Muted>
                  ))}
                  {(check.data.warnings || []).map((issue) => (
                    <Muted key={`w-${issue}`} as="p">{issue}</Muted>
                  ))}
                </>
              ) : null}
            </div>
          ) : null}
        </Field>
        <div className="span-all perf-actions">
          <Button type="button" variant="secondary" onClick={() => check.mutate({ text: body, brand, recipients: recipients === "" ? 0 : Number(recipients), panel_id: panels.data?.[0]?.id })}>
            <Bi en="Check rules" fa="چک قوانین" />
          </Button>
          <Button
            type="button"
            disabled={draft.isPending}
            onClick={() =>
              draft.mutate({
                brand: brand || campaign?.brand || "",
                cars: cars || campaign?.title || "",
                offer,
                phone,
                link,
                campaign_code: campaign?.code || "",
              })
            }
          >
            {draft.isPending ? <Bi en="Writing" fa="در حال نوشتن…" /> : <Bi en="Write samples" fa="نمونه را بنویس" />}
          </Button>
        </div>
        <details className="span-all">
          <summary className="muted"><Bi en="Text details" fa="جزئیات متن" /></summary>
          <div className="form-grid">
            <Field label={<Bi en="Brand" fa="برند" />}><Input value={brand} placeholder={campaign?.brand} onChange={(e) => setBrand(e.target.value)} /></Field>
            <Field label={<Bi en="Cars" fa="خودروها" />}><Input value={cars} placeholder={campaign?.title} onChange={(e) => setCars(e.target.value)} /></Field>
            <Field label={<Bi en="Offer" fa="پیشنهاد" />}><Input value={offer} onChange={(e) => setOffer(e.target.value)} /></Field>
            <Field label={<Bi en="Phone" fa="تلفن" />}><Input value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
            <Field label={<Bi en="Link" fa="لینک" />}><Input value={link} onChange={(e) => setLink(e.target.value)} /></Field>
          </div>
        </details>
      </div>
      {draft.data?.messages.length ? (
        <div className="perf-samples">
          {draft.data.messages.map((item) => (
            <button key={item.kind || item.text} type="button" className="perf-sample" onClick={() => onBody(item.text)}>
              <span className="row">
                <Badge tone={item.check.pages > 1 ? "warn" : "ok"}>{item.label || `${toman(item.check.pages)} صفحه`}</Badge>
                <Muted>
                  {toman(item.check.chars)} نویسه · {toman(item.check.room ?? 0)} تا صفحهٔ بعد
                </Muted>
              </span>
              <p>{item.text}</p>
              {item.note ? <Muted>{item.note}</Muted> : null}
            </button>
          ))}
        </div>
      ) : null}
    </Card>
  );
}

function AudienceStep({
  kind,
  onKind,
  campaignId,
  listId,
  onListId,
  body,
  smartKeys,
  onSmartKeys,
  onSmartPreview,
  serviceMobiles,
  onServiceMobiles,
  senderLine,
}: {
  kind: AudienceKind;
  onKind: (k: AudienceKind) => void;
  campaignId: string;
  listId: string;
  onListId: (id: string) => void;
  body: string;
  smartKeys: string[];
  onSmartKeys: (keys: string[]) => void;
  onSmartPreview: (p: PishgamPreviewResult | null) => void;
  serviceMobiles: string;
  onServiceMobiles: (v: string) => void;
  senderLine: string;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const remove = useRemove();
  const lists = useQuery({ queryKey: ["perf", "lists"], queryFn: perfApi.lists });
  const blocked = useQuery({ queryKey: ["perf", "blacklist"], queryFn: perfApi.blacklist });
  const [phone, setPhone] = useState("");
  const prepare = useMutation({
    mutationFn: (file: File) => {
      const data = new FormData();
      data.append("file", file);
      data.append("recent_days", "14");
      data.append("chunk_size", "15000");
      if (campaignId) data.append("campaign_id", campaignId);
      return perfApi.prepareList(data);
    },
    onSuccess: (row) => {
      toast("لیست آماده شد");
      qc.invalidateQueries({ queryKey: ["perf", "lists"] });
      onListId(row.id);
    },
    onError: (error: Error) => toast(error.message),
  });
  const block = useMutation({
    mutationFn: () => perfApi.addBlacklist(phone, "لغو"),
    onSuccess: () => {
      setPhone("");
      toast("به لیست سیاه اضافه شد");
      qc.invalidateQueries({ queryKey: ["perf", "blacklist"] });
    },
    onError: (error: Error) => toast(error.message),
  });

  return (
    <Card>
      <SectionHeader icon="users" title={<Bi en="Audience" fa="مخاطب" />} />
      <Segmented
        value={kind}
        onChange={onKind}
        items={[
          { key: "list", label: <Bi en="Our list" fa="لیست خودمان" /> },
          { key: "smart", label: <Bi en="Smart area" fa="محلهٔ هوشمند" /> },
          { key: "postal", label: <Bi en="Postal zone" fa="منطقهٔ کدپستی" /> },
          { key: "isms", label: <Bi en="Service numbers" fa="شماره‌های خدماتی" /> },
        ]}
      />
      {kind === "list" ? (
        <div className="sms-flow-audience-panel">
          <FilePick accept=".xlsx" label={<Bi en="Didar Excel" fa="فایل دیدار" />} hint=".xlsx" busy={prepare.isPending} onFile={(file) => prepare.mutate(file)} />
          <Field label={<Bi en="Prepared list" fa="لیست آماده" />}>
            <Select value={listId} onChange={(e) => onListId(e.target.value)}>
              <option value="">—</option>
              {(lists.data ?? []).map((row) => <option key={row.id} value={row.id}>{row.name} ({toman(row.final_count)})</option>)}
            </Select>
          </Field>
          {listId ? (
            <Button type="button" variant="secondary" onClick={() => downloadPerf(`/perf/lists/${listId}/export`, "recipients.xlsx")}>
              <Bi en="Download xlsx" fa="دانلود xlsx" />
            </Button>
          ) : null}
          <details className="perf-fold">
            <summary>لیست سیاه</summary>
            <div className="form-grid">
              <Field className="span-2" label={<Bi en="Number" fa="شماره" />}>
                <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
              </Field>
              <Button type="button" variant="secondary" disabled={!phone} onClick={() => block.mutate()}><Bi en="Add" fa="افزودن" /></Button>
            </div>
            {blocked.data?.length ? (
              <ul className="perf-car-list">
                {blocked.data.map((row) => (
                  <li key={row.id}>
                    <span>{row.phone}</span>
                    <Button type="button" variant="danger-quiet" className="btn-sm" onClick={() => void remove(row.phone, () => perfApi.deleteBlacklist(row.id))}>حذف</Button>
                  </li>
                ))}
              </ul>
            ) : null}
          </details>
          {lists.data?.length ? (
            <Table
              rows={lists.data.slice(0, 6)}
              rowKey={(row: RecipientList) => row.id}
              columns={[
                { key: "name", header: "نام", render: (row) => row.name },
                { key: "final", header: "نهایی", render: (row) => toman(row.final_count) },
                { key: "pick", header: "", render: (row) => <Button type="button" variant="ghost" onClick={() => onListId(row.id)}>انتخاب</Button> },
              ]}
            />
          ) : null}
        </div>
      ) : null}
      {kind === "smart" ? (
        <TargetingCard smsBody={body} pickedKeys={smartKeys} onPickedChange={onSmartKeys} onPreviewChange={onSmartPreview} />
      ) : null}
      {kind === "postal" ? <PishgamPostalAudience body={body} senderLine={senderLine} /> : null}
      {kind === "isms" ? (
        <div className="sms-flow-audience-panel">
          <Muted as="p">
            <Link to="/perf/connections"><Bi en="Connections" fa="اتصالات" /></Link>
            {" — "}
            <Bi en="Up to 20 service numbers via iSMS API." fa="حداکثر ۲۰ شماره با وب‌سرویس آی‌اس‌ام‌اس." />
          </Muted>
          <Field label={<Bi en="Service numbers" fa="شماره‌های خدماتی" />}>
            <TextArea value={serviceMobiles} rows={4} placeholder="هر شماره یک خط" onChange={(e) => onServiceMobiles(e.target.value)} />
          </Field>
        </div>
      ) : null}
    </Card>
  );
}

function SendStep({
  campaignId,
  body,
  panelId,
  onPanelId,
  audienceKind,
  listId,
  recipientCount,
  serviceMobiles,
  onServiceMobiles,
  messageId,
  onMessageId,
  smartPreview,
}: {
  campaignId: string;
  body: string;
  panelId: string;
  onPanelId: (id: string) => void;
  audienceKind: AudienceKind;
  listId: string;
  recipientCount: number;
  serviceMobiles: string;
  onServiceMobiles: (v: string) => void;
  messageId: string;
  onMessageId: (v: string) => void;
  smartPreview: PishgamPreviewResult | null;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const panels = useQuery({ queryKey: ["perf", "panels"], queryFn: perfApi.panels });
  const panel = (panels.data ?? []).find((item) => item.id === panelId);
  const sender = panel?.sender_line || "";
  const save = useMutation({
    mutationFn: () =>
      perfApi.createSend({
        body,
        campaign_id: campaignId || null,
        panel_id: panelId || null,
        list_id: audienceKind === "list" ? listId || null : null,
        recipient_count: recipientCount,
        leads: 0,
        pishgam_message_id: panel?.code === "pishgam" && messageId.trim() ? Number(messageId) : null,
      }),
    onSuccess: () => {
      toast("ارسال ثبت شد");
      onMessageId("");
      qc.invalidateQueries({ queryKey: ["perf"] });
    },
    onError: (error: Error) => toast(error.message),
  });

  return (
    <Card>
      <SectionHeader icon="send" title={<Bi en="Send" fa="ارسال" />} />
      <div className="form-grid">
        <Field label={<Bi en="Panel" fa="پنل" />}>
          <Select value={panelId} onChange={(e) => onPanelId(e.target.value)}>
            <option value="">—</option>
            {(panels.data ?? []).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </Select>
        </Field>
        {audienceKind === "list" && listId ? (
          <div className="span-all perf-actions">
            <Button type="button" variant="secondary" onClick={() => downloadPerf(`/perf/lists/${listId}/export`, "recipients.xlsx")}>
              <Bi en="Download list" fa="دانلود لیست" />
            </Button>
            {panel?.code === "pishgam" ? (
              <Button
                type="button"
                onClick={() => {
                  window.open(pishgamPageUrl("sendBulkSMS", body, sender), "_blank", "noopener,noreferrer");
                  toast("پنل پیشگام باز شد.");
                }}
              >
                <Bi en="Open Pishgam" fa="ارسال در پیشگام" />
              </Button>
            ) : null}
          </div>
        ) : null}
        {audienceKind === "smart" ? (
          <div className="span-all">
            <Muted as="p">ارسال هوشمند قفل است تا تأیید دستی شما. اولین ارسال واقعی با تعداد کم در پنل پیشگام انجام شود.</Muted>
            <Button type="button" variant="secondary" disabled title="قفل">
              <Bi en="Smart send locked" fa="ارسال هوشمند (قفل)" />
            </Button>
            {smartPreview?.status === "done" ? (
              <Muted as="p">شناسهٔ درخواست‌ها: {(smartPreview.requests ?? []).map((r) => r.smart_sms_request_id).join("، ")}</Muted>
            ) : null}
          </div>
        ) : null}
        {audienceKind === "postal" ? (
          <div className="span-all">
            <Muted as="p">بعد از ارسال در پنل پیشگام، سابقه را اینجا ثبت کنید.</Muted>
            <PishgamPostalAudience body={body} senderLine={sender} />
          </div>
        ) : null}
        {audienceKind === "isms" ? (
          <Field className="span-all" label={<Bi en="Service numbers" fa="شماره‌های خدماتی" />}>
            <TextArea value={serviceMobiles} rows={3} onChange={(e) => onServiceMobiles(e.target.value)} />
          </Field>
        ) : null}
        {panel?.code === "pishgam" && audienceKind !== "smart" ? (
          <Field label={<Bi en="Panel send id" fa="شناسهٔ ارسال پنل" />}>
            <Input type="number" dir="ltr" value={messageId} placeholder="از صف پیشگام" onChange={(e) => onMessageId(e.target.value)} />
          </Field>
        ) : null}
        <Field className="span-all" label={<Bi en="Text" fa="متن" />}>
          <TextArea value={body} readOnly rows={3} />
        </Field>
        <Field label={<Bi en="Recipients" fa="گیرنده" />}>
          <Input readOnly value={toman(recipientCount)} />
        </Field>
        <div className="span-all perf-actions">
          {audienceKind === "isms" ? (
            <Button
              type="button"
              disabled={!panelId}
              onClick={() => {
                void (async () => {
                  if (!panel || panel.code !== "isms") {
                    toast("پنل آی‌اس‌ام‌اس انتخاب کنید.");
                    return;
                  }
                  const numbers = serviceMobiles.split(/[\s,،]+/).map((item) => item.trim()).filter(Boolean);
                  if (!numbers.length || numbers.length > 20) {
                    toast("۱ تا ۲۰ شماره بنویسید.");
                    return;
                  }
                  if (!panel.has_secret || !panel.api_username) {
                    toast("اتصال آی‌اس‌ام‌اس را در اتصالات ذخیره کنید.");
                    return;
                  }
                  const ok = await confirm("ارسال پیامک", `به ${toman(numbers.length)} شماره ارسال می‌شود.`, "بله", { danger: true });
                  if (!ok) return;
                  perfApi.isms({ panel_id: panelId, mobiles: numbers, body }).then(() => toast("فرستاده شد")).catch((e: Error) => toast(e.message));
                })();
              }}
            >
              <Bi en="Send iSMS" fa="ارسال خدماتی" />
            </Button>
          ) : null}
          <Button type="button" variant="secondary" disabled={!body.trim() || save.isPending} onClick={() => save.mutate()}>
            <Bi en="Save record" fa="ثبت سابقه" />
          </Button>
        </div>
      </div>
    </Card>
  );
}

function SmsSummary({
  campaign,
  shape,
  hasCancel,
  audienceKind,
  recipientCount,
  smartPreview,
  missing,
  onJump,
}: {
  campaign?: { code: string; title: string };
  shape: ReturnType<typeof smsShape>;
  hasCancel: boolean;
  audienceKind: AudienceKind;
  recipientCount: number;
  smartPreview: PishgamPreviewResult | null;
  missing: Array<{ label: string; step: FlowStep }>;
  onJump: (step: FlowStep) => void;
}) {
  const audienceLabel =
    audienceKind === "list" ? "لیست خودمان" :
    audienceKind === "smart" ? "محلهٔ هوشمند" :
    audienceKind === "postal" ? "کدپستی (پنل)" : "خدماتی";
  const estimate = smartPreview?.estimates?.tariff_total;
  const credit = smartPreview?.credit;
  return (
    <Card className="sms-flow-summary-card">
      <SectionHeader icon="sparkles" title={<Bi en="Summary" fa="خلاصه" />} />
      <ul className="sms-flow-summary-list">
        <li><strong>کمپین:</strong> {campaign ? <TitleCode title={campaign.title} code={campaign.code} /> : "—"}</li>
        <li><strong>متن:</strong> {toman(shape.chars)} نویسه · {toman(shape.pages)} صفحه</li>
        <li><strong>لغو۱۱:</strong> {hasCancel ? <Badge tone="ok">بله</Badge> : <Badge tone="warn">خیر</Badge>}</li>
        <li><strong>مخاطب:</strong> {audienceLabel} · {toman(recipientCount)} نفر</li>
        {estimate != null ? <li><strong>برآورد (تعرفه):</strong> <span className="perf-num">{toman(estimate)}</span> ریال</li> : null}
        {credit != null ? <li><strong>موجودی پیشگام:</strong> <span className="perf-num">{toman(credit)}</span> ریال</li> : null}
      </ul>
      {missing.length ? (
        <div className="sms-flow-missing">
          <Muted as="p">موارد کم:</Muted>
          <ul>
            {missing.map((item) => (
              <li key={item.label}>
                <button type="button" className="sms-flow-missing-link" onClick={() => onJump(item.step)}>{item.label}</button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <Badge tone="ok">آمادهٔ ثبت یا ارسال</Badge>
      )}
    </Card>
  );
}
