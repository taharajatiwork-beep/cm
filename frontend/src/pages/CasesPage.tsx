import { useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorMessage,
  List,
  ListItem,
  Muted,
  PageHeader,
} from "../components/ui";
import { Bi, useBi } from "../i18n";
import { ConceptHint, StatusLabel } from "../ux";

export function CasesPage() {
  const { has } = useAuth();
  const bi = useBi();
  const [subject, setSubject] = useState("");
  const [created, setCreated] = useState<Record<string, unknown> | null>(null);
  const [timeline, setTimeline] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState("");

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const c = await api.cases.create({
        subject,
        type: "GENERAL_OPERATIONAL_REQUEST",
        priority: "MEDIUM",
      });
      setCreated(c);
      setTimeline(await api.cases.timeline(String(c.id)));
      setSubject("");
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Follow-ups" fa="پیگیری‌ها" />}
        description={
          <>
            <ConceptHint kind="followup" />
            <p>
              <Bi
                en="Write a subject below to open a follow-up. For daily work, use My Work instead."
                fa="برای باز کردن یک پیگیری، موضوعش را پایین بنویسید. برای کارهای روزمره از «کارهای من» استفاده کنید."
              />
            </p>
          </>
        }
        actions={
          <Button variant="secondary" to="/my-work">
            <Bi en="My Work" fa="کارهای من" />
          </Button>
        }
      />

      {has("case.write") && (
        <Card as="form" stack onSubmit={create} style={{ marginBottom: "1rem" }}>
          <div className="field">
            <label>
              <Bi en="What needs follow-up?" fa="چه چیزی باید پیگیری شود؟" />
            </label>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              required
              placeholder={bi("e.g. Buyer asked about Camry #124", "مثلاً خریدار درباره کمری ۱۲۴ پرسید")}
            />
          </div>
          <Button type="submit">
            <Bi en="New follow-up" fa="پیگیری جدید" />
          </Button>
        </Card>
      )}

      {!created && !has("case.write") && (
        <EmptyState
          titleEn="No follow-up open"
          titleFa="پیگیری بازی نیست"
          bodyEn="Follow-ups are usually created from a vehicle or project."
          bodyFa="پیگیری‌ها معمولاً از خودرو یا پروژه ساخته می‌شوند."
        />
      )}
      <ErrorMessage error={error} />

      {created && (
        <div className="grid grid-2">
          <Card>
            <CardTitle>
              <Bi en="Follow-up" fa="پیگیری" />
            </CardTitle>
            <p>{String(created.subject)}</p>
            <p className="row">
              <StatusLabel status={String(created.status)} />
              {created.sla_state && created.sla_state !== "NONE" && created.sla_state !== "ACTIVE" ? (
                <StatusLabel status={String(created.sla_state)} />
              ) : null}
            </p>
          </Card>
          <Card>
            <CardTitle>
              <Bi en="What happened" fa="چه اتفاقاتی افتاده" />
            </CardTitle>
            <List variant="timeline">
              {timeline.map((e) => (
                <ListItem key={String(e.id)}>
                  <strong>{String(e.event_type).split(".").pop()?.replace(/_/g, " ")}</strong>
                  <div>
                    <Muted>{new Date(String(e.created_at)).toLocaleString()}</Muted>
                  </div>
                </ListItem>
              ))}
            </List>
          </Card>
        </div>
      )}
    </>
  );
}
