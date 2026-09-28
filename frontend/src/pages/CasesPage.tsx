import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Field,
  Input,
  PageHeader,
  Select,
} from "../components/ui";
import { DateText } from "../components/DateText";
import { Bi, useBi } from "../i18n";

export function CasesPage() {
  const { has } = useAuth();
  const bi = useBi();
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const [subject, setSubject] = useState("");
  const [selected, setSelected] = useState<string>("");
  const list = useQuery({
    queryKey: ["cases", status],
    queryFn: () => api.cases.list(status ? { status } : undefined),
  });
  const timeline = useQuery({
    queryKey: ["cases", selected, "timeline"],
    enabled: Boolean(selected),
    queryFn: () => api.cases.timeline(selected),
  });
  const create = useMutation({
    mutationFn: () =>
      api.cases.create({ subject, type: "GENERAL_OPERATIONAL_REQUEST", priority: "MEDIUM" }),
    onSuccess: () => {
      setSubject("");
      void qc.invalidateQueries({ queryKey: ["cases"] });
    },
  });
  const rows = list.data ?? [];

  function onCreate(e: FormEvent) {
    e.preventDefault();
    if (has("case.write")) create.mutate();
  }

  return (
    <>
      <PageHeader title={<Bi en="Cases" fa="پرونده‌ها" />} />
      <div className="toolbar">
        <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label={bi("Status", "وضعیت")}>
          <option value="">{bi("All", "همه")}</option>
          <option value="OPEN">OPEN</option>
          <option value="IN_PROGRESS">IN_PROGRESS</option>
          <option value="COMPLETED">COMPLETED</option>
        </Select>
      </div>
      <ErrorMessage error={list.isError ? String((list.error as Error).message) : ""} />
      <div className="split">
        <Card>
          {rows.length === 0 ? (
            <EmptyState
              titleEn="No cases"
              titleFa="پرونده‌ای نیست"
              bodyEn="Create a follow-up when work needs a record."
              bodyFa="وقتی کاری باید ثبت شود، یک پرونده بسازید."
            />
          ) : (
            rows.map((row) => (
              <button
                key={String(row.id)}
                type="button"
                className="row-item"
                onClick={() => setSelected(String(row.id))}
              >
                <strong>{String(row.subject)}</strong>
                <span className="muted">{String(row.sla_state || row.status || "")}</span>
                <DateText value={row.created_at} />
              </button>
            ))
          )}
          {has("case.write") ? (
            <form onSubmit={onCreate} className="form-grid">
              <Field label={<Bi en="Subject" fa="موضوع" />}>
                <Input value={subject} onChange={(e) => setSubject(e.target.value)} required />
              </Field>
              <Button type="submit">
                <Bi en="Create" fa="ساخت" />
              </Button>
            </form>
          ) : null}
        </Card>
        <Card>
          {(timeline.data ?? []).map((event) => (
            <div key={String(event.id)} className="row-item">
              <span>{String(event.event_type)}</span>
              <DateText value={event.created_at} withTime />
            </div>
          ))}
        </Card>
      </div>
    </>
  );
}
