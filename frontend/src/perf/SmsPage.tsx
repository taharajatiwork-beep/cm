import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Card, ErrorMessage, Field, Input, LoadingState, Muted, PageHeader, SectionHeader, Segmented, Select, Table, TextArea } from "../components/ui";
import { DateText } from "../components/DateText";
import { useToast } from "../components/ui/Toast";
import { Bi } from "../i18n";
import { downloadPerf, perfApi, toman, type PanelStatus, type PishgamDelivery, type RecipientList, type SmsSend } from "./api";
import { CampaignCode, FilePick, RelatedLinks } from "./bits";
import { ArrangeBar, hit, ShowMore, useArrange, type SortOption } from "./browse";
import { useLiveConnections, useSavedConnections } from "./connectionsQuery";
import { RowActions, SmsDelivery, SmsEdit, useRemove } from "./edit";

type Tab = "write" | "list" | "send" | "pishgam";

function visibleCampaigns(rows: Array<{ id: string; code: string; title: string }> | undefined, query: string, selected: string) {
  return (rows ?? []).filter((row) => row.id === selected || hit(query, row.code, row.title));
}

export function SmsPage() {
  const [params] = useSearchParams();
  const fromUrl = params.get("campaign") || "";
  const step = params.get("step") || "";
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const fromLink = (campaigns.data ?? []).find((row) => row.id === fromUrl || row.code === fromUrl)?.id || "";
  const [campaignId, setCampaignId] = useState(fromUrl.length > 8 ? fromUrl : "");
  const [tab, setTab] = useState<Tab>(step === "delivery" ? "send" : "write");
  const [readyText, setReadyText] = useState("");
  const [readyCount, setReadyCount] = useState(0);
  const [listId, setListId] = useState("");
  useEffect(() => {
    if (fromLink) setCampaignId((current) => current || fromLink);
  }, [fromLink]);
  const picked = (campaigns.data ?? []).find((row) => row.id === campaignId);
  return (
    <>
      <PageHeader
        title={<Bi en="SMS" fa="پیامک" />}
        description={<Bi en="The draft and the rule check fill in from the campaign. The list attaches itself. Sending still waits for the button." fa="متن و چک قوانین از روی کمپین پر می‌شود. لیست به همان کمپین می‌چسبد. ارسال هنوز با دکمه است." />}
        actions={picked ? <RelatedLinks id={picked.id} code={picked.code} here="sms" /> : null}
      />
      <Segmented
        value={tab}
        onChange={setTab}
        items={[
          { key: "write", label: <Bi en="Write" fa="نوشتن پیام" /> },
          { key: "list", label: <Bi en="List" fa="آماده‌سازی لیست" /> },
          { key: "send", label: <Bi en="Record" fa="ثبت ارسال" /> },
          { key: "pishgam", label: <Bi en="Pishgam" fa="پیشگام" /> },
        ]}
      />
      {tab === "write" ? (
        <WriteTab
          campaignId={campaignId}
          onCampaign={setCampaignId}
          onUse={(text, count) => {
            setReadyText(text);
            if (count) setReadyCount(count);
            setTab("send");
          }}
        />
      ) : null}
      {tab === "list" ? <ListTab campaignId={campaignId} onUse={(id, count) => { setListId(id); setReadyCount(count); setTab("send"); }} /> : null}
      {tab === "send" ? <SendTab campaignId={campaignId} onCampaign={setCampaignId} initialBody={readyText} initialCount={readyCount} initialListId={listId} missing={step === "delivery"} /> : null}
      {tab === "pishgam" ? <PishgamTab /> : null}
    </>
  );
}

