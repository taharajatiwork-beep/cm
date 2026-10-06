import { useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Field, Input, SectionHeader, Select, TextArea } from "../components/ui";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { Bi, useBi } from "../i18n";
import { perfApi, type CampaignRow, type SmsSend, type Story } from "./api";

type CostRow = {
  id: string;
  spent_on: string | null;
  amount_toman: number;
  kind: string;
  detail: string;
  brand: string;
  campaign_code: string;
  description: string;
};

export function RowActions({ onEdit, onDelete }: { onEdit?: () => void; onDelete: () => void }) {
  return (
    <div className="row-actions" onClick={(event) => event.stopPropagation()}>
      {onEdit ? (
        <Button type="button" variant="secondary" className="btn-sm" onClick={onEdit}>
          <Bi en="Edit" fa="ویرایش" />
        </Button>
      ) : null}
      <Button type="button" variant="danger" className="btn-sm" onClick={onDelete}>
        <Bi en="Delete" fa="حذف" />
      </Button>
    </div>
  );
}

export function useRemove() {
  const confirm = useConfirm();
  const qc = useQueryClient();
  const toast = useToast();
  return async (label: string, run: () => Promise<unknown>) => {
    const ok = await confirm("حذف", `${label} حذف شود؟`, "حذف");
    if (!ok) return;
    try {
      await run();
      toast("حذف شد");
      await qc.invalidateQueries({ queryKey: ["perf"] });
    } catch (error) {
      toast(error instanceof Error ? error.message : "حذف نشد");
    }
  };
}

function EditPop({ title, onClose, children }: { title: ReactNode; onClose: () => void; children: ReactNode }) {
  const bi = useBi();
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="detail-pop form-pop" role="dialog" aria-modal="true">
      <button type="button" className="detail-pop-backdrop" onClick={onClose} aria-label={bi("Close", "بستن")} />
      <div className="detail-pop-card">
        <SectionHeader title={title} action={<button type="button" className="kpi-more" onClick={onClose}><Bi en="Close" fa="بستن" /></button>} />
        {children}
      </div>
    </div>
  );
}

