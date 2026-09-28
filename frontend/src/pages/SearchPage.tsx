import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import {
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Input,
  List,
  ListItem,
  Muted,
  PageHeader,
  Toolbar,
} from "../components/ui";
import { Bi, useBi } from "../i18n";

export function SearchPage({ initialQuery = "" }: { initialQuery?: string }) {
  const bi = useBi();
  const [q, setQ] = useState(initialQuery);
  const [submitted, setSubmitted] = useState(initialQuery);
  const searchQuery = useQuery({
    queryKey: ["search", submitted],
    enabled: submitted.trim().length > 0,
    queryFn: () => api.search(submitted),
  });
  const hits = searchQuery.data?.hits ?? [];
  const error = searchQuery.isError ? String((searchQuery.error as Error).message) : "";
  const ran = submitted.trim().length > 0;

  function runQuery(query: string) {
    setSubmitted(query);
  }

  async function run(e?: FormEvent) {
    e?.preventDefault();
    await runQuery(q);
  }

  function openHref(h: Record<string, unknown>) {
    const t = String(h.entity_type);
    const id = String(h.entity_id);
    if (t === "vehicle") return `/vehicles/${id}`;
    if (t === "work_item") return `/work-items/${id}`;
    if (t === "user") return `/people`;
    return null;
  }

  function typeLabel(t: string) {
    if (t === "vehicle") return bi("Vehicle", "خودرو");
    if (t === "work_item") return bi("Project", "پروژه");
    if (t === "case") return bi("Follow-up", "پیگیری");
    if (t === "user") return bi("Colleague", "همکار");
    return t;
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Search" fa="جستجو" />}
        description={
          <Bi
            en="Type a name, a car or a plate — we look everywhere for you."
            fa="یک نام، خودرو یا پلاک بنویسید — همه‌جا را برایتان می‌گردیم."
          />
        }
      />
      <Card className="block-gap">
        <Toolbar as="form" onSubmit={run}>
          <Input
            grow
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={bi("e.g. white Camry, Reza, Mashhad…", "مثلاً کمری سفید، رضا، مشهد…")}
            autoFocus
          />
          <Button type="submit">
            <Bi en="Search" fa="جستجو" />
          </Button>
        </Toolbar>
      </Card>
      <ErrorMessage error={error} />
      <Card>
        {!ran ? (
          <EmptyState
            titleEn="Start typing"
            titleFa="شروع به نوشتن کنید"
            bodyEn="Use the top bar or this page to search across the company."
            bodyFa="از نوار بالا یا همین صفحه در همه اطلاعات شرکت جستجو کنید."
          />
        ) : hits.length === 0 ? (
          <EmptyState
            titleEn="No matches"
            titleFa="نتیجه‌ای نبود"
            bodyEn="Try another name, stock number, or plate-related keyword."
            bodyFa="نام دیگر، شماره انبار یا کلیدواژه مرتبط را امتحان کنید."
          />
        ) : (
          <List>
            {hits.map((h, i) => {
              const href = openHref(h);
              return (
                <ListItem key={`${h.entity_type}-${h.entity_id}-${i}`}>
                  <div>
                    <strong>{String(h.title || h.entity_id)}</strong>
                    <div>
                      <Muted>{typeLabel(String(h.entity_type))}</Muted>
                    </div>
                  </div>
                  {href ? (
                    <Button variant="secondary" to={href}>
                      <Bi en="Open" fa="باز کردن" />
                    </Button>
                  ) : null}
                </ListItem>
              );
            })}
          </List>
        )}
      </Card>
    </>
  );
}