function WriteTab({ campaignId, onCampaign, onUse }: { campaignId: string; onCampaign: (id: string) => void; onUse: (text: string, count: number) => void }) {
  const toast = useToast();
  const panels = useQuery({ queryKey: ["perf", "panels"], queryFn: perfApi.panels });
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const requests = useQuery({ queryKey: ["perf", "requests"], queryFn: perfApi.requests });
  const lists = useQuery({ queryKey: ["perf", "lists"], queryFn: perfApi.lists });
  const [campaignQuery, setCampaignQuery] = useState("");
  const campaign = campaigns.data?.find((row) => row.id === campaignId);
  const [text, setText] = useState("");
  const [brand, setBrand] = useState("");
  const [cars, setCars] = useState("");
  const [offer, setOffer] = useState("تحویل فوری");
  const [phone, setPhone] = useState("021-47677777");
  const [link, setLink] = useState("");
  const [recipients, setRecipients] = useState(0);
  const textRef = useRef("");
  const drafted = useRef("");
  const check = useMutation({
    mutationFn: (body: { text: string; brand: string; recipients: number; panel_id?: string }) => perfApi.checkSms(body),
  });
  // mutate در TanStack پایدار است؛ با آن (نه کل شیء check) چک خودکار به آخرین مقدارها وصل می‌ماند بی‌آنکه هر رندر دوباره اجرا شود
  const runCheck = check.mutate;
  // ref فقط بعد از رندر به‌روز می‌شود (نه وسط رندر)؛ این افکت قبل از افکت پیش‌نویس پایین اجرا می‌شود
  useEffect(() => {
    textRef.current = text;
  }, [text]);
  const draft = useMutation({
    mutationFn: (body: Record<string, string>) => perfApi.draftSms(body),
    onSuccess: (data, variables) => {
      const first = data.messages.find((item) => item.kind === "ad1")?.text || data.messages[0]?.text || "";
      if (!first) {
        if (!variables.quiet) toast("نمونه‌ای ساخته نشد");
        return;
      }
      setText(first);
      if (!variables.quiet) toast("نمونه در متن نشست");
    },
    onError: (error: Error) => toast(error.message),
  });
  useEffect(() => {
    if (!text.trim()) return;
    const handle = window.setTimeout(() => {
      runCheck({ text, brand, recipients, panel_id: panels.data?.[0]?.id });
    }, 400);
    return () => window.clearTimeout(handle);
  }, [text, brand, recipients, panels.data, runCheck]);
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
    if (linked) setRecipients(linked.final_count);
    draft.mutate({
      quiet: "1",
      brand: campaign.brand || "",
      cars: carLine,
      offer: "تحویل فوری",
      phone: "021-47677777",
      link: "",
      campaign_code: campaign.code,
    });
  }, [campaign, requests.isFetched, requests.data, lists.isFetched, lists.data, draft]);
  return (
    <Card>
      <SectionHeader
        icon="message"
        title={<Bi en="Write the text" fa="نوشتن متن" />}
        hint={<Bi en="Persian stays one page through 70 characters. Character 71 doubles the price. A second page is offered on purpose." fa="فارسی تا ۷۰ نویسه یک صفحه است. نویسهٔ ۷۱ هزینه را دو برابر می‌کند. نمونهٔ دو صفحه‌ای عمداً جداست." />}
      />
      <div className="form-grid">
        <Field className="span-2" label={<Bi en="Campaign" fa="کمپین" />}>
          <Input value={campaignQuery} placeholder="جستجوی کد یا عنوان" onChange={(event) => setCampaignQuery(event.target.value)} />
          <Select value={campaignId} onChange={(e) => onCampaign(e.target.value)}>
            <option value="">—</option>
            {visibleCampaigns(campaigns.data, campaignQuery, campaignId).map((row) => <option key={row.id} value={row.id}>{row.code} — {row.title}</option>)}
          </Select>
        </Field>
        <Field className="span-all" label={<Bi en="Message" fa="متن" />}>
          <TextArea value={text} onChange={(e) => setText(e.target.value)} rows={6} />
          <Meter text={text} recipients={recipients} tariff={panels.data?.[0]?.tariff_toman || 0} />
        </Field>
        <Field label={<Bi en="Recipients" fa="تعداد گیرنده" />}>
          <Input type="number" value={recipients || ""} placeholder="۰" onChange={(e) => setRecipients(Number(e.target.value))} />
        </Field>
        <div className="span-all perf-actions">
          <Button type="button" variant="secondary" onClick={() => check.mutate({ text, brand, recipients, panel_id: panels.data?.[0]?.id })}><Bi en="Check rules" fa="چک قوانین" /></Button>
          <Button type="button" disabled={draft.isPending} onClick={() => draft.mutate({
            brand: brand || campaign?.brand || "",
            cars: cars || campaign?.title || "",
            offer,
            phone,
            link,
            campaign_code: campaign?.code || "",
          })}>
            {draft.isPending ? <Bi en="Writing" fa="در حال نوشتن…" /> : <Bi en="Write samples" fa="نمونه را بنویس" />}
          </Button>
          {text.trim() || draft.data?.messages[0] ? (
            <Button type="button" variant="secondary" onClick={() => onUse(text.trim() || draft.data!.messages[0].text, recipients)}>
              <Bi en="Use this text" fa="همین متن برای ارسال" />
            </Button>
          ) : null}
        </div>
        <details className="span-all">
          <summary className="muted"><Bi en="Change the ingredients" fa="جزئیات متن" /></summary>
          <div className="form-grid">
            <Field label={<Bi en="Brand" fa="برند" />}><Input value={brand} placeholder={campaign?.brand} onChange={(e) => setBrand(e.target.value)} /></Field>
            <Field label={<Bi en="Cars" fa="خودروها" />}><Input value={cars} placeholder={campaign?.title} onChange={(e) => setCars(e.target.value)} /></Field>
            <Field label={<Bi en="Offer" fa="پیشنهاد" />}><Input value={offer} onChange={(e) => setOffer(e.target.value)} /></Field>
            <Field label={<Bi en="Phone" fa="تلفن" />}><Input value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
            <Field label={<Bi en="Link" fa="لینک" />}><Input value={link} onChange={(e) => setLink(e.target.value)} /></Field>
          </div>
        </details>
      </div>
      {check.data ? (
        <div className="perf-check">
          <Badge tone={check.data.ok ? "ok" : "warn"}>
            {toman(check.data.pages)} صفحه، {toman(check.data.chars)} نویسه، حدود {toman(check.data.estimated_cost_toman)} تومان
          </Badge>
          {check.data.issues.map((issue) => (
            <Muted key={issue} as="p">{issue}</Muted>
          ))}
          {(check.data.warnings || []).map((issue) => (
            <Muted key={issue} as="p">{issue}</Muted>
          ))}
        </div>
      ) : null}
      {draft.data?.messages.length ? (
        <div className="perf-samples">
          {draft.data.messages.map((item) => (
            <button key={item.kind || item.text} type="button" className="perf-sample" onClick={() => setText(item.text)}>
              <span className="row">
                <Badge tone={item.check.pages > 1 ? "warn" : "ok"}>{item.label || `${item.check.pages} صفحه`}</Badge>
                <Muted>{toman(item.check.chars)} نویسه · {toman(item.check.room ?? 0)} تا صفحهٔ بعد</Muted>
              </span>
              <p>{item.text}</p>
              <Muted>{item.note}</Muted>
            </button>
          ))}
        </div>
      ) : null}
    </Card>
  );
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

