import type { ReactNode } from "react";
import type { AiRecommendation, AiResult } from "./api";
import { Button } from "../components/ui";
import { Bi } from "../i18n";

function severityBadge(severity: string): string {
  const s = severity.toLowerCase();
  if (s === "high") return "badge danger";
  if (s === "medium") return "badge warn";
  if (s === "low") return "badge ok";
  return "badge";
}

function confidenceBadge(confidence: string): string {
  const c = confidence.toLowerCase();
  if (c === "high") return "badge ok";
  if (c === "medium") return "badge warn";
  if (c === "low") return "badge";
  return "badge";
}

function severityLabel(severity: string, bi: (en: string, fa: string) => string): string {
  const s = severity.toLowerCase();
  if (s === "high") return bi("High", "بالا");
  if (s === "medium") return bi("Medium", "متوسط");
  if (s === "low") return bi("Low", "پایین");
  return severity;
}

function confidenceLabel(confidence: string, bi: (en: string, fa: string) => string): string {
  const c = confidence.toLowerCase();
  if (c === "high") return bi("High confidence", "اطمینان بالا");
  if (c === "medium") return bi("Medium confidence", "اطمینان متوسط");
  if (c === "low") return bi("Low confidence", "اطمینان پایین");
  return confidence;
}

type Props = {
  result: AiResult;
  decisions: Record<string, string>;
  bi: (en: string, fa: string) => string;
  onDecide: (recId: string, decision: "accepted" | "rejected") => void;
  decidePending: boolean;
  evalSlot: ReactNode;
};

export function AiLabResultView({ result, decisions, bi, onDecide, decidePending, evalSlot }: Props) {
  const findings = result.findings ?? [];
  const recommendations = result.recommendations ?? [];
  const gaps = result.data_gaps ?? [];

  return (
    <div className="ai-lab-result">
      {result.summary?.trim() && <p className="ai-lab-summary">{result.summary}</p>}

      {findings.length > 0 && (
        <section className="ai-lab-section" aria-labelledby="ai-lab-findings-title">
          <h3 id="ai-lab-findings-title" className="ai-lab-section-title">
            <Bi en="Findings" fa="یافته‌ها" />
          </h3>
          <div className="ai-lab-findings">
            {findings.map((f, i) => (
              <article key={`${f.title}-${i}`} className="ai-lab-finding">
                <div className="ai-lab-finding-head">
                  <strong>{f.title}</strong>
                  <span className={severityBadge(f.severity)}>{severityLabel(f.severity, bi)}</span>
                </div>
                <p className="ai-lab-evidence">{f.evidence}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      {recommendations.length > 0 && (
        <section className="ai-lab-section" aria-labelledby="ai-lab-recs-title">
          <h3 id="ai-lab-recs-title" className="ai-lab-section-title">
            <Bi en="Recommendations" fa="پیشنهادها" />
          </h3>
          <div className="ai-lab-recs">
            {recommendations.map((rec: AiRecommendation) => {
              const decision = decisions[rec.id];
              const recClass = decision === "accepted" ? "ai-lab-rec accepted" : decision === "rejected" ? "ai-lab-rec rejected" : "ai-lab-rec";
              return (
                <article key={rec.id} className={recClass}>
                  <p className="ai-lab-rec-action">{rec.action}</p>
                  <p className="ai-lab-rec-reason">{rec.reason}</p>
                  <div className="ai-lab-rec-meta">
                    <span className={confidenceBadge(rec.confidence)}>{confidenceLabel(rec.confidence, bi)}</span>
                    {rec.expected_impact?.trim() && (
                      <span>
                        <Bi en="Expected impact" fa="اثر مورد انتظار" />: {rec.expected_impact}
                      </span>
                    )}
                  </div>
                  <div className="ai-lab-rec-actions">
                    <Button
                      variant="ghost"
                      type="button"
                      disabled={decidePending || decision === "accepted"}
                      onClick={() => onDecide(rec.id, "accepted")}
                    >
                      <Bi en="Accept" fa="قبول" />
                    </Button>
                    <Button
                      variant="ghost"
                      type="button"
                      disabled={decidePending || decision === "rejected"}
                      onClick={() => onDecide(rec.id, "rejected")}
                    >
                      <Bi en="Reject" fa="رد" />
                    </Button>
                    {decision && (
                      <span className="badge ai">
                        {decision === "accepted" ? bi("Accepted", "پذیرفته") : bi("Rejected", "رد شده")}
                      </span>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      )}

      {gaps.length > 0 && (
        <section className="ai-lab-section" aria-labelledby="ai-lab-gaps-title">
          <h3 id="ai-lab-gaps-title" className="ai-lab-section-title">
            <Bi en="Data gaps" fa="خلأهای داده" />
          </h3>
          <ul className="ai-lab-gaps">
            {gaps.map((gap, i) => (
              <li key={i}>{gap}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="ai-lab-eval">{evalSlot}</div>
    </div>
  );
}

export function statusBadgeClass(status: string): string {
  if (status === "done") return "badge ok";
  if (status === "failed" || status === "expired") return "badge danger";
  if (status === "waiting" || status === "sent") return "badge warn";
  return "badge";
}
