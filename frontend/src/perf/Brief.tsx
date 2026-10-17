import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Field, Icon, Input, Muted, SectionHeader, TextArea } from "../components/ui";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { Bi } from "../i18n";
import { perfApi, type BriefAdPhase, type CampaignBriefData, type CampaignRow } from "./api";
import { EditPop } from "./edit";

const WEEK = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];

function emptyBrief(): CampaignBriefData {
  return {
    slogan: "",
    goals: [],
    angle: "",
    content_plan: WEEK.map((day) => ({ day, kind: "", details: "", place: "" })),
    caption: "",
    reels: [],
    ad_phases: [],
    ctas: [],
    hashtags: [],
    highlight: "",
    pinned: "",
  };
}

function hasContent(brief: CampaignBriefData): boolean {
  return Boolean(
    brief.slogan
    || brief.goals.length
    || brief.angle
    || brief.caption
    || brief.reels.length
    || brief.ad_phases.length
    || brief.ctas.length
    || brief.hashtags.length
    || brief.highlight
    || brief.pinned
    || brief.content_plan.some((row) => row.details || row.kind),
  );
}

const lines = (items: string[]) => items.join("\n");
const splitLines = (text: string) => text.split("\n").map((part) => part.trim()).filter(Boolean);

function asBrief(value: unknown): CampaignBriefData {
  const base = emptyBrief();
  if (!value || typeof value !== "object") return base;
  const raw = value as Partial<CampaignBriefData>;
  return {
    slogan: raw.slogan || "",
    goals: Array.isArray(raw.goals) ? raw.goals : [],
    angle: raw.angle || "",
    content_plan: Array.isArray(raw.content_plan) && raw.content_plan.length
      ? raw.content_plan.slice(0, 7).map((row, index) => ({ day: row?.day || WEEK[index] || `روز ${index + 1}`, kind: row?.kind || "", details: row?.details || "", place: row?.place || "" }))
      : base.content_plan,
    caption: raw.caption || "",
    reels: Array.isArray(raw.reels) ? raw.reels : [],
    ad_phases: Array.isArray(raw.ad_phases) ? raw.ad_phases : [],
    ctas: Array.isArray(raw.ctas) ? raw.ctas : [],
    hashtags: Array.isArray(raw.hashtags) ? raw.hashtags : [],
    highlight: raw.highlight || "",
    pinned: raw.pinned || "",
  };
}

export function CampaignBriefSection({ campaign, brief }: { campaign: CampaignRow; brief?: CampaignBriefData }) {
  const toast = useToast();
  const [editing, setEditing] = useState<CampaignBriefData | null>(null);
  const [source, setSource] = useState("");
  const draft = useMutation({
    mutationFn: () => perfApi.briefDraft(campaign.id),
    onSuccess: (result) => {
      setSource(result.source);
      setEditing(asBrief(result.brief));
      toast(result.source === "llm" ? "پیش‌نویس با هوش مصنوعی ساخته شد؛ بازبینی و ذخیره کنید" : "هوش مصنوعی در دسترس نبود؛ پیش‌نویس با قالب ساخته شد");
    },
    onError: (error: Error) => toast(error.message),
  });
  const present = hasContent(asBrief(brief));
  return (
    <Card className="brief-card">
      <SectionHeader
        icon="book"
        title={<Bi en="Campaign brief" fa="بریف کمپین" />}
        hint={<Bi en="Goals, weekly content, caption, ads." fa="هدف، محتوای هفتگی، کپشن و تبلیغ." />}
        action={
          <div className="row no-print">
            <Button type="button" className="btn-sm" disabled={draft.isPending} onClick={() => draft.mutate()}>
              <Icon name="sparkles" size={14} />
              <Bi en={draft.isPending ? "Drafting…" : "AI draft"} fa={draft.isPending ? "در حال ساخت…" : "پیش‌نویس"} />
            </Button>
            <Button type="button" variant="ghost" className="btn-sm" onClick={() => setEditing(asBrief(brief))}>
              <Bi en="Edit" fa="ویرایش" />
            </Button>
          </div>
        }
      />
      {source ? <p className="muted brief-source no-print">آخرین پیش‌نویس: {source === "llm" ? "هوش مصنوعی" : "قالب آماده"}</p> : null}
      {present && brief ? <BriefView brief={asBrief(brief)} /> : (
        <Muted as="p"><Bi en="No brief yet — use Draft or Edit." fa="بریفی نیست — «پیش‌نویس» یا «ویرایش»." /></Muted>
      )}
      {editing ? <BriefEdit campaign={campaign} brief={editing} onClose={() => setEditing(null)} /> : null}
    </Card>
  );
}