function smsShape(text: string) {
  const persian = text.length === 0 || /[\u0600-\u06FF]/.test(text) || /[^\u0000-\u007F]/.test(text);
  const units = Array.from(text).reduce((sum, ch) => sum + ((ch.codePointAt(0) || 0) > 0xffff ? 2 : 1), 0);
  const single = persian ? 70 : 160;
  const part = persian ? 67 : 153;
  const pages = units === 0 ? 0 : units <= single ? 1 : Math.ceil(units / part);
  const capacity = pages <= 1 ? single : part * pages;
  return { chars: units, pages, room: capacity - units, language: persian ? "فارسی" : "انگلیسی" };
}

function ListTab({ campaignId, onUse }: { campaignId: string; onUse: (id: string, count: number) => void }) {
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
      toast(campaignId ? "لیست آماده شد و روی فرم ارسال نشست" : "لیست آماده شد");
      qc.invalidateQueries({ queryKey: ["perf", "lists"] });
      if (campaignId) onUse(row.id, row.final_count);
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
    <>
      <Card>
        <SectionHeader
          icon="upload"
          title={<Bi en="Didar file" fa="فایل دیدار" />}
          hint={<Bi en="Duplicates, blacklist and recent sends are removed. The download is split for the panel, without a leading zero." fa="تکراری، لیست سیاه و ارسال اخیر حذف می‌شود. خروجی برای پنل، بدون صفر اول و در دسته‌های ۱۵هزارتایی است." />}
        />
        <FilePick
          accept=".xlsx"
          label={<Bi en="Choose the Excel" fa="انتخاب اکسل" />}
          hint=".xlsx"
          busy={prepare.isPending}
          onFile={(file) => prepare.mutate(file)}
        />
      </Card>
      <Card>
        <SectionHeader icon="alert" title={<Bi en="Blacklist" fa="لیست سیاه" />} hint={<Bi en="Numbers that must never receive a campaign." fa="شماره‌هایی که نباید کمپین بگیرند." />} />
        <div className="form-grid">
          <Field className="span-2" label={<Bi en="Number" fa="شماره" />}>
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </Field>
          <div className="perf-actions">
            <Button type="button" variant="secondary" disabled={!phone} onClick={() => block.mutate()}><Bi en="Add" fa="افزودن" /></Button>
          </div>
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
      </Card>
      {lists.isLoading ? <LoadingState /> : null}
      {lists.error ? <ErrorMessage error={lists.error instanceof Error ? lists.error.message : String(lists.error)} /> : null}
      {lists.data ? (
        <Card>
          <SectionHeader icon="users" title={<Bi en="Prepared lists" fa="لیست‌های آماده" />} count={lists.data.length} />
          <Table
            rows={lists.data}
            rowKey={(row) => row.id}
            columns={[
              { key: "name", header: "نام", render: (row: RecipientList) => row.name },
              { key: "raw", header: "خام", render: (row) => toman(row.raw_count) },
              { key: "dup", header: "تکراری", render: (row) => toman(row.duplicate_count) },
              { key: "black", header: "سیاه", render: (row) => toman(row.blacklist_count) },
              { key: "recent", header: "اخیر", render: (row) => toman(row.recent_count) },
              { key: "final", header: "نهایی", render: (row) => toman(row.final_count) },
              {
                key: "file",
                header: "فایل",
                render: (row) => (
                  <div className="row">
                    <Button type="button" variant="secondary" onClick={() => downloadPerf(`/perf/lists/${row.id}/export`, "recipients.xlsx")}>
                      xlsx
                    </Button>
                    <Button type="button" variant="ghost" onClick={() => onUse(row.id, row.final_count)}>
                      <Bi en="Use for send" fa="برای ارسال" />
                    </Button>
                    <Button type="button" variant="danger-quiet" className="btn-sm" onClick={() => void remove(row.name || "لیست", () => perfApi.deleteList(row.id))}>
                      حذف
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      ) : null}
    </>
  );
}

function SendTab({
  campaignId,
  onCampaign,
  initialBody,
  initialCount,
  initialListId,
  missing,
}: {
  campaignId: string;
  onCampaign: (id: string) => void;
  initialBody: string;
  initialCount: number;
  initialListId: string;
  missing?: boolean;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const panels = useQuery({ queryKey: ["perf", "panels"], queryFn: perfApi.panels });
  const lists = useQuery({ queryKey: ["perf", "lists"], queryFn: perfApi.lists });
  const sends = useQuery({ queryKey: ["perf", "sends"], queryFn: perfApi.sends });
  const [body, setBody] = useState(initialBody);
  const [campaignQuery, setCampaignQuery] = useState("");
  useEffect(() => {
    if (initialBody) setBody(initialBody);
  }, [initialBody]);
  const [panelId, setPanelId] = useState("");
  const [listId, setListId] = useState(initialListId);
  const [count, setCount] = useState(initialCount);
  useEffect(() => {
    if (initialListId) setListId(initialListId);
  }, [initialListId]);
  useEffect(() => {
    if (initialCount) setCount(initialCount);
  }, [initialCount]);
  useEffect(() => {
    if (!panelId && panels.data?.length === 1) setPanelId(panels.data[0].id);
  }, [panelId, panels.data]);
  const [leads, setLeads] = useState(0);
  const [username, setUsername] = useState("");
  const [secret, setSecret] = useState("");
  const [sender, setSender] = useState("");
  const [mobiles, setMobiles] = useState("");
  const [messageId, setMessageId] = useState("");
  const panel = (panels.data ?? []).find((item) => item.id === panelId);
  useEffect(() => {
    if (!panel) return;
    setUsername(panel.api_username || "");
    setSender(panel.sender_line || "");
    setSecret("");
  }, [panel]);
  useEffect(() => {
    const list = lists.data?.find((row) => row.id === listId);
    if (list) setCount(list.final_count);
  }, [listId, lists.data]);
  const save = useMutation({
    mutationFn: () =>
      perfApi.createSend({
        body,
        campaign_id: campaignId || null,
        panel_id: panelId || null,
        list_id: listId || null,
        recipient_count: count,
        leads,
        pishgam_message_id: panel?.code === "pishgam" && messageId.trim() ? Number(messageId) : null,
      }),
    onSuccess: () => {
      toast("ارسال ثبت شد");
      setBody("");
      setMessageId("");
      qc.invalidateQueries({ queryKey: ["perf"] });
    },
    onError: (error: Error) => toast(error.message),
  });
  return (
    <>
      <Card>
        <SectionHeader
          icon="send"
          title={<Bi en="Record a send" fa="ثبت ارسال" />}
          hint={<Bi en="Save the iSMS username and password, then send up to 20 service numbers. Bulk ads use the prepared file in the iSMS panel." fa="نام کاربری و رمز آی‌اس‌ام‌اس را ذخیره کنید. وب‌سرویس تا ۲۰ شماره خدماتی می‌فرستد. تبلیغ انبوه با فایل لیست، داخل خود پنل انجام می‌شود." />}
        />
        <div className="form-grid">
          <Field label={<Bi en="Campaign" fa="کمپین" />}>
            <Input value={campaignQuery} placeholder="جستجوی کد یا عنوان" onChange={(event) => setCampaignQuery(event.target.value)} />
            <Select value={campaignId} onChange={(e) => onCampaign(e.target.value)}>
              <option value="">—</option>
              {visibleCampaigns(campaigns.data, campaignQuery, campaignId).map((row) => (
                <option key={row.id} value={row.id}>{row.code} — {row.title}</option>
              ))}
            </Select>
          </Field>
          <Field label={<Bi en="Panel" fa="پنل" />}>
            <Select value={panelId} onChange={(e) => setPanelId(e.target.value)}>
              <option value="">—</option>
              {(panels.data ?? []).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </Select>
          </Field>
          <Field label={<Bi en="Prepared list" fa="لیست آماده" />}>
            <Select value={listId} onChange={(e) => setListId(e.target.value)}>
              <option value="">—</option>
              {(lists.data ?? []).map((row) => <option key={row.id} value={row.id}>{row.name} ({toman(row.final_count)})</option>)}
            </Select>
          </Field>
          {panel?.code === "isms" ? (
            <>
              <Field label={<Bi en="Username" fa="نام کاربری آی‌اس‌ام‌اس" />}>
                <Input value={username} onChange={(e) => setUsername(e.target.value)} />
              </Field>
              <Field label={<Bi en="API password" fa="رمز وب‌سرویس" />}>
                <Input type="password" value={secret} placeholder={panel.has_secret ? "رمز ذخیره شده" : ""} onChange={(e) => setSecret(e.target.value)} />
              </Field>
              <Field label={<Bi en="Sender" fa="خط ارسال" />}>
                <Input value={sender} onChange={(e) => setSender(e.target.value)} />
              </Field>
              <div className="perf-actions">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    const payload: Record<string, string> = { api_username: username, sender_line: sender };
                    if (secret.trim()) payload.api_secret = secret.trim();
                    perfApi.updatePanel(panel.id, payload).then(() => {
                      toast(secret.trim() || panel.has_secret ? "اتصال آی‌اس‌ام‌اس ذخیره شد" : "نام کاربری ذخیره شد. رمز وب‌سرویس هنوز خالی است.");
                      setSecret("");
                      qc.invalidateQueries({ queryKey: ["perf", "panels"] });
                    }).catch((error: Error) => toast(error.message));
                  }}
                >
                  <Bi en="Save connection" fa="ذخیره اتصال" />
                </Button>
              </div>
              <Field className="span-all" label={<Bi en="Service numbers" fa="شماره‌های خدماتی" />}>
                <TextArea value={mobiles} rows={3} placeholder="هر شماره یک خط. حداکثر ۲۰ شماره." onChange={(e) => setMobiles(e.target.value)} />
              </Field>
            </>
          ) : null}
          {panel?.code === "pishgam" ? (
            <>
              <Field label={<Bi en="Sender line" fa="خط ارسال" />}>
                <Input dir="ltr" value={sender} placeholder="مثل 5000302137682" onChange={(e) => setSender(e.target.value)} />
              </Field>
              <div className="perf-actions">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    perfApi.updatePanel(panel.id, { sender_line: sender }).then(() => {
                      toast("خط ارسال پیشگام ذخیره شد");
                      qc.invalidateQueries({ queryKey: ["perf", "panels"] });
                    }).catch((error: Error) => toast(error.message));
                  }}
                >
                  <Bi en="Save line" fa="ذخیره خط" />
                </Button>
              </div>
              <Field label={<Bi en="Panel send id" fa="شناسهٔ ارسال پنل" />}>
                <Input type="number" dir="ltr" value={messageId} placeholder="از صف ارسال پنل پیشگام" onChange={(e) => setMessageId(e.target.value)} />
              </Field>
              <div className="span-all">
                <Muted>
                  ثبت ارسال فقط سابقه را اینجا نگه می‌دارد. برای فرستادن، تب پیشگام را باز کنید؛ هر بخش به صفحهٔ خودش در پیشگام می‌رود و ارسال آنجا انجام می‌شود.
                </Muted>
              </div>
            </>
          ) : null}
          <Field className="span-all" label={<Bi en="Text" fa="متن" />}><TextArea value={body} onChange={(e) => setBody(e.target.value)} rows={4} /></Field>
          <Field label={<Bi en="Recipients" fa="گیرنده" />}><Input type="number" value={count || ""} placeholder="۰" onChange={(e) => setCount(Number(e.target.value))} /></Field>
          <Field label={<Bi en="Leads" fa="ورودی" />}><Input type="number" value={leads || ""} placeholder="۰" onChange={(e) => setLeads(Number(e.target.value))} /></Field>
          <div className="span-all perf-actions">
            <Button type="button" disabled={!body.trim() || save.isPending} onClick={() => save.mutate()}><Bi en="Save send" fa="ثبت ارسال" /></Button>
            <Button
              type="button"
              variant="secondary"
              disabled={!panelId}
              onClick={() => {
                if (panel?.code === "pishgam") {
                  const url = pishgamPageUrl("sendSMS", {
                    body,
                    sender,
                    state: "",
                    city: "",
                    region: "",
                    postal: "",
                    numbers: mobiles,
                  });
                  window.open(url, "_blank", "noopener,noreferrer");
                  toast("صفحهٔ ارسال پیشگام باز شد. ارسال را آنجا بزنید.");
                  return;
                }
                if (!panel || panel.code !== "isms") {
                  toast("وب‌سرویس فقط برای آی‌اس‌ام‌اس و پیام خدماتی است");
                  return;
                }
                const numbers = mobiles.split(/[\s,،]+/).map((item) => item.trim()).filter(Boolean);
                if (!numbers.length) {
                  toast("شماره را بنویسید. وب‌سرویس تا ۲۰ شماره خدماتی می‌فرستد.");
                  return;
                }
                if (numbers.length > 20) {
                  toast("بیش از ۲۰ شماره است. برای تبلیغ انبوه، فایل لیست را در خود پنل آی‌اس‌ام‌اس آپلود کنید.");
                  return;
                }
                if (!panel.has_secret || username.trim() !== (panel.api_username || "")) {
                  toast("اول نام کاربری و رمز را با «ذخیره اتصال» ثبت کنید.");
                  return;
                }
                perfApi.isms({ panel_id: panelId, mobiles: numbers, body }).then(() => {
                  toast("به وب‌سرویس آی‌اس‌ام‌اس فرستاده شد");
                }).catch((error: Error) => toast(error.message));
              }}
            >
              {panel?.code === "pishgam" ? (
                <Bi en="Open in Pishgam" fa="ادامه در پیشگام" />
              ) : (
                <Bi en="Send service SMS" fa="ارسال خدماتی آی‌اس‌ام‌اس" />
              )}
            </Button>
          </div>
        </div>
      </Card>
      {sends.isLoading ? <LoadingState /> : null}
      {sends.data ? <RecordedSends rows={sends.data} missing={missing} /> : null}
    </>
  );
}

const SEND_SORTS: SortOption<SmsSend>[] = [
  { key: "cost-desc", label: "بیشترین هزینه", pick: (row) => row.cost_toman, dir: "desc" },
  { key: "n-desc", label: "بیشترین گیرنده", pick: (row) => row.recipient_count, dir: "desc" },
  { key: "del-desc", label: "بیشترین تحویل", pick: (row) => row.delivered_count, dir: "desc" },
  { key: "leads-desc", label: "بیشترین ورودی", pick: (row) => row.leads, dir: "desc" },
  { key: "date", label: "جدیدترین ارسال", pick: (row) => row.sent_at || "", dir: "desc" },
  { key: "code", label: "کد کمپین", pick: (row) => row.campaign_code, dir: "asc" },
];

function sendText(body: string): string {
  return body.replace(/\[\[[^\]]+\]\]/g, "").replace(/\s+/g, " ").trim();
}

