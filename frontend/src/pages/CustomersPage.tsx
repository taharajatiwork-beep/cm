import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
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

type Customer = Record<string, unknown>;

export function CustomersPage() {
  const bi = useBi();
  const [rows, setRows] = useState<Customer[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Customer | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load(q?: string) {
    setRows(await api.customers.list(q));
  }

  useEffect(() => {
    void load().catch((e) => setError(String((e as Error).message)));
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.customers.create({
        full_name: fullName,
        phone: phone || null,
        email: email || null,
        notes: notes || null,
      });
      setFullName("");
      setPhone("");
      setEmail("");
      setNotes("");
      setShowAdd(false);
      await load(query || undefined);
    } catch (err) {
      setError(String((err as Error).message));
    } finally {
      setBusy(false);
    }
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
      <ErrorMessage error={error} />

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
