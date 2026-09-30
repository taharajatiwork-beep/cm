import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { Button, Card, EmptyState, ErrorMessage, PageHeader } from "../components/ui";
import { DateText } from "../components/DateText";
import { useToast } from "../components/ui/Toast";
import { Bi, useBi } from "../i18n";
import { StatusLabel } from "../ux";

type Step = { step_no: number; approver_id: string; decision: string | null; comment: string | null };
type Row = {
  id: string;
  title: string;
  status: string;
  requester_id: string;
  current_step: number;
  created_at?: string;
  steps?: Step[];
};

export function ApprovalsPage() {
  const { user } = useAuth();
  const bi = useBi();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["approvals"], queryFn: () => api.approvals.list() as Promise<Row[]> });
  const decide = useMutation({
    mutationFn: (body: { id: string; decision: "approved" | "rejected" }) =>
      api.approvals.decide(body.id, body.decision),
    onSuccess: () => {
      toast(bi("Saved", "ثبت شد"));
      void qc.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
  const rows = q.data ?? [];
  const mine = rows.filter((row) => row.requester_id === user?.id);
  const waiting = rows.filter((row) =>
    (row.steps ?? []).some(
      (step) => step.approver_id === user?.id && step.step_no === row.current_step && !step.decision,
    ),
  );

  return (
    <>
      <PageHeader title={<Bi en="Approvals" fa="تأییدها" />} />
      <ErrorMessage error={q.isError ? String((q.error as Error).message) : ""} />
      <Card>
        <h2>{bi("Waiting for me", "منتظر تصمیم من")}</h2>
        {waiting.length === 0 ? (
          <EmptyState titleEn="Nothing to decide" titleFa="چیزی برای تصمیم نیست" bodyEn="No request is waiting on you." bodyFa="درخواستی منتظر شما نیست." />
        ) : (
          waiting.map((row) => (
            <div key={row.id} className="row-item">
              <div>
                <strong>{row.title}</strong>
                <div className="muted">
                  <DateText value={row.created_at} />
                </div>
                {(row.steps ?? []).map((step) => (
                  <div key={step.step_no} className="muted">
                    {step.step_no}. {step.decision || bi("pending", "در انتظار")} {step.comment || ""}
                  </div>
                ))}
              </div>
              <Button onClick={() => decide.mutate({ id: row.id, decision: "approved" })}>
                <Bi en="Approve" fa="تأیید" />
              </Button>
              <Button variant="secondary" onClick={() => decide.mutate({ id: row.id, decision: "rejected" })}>
                <Bi en="Reject" fa="رد" />
              </Button>
            </div>
          ))
        )}
      </Card>
      <Card>
        <h2>{bi("My requests", "درخواست‌های من")}</h2>
        {mine.length === 0 ? (
          <EmptyState titleEn="No requests" titleFa="درخواستی نیست" bodyEn="You have not asked for an approval." bodyFa="درخواست تأییدی نداده‌اید." />
        ) : (
          mine.map((row) => (
            <div key={row.id} className="row-item">
              <span>{row.title}</span>
              <StatusLabel status={String(row.status)} />
            </div>
          ))
        )}
      </Card>
    </>
  );
}