function day(value: string | null | undefined): string {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function saved(toast: (text: string) => void, qc: ReturnType<typeof useQueryClient>, onClose: () => void) {
  return () => {
    toast("ذخیره شد");
    void qc.invalidateQueries({ queryKey: ["perf"] });
    onClose();
  };
}

export function CampaignEdit({ row, onClose }: { row: CampaignRow; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [code, setCode] = useState(row.code);
  const [title, setTitle] = useState(row.title);
  const [brand, setBrand] = useState(row.brand);
  const [goal, setGoal] = useState(row.goal);
  const [budget, setBudget] = useState(row.budget_toman ? String(row.budget_toman) : "");
  const [status, setStatus] = useState(row.status || "active");
  const [busy, setBusy] = useState(false);
  function save() {
    setBusy(true);
    perfApi.patchCampaign(row.id, {
      code: code.trim(),
      title: title.trim(),
      brand: brand.trim(),
      goal: goal.trim(),
      status,
      budget_toman: budget === "" ? null : Number(budget),
    }).then(saved(toast, qc, onClose)).catch((error: Error) => toast(error.message)).finally(() => setBusy(false));
  }
  return (
    <EditPop title={<Bi en="Edit campaign" fa="ویرایش کمپین" />} onClose={onClose}>
      <Field label="کد"><Input value={code} onChange={(event) => setCode(event.target.value)} /></Field>
      <Field label="عنوان"><Input value={title} onChange={(event) => setTitle(event.target.value)} /></Field>
      <Field label="برند"><Input value={brand} onChange={(event) => setBrand(event.target.value)} /></Field>
      <Field label="هدف"><Input value={goal} onChange={(event) => setGoal(event.target.value)} /></Field>
      <Field label="بودجه (تومان)"><Input type="number" value={budget} onChange={(event) => setBudget(event.target.value)} /></Field>
      <Field label="وضعیت">
        <Select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="active">فعال</option>
          <option value="draft">پیش‌نویس</option>
          <option value="done">تمام</option>
        </Select>
      </Field>
      <Button type="button" disabled={!title.trim() || !code.trim() || busy} onClick={save}><Bi en="Save" fa="ذخیره" /></Button>
    </EditPop>
  );
}

export function SmsEdit({ row, onClose }: { row: SmsSend; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [body, setBody] = useState(row.body);
  const [count, setCount] = useState(String(row.recipient_count || ""));
  const [cost, setCost] = useState(String(row.cost_toman || ""));
  const [delivered, setDelivered] = useState(String(row.delivered_count || ""));
  const [leads, setLeads] = useState(String(row.leads || ""));
  const [sent, setSent] = useState(day(row.sent_at));
  const [busy, setBusy] = useState(false);
  function save() {
    setBusy(true);
    perfApi.patchSend(row.id, {
      body,
      recipient_count: Number(count) || 0,
      cost_toman: Number(cost) || 0,
      delivered_count: Number(delivered) || 0,
      leads: Number(leads) || 0,
      sent_at: sent ? `${sent}T12:00:00` : null,
    }).then(saved(toast, qc, onClose)).catch((error: Error) => toast(error.message)).finally(() => setBusy(false));
  }
  return (
    <EditPop title={<Bi en="Edit send" fa="ویرایش ارسال" />} onClose={onClose}>
      <Field label="متن"><TextArea rows={4} value={body} onChange={(event) => setBody(event.target.value)} /></Field>
      <Field label="تاریخ"><Input type="date" value={sent} onChange={(event) => setSent(event.target.value)} /></Field>
      <Field label="گیرنده"><Input type="number" value={count} onChange={(event) => setCount(event.target.value)} /></Field>
      <Field label="هزینه"><Input type="number" value={cost} onChange={(event) => setCost(event.target.value)} /></Field>
      <Field label="تحویل"><Input type="number" value={delivered} onChange={(event) => setDelivered(event.target.value)} /></Field>
      <Field label="ورودی"><Input type="number" value={leads} onChange={(event) => setLeads(event.target.value)} /></Field>
      <Button type="button" disabled={busy} onClick={save}><Bi en="Save" fa="ذخیره" /></Button>
    </EditPop>
  );
}

export function StoryEdit({ row, onClose }: { row: Story; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [kind, setKind] = useState(row.kind || "story");
  const [published, setPublished] = useState(day(row.published_on));
  const [cost, setCost] = useState(String(row.cost_toman || ""));
  const [views, setViews] = useState(String(row.views || ""));
  const [leads, setLeads] = useState(String(row.leads || ""));
  const [busy, setBusy] = useState(false);
  function save() {
    setBusy(true);
    perfApi.patchStory(row.id, {
      kind,
      published_on: published || null,
      cost_toman: Number(cost) || 0,
      views: Number(views) || 0,
      leads: Number(leads) || 0,
    }).then(saved(toast, qc, onClose)).catch((error: Error) => toast(error.message)).finally(() => setBusy(false));
  }
  return (
    <EditPop title={<Bi en="Edit placement" fa="ویرایش قرار" />} onClose={onClose}>
      <Field label="نوع">
        <Select value={kind} onChange={(event) => setKind(event.target.value)}>
          <option value="story">استوری</option>
          <option value="post">پست</option>
          <option value="banner">بنر</option>
        </Select>
      </Field>
      <Field label="تاریخ انتشار"><Input type="date" value={published} onChange={(event) => setPublished(event.target.value)} /></Field>
      <Field label="هزینه"><Input type="number" value={cost} onChange={(event) => setCost(event.target.value)} /></Field>
      <Field label="نمایش"><Input type="number" value={views} onChange={(event) => setViews(event.target.value)} /></Field>
      <Field label="ورودی"><Input type="number" value={leads} onChange={(event) => setLeads(event.target.value)} /></Field>
      <Button type="button" disabled={busy} onClick={save}><Bi en="Save" fa="ذخیره" /></Button>
    </EditPop>
  );
}

export function CostEdit({ row, onClose }: { row: CostRow; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [spent, setSpent] = useState(day(row.spent_on));
  const [amount, setAmount] = useState(String(row.amount_toman || ""));
  const [kind, setKind] = useState(row.kind);
  const [brand, setBrand] = useState(row.brand);
  const [code, setCode] = useState(row.campaign_code);
  const [detail, setDetail] = useState(row.detail || row.description);
  const [busy, setBusy] = useState(false);
  function save() {
    setBusy(true);
    perfApi.patchCost(row.id, {
      spent_on: spent || null,
      amount_toman: Number(amount) || 0,
      kind,
      brand,
      campaign_code: code,
      detail,
      description: detail,
    }).then(saved(toast, qc, onClose)).catch((error: Error) => toast(error.message)).finally(() => setBusy(false));
  }
  return (
    <EditPop title={<Bi en="Edit cost" fa="ویرایش هزینه" />} onClose={onClose}>
      <Field label="تاریخ"><Input type="date" value={spent} onChange={(event) => setSpent(event.target.value)} /></Field>
      <Field label="مبلغ"><Input type="number" value={amount} onChange={(event) => setAmount(event.target.value)} /></Field>
      <Field label="نوع"><Input value={kind} onChange={(event) => setKind(event.target.value)} /></Field>
      <Field label="برند"><Input value={brand} onChange={(event) => setBrand(event.target.value)} /></Field>
      <Field label="کمپین"><Input value={code} onChange={(event) => setCode(event.target.value)} /></Field>
      <Field label="شرح"><Input value={detail} onChange={(event) => setDetail(event.target.value)} /></Field>
      <Button type="button" disabled={busy} onClick={save}><Bi en="Save" fa="ذخیره" /></Button>
    </EditPop>
  );
}

export function PageEdit({ row, onClose }: { row: { id: string; name: string; topic: string; contact: string; price_toman: number }; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(row.name);
  const [topic, setTopic] = useState(row.topic);
  const [contact, setContact] = useState(row.contact);
  const [price, setPrice] = useState(String(row.price_toman || ""));
  const [busy, setBusy] = useState(false);
  function save() {
    setBusy(true);
    perfApi.updatePage(row.id, {
      name: name.trim(),
      topic,
      contact,
      price_toman: Number(price) || 0,
    }).then(saved(toast, qc, onClose)).catch((error: Error) => toast(error.message)).finally(() => setBusy(false));
  }
  return (
    <EditPop title={<Bi en="Edit page" fa="ویرایش پیج" />} onClose={onClose}>
      <Field label="اسم"><Input value={name} onChange={(event) => setName(event.target.value)} /></Field>
      <Field label="موضوع"><Input value={topic} onChange={(event) => setTopic(event.target.value)} /></Field>
      <Field label="مخاطب"><Input value={contact} onChange={(event) => setContact(event.target.value)} /></Field>
      <Field label="قیمت"><Input type="number" value={price} onChange={(event) => setPrice(event.target.value)} /></Field>
      <Button type="button" disabled={!name.trim() || busy} onClick={save}><Bi en="Save" fa="ذخیره" /></Button>
    </EditPop>
  );
}
