import { useState, type FormEvent } from "react";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { DateText } from "../components/DateText";
import { useConfirm } from "../components/ui/ConfirmDialog";
import {
  Avatar,
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Field,
  Icon,
  Input,
  Muted,
  PageHeader,
  SectionHeader,
  Sheet,
  Table,
  TextArea,
} from "../components/ui";
import { Bi, useBi } from "../i18n";
import { nextCursor } from "../lib/pagination";
import { queryKeys } from "../lib/queryKeys";

type Customer = Record<string, unknown>;

export function CustomersPage() {
  const bi = useBi();
  const { has } = useAuth();
  const confirm = useConfirm();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Customer | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const qc = useQueryClient();

  const listQuery = useInfiniteQuery({
    queryKey: queryKeys.customers(query),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => api.customers.page(query, pageParam),
    getNextPageParam: (last) => nextCursor(last),
  });
  const rows = listQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const listError = listQuery.isError ? String((listQuery.error as Error).message) : "";

  const createMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.customers.create(body),
    onSuccess: () => {
      setFullName("");
      setPhone("");
      setEmail("");
      setNotes("");
      setShowAdd(false);
      void qc.invalidateQueries({ queryKey: queryKeys.customersRoot });
    },
    onError: (err) => setError(String((err as Error).message)),
  });
  const busy = createMutation.isPending;

  function load(q?: string) {
    if (q !== undefined && q !== query) setQuery(q);
    return listQuery.refetch();
  }

  function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    createMutation.mutate({
      full_name: fullName,
      phone: phone || null,
      email: email || null,
      notes: notes || null,
    });
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Customers" fa="مشتریان" />}
        description={
          <Bi
            en="People who buy or sell cars with you. Click a name to see their details, or add a new customer."
            fa="کسانی که با شما خودرو می‌خرند یا می‌فروشند. روی نام بزنید تا جزئیات را ببینید، یا مشتری جدید اضافه کنید."
          />
        }
        actions={
          <Button onClick={() => setShowAdd(true)}>
            <Icon name="plus" size={14} />
            <Bi en="Add customer" fa="افزودن مشتری" />
          </Button>
        }
      />
      <ErrorMessage error={error || listError} />

      <div className="split">
        <Card padded={false}>
          <div className="card-bar">
            <SectionHeader title={<Bi en="All customers" fa="همه مشتریان" />} count={rows.length} />
            <form
              className="search-field"
              onSubmit={(e) => {
                e.preventDefault();
                void load(query || undefined);
              }}
            >
              <Icon name="search" size={14} />
              <Input
                placeholder={bi("Name or phone…", "نام یا تلفن…")}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </form>
          </div>
          <Table
            rows={rows}
            rowKey={(c) => String(c.id)}
            onRowClick={setSelected}
            isRowActive={(c) => selected?.id === c.id}
            columns={[
              {
                key: "name",
                header: <Bi en="Name" fa="نام" />,
                render: (c) => (
                  <span className="cell-main">
                    <Avatar name={String(c.full_name)} size={26} />
                    <strong>{String(c.full_name)}</strong>
                  </span>
                ),
              },
              {
                key: "phone",
                header: <Bi en="Phone" fa="تلفن" />,
                className: "mono",
                render: (c) => String(c.phone || "—"),
              },
              {
                key: "email",
                header: <Bi en="Email" fa="ایمیل" />,
                render: (c) => <span className="cell-sub">{String(c.email || "—")}</span>,
              },
            ]}
            empty={
              <EmptyState
                titleEn="No customers yet"
                titleFa="هنوز مشتری‌ای نیست"
                bodyEn="Add a buyer or seller to get started."
                bodyFa="یک خریدار یا فروشنده اضافه کنید."
                action={
                  <Button variant="secondary" onClick={() => setShowAdd(true)}>
                    <Icon name="plus" size={14} />
                    <Bi en="Add customer" fa="افزودن مشتری" />
                  </Button>
                }
              />
            }
          />
        </Card>

        <aside className="side-stack">
          <Card>
            {!selected ? (
              <div className="pane-empty" style={{ padding: "var(--space-4)" }}>
                <div>
                  <Icon name="user" size={22} />
                  <div className="muted">
                    <Bi en="Select a customer to see details." fa="برای دیدن جزئیات، یک مشتری انتخاب کنید." />
                  </div>
                </div>
              </div>
            ) : (
              <>
                <div className="person-head">
                  <Avatar name={String(selected.full_name)} size={42} />
                  <div>
                    <h2>{String(selected.full_name)}</h2>
                    <Muted>
                      <Bi en="Customer" fa="مشتری" />
                    </Muted>
                  </div>
                </div>
                <dl className="spec-grid" style={{ gridTemplateColumns: "1fr" }}>
                  <div>
                    <dt>{bi("Phone", "تلفن")}</dt>
                    <dd className="mono">{String(selected.phone || "—")}</dd>
                  </div>
                  <div>
                    <dt>{bi("Email", "ایمیل")}</dt>
                    <dd>{String(selected.email || "—")}</dd>
                  </div>
                  <div>
                    <dt>{bi("Added", "ثبت")}</dt>
                    <dd>
                      <DateText value={selected.created_at} />
                    </dd>
                  </div>
                  <div className="row">
                    {has("org.admin") ? (
                      <>
                        <Button
                          variant="secondary"
                          onClick={() => {
                            void api.customers.exportJson(String(selected.id)).then((body) => {
                              const blob = new Blob([JSON.stringify(body)], { type: "application/json" });
                              const url = URL.createObjectURL(blob);
                              const a = document.createElement("a");
                              a.href = url;
                              a.download = "customer.json";
                              a.click();
                            });
                          }}
                        >
                          <Bi en="Export" fa="خروجی" />
                        </Button>
                        <Button
                          variant="secondary"
                          onClick={() => {
                            void (async () => {
                              const first = await confirm(
                                "ناشناس کردن مشتری",
                                "نام، تلفن و ایمیل این مشتری پاک می‌شود.",
                                "ادامه",
                              );
                              if (!first) return;
                              const second = await confirm(
                                "تأیید نهایی",
                                "این کار برگشت‌پذیر نیست. دوباره تأیید کنید.",
                                "ناشناس کن",
                              );
                              if (!second || !selected) return;
                              await api.customers.erase(String(selected.id));
                              setSelected(null);
                              void qc.invalidateQueries({ queryKey: queryKeys.customersRoot });
                            })();
                          }}
                        >
                          <Bi en="Erase" fa="ناشناس" />
                        </Button>
                      </>
                    ) : null}
                  </div>
                  {selected.notes ? (
                    <div>
                      <dt>{bi("Notes", "یادداشت")}</dt>
                      <dd className="prose-block">{String(selected.notes)}</dd>
                    </div>
                  ) : null}
                </dl>
              </>
            )}
          </Card>
        </aside>
      </div>

      <Sheet
        open={showAdd}
        onClose={() => setShowAdd(false)}
        title={<Bi en="Add customer" fa="افزودن مشتری" />}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAdd(false)}>
              <Bi en="Cancel" fa="انصراف" />
            </Button>
            <Button type="submit" form="customer-form" disabled={busy}>
              {busy ? bi("Saving…", "در حال ذخیره…") : bi("Save customer", "ثبت مشتری")}
            </Button>
          </>
        }
      >
        <form id="customer-form" className="form-grid" onSubmit={create}>
          <Field label={<Bi en="Full name" fa="نام کامل" />} className="span-all">
            <Input value={fullName} onChange={(e) => setFullName(e.target.value)} required autoFocus />
          </Field>
          <Field label={<Bi en="Phone" fa="تلفن" />}>
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </Field>
          <Field label={<Bi en="Email" fa="ایمیل" />}>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label={<Bi en="Notes" fa="یادداشت" />} className="span-all">
            <TextArea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
        </form>
      </Sheet>
    </>
  );
}