function RecordedSends({ rows, missing }: { rows: SmsSend[]; missing?: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const remove = useRemove();
  const [edit, setEdit] = useState<SmsSend | null>(null);
  const [delivery, setDelivery] = useState<SmsSend | null>(null);
  const start = missing ? "open" : "linked";
  const [scope, setScope] = useState(start);
  const narrowed = rows.filter((row) => {
    if (scope === "delivered") return row.delivered_count > 0;
    if (scope === "open") return row.recipient_count > 0 && !row.delivered_count;
    if (scope === "linked") return Boolean(row.campaign_code);
    if (scope === "loose") return !row.campaign_code;
    return true;
  });
  const list = useArrange(narrowed, 12, SEND_SORTS, (row) => [row.campaign_code, row.body, row.recipient_count], scope);
  const dirty = scope !== start || list.searching || list.sortChanged;
  return (
    <Card>
      <SectionHeader icon="clock" title={<Bi en="Recorded sends" fa="ارسال‌های ثبت‌شده" />} count={list.ordered.length} />
      <FilePick
        accept=".xlsx"
        label={<Bi en="Drop the panel report" fa="گزارش پنل را بیندازید" />}
        hint={<Bi en="Matched by date or recipient count. Successful delivery counts; waiting does not." fa="با تاریخ یا تعداد گیرنده جور می‌شود. دریافت موفق شمرده می‌شود و منتظر گزارش نه." />}
        onFile={(file) => {
          perfApi.matchDelivery(file).then((result) => {
            toast(`${result.campaign_code || "ارسال"}: ${toman(result.delivered_count)} تحویل`);
            qc.invalidateQueries({ queryKey: ["perf", "sends"] });
          }).catch((error: Error) => toast(error.message));
        }}
      />
      <ArrangeBar
        query={list.query}
        onQuery={list.setQuery}
        placeholder="کد کمپین یا متن"
        sortKey={list.sortKey}
        onSort={list.setSortKey}
        sorts={list.sorts}
        onReset={dirty ? () => { setScope(start); list.resetSort(); } : undefined}
      >
        <Select aria-label="تحویل" value={scope} onChange={(event) => setScope(event.target.value)}>
          <option value="">همهٔ ارسال‌ها</option>
          <option value="linked">فقط با کمپین</option>
          <option value="open">بدون تحویل</option>
          <option value="loose">بدون کمپین</option>
          <option value="delivered">فقط تحویل‌شده</option>
        </Select>
      </ArrangeBar>
      {list.windowed.total === 0 ? <Muted as="p">ارسالی با این فیلتر نیست.</Muted> : (
        <Table
          rows={list.windowed.rows}
          rowKey={(row) => row.id}
          columns={[
            { key: "code", header: "کمپین", className: "cell-nowrap", render: (row: SmsSend) => <CampaignCode code={row.campaign_code} /> },
            { key: "when", header: "تاریخ", render: (row) => row.sent_at ? <DateText value={row.sent_at} /> : "—" },
            { key: "panel", header: "پنل", render: (row) => row.panel_name || "—" },
            { key: "body", header: "متن", render: (row) => <span className="cell-clamp">{sendText(row.body) || "—"}</span> },
            { key: "n", header: "گیرنده", render: (row) => toman(row.recipient_count) },
            { key: "cost", header: "هزینه", render: (row) => toman(row.cost_toman) },
            { key: "del", header: "تحویل", render: (row) => toman(row.delivered_count) },
            { key: "leads", header: "ورودی", render: (row) => toman(row.leads) },
            {
              key: "actions",
              header: "",
              render: (row) => (
                <RowActions
                  onDelivery={() => setDelivery(row)}
                  onEdit={() => setEdit(row)}
                  onDelete={() => void remove(`ارسال ${row.campaign_code || ""}`, () => perfApi.deleteSend(row.id))}
                />
              ),
            },
          ]}
        />
      )}
      <ShowMore left={list.windowed.left} onMore={list.windowed.grow} />
      {edit ? <SmsEdit row={edit} onClose={() => setEdit(null)} /> : null}
      {delivery ? <SmsDelivery row={delivery} onClose={() => setDelivery(null)} /> : null}
    </Card>
  );
}

const PISHGAM_WEB = "https://sms.pishgamrayan.com";

/** نام صفحه‌ها همان تب‌های پنل sms.pishgamrayan.com است. */
const PISHGAM_SECTIONS: Array<{ page: string; title: string; hint: string }> = [
  { page: "sendSMS", title: "ارسال پیامک", hint: "تکی و گروهی" },
  { page: "sendSMSWithPhonebook", title: "دفترچه تلفن", hint: "از مخاطبان ذخیره‌شده" },
  { page: "sendBulkSMS", title: "ارسال انبوه", hint: "شهر و استان" },
  { page: "sendBulkSMS2", title: "ارسال انبوه ۲", hint: "انبوه به‌روز" },
  { page: "sendBalkSms", title: "ارسال منطقه‌ای", hint: "کدپستی و منطقه" },
  { page: "sendSmsFromMap", title: "ارسال از نقشه", hint: "محدوده روی نقشه" },
  { page: "sendP2pSms", title: "نظیر به نظیر", hint: "متن جدا برای هر شماره" },
  { page: "dynamicSendSms", title: "ارسال پویا", hint: "متن متغیر" },
  { page: "sendSmartSMS", title: "مکان‌محور", hint: "ساکنین یک محدوده" },
  { page: "sendOccasionSms", title: "مناسبتی", hint: "در زمان مقرر" },
  { page: "sendWhiteMessage", title: "باشگاه مشتریان", hint: "پیام سفید" },
  { page: "fastSendSmsPatternByPhonebook", title: "پیام الگو", hint: "الگو با دفترچه" },
  { page: "sendQueue", title: "صف ارسال", hint: "فقط دیدن صندوق" },
];

type PishgamDraft = {
  body: string;
  sender: string;
  state: string;
  city: string;
  region: string;
  postal: string;
  numbers: string;
};

function pishgamPageUrl(page: string, draft: PishgamDraft): string {
  const params = new URLSearchParams();
  if (draft.body.trim()) params.set("smsBody", draft.body.trim());
  if (draft.sender.trim()) params.set("senderNumber", draft.sender.trim());
  if (draft.state.trim()) params.set("state", draft.state.trim());
  if (draft.city.trim()) params.set("city", draft.city.trim());
  if (draft.region.trim()) params.set("region", draft.region.trim());
  if (draft.postal.trim()) params.set("postalCode", draft.postal.trim());
  if (draft.numbers.trim()) params.set("receivers", draft.numbers.trim());
  const query = params.toString();
  return `${PISHGAM_WEB}/${page}${query ? `?${query}` : ""}`;
}

function PishgamSections({ lines }: { lines: string[] }) {
  const toast = useToast();
  const [body, setBody] = useState("");
  const [sender, setSender] = useState(lines[0] || "");
  const [stateName, setStateName] = useState("");
  const [city, setCity] = useState("");
  const [region, setRegion] = useState("");
  const [postal, setPostal] = useState("");
  const [numbers, setNumbers] = useState("");
  useEffect(() => {
    if (!sender && lines[0]) setSender(lines[0]);
  }, [lines, sender]);
  const draft: PishgamDraft = { body, sender, state: stateName, city, region, postal, numbers };

  async function openSection(page: string, title: string) {
    if (body.trim()) {
      try {
        await navigator.clipboard.writeText(body.trim());
      } catch {
        /* پیشگام خودش کلیپ‌بورد را نمی‌خواند؛ آدرس صفحه متن را دارد. */
      }
    }
    window.open(pishgamPageUrl(page, draft), "_blank", "noopener,noreferrer");
    toast(`${title} در پیشگام باز شد. ارسال را آنجا بزنید.`);
  }

  return (
    <Card>
      <SectionHeader
        icon="send"
        title={<Bi en="Pishgam sections" fa="بخش‌های پیشگام" />}
        hint={
          <Bi
            en="Opening a section fills the link with this draft and opens that Pishgam page. Nothing is sent from here."
            fa="هر دکمه همان صفحه را در پیشگام باز می‌کند و متن، خط، شهر و منطقه را روی لینک می‌گذارد. از اینجا پیامکی فرستاده نمی‌شود؛ ارسال را در خود پیشگام می‌زنید."
          />
        }
      />
      <div className="form-grid">
        <Field className="span-all" label={<Bi en="Text" fa="متن" />}>
          <TextArea value={body} rows={3} onChange={(event) => setBody(event.target.value)} />
        </Field>
        <Field label={<Bi en="Sender line" fa="خط ارسال" />}>
          <Input dir="ltr" value={sender} onChange={(event) => setSender(event.target.value)} placeholder={lines[0] || "5000…"} />
        </Field>
        <Field label={<Bi en="Province" fa="استان" />}>
          <Input value={stateName} onChange={(event) => setStateName(event.target.value)} placeholder="تهران" />
        </Field>
        <Field label={<Bi en="City" fa="شهر" />}>
          <Input value={city} onChange={(event) => setCity(event.target.value)} placeholder="تهران" />
        </Field>
        <Field label={<Bi en="Region" fa="منطقه" />}>
          <Input value={region} onChange={(event) => setRegion(event.target.value)} />
        </Field>
        <Field label={<Bi en="Postal code" fa="کدپستی" />}>
          <Input dir="ltr" value={postal} onChange={(event) => setPostal(event.target.value)} />
        </Field>
        <Field className="span-all" label={<Bi en="Numbers" fa="شماره‌ها" />}>
          <TextArea value={numbers} rows={2} placeholder="برای ارسال تکی یا گروهی" onChange={(event) => setNumbers(event.target.value)} />
        </Field>
      </div>
      <div className="conn-grid">
        {PISHGAM_SECTIONS.map((section) => (
          <article key={section.page} className="conn-tile">
            <h3>{section.title}</h3>
            <p className="conn-help">{section.hint}</p>
            <div className="perf-actions">
              <Button type="button" onClick={() => void openSection(section.page, section.title)}>
                <Bi en="Open in Pishgam" fa="ادامه در پیشگام" />
              </Button>
            </div>
          </article>
        ))}
      </div>
    </Card>
  );
}

function PishgamTab() {
  const qc = useQueryClient();
  const toast = useToast();
  // باز کردن این تب به پنل پیشگام کال نمی‌زند؛ موجودی زنده فقط با دکمه (همان بررسی صفحهٔ اتصالات).
  const saved = useSavedConnections();
  const live = useLiveConnections();
  const checking = live.isFetching;
  const sends = useQuery({ queryKey: ["perf", "sends"], queryFn: perfApi.sends });
  const panel: PanelStatus | undefined = ((live.data ?? saved.data)?.panels ?? []).find((row) => row.code === "pishgam");
  const pishgamSends = (sends.data ?? []).filter((row) => (row.panel_name || "").includes("پیشگام"));
  return (
    <>
      <Card>
        <SectionHeader
          icon="message"
          title={<Bi en="Pishgam live status" fa="پیشگام — وضعیت زنده" />}
          hint={<Bi en="Balance and lines are read live only when you press Check now (it checks all connections). Nothing is sent from here." fa="موجودی و خطوط فقط با «بررسی همین حالا» زنده خوانده می‌شود (همهٔ اتصال‌ها با هم بررسی می‌شوند). از همین‌جا چیزی ارسال نمی‌شود." />}
          action={
            <div className="row">
              {checking
                ? <Badge tone="warn"><Bi en="Checking" fa="در حال بررسی" /></Badge>
                : !panel?.live
                  ? <Badge tone="warn"><Bi en="Not checked" fa="بررسی نشده" /></Badge>
                  : panel.live.ok
                    ? <Badge tone="ok"><Bi en="Connected" fa="وصل" /></Badge>
                    : <Badge tone="danger"><Bi en="Not connected" fa="وصل نیست" /></Badge>}
              <Button type="button" variant="secondary" disabled={checking} aria-busy={checking} onClick={() => void live.refetch()}>
                {checking ? <Bi en="Checking…" fa="در حال بررسی…" /> : <Bi en="Check now" fa="بررسی همین حالا" />}
              </Button>
            </div>
          }
        />
        {live.dataUpdatedAt && !checking ? (
          <Muted as="p">آخرین بررسی زنده: <DateText value={new Date(live.dataUpdatedAt).toISOString()} withTime /></Muted>
        ) : null}
        {live.error && !checking ? (
          <ErrorMessage friendly={false} message={live.error instanceof Error ? live.error.message : "بررسی زنده انجام نشد."} />
        ) : null}
        {!panel || !panel.live ? (
          <Muted as="p">{checking ? "در حال بررسی زنده…" : "وضعیت زنده بررسی نشده است. برای خواندن موجودی و خطوط «بررسی همین حالا» را بزنید."}</Muted>
        ) : panel.live.ok ? (
          <div className="form-grid">
            <Field label={<Bi en="Balance" fa="موجودی" />}>
              <Input readOnly value={panel.live.balance || "—"} />
            </Field>
            <Field label={<Bi en="Sender lines" fa="خطوط ارسال" />}>
              <Input readOnly dir="ltr" value={(panel.live.lines ?? []).join(" ، ") || "—"} />
            </Field>
            <div className="span-all">
              <Muted>
                {panel.live.lines?.length ? toman(panel.live.lines.length) + " خط فعال. " : ""}
                آدرس API: <span dir="ltr">{panel.api_base || "—"}</span>
              </Muted>
            </div>
          </div>
        ) : (
          <ErrorMessage friendly={false} message={panel.live.reason || "کال زنده به پنل انجام نشد."} />
        )}
      </Card>
      <PishgamSections lines={panel?.live?.lines ?? []} />
      <Card>
        <SectionHeader icon="sparkles" title={<Bi en="Send analytics" fa="تحلیل ارسال‌ها" />} count={pishgamSends.length} />
        {pishgamSends.length === 0 ? (
          <Muted as="p">هنوز ارسالی از پیشگام ثبت نشده است. بعد از اولین ثبت ارسال، همین‌جا هزینه و تحویل جمع می‌شود.</Muted>
        ) : (
          <>
            <div className="form-grid">
              <Field label={<Bi en="Sends" fa="ارسال‌ها" />}><Input readOnly value={toman(pishgamSends.length)} /></Field>
              <Field label={<Bi en="Recipients" fa="گیرنده" />}><Input readOnly value={toman(pishgamSends.reduce((s, r) => s + (r.recipient_count || 0), 0))} /></Field>
              <Field label={<Bi en="Cost (toman)" fa="هزینه (تومان)" />}><Input readOnly value={toman(pishgamSends.reduce((s, r) => s + (r.cost_toman || 0), 0))} /></Field>
              <Field label={<Bi en="Delivered" fa="تحویل" />}><Input readOnly value={toman(pishgamSends.reduce((s, r) => s + (r.delivered_count || 0), 0))} /></Field>
              <Field label={<Bi en="Leads" fa="ورودی" />}><Input readOnly value={toman(pishgamSends.reduce((s, r) => s + (r.leads || 0), 0))} /></Field>
            </div>
            <Table
              rows={pishgamSends.slice(0, 8)}
              rowKey={(row) => row.id}
              columns={[
                { key: "code", header: "کمپین", className: "cell-nowrap", render: (row: SmsSend) => <CampaignCode code={row.campaign_code} /> },
                { key: "when", header: "تاریخ", render: (row) => row.sent_at ? <DateText value={row.sent_at} /> : "—" },
                { key: "n", header: "گیرنده", render: (row) => toman(row.recipient_count) },
                { key: "cost", header: "هزینه", render: (row) => toman(row.cost_toman) },
                { key: "del", header: "تحویل", render: (row) => toman(row.delivered_count) },
                { key: "leads", header: "ورودی", render: (row) => toman(row.leads) },
              ]}
            />
          </>
        )}
      </Card>
      <PishgamDeliveryCard
        panelId={panel?.id || ""}
        onDone={(result) => {
          toast(`${toman(result.delivered_count)} رسیده به گوشی از ${toman(result.rows.length)} شماره`);
          void qc.invalidateQueries({ queryKey: ["perf", "sends"] });
        }}
      />
    </>
  );
}

function PishgamDeliveryCard({
  panelId,
  onDone,
}: {
  panelId: string;
  onDone: (result: PishgamDelivery) => void;
}) {
  const toast = useToast();
  const [messageId, setMessageId] = useState("");
  const [recipients, setRecipients] = useState("");
  const delivery = useMutation({
    mutationFn: () => {
      const numbers = recipients.split(/[\s,،]+/).map((item) => item.trim()).filter(Boolean);
      return perfApi.pishgamDelivery({ panel_id: panelId, message_id: Number(messageId), recipients: numbers });
    },
    onSuccess: onDone,
    onError: (error: Error) => toast(error.message),
  });
  return (
    <Card>
      <SectionHeader
        icon="clock"
        title={<Bi en="Delivery status" fa="بررسی وضعیت تحویل" />}
        hint={<Bi en="Enter the send id from the Pishgam panel (Outbox) and up to 100 recipients. Read-only." fa="شناسهٔ ارسال را از صف ارسال یا صندوق ارسال پنل پیشگام بردارید و حداکثر ۱۰۰ گیرنده بنویسید. فقط خواندن." />}
      />
      <div className="form-grid">
        <Field label={<Bi en="Send id" fa="شناسهٔ ارسال" />}>
          <Input type="number" value={messageId} placeholder="مثلاً ۱۲۳۴۵۶" onChange={(e) => setMessageId(e.target.value)} />
        </Field>
        <Field className="span-all" label={<Bi en="Recipients" fa="شمارهٔ گیرنده‌ها" />}>
          <TextArea value={recipients} rows={3} placeholder="هر شماره یک خط یا با ویرگول. حداکثر ۱۰۰ شماره." onChange={(e) => setRecipients(e.target.value)} />
        </Field>
        <div className="span-all perf-actions">
          <Button
            type="button"
            disabled={!panelId || !messageId.trim() || !recipients.trim() || delivery.isPending}
            onClick={() => delivery.mutate()}
          >
            {delivery.isPending ? <Bi en="Checking" fa="در حال بررسی…" /> : <Bi en="Check delivery" fa="بررسی وضعیت" />}
          </Button>
        </div>
      </div>
      {delivery.data ? (
        delivery.data.ok ? (
          <Table
            rows={delivery.data.rows}
            rowKey={(row) => row.to_number || row.text}
            columns={[
              { key: "number", header: "شماره", className: "cell-nowrap", render: (row: PishgamDelivery["rows"][number]) => <span dir="ltr">{row.to_number}</span> },
              { key: "text", header: "وضعیت", render: (row) => row.text || "—" },
            ]}
          />
        ) : (
          <ErrorMessage friendly={false} message={delivery.data.reason} />
        )
      ) : null}
    </Card>
  );
}
