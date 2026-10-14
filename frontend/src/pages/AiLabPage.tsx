import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import "../ai-lab/ai-lab.css";
import { AiLabResultView, statusBadgeClass } from "../ai-lab/AiLabResultView";
import { aiLabApi, type AiTask, type AiTaskKind } from "../ai-lab/api";
import { perfApi } from "../perf/api";
import {
  Button,
  Card,
  Dialog,
  EmptyState,
  ErrorMessage,
  Field,
  Input,
  LoadingState,
  PageHeader,
  SectionHeader,
  Select,
  TextArea,
} from "../components/ui";
import { Bi, useBi } from "../i18n";
import { isForbiddenError } from "../lib/apiError";

const STATUS_LABEL: Record<string, { en: string; fa: string }> = {
  pending: { en: "pending", fa: "در انتظار ارسال" },
  sent: { en: "sent", fa: "ارسال شد" },
  waiting: { en: "waiting", fa: "منتظر نتیجه" },
  done: { en: "done", fa: "انجام شد" },
  failed: { en: "failed", fa: "ناموفق" },
  expired: { en: "expired", fa: "منقضی" },
};

function formatPollTime(iso: string | null | undefined, bi: (en: string, fa: string) => string) {
  if (!iso) return bi("never", "هنوز چک نشده");
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

const KIND_LABEL: Record<AiTaskKind, { en: string; fa: string }> = {
  period_review: { en: "Period review", fa: "بررسی بازه" },
  campaign_review: { en: "Campaign review", fa: "تحلیل کمپین" },
  channel_budget: { en: "Budget split", fa: "تقسیم بودجه" },
};

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function weekAgoIso() {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

export function AiLabPage() {
  const bi = useBi();
  const qc = useQueryClient();
  const config = useQuery({ queryKey: ["ai-lab", "config"], queryFn: aiLabApi.config });
  const tasks = useQuery({ queryKey: ["ai-lab", "tasks"], queryFn: aiLabApi.tasks, enabled: config.data?.enabled });
  const summary = useQuery({
    queryKey: ["ai-lab", "summary"],
    queryFn: aiLabApi.evaluationSummary,
    enabled: config.data?.enabled,
  });
  const campaigns = useQuery({
    queryKey: ["perf", "campaigns"],
    queryFn: perfApi.campaigns,
    enabled: config.data?.enabled,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [kind, setKind] = useState<AiTaskKind>("period_review");
  const [fromDate, setFromDate] = useState(weekAgoIso());
  const [toDate, setToDate] = useState(todayIso());
  const [brand, setBrand] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const [nextBudget, setNextBudget] = useState("50000000");
  const [refFrom, setRefFrom] = useState(weekAgoIso());
  const [refTo, setRefTo] = useState(todayIso());
  const [snapshotPreview, setSnapshotPreview] = useState<string>("");
  const [manualJson, setManualJson] = useState("");
  const [evalRating, setEvalRating] = useState("4");
  const [evalUseful, setEvalUseful] = useState("yes");
  const [evalNote, setEvalNote] = useState("");

  const inputPayload = useMemo(() => {
    if (kind === "period_review") return { from_date: fromDate, to_date: toDate, brand };
    if (kind === "campaign_review") return { campaign_id: campaignId };
    return {
      next_budget_toman: Number(nextBudget) || 0,
      reference_from: refFrom,
      reference_to: refTo,
    };
  }, [kind, fromDate, toDate, brand, campaignId, nextBudget, refFrom, refTo]);

  const previewMut = useMutation({
    mutationFn: () => aiLabApi.previewSnapshot(kind, inputPayload),
    onSuccess: (data) => setSnapshotPreview(JSON.stringify(data, null, 2)),
  });

  const createMut = useMutation({
    mutationFn: () => aiLabApi.createTask(kind, inputPayload),
    onSuccess: (row) => {
      qc.invalidateQueries({ queryKey: ["ai-lab", "tasks"] });
      setCreateOpen(false);
      setDetailId(row.id);
    },
  });

  const detail = useQuery({
    queryKey: ["ai-lab", "task", detailId],
    queryFn: () => aiLabApi.task(detailId!),
    enabled: Boolean(detailId),
  });

  const manualMut = useMutation({
    mutationFn: () => aiLabApi.manualResult(detailId!, JSON.parse(manualJson) as Record<string, unknown>),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ai-lab", "tasks"] });
      qc.invalidateQueries({ queryKey: ["ai-lab", "task", detailId] });
    },
  });

  const decideMut = useMutation({
    mutationFn: ({ recId, decision }: { recId: string; decision: "accepted" | "rejected" }) =>
      aiLabApi.decide(detailId!, recId, decision),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-lab", "task", detailId] }),
  });

  const pollMut = useMutation({
    mutationFn: () => aiLabApi.pollNow(detailId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ai-lab", "tasks"] });
      qc.invalidateQueries({ queryKey: ["ai-lab", "task", detailId] });
    },
  });

  const evalMut = useMutation({
    mutationFn: () =>
      aiLabApi.evaluate(detailId!, Number(evalRating), evalUseful === "yes", evalNote),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ai-lab", "tasks"] });
      qc.invalidateQueries({ queryKey: ["ai-lab", "summary"] });
    },
  });

  if (config.isLoading) return <LoadingState />;
  if (config.error) {
    if (isForbiddenError(config.error)) {
      return <EmptyState titleEn="No access" titleFa="دسترسی ندارید" bodyEn="" bodyFa="" />;
    }
    if ((config.error as Error).message.includes("404") || (config.error as Error).message.includes("disabled")) {
      return (
        <EmptyState
          titleEn="AI Lab is off"
          titleFa="آزمایشگاه AI خاموش است"
          bodyEn="Set AI_LAB_ENABLED=true on the server to try the pilot."
          bodyFa="روی سرور AI_LAB_ENABLED=true بگذارید تا پایلوت فعال شود."
        />
      );
    }
    return <ErrorMessage error={config.error} />;
  }

  const mode = config.data?.mode ?? "manual";
  const resultSource = config.data?.result_source ?? "callback";
  const statusLabel = (s: string) => {
    const pair = STATUS_LABEL[s] ?? { en: s, fa: s };
    return bi(pair.en, pair.fa);
  };
  const rows = tasks.data ?? [];
  const active: AiTask | undefined = detail.data ?? rows.find((r) => r.id === detailId);

  return (
    <>
      <PageHeader
        title={<Bi en="AI Lab" fa="آزمایشگاه AI مارکتینگ" />}
        description={
          <Bi
            en="Structured analysis from perf data. Webhook + GitHub polling, or manual paste as fallback."
            fa="تحلیل ساختاریافته از دادهٔ پرفورمنس. با webhook و polling از GitHub، یا چسباندن دستی در صورت خطا."
          />
        }
        actions={
          <Button type="button" onClick={() => setCreateOpen(true)}>
            <Bi en="New analysis" fa="تحلیل جدید" />
          </Button>
        }
      />

      {summary.data && Object.keys(summary.data.by_kind).length > 0 && (
        <Card>
          <SectionHeader icon="activity" title={<Bi en="Evaluation" fa="ارزیابی" />} />
          <div className="form-grid">
            {Object.entries(summary.data.by_kind).map(([k, v]) => (
              <div key={k} className="muted">
                <strong>{bi(KIND_LABEL[k as AiTaskKind]?.en ?? k, KIND_LABEL[k as AiTaskKind]?.fa ?? k)}</strong>
                <div>
                  <Bi en="Tasks" fa="کارها" />: {v.tasks}
                  {v.avg_rating != null ? ` · ★ ${v.avg_rating}` : ""}
                  {v.accept_rate != null ? ` · ${Math.round(v.accept_rate * 100)}% accepted` : ""}
                  {v.median_latency_seconds != null ? ` · ${v.median_latency_seconds}s` : ""}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <SectionHeader icon="layers" title={<Bi en="Tasks" fa="کارها" />} count={rows.length} />
        {tasks.isLoading ? (
          <LoadingState />
        ) : !rows.length ? (
          <EmptyState titleEn="No tasks yet" titleFa="هنوز کاری نیست" bodyEn="" bodyFa="" />
        ) : (
          <table className="ui-table">
            <thead>
              <tr>
                <th><Bi en="Kind" fa="نوع" /></th>
                <th><Bi en="Status" fa="وضعیت" /></th>
                <th><Bi en="Rating" fa="امتیاز" /></th>
                <th><Bi en="Accepted" fa="پذیرفته" /></th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{bi(KIND_LABEL[row.kind].en, KIND_LABEL[row.kind].fa)}</td>
                  <td><span className={statusBadgeClass(row.status)}>{statusLabel(row.status)}</span></td>
                  <td>{row.rating ?? "—"}</td>
                  <td>{row.accepted_count}</td>
                  <td>
                    <Button variant="ghost" type="button" onClick={() => setDetailId(row.id)}>
                      <Bi en="Open" fa="باز کردن" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {createOpen && (
        <Dialog layout="pop" className="form-pop" onClose={() => setCreateOpen(false)} label={bi("New analysis", "تحلیل جدید")}>
          <h2 id="ai-lab-create-title"><Bi en="New analysis" fa="تحلیل جدید" /></h2>
          <Field label={<Bi en="Kind" fa="نوع کار" />}>
            <Select value={kind} onChange={(e) => setKind(e.target.value as AiTaskKind)}>
              <option value="period_review">{bi("Period review", "بررسی بازه")}</option>
              <option value="campaign_review">{bi("Campaign review", "تحلیل کمپین")}</option>
              <option value="channel_budget">{bi("Budget split", "تقسیم بودجه")}</option>
            </Select>
          </Field>
          {kind === "period_review" && (
            <>
              <Field label={<Bi en="From" fa="از" />}><Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} /></Field>
              <Field label={<Bi en="To" fa="تا" />}><Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} /></Field>
              <Field label={<Bi en="Brand (optional)" fa="برند (اختیاری)" />}><Input value={brand} onChange={(e) => setBrand(e.target.value)} /></Field>
            </>
          )}
          {kind === "campaign_review" && (
            <Field label={<Bi en="Campaign" fa="کمپین" />}>
              <Select value={campaignId} onChange={(e) => setCampaignId(e.target.value)}>
                <option value="">{bi("Choose…", "انتخاب…")}</option>
                {(campaigns.data ?? []).map((c) => (
                  <option key={c.id} value={c.id}>{c.code} — {c.title}</option>
                ))}
              </Select>
            </Field>
          )}
          {kind === "channel_budget" && (
            <>
              <Field label={<Bi en="Next budget (toman)" fa="بودجهٔ بعد (تومان)" />}>
                <Input value={nextBudget} onChange={(e) => setNextBudget(e.target.value)} />
              </Field>
              <Field label={<Bi en="Reference from" fa="مرجع از" />}><Input type="date" value={refFrom} onChange={(e) => setRefFrom(e.target.value)} /></Field>
              <Field label={<Bi en="Reference to" fa="مرجع تا" />}><Input type="date" value={refTo} onChange={(e) => setRefTo(e.target.value)} /></Field>
            </>
          )}
          <div className="toolbar">
            <Button variant="ghost" type="button" onClick={() => previewMut.mutate()} disabled={previewMut.isPending}>
              <Bi en="Preview snapshot" fa="پیش‌نمایش داده" />
            </Button>
            <Button type="button" onClick={() => createMut.mutate()} disabled={createMut.isPending}>
              <Bi en="Create task" fa="ثبت کار" />
            </Button>
          </div>
          {snapshotPreview && (
            <pre className="code-block" style={{ maxHeight: 240, overflow: "auto" }}>{snapshotPreview}</pre>
          )}
          {previewMut.error && <ErrorMessage error={previewMut.error} />}
          {createMut.error && <ErrorMessage error={createMut.error} />}
        </Dialog>
      )}

      {detailId && (
        <Dialog layout="pop" className="brief-pop ai-lab-pop" onClose={() => setDetailId(null)} label={bi("Task detail", "جزئیات کار")}>
          {detail.isLoading && !active ? (
            <LoadingState />
          ) : !active ? null : (
          <>
          <div className="ai-lab-detail-head">
            <h2><Bi en="Analysis" fa="تحلیل" /></h2>
            <span className={`ai-lab-status ${statusBadgeClass(active.status)}`}>{statusLabel(active.status)}</span>
          </div>
          <p className="muted ai-lab-meta">{bi(KIND_LABEL[active.kind].en, KIND_LABEL[active.kind].fa)}</p>
          {resultSource === "github" && (active.status === "waiting" || active.status === "sent") && (
            <div className="ai-lab-waiting">
              <span>
                <Bi en="Last GitHub check" fa="آخرین چک GitHub" />: {formatPollTime(active.last_polled_at, bi)}
              </span>
              <Button type="button" variant="ghost" onClick={() => pollMut.mutate()} disabled={pollMut.isPending}>
                <Bi en="Check now" fa="چک الان" />
              </Button>
              {pollMut.error && <ErrorMessage error={pollMut.error} />}
            </div>
          )}
          {(active.status === "failed" || active.error === "timeout") && (
            <>
              <Field label={<Bi en="Paste bot JSON (fallback)" fa="چسباندن JSON جواب (پشتیبان)" />}>
                <TextArea rows={8} value={manualJson} onChange={(e) => setManualJson(e.target.value)} />
              </Field>
              <Button type="button" onClick={() => manualMut.mutate()} disabled={manualMut.isPending || !manualJson.trim()}>
                <Bi en="Save result" fa="ذخیرهٔ نتیجه" />
              </Button>
            </>
          )}
          {mode === "manual" && active.status === "pending" && (
            <>
              <Button
                variant="ghost"
                type="button"
                onClick={() => {
                  const blob = JSON.stringify(
                    {
                      task_id: active.id,
                      kind: active.kind,
                      input: active.input,
                      snapshot: active.snapshot,
                    },
                    null,
                    2,
                  );
                  void navigator.clipboard.writeText(blob);
                }}
              >
                <Bi en="Copy for bot" fa="کپی برای بات" />
              </Button>
              <Field label={<Bi en="Paste bot JSON" fa="چسباندن JSON جواب" />}>
                <TextArea rows={8} value={manualJson} onChange={(e) => setManualJson(e.target.value)} />
              </Field>
              <Button type="button" onClick={() => manualMut.mutate()} disabled={manualMut.isPending || !manualJson.trim()}>
                <Bi en="Save result" fa="ذخیرهٔ نتیجه" />
              </Button>
            </>
          )}
          {active.error && <p className="error-text">{active.error}</p>}
          {active.result && (
            <AiLabResultView
              result={active.result}
              decisions={active.decisions}
              bi={bi}
              decidePending={decideMut.isPending}
              onDecide={(recId, decision) => decideMut.mutate({ recId, decision })}
              evalSlot={
                <>
                  <Field label={<Bi en="Rating 1-5" fa="امتیاز ۱–۵" />}>
                    <Select value={evalRating} onChange={(e) => setEvalRating(e.target.value)}>
                      {[1, 2, 3, 4, 5].map((n) => (
                        <option key={n} value={String(n)}>{n}</option>
                      ))}
                    </Select>
                  </Field>
                  <Field label={<Bi en="Useful?" fa="مفید بود؟" />}>
                    <Select value={evalUseful} onChange={(e) => setEvalUseful(e.target.value)}>
                      <option value="yes">{bi("Yes", "بله")}</option>
                      <option value="no">{bi("No", "خیر")}</option>
                    </Select>
                  </Field>
                  <Field label={<Bi en="Note" fa="یادداشت" />}>
                    <TextArea rows={2} value={evalNote} onChange={(e) => setEvalNote(e.target.value)} />
                  </Field>
                  <Button type="button" onClick={() => evalMut.mutate()} disabled={evalMut.isPending}>
                    <Bi en="Save evaluation" fa="ذخیرهٔ ارزیابی" />
                  </Button>
                </>
              }
            />
          )}
          </>
          )}
        </Dialog>
      )}
    </>
  );
}
