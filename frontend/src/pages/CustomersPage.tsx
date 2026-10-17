import { useState, type FormEvent } from "react";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { DateText } from "../components/DateText";
import { useConfirm } from "../components/ui/ConfirmDialog";
import {
  Avatar,
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  ForbiddenState,
  LoadingState,
  Field,
  Icon,
  Input,
  MoreMenu,
  Muted,
  PageHeader,
  SectionHeader,
  Sheet,
  Table,
  TextArea,
} from "../components/ui";
import { SheetsSyncCard } from "../components/SheetsSyncCard";
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
  const listForbidden = listQuery.isError && listQuery.error instanceof ApiError && listQuery.error.status === 403;
  const listError =
    listQuery.isError && !listForbidden ? String((listQuery.error as Error).message) : "";
  const canAddCustomer = has("customer.write") || has("org.admin");

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
          <div className="row">
            {has("customer.write") || has("org.admin") ? (
              <Button onClick={() => setShowAdd(true)}>
                <Icon name="plus" size={14} />
                <Bi en="Add customer" fa="افزودن مشتری" />
              </Button>
            ) : null}
            {has("org.admin") && selected ? (
              <MoreMenu label={<Bi en="More" fa="بیشتر" />}>
                <Button
                  variant="ghost"
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
                  <Bi en="Export JSON" fa="خروجی JSON" />
                </Button>
              </MoreMenu>
            ) : null}
          </div>
        }
      />
      <SheetsSyncCard />
      <ErrorMessage error={error} />
      {listForbidden ? (
        <ForbiddenState />
      ) : listQuery.isLoading ? (
        <LoadingState />
      ) : (
      <Card padded={false} className="customers-list">
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
                render: (c) => <span className="cell-sub ltr-value">{String(c.email || "—")}</span>,
              },
            ]}
            empty={
              listError ? (
                <ErrorMessage error={listError} />
              ) : (
              <EmptyState
                titleEn="No customers yet"
                titleFa="هنوز مشتری‌ای نیست"
                bodyEn="Add a buyer or seller to get started."
                bodyFa="یک خریدار یا فروشنده اضافه کنید."
                action={
                  canAddCustomer ? (
                    <Button variant="secondary" onClick={() => setShowAdd(true)}>
                      <Icon name="plus" size={14} />
                      <Bi en="Add customer" fa="افزودن مشتری" />
                    </Button>
                  ) : undefined
                }
              />
              )
            }
          />
      </Card>
      )}

      <Sheet
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? String(selected.full_name) : ""}
      >
        {selected ? (
          <div className="stack stack--roomy">
            <div className="person-head">
              <Avatar name={String(selected.full_name)} size={42} />
              <div>
                <Muted><Bi en="Customer" fa="مشتری" /></Muted>
              </div>
              <Button
                variant="secondary"
                to={`/communication?new=1&customer=${String(selected.id)}&topic=${encodeURIComponent(
                  bi(`About: ${String(selected.full_name)}`, `درباره: ${String(selected.full_name)}`),
                )}`}
              >
                <Icon name="message" size={14} />
                <Bi en="Message" fa="پیام" />
              </Button>
            </div>
            <dl className="spec-grid spec-grid--single">
              <div>
                <dt>{bi("Phone", "تلفن")}</dt>
                <dd className="mono">{String(selected.phone || "—")}</dd>
              </div>
              <div>
                <dt>{bi("Email", "ایمیل")}</dt>
                <dd className="ltr-value">{String(selected.email || "—")}</dd>
              </div>
              <div>
                <dt>{bi("Added", "ثبت")}</dt>
                <dd><DateText value={selected.created_at} /></dd>
              </div>
              {selected.notes ? (
                <div>
                  <dt>{bi("Notes", "یادداشت")}</dt>
                  <dd className="prose-block">{String(selected.notes)}</dd>
                </div>
              ) : null}
            </dl>
            {has("org.admin") ? (
              <Button
                variant="danger-quiet"
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
                      "بله، ناشناس کن",
                      { danger: true },
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
            ) : null}
          </div>
        ) : null}
      </Sheet>

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