function BriefView({ brief }: { brief: CampaignBriefData }) {
  const plan = (brief.content_plan || []).filter((row) => row.kind || row.details);
  return (
    <div className="brief-view">
      {brief.slogan ? <p className="brief-slogan">{brief.slogan}</p> : null}
      {brief.goals.length ? (
        <div className="brief-block">
          <h4>هدف این هفته</h4>
          <ul>{brief.goals.map((goal) => <li key={goal}>{goal}</li>)}</ul>
        </div>
      ) : null}
      {brief.angle ? (
        <div className="brief-block">
          <h4>زاویه محتوایی</h4>
          <p>{brief.angle}</p>
        </div>
      ) : null}
      {plan.length ? (
        <div className="brief-block">
          <h4>برنامهٔ محتوایی هفته</h4>
          <table className="brief-plan">
            <thead><tr><th>روز</th><th>نوع محتوا</th><th>جزئیات</th><th>محل انتشار</th></tr></thead>
            <tbody>
              {plan.map((row, index) => (
                <tr key={`${row.day}-${index}`}>
                  <td className="brief-day">{row.day}</td>
                  <td>{row.kind || "—"}</td>
                  <td>{row.details || "—"}</td>
                  <td className="hide-sm">{row.place || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {brief.caption ? (
        <div className="brief-block">
          <h4>کپشن آماده</h4>
          <p className="brief-caption">{brief.caption}</p>
        </div>
      ) : null}
      {brief.reels.length ? (
        <div className="brief-block">
          <h4>ایده‌های ریلز</h4>
          <ol>{brief.reels.map((idea) => <li key={idea}>{idea}</li>)}</ol>
        </div>
      ) : null}
      {brief.ad_phases.length ? (
        <div className="brief-block">
          <h4>استراتژی تبلیغ</h4>
          {brief.ad_phases.map((phase, index) => <AdPhase key={`${phase.name}-${index}`} phase={phase} />)}
        </div>
      ) : null}
      {brief.ctas.length || brief.highlight || brief.hashtags.length || brief.pinned ? (
        <div className="brief-block">
          <h4>دعوت به اقدام، هایلایت و هشتگ</h4>
          {brief.ctas.length ? <p className="brief-ctas">{brief.ctas.map((cta) => <span className="brief-chip" key={cta}>{cta}</span>)}</p> : null}
          {brief.highlight ? <p>هایلایت: <strong>{brief.highlight}</strong>{brief.pinned ? <> · پست پین‌شده: «{brief.pinned}»</> : null}</p> : brief.pinned ? <p>پست پین‌شده: «{brief.pinned}»</p> : null}
          {brief.hashtags.length ? <p className="brief-hashtags">{brief.hashtags.join(" ")}</p> : null}
        </div>
      ) : null}
    </div>
  );
}

function AdPhase({ phase }: { phase: BriefAdPhase }) {
  return (
    <div className="brief-phase">
      <p className="brief-phase-name">
        {phase.name || "فاز تبلیغ"}
        {phase.budget_share != null ? <span className="muted"> · {phase.budget_share}٪ بودجهٔ هفته</span> : null}
      </p>
      {phase.goal ? <p className="muted">هدف: {phase.goal}</p> : null}
      {phase.audience ? <p className="muted">مخاطب: {phase.audience}</p> : null}
      {phase.text ? <p className="brief-phase-text">«{phase.text}»</p> : null}
    </div>
  );
}

function BriefEdit({ campaign, brief, onClose }: { campaign: CampaignRow; brief: CampaignBriefData; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [slogan, setSlogan] = useState(brief.slogan);
  const [goals, setGoals] = useState(lines(brief.goals));
  const [angle, setAngle] = useState(brief.angle);
  const [plan, setPlan] = useState(brief.content_plan.length ? brief.content_plan : emptyBrief().content_plan);
  const [caption, setCaption] = useState(brief.caption);
  const [reels, setReels] = useState(lines(brief.reels));
  const [phases, setPhases] = useState<BriefAdPhase[]>(brief.ad_phases.length ? brief.ad_phases : []);
  const [ctas, setCtas] = useState(lines(brief.ctas));
  const [hashtags, setHashtags] = useState(brief.hashtags.join(" "));
  const [highlight, setHighlight] = useState(brief.highlight);
  const [pinned, setPinned] = useState(brief.pinned);
  const [busy, setBusy] = useState(false);
  function setPhase(index: number, key: keyof BriefAdPhase, value: string) {
    setPhases((rows) => rows.map((row, at) => (at === index ? { ...row, [key]: key === "budget_share" ? (value === "" ? null : Math.max(0, Math.min(100, Number(value) || 0))) : value } : row)));
  }
  function save() {
    setBusy(true);
    perfApi.patchCampaign(campaign.id, {
      brief: {
        slogan: slogan.trim(),
        goals: splitLines(goals),
        angle: angle.trim(),
        content_plan: plan.map((row, index) => ({ ...row, day: row.day || WEEK[index] })),
        caption,
        reels: splitLines(reels),
        ad_phases: phases.filter((phase) => phase.name || phase.goal || phase.text),
        ctas: splitLines(ctas),
        hashtags: hashtags.split(/\s+/).map((part) => part.trim()).filter(Boolean),
        highlight: highlight.trim(),
        pinned: pinned.trim(),
      },
    })
      .then(() => {
        toast("بریف ذخیره شد");
        void qc.invalidateQueries({ queryKey: ["perf"] });
        onClose();
      })
      .catch((error: Error) => toast(error.message))
      .finally(() => setBusy(false));
  }
  return (
    <EditPop className="brief-pop" title={<Bi en="Edit brief" fa="ویرایش بریف" />} onClose={onClose}>
      <div className="brief-edit">
        <section className="brief-edit-block">
          <h5>شعار و زاویه</h5>
          <div className="brief-pair">
            <Field label="شعار"><Input value={slogan} onChange={(event) => setSlogan(event.target.value)} /></Field>
            <Field label="زاویه محتوایی"><Input value={angle} onChange={(event) => setAngle(event.target.value)} /></Field>
          </div>
          <Field label="هدف‌های هفته، هر هدف یک خط"><TextArea rows={3} value={goals} onChange={(event) => setGoals(event.target.value)} /></Field>
        </section>
        <section className="brief-edit-block">
          <h5>برنامهٔ هفت روز</h5>
          {plan.map((row, index) => (
            <div className="brief-plan-row" key={index}>
              <span className="brief-plan-day">{row.day}</span>
              <Input placeholder="نوع" value={row.kind} onChange={(event) => { const value = event.target.value; setPlan((rows) => rows.map((item, at) => (at === index ? { ...item, kind: value } : item))); }} />
              <Input placeholder="جزئیات" value={row.details} onChange={(event) => { const value = event.target.value; setPlan((rows) => rows.map((item, at) => (at === index ? { ...item, details: value } : item))); }} />
              <Input placeholder="محل" value={row.place} onChange={(event) => { const value = event.target.value; setPlan((rows) => rows.map((item, at) => (at === index ? { ...item, place: value } : item))); }} />
            </div>
          ))}
        </section>
        <section className="brief-edit-block">
          <h5>کپشن و ریلز</h5>
          <Field label="کپشن آماده"><TextArea rows={3} value={caption} onChange={(event) => setCaption(event.target.value)} /></Field>
          <Field label="ایده‌های ریلز، هر ایده یک خط"><TextArea rows={2} value={reels} onChange={(event) => setReels(event.target.value)} /></Field>
        </section>
        <section className="brief-edit-block">
          <h5>تبلیغ</h5>
          {phases.map((phase, index) => (
            <div className="brief-phase-edit" key={index}>
              <Input placeholder="نام فاز" value={phase.name} onChange={(event) => setPhase(index, "name", event.target.value)} />
              <Input type="number" placeholder="٪ بودجه" value={phase.budget_share ?? ""} onChange={(event) => setPhase(index, "budget_share", event.target.value)} />
              <Input placeholder="هدف" value={phase.goal} onChange={(event) => setPhase(index, "goal", event.target.value)} />
              <Input placeholder="مخاطب" value={phase.audience} onChange={(event) => setPhase(index, "audience", event.target.value)} />
              <Input className="span-all" placeholder="متن تبلیغ" value={phase.text} onChange={(event) => setPhase(index, "text", event.target.value)} />
              <Button
                type="button"
                variant="danger-quiet"
                className="btn-sm"
                onClick={() => {
                  void confirm("حذف فاز", "این فاز تبلیغ از بریف حذف شود؟", "بله، حذف کن", { danger: true }).then((ok) => {
                    if (ok) setPhases((rows) => rows.filter((_row, at) => at !== index));
                  });
                }}
              >
                حذف
              </Button>
            </div>
          ))}
          <Button type="button" variant="ghost" className="btn-sm" onClick={() => setPhases((rows) => [...rows, { name: "", goal: "", audience: "", budget_share: null, text: "" }])}>افزودن فاز</Button>
        </section>
        <section className="brief-edit-block">
          <h5>انتشار</h5>
          <div className="brief-pair">
            <Field label="هایلایت"><Input value={highlight} onChange={(event) => setHighlight(event.target.value)} /></Field>
            <Field label="پست پین‌شده"><Input value={pinned} onChange={(event) => setPinned(event.target.value)} /></Field>
          </div>
          <Field label="دعوت به اقدام، هر کدام یک خط"><TextArea rows={2} value={ctas} onChange={(event) => setCtas(event.target.value)} /></Field>
          <Field label="هشتگ‌ها با فاصله"><Input value={hashtags} onChange={(event) => setHashtags(event.target.value)} /></Field>
        </section>
      </div>
      <div className="brief-save">
        <Button type="button" className="btn-sm" disabled={busy} onClick={save}><Bi en="Save" fa="ذخیره" /></Button>
      </div>
    </EditPop>
  );
}