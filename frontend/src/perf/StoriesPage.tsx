import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, ErrorMessage, Field, Input, LoadingState, Muted, PageHeader, SectionHeader, Select, Table, TextArea } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { Bi } from "../i18n";
import { perfApi, toman, type CarRequest, type PageRow, type Story } from "./api";
import { FileButton } from "./bits";

export function StoriesPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const requests = useQuery({ queryKey: ["perf", "requests"], queryFn: perfApi.requests });
  const pages = useQuery({ queryKey: ["perf", "pages"], queryFn: perfApi.pages });
  const stories = useQuery({ queryKey: ["perf", "stories"], queryFn: perfApi.stories });
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const [raw, setRaw] = useState("");
  const [source, setSource] = useState("whatsapp");
  const [name, setName] = useState("");
  const [price, setPrice] = useState(0);
  const [followers, setFollowers] = useState(0);
  const [topic, setTopic] = useState("");
  const [budget, setBudget] = useState(0);
  const [campaignId, setCampaignId] = useState("");
  const [pageId, setPageId] = useState("");
  const [views, setViews] = useState(0);
  const [clicks, setClicks] = useState(0);
  const [leads, setLeads] = useState(0);
  const [cost, setCost] = useState(0);
  const [exited, setExited] = useState(0);
  const suggest = useMutation({ mutationFn: () => perfApi.suggest(budget) });
  const addRequest = useMutation({
    mutationFn: () => perfApi.createRequest(raw, source),
    onSuccess: () => {
      setRaw("");
      toast("درخواست ثبت شد");
      qc.invalidateQueries({ queryKey: ["perf", "requests"] });
    },
    onError: (error: Error) => toast(error.message),
  });
  const addPage = useMutation({
    mutationFn: () => perfApi.createPage({ name, price_toman: price, followers, topic }),
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["perf", "pages"] });
    },
    onError: (error: Error) => toast(error.message),
  });
  const addStory = useMutation({
    mutationFn: () =>
      perfApi.createStory({
        campaign_id: campaignId || null,
        page_id: pageId || null,
        cost_toman: cost,
        views,
        link_clicks: clicks,
        leads,
        exited,
      }),
    onSuccess: () => {
      toast("استوری ثبت شد");
      qc.invalidateQueries({ queryKey: ["perf"] });
    },
    onError: (error: Error) => toast(error.message),
  });

  return (
    <>
      <PageHeader
        title={<Bi en="Stories" fa="استوری" />}
        description={<Bi en="Car requests, pages, insight numbers and a budget suggestion from past CPV and CPL." fa="درخواست تبلیغ، پیج‌ها، اینسایت و پیشنهاد بودجه از CPV و CPL قبلی." />}
      />
      <Card>
        <SectionHeader
          icon="chat"
          title={<Bi en="Car promo inbox" fa="صندوق درخواست تبلیغ" />}
          hint={<Bi en="Paste the WhatsApp or Mizito message as it arrived." fa="متن واتساپ یا میزیتو را همان‌طور که رسیده بچسبانید." />}
        />
        <div className="form-grid">
          <Field className="span-all" label={<Bi en="Message" fa="متن" />}>
            <TextArea value={raw} onChange={(e) => setRaw(e.target.value)} rows={4} />
          </Field>
          <Field label={<Bi en="Source" fa="منبع" />}>
            <Select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="whatsapp">واتساپ</option>
              <option value="mizito">میزیتو</option>
            </Select>
          </Field>
          <div className="perf-actions">
            <Button type="button" disabled={!raw.trim()} onClick={() => addRequest.mutate()}><Bi en="Save request" fa="ثبت درخواست" /></Button>
          </div>
        </div>
        {requests.isLoading ? <LoadingState /> : null}
        {requests.error ? <ErrorMessage error={requests.error instanceof Error ? requests.error.message : String(requests.error)} /> : null}
        {requests.data ? (
          <Table
            rows={requests.data}
            rowKey={(row) => row.id}
            columns={[
              { key: "brand", header: "برند", render: (row: CarRequest) => row.brand || "—" },
              { key: "summary", header: "خلاصه", render: (row) => row.summary },
              { key: "source", header: "منبع", render: (row) => row.source },
              { key: "status", header: "وضعیت", render: (row) => row.status },
            ]}
          />
        ) : null}
      </Card>
      <Card>
        <SectionHeader icon="users" title={<Bi en="Pages" fa="پیج‌ها" />} hint={<Bi en="Price is in toman." fa="قیمت به تومان است." />} />
        <div className="form-grid">
          <Field label={<Bi en="Name" fa="نام" />}><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label={<Bi en="Followers" fa="فالوئر" />}><Input type="number" value={followers} onChange={(e) => setFollowers(Number(e.target.value))} /></Field>
          <Field label={<Bi en="Topic" fa="موضوع" />}><Input value={topic} onChange={(e) => setTopic(e.target.value)} /></Field>
          <Field label={<Bi en="Price" fa="قیمت" />}><Input type="number" value={price} onChange={(e) => setPrice(Number(e.target.value))} /></Field>
          <div className="perf-actions">
            <Button type="button" disabled={!name.trim()} onClick={() => addPage.mutate()}><Bi en="Add page" fa="افزودن پیج" /></Button>
          </div>
        </div>
        {pages.data ? (
          <Table
            rows={pages.data}
            rowKey={(row) => row.id}
            columns={[
              { key: "name", header: "پیج", render: (row: PageRow) => row.name },
              { key: "followers", header: "فالوئر", render: (row) => toman(row.followers) },
              { key: "topic", header: "موضوع", render: (row) => row.topic },
              { key: "price", header: "قیمت", render: (row) => toman(row.price_toman) },
            ]}
          />
        ) : null}
        <div className="form-grid">
          <Field label={<Bi en="Budget" fa="بودجه" />}><Input type="number" value={budget} onChange={(e) => setBudget(Number(e.target.value))} /></Field>
          <div className="perf-actions">
            <Button type="button" variant="secondary" onClick={() => suggest.mutate()}><Bi en="Suggest pages" fa="پیشنهاد پیج" /></Button>
          </div>
        </div>
        {suggest.data ? (
          <Muted as="p">
            {suggest.data.pages.map((row) => row.name).join("، ") || "با این بودجه پیجی انتخاب نشد."}
            {" — "}باقی‌مانده {toman(suggest.data.remaining_toman)}
          </Muted>
        ) : null}
      </Card>
      <Card>
        <SectionHeader
          icon="flag"
          title={<Bi en="Record a story" fa="ثبت استوری و اینسایت" />}
          hint={<Bi en="Type the numbers, or upload a screenshot for a first read." fa="عددها را بنویسید، یا اسکرین‌شات را برای خواندن اول بگذارید." />}
        />
        <div className="form-grid">
          <Field label={<Bi en="Campaign" fa="کمپین" />}>
            <Select value={campaignId} onChange={(e) => setCampaignId(e.target.value)}>
              <option value="">—</option>
              {(campaigns.data ?? []).map((row) => <option key={row.id} value={row.id}>{row.code}</option>)}
            </Select>
          </Field>
          <Field label={<Bi en="Page" fa="پیج" />}>
            <Select value={pageId} onChange={(e) => setPageId(e.target.value)}>
              <option value="">—</option>
              {(pages.data ?? []).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </Select>
          </Field>
          <Field label={<Bi en="Cost" fa="هزینه" />}><Input type="number" value={cost} onChange={(e) => setCost(Number(e.target.value))} /></Field>
          <Field label="Views"><Input type="number" value={views} onChange={(e) => setViews(Number(e.target.value))} /></Field>
          <Field label="Clicks"><Input type="number" value={clicks} onChange={(e) => setClicks(Number(e.target.value))} /></Field>
          <Field label={<Bi en="Leads" fa="ورودی" />}><Input type="number" value={leads} onChange={(e) => setLeads(Number(e.target.value))} /></Field>
          <Field label="Exited"><Input type="number" value={exited} onChange={(e) => setExited(Number(e.target.value))} /></Field>
          <div className="perf-actions">
            <Button type="button" onClick={() => addStory.mutate()}><Bi en="Save" fa="ثبت" /></Button>
          </div>
        </div>
        {stories.data ? (
          <Table
            rows={stories.data}
            rowKey={(row) => row.id}
            columns={[
              { key: "page", header: "پیج", render: (row: Story) => row.page },
              { key: "views", header: "Views", render: (row) => toman(row.views) },
              { key: "cpl", header: "CPL", render: (row) => toman(row.cpl) },
              { key: "cpv", header: "CPV", render: (row) => toman(row.cpv) },
              { key: "ctr", header: "CTR", render: (row) => row.ctr ?? "—" },
              { key: "exit", header: "Exit", render: (row) => row.exit_rate ?? "—" },
              {
                key: "shot",
                header: "اسکرین‌شات",
                render: (row) => (
                  <FileButton
                    accept="image/*"
                    label={<Bi en="Image" fa="تصویر" />}
                    onFile={(file) => {
                      perfApi.insight(row.id, file).then((result) => {
                        toast(result.ok ? "اعداد از تصویر خوانده شد" : (result.reason || "عدد خوانده نشد"));
                      }).catch((error: Error) => toast(error.message));
                    }}
                  />
                ),
              },
            ]}
          />
        ) : null}
      </Card>
    </>
  );
}
