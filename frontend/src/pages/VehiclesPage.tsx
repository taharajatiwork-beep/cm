import { useId, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { DateText } from "../components/DateText";
import { useAuth } from "../auth";
import { isForbiddenError } from "../lib/apiError";
import {
  Button,
  Card,
  MoreMenu,
  Dialog,
  EmptyState,
  ErrorMessage,
  ForbiddenState,
  Field,
  Icon,
  Input,
  List,
  Select,
  ListItem,
  LoadingState,
  Muted,
  PageHeader,
  SectionHeader,
  Sheet,
  Table,
  TextArea,
} from "../components/ui";
import { faDigits, faNum, faYear, tomanText } from "../fa";
import { Bi, useBi } from "../i18n";
import { useToast } from "../components/ui/Toast";
import { nextCursor } from "../lib/pagination";
import { queryKeys } from "../lib/queryKeys";
import { formatEngine, useVehicleHistoryNote, useVehicleLabel } from "../lib/vehicleLabels";
import { InquiryDialog } from "../components/InquiryDialog";
import { StatusLabel } from "../ux";

type VehicleForm = {
  vin: string;
  brand: string;
  model: string;
  year: string;
  stock_number: string;
  color: string;
  trim: string;
  mileage: string;
  sale_price: string;
  purchase_price: string;
  body_type: string;
  transmission: string;
  fuel_type: string;
  engine: string;
  plate_number: string;
  doors: string;
  seats: string;
  options: string;
  exterior_condition: string;
  interior_condition: string;
  description: string;
  notes: string;
};

const emptyForm: VehicleForm = {
  vin: "",
  brand: "",
  model: "",
  year: "",
  stock_number: "",
  color: "",
  trim: "",
  mileage: "",
  sale_price: "",
  purchase_price: "",
  body_type: "",
  transmission: "",
  fuel_type: "",
  engine: "",
  plate_number: "",
  doors: "",
  seats: "",
  options: "",
  exterior_condition: "",
  interior_condition: "",
  description: "",
  notes: "",
};

function numOrNull(v: string): number | null {
  const t = v.trim();
  if (!t) return null;
  const n = Number(t.replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

function strOrNull(v: string): string | null {
  const t = v.trim();
  return t || null;
}

function formBody(form: VehicleForm, includePrice: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = {
    vin: strOrNull(form.vin),
    brand: form.brand.trim(),
    model: form.model.trim(),
    year: Number(form.year),
    stock_number: strOrNull(form.stock_number),
    color: strOrNull(form.color),
    trim: strOrNull(form.trim),
    mileage: numOrNull(form.mileage),
    body_type: strOrNull(form.body_type),
    transmission: strOrNull(form.transmission),
    fuel_type: strOrNull(form.fuel_type),
    engine: strOrNull(form.engine),
    plate_number: strOrNull(form.plate_number),
    doors: numOrNull(form.doors),
    seats: numOrNull(form.seats),
    options: strOrNull(form.options),
    exterior_condition: strOrNull(form.exterior_condition),
    interior_condition: strOrNull(form.interior_condition),
    description: strOrNull(form.description),
    notes: strOrNull(form.notes),
  };
  if (includePrice) {
    const sale = numOrNull(form.sale_price);
    if (sale != null) body.sale_price = sale;
    body.purchase_price = numOrNull(form.purchase_price);
  }
  return body;
}

function QuickEditPop({
  rows,
  canPrice,
  saving,
  onClose,
  onSave,
}: {
  rows: Array<Record<string, unknown>>;
  canPrice: boolean;
  saving: boolean;
  onClose: () => void;
  onSave: (id: string, fields: Record<string, unknown>) => void;
}) {
  const bi = useBi();
  const vehicleLabel = useVehicleLabel();
  const titleId = useId();

  return (
    <Dialog onClose={onClose} className="quick-edit-pop" labelledBy={titleId} closeLabel={bi("Close", "بستن")}>
        <SectionHeader
          title={<span id={titleId}><Bi en="Quick edit" fa="ویرایش سریع" /></span>}
          count={rows.length}
          action={
            <button type="button" className="kpi-more" onClick={onClose}>
              <Bi en="Close" fa="بستن" />
            </button>
          }
        />
        <p className="help-text">
          <Bi
            en="Price is in million toman. Saving a price needs the finance permission; otherwise it stays unchanged."
            fa="قیمت به میلیون تومان است. ثبت قیمت فقط با مجوز مالی انجام می‌شود."
          />
        </p>
        <div className="quick-edit-list">
          {rows.map((row) => {
            const id = String(row.id);
            return (
              <form
                key={id}
                className="quick-edit-row"
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  const million = String(data.get("price") || "").trim();
                  const fields: Record<string, unknown> = {
                    status: String(data.get("status") || row.status),
                    mileage: numOrNull(String(data.get("mileage") || "")),
                    delivery_note: strOrNull(String(data.get("note") || "")),
                  };
                  if (million && canPrice) fields.sale_price = Number(million.replace(/,/g, "")) * 1_000_000;
                  onSave(id, fields);
                }}
              >
                <strong>
                  {vehicleLabel(String(row.brand))} {vehicleLabel(String(row.model))}
                </strong>
                <Input name="price" defaultValue={row.sale_price != null ? String(Math.round(Number(row.sale_price) / 1_000_000)) : ""} placeholder={bi("Price, million", "قیمت، میلیون")} disabled={!canPrice} />
                <Input name="mileage" defaultValue={row.mileage != null ? String(row.mileage) : ""} placeholder={bi("Mileage", "کارکرد")} />
                <Input name="note" defaultValue={row.delivery_note != null ? String(row.delivery_note) : ""} placeholder={bi("Delivery note", "یادداشت تحویل")} />
                <Select name="status" defaultValue={String(row.status)}>
                  <option value="IN_STOCK">{bi("In stock", "موجود")}</option>
                  <option value="RESERVED">{bi("Reserved", "رزرو")}</option>
                  <option value="SOLD">{bi("Sold", "فروخته‌شده")}</option>
                </Select>
                <Button type="submit" variant="secondary" disabled={saving}>
                  <Bi en="Save" fa="ثبت" />
                </Button>
              </form>
            );
          })}
        </div>
    </Dialog>
  );
}

export function VehiclesPage() {
  const { has } = useAuth();
  const bi = useBi();
  const vehicleLabel = useVehicleLabel();
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [showPaste, setShowPaste] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [preview, setPreview] = useState<{
    rows: Array<Record<string, unknown>>;
    missing: Array<Record<string, unknown>>;
  } | null>(null);
  const [quick, setQuick] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [form, setForm] = useState<VehicleForm>(emptyForm);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canRead = has("inventory.read");
  const canWrite = has("inventory.write");
  const canPrice = has("price.approve") || has("price.write");

  // Filter text is part of the key: every search is its own cache entry.
  const listQuery = useInfiniteQuery({
    queryKey: queryKeys.vehicles(q, canRead),
    enabled: canRead,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => api.vehicles.page(q, pageParam),
    getNextPageParam: (last) => nextCursor(last),
  });
  const rows = useMemo(
    () => listQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [listQuery.data],
  );
  const loading = listQuery.isLoading;
  const listForbidden = listQuery.isError && isForbiddenError(listQuery.error);
  const listError = listQuery.isError && !listForbidden ? listQuery.error : null;
  const scopeEmpty = canRead && !loading && !listQuery.isError && rows.length === 0 && !q.trim() && statusFilter === "ALL";
  const invalidateVehicles = () => qc.invalidateQueries({ queryKey: queryKeys.vehiclesRoot });

  function setField<K extends keyof VehicleForm>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  const saveMutation = useMutation({
    mutationFn: (input: { id: string | null; body: Record<string, unknown> }) =>
      input.id ? api.vehicles.update(input.id, input.body) : api.vehicles.create(input.body),
    onSuccess: (v, input) => {
      setShowAdd(false);
      setEditingId(null);
      void invalidateVehicles();
      if (!input.id) navigate(`/vehicles/${v.id}`);
      else toast(bi("Saved", "ثبت شد"));
    },
    onError: (err) => setError(String((err as Error).message)),
  });
  function openAdd() {
    setEditingId(null);
    setForm(emptyForm);
    setError("");
    setShowAdd(true);
  }

  function closeForm() {
    setShowAdd(false);
    setEditingId(null);
  }

  function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    saveMutation.mutate({ id: editingId, body: formBody(form, !editingId || canPrice) });
  }

  const importMutation = useMutation({
    mutationFn: (file: File) => api.vehicles.importFile(file),
    onSuccess: (result) => {
      toast(
        bi(
          `Imported ${result.created} vehicle(s), skipped ${result.skipped}.`,
          `${result.created} خودرو ثبت شد، ${result.skipped} رد شد.`,
        ) +
          (result.errors.length
            ? ` ${bi("First issues:", "اولین خطاها:")} ${result.errors.slice(0, 3).join(" · ")}`
            : ""),
      );
      setShowImport(false);
      void invalidateVehicles();
    },
    onError: (e) => setError(String((e as Error).message)),
    onSettled: () => {
      if (fileRef.current) fileRef.current.value = "";
    },
  });
  const importing = importMutation.isPending;

  function onImportFile(file: File | null) {
    if (!file) return;
    setError("");
    importMutation.mutate(file);
  }

  const pastePreview = useMutation({
    mutationFn: () => api.vehicles.pastePreview(pasteText),
    onSuccess: (result) => setPreview(result),
    onError: (e) => setError(String((e as Error).message)),
  });
  const pasteApply = useMutation({
    mutationFn: () => api.vehicles.pasteApply([...(preview?.rows ?? []), ...(preview?.missing ?? [])]),
    onSuccess: (result) => {
      toast(
        bi(
          `Added ${result.created}, prices updated ${result.updated}, sent to finance ${result.proposed}.`,
          `${result.created} خودرو اضافه شد، ${result.updated} قیمت ثبت شد، ${result.proposed} مورد برای مالی رفت.`,
        ),
      );
      setShowPaste(false);
      setPreview(null);
      void invalidateVehicles();
    },
    onError: (e) => setError(String((e as Error).message)),
  });
  const quickSave = useMutation({
    mutationFn: (body: { id: string; fields: Record<string, unknown> }) => api.vehicles.update(body.id, body.fields),
    onSuccess: () => {
      toast(bi("Saved", "ثبت شد"));
      void invalidateVehicles();
    },
    onError: (e) => setError(String((e as Error).message)),
  });

  function togglePreview(kind: "rows" | "missing", index: number) {
    setPreview((current) => {
      if (!current) return current;
      const list = current[kind].map((row, i) => (i === index ? { ...row, apply: !row.apply } : row));
      return { ...current, [kind]: list };
    });
  }

  async function copyStockMessage() {
    const lines = rows
      .filter((row) => String(row.status) === "IN_STOCK")
      .map((row) => {
        const price =
          row.sale_price != null ? Math.round(Number(row.sale_price) / 1_000_000).toLocaleString("fa-IR") : "—";
        return `${vehicleLabel(String(row.brand))} ${vehicleLabel(String(row.model))}${row.color ? ` ${vehicleLabel(String(row.color))}` : ""} ${row.year} — ${price}`;
      });
    const text = [`موجودی خودرو`, ...lines].join("\n");
    await navigator.clipboard.writeText(text);
    toast(bi("Stock message copied", "پیام موجودی کپی شد"));
  }

  const statusCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of rows) c[String(r.status)] = (c[String(r.status)] || 0) + 1;
    return c;
  }, [rows]);

  const visible =
    statusFilter === "ALL" ? rows : rows.filter((r) => String(r.status) === statusFilter);

  const statusChips: Array<[string, string, string]> = [
    ["ALL", "All", "همه"],
    ["IN_STOCK", "In stock", "موجود"],
    ["RESERVED", "Reserved", "رزرو"],
    ["SOLD", "Sold", "فروخته‌شده"],
  ];

  function text(
    key: keyof VehicleForm,
    en: string,
    fa: string,
    opts: { required?: boolean; span?: string; placeholder?: string; disabled?: boolean } = {},
  ) {
    return (
      <Field
        label={
          <>
            <Bi en={en} fa={fa} />
            {opts.required ? <span className="req"> *</span> : null}
          </>
        }
        className={opts.span}
      >
        <Input
          value={form[key]}
          onChange={(e) => setField(key, e.target.value)}
          required={opts.required}
          placeholder={opts.placeholder}
          disabled={opts.disabled}
        />
      </Field>
    );
  }

  if (!canRead || listForbidden) {
    return (
      <>
        <PageHeader title={<Bi en="Vehicles" fa="خودروها" />} />
        <ForbiddenState />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Vehicles" fa="خودروها" />}
        description={
          has("inventory.write") ? (
            <Bi
              en="All cars you have. Click a car to see its details, or add a new one."
              fa="همه خودروهای شما. روی هر خودرو بزنید تا جزئیاتش را ببینید، یا خودروی جدید اضافه کنید."
            />
          ) : (
            <Bi
              en="Cars in stock. Click a row to see details."
              fa="خودروهای موجود. روی هر ردیف بزنید تا جزئیات را ببینید."
            />
          )
        }
        actions={
          has("inventory.write") ? (
            <>
              <Button onClick={openAdd}>
                <Icon name="plus" size={14} />
                <Bi en="Add vehicle" fa="افزودن خودرو" />
              </Button>
              <MoreMenu label={<Bi en="More" fa="بیشتر" />}>
                <Button variant="ghost" onClick={() => void copyStockMessage()}>
                  <Bi en="Copy stock message" fa="کپی پیام موجودی" />
                </Button>
                <Button variant="ghost" onClick={() => setQuick(true)}>
                  <Bi en="Quick edit" fa="ویرایش سریع" />
                </Button>
                <Button variant="ghost" onClick={() => { setPreview(null); setShowPaste(true); }}>
                  <Bi en="Paste stock message" fa="چسباندن پیام موجودی" />
                </Button>
                <Button variant="ghost" onClick={() => setShowImport(true)}>
                  <Icon name="upload" size={14} />
                  <Bi en="Add from Excel" fa="افزودن از اکسل" />
                </Button>
              </MoreMenu>
            </>
          ) : undefined
        }
      />

      <ErrorMessage error={error || listError} />

      <Card padded={false}>
        <div className="card-bar">
          <div className="chips">
            {statusChips.map(([key, en, fa]) => (
              <button
                key={key}
                type="button"
                className={`chip${statusFilter === key ? " active" : ""}`}
                onClick={() => setStatusFilter(key)}
              >
                {bi(en, fa)}
                <span className="chip-count">
                  {faNum(key === "ALL" ? rows.length : statusCounts[key] || 0)}
                </span>
              </button>
            ))}
          </div>
          <form
            className="search-field"
            onSubmit={(e) => {
              e.preventDefault();
              void listQuery.refetch();
            }}
          >
            <Icon name="search" size={14} />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={bi("Search brand, model, plate…", "جستجوی برند، مدل، پلاک…")}
            />
          </form>
        </div>

        {loading ? (
          <LoadingState />
        ) : (
          <Table
            rows={visible}
            rowKey={(v) => String(v.id)}
            onRowClick={(v) => navigate(`/vehicles/${String(v.id)}`)}
            empty={
              <EmptyState
                titleEn={scopeEmpty ? "No vehicles in your scope" : "No vehicles match"}
                titleFa={scopeEmpty ? "در محدودهٔ شما خودرویی نیست" : "خودرویی پیدا نشد"}
                bodyEn={
                  scopeEmpty
                    ? "Your role can browse inventory, but nothing is visible in your team scope right now."
                    : canWrite
                      ? "Change the filter, or add / import vehicles."
                      : "Change the filter or ask someone who can edit inventory."
                }
                bodyFa={
                  scopeEmpty
                    ? "دسترسی مشاهده دارید، اما در محدودهٔ تیم شما فعلاً خودرویی ثبت نشده."
                    : canWrite
                      ? "فیلتر را تغییر دهید یا خودرو اضافه / وارد کنید."
                      : "فیلتر را عوض کنید یا از کسی که به موجودی دسترسی دارد بخواهید."
                }
                action={
                  has("inventory.write") ? (
                    <Button variant="secondary" onClick={openAdd}>
                      <Icon name="plus" size={14} />
                      <Bi en="Add vehicle" fa="افزودن خودرو" />
                    </Button>
                  ) : undefined
                }
              />
            }
            columns={[
              {
                key: "vehicle",
                header: <Bi en="Vehicle" fa="خودرو" />,
                render: (v) => (
                  <div className="vehicle-cell">
                    <span className="vehicle-thumb">
                      <Icon name="car" />
                    </span>
                    <div>
                      <strong>
                        {vehicleLabel(String(v.brand))} {vehicleLabel(String(v.model))}
                      </strong>
                      <div className="cell-sub">
                        {faYear(v.year as number | string)}
                        {v.trim ? ` · ${vehicleLabel(String(v.trim))}` : ""}
                        {v.stock_number ? ` · #${String(v.stock_number)}` : ""}
                      </div>
                    </div>
                  </div>
                ),
              },
              {
                key: "specs",
                header: <Bi en="Specs" fa="مشخصات" />,
                render: (v) => (
                  <span className="cell-sub">
                    {[
                      v.color ? vehicleLabel(String(v.color)) : null,
                      v.mileage != null ? `${faNum(Number(v.mileage))} کیلومتر` : null,
                      v.transmission ? vehicleLabel(String(v.transmission)) : null,
                      v.fuel_type ? vehicleLabel(String(v.fuel_type)) : null,
                    ]
                      .filter(Boolean)
                      .map(String)
                      .join(" · ") || "—"}
                  </span>
                ),
              },
              {
                key: "price",
                header: <Bi en="Price" fa="قیمت" />,
                render: (v) =>
                  v.sale_price != null ? (
                    <span className="num">{tomanText(Number(v.sale_price))}</span>
                  ) : (
                    <Muted>—</Muted>
                  ),
              },
              {
                key: "status",
                header: <Bi en="Status" fa="وضعیت" />,
                render: (v) => <StatusLabel status={String(v.status)} />,
              },
              {
                key: "created",
                header: <Bi en="Added" fa="ثبت" />,
                render: (v) => <DateText value={v.created_at} />,
              },
            ]}
          />
        )}
      </Card>

      {quick && has("inventory.write") ? <QuickEditPop rows={visible.slice(0, 30)} canPrice={has("price.approve") || has("price.write")} saving={quickSave.isPending} onClose={() => setQuick(false)} onSave={(id, fields) => quickSave.mutate({ id, fields })} /> : null}

      <Sheet
        open={showPaste}
        onClose={() => setShowPaste(false)}
        title={<Bi en="Paste the stock message" fa="چسباندن پیام موجودی" />}
        footer={
          <>
            <Button variant="secondary" onClick={() => pastePreview.mutate()} disabled={!pasteText.trim()}>
              <Bi en="Preview" fa="پیش‌نمایش" />
            </Button>
            <Button onClick={() => pasteApply.mutate()} disabled={!preview}>
              <Bi en="Apply selected" fa="اعمال موارد انتخاب‌شده" />
            </Button>
          </>
        }
      >
        <TextArea rows={8} value={pasteText} onChange={(e) => setPasteText(e.target.value)} placeholder={bi("Paste the manager’s stock message", "پیام موجودی مدیر فروش را اینجا بگذارید")} />
        {preview ? (
          <div className="stack">
            {preview.rows.map((row, index) => (
              <label key={`row-${index}`} className="check-row">
                <input type="checkbox" checked={Boolean(row.apply)} onChange={() => togglePreview("rows", index)} />
                <span>
                  {String(row.action)} · {vehicleLabel(String(row.brand || ""))} {vehicleLabel(String(row.model || ""))} · {row.price_million != null ? String(row.price_million) : ""}
                </span>
              </label>
            ))}
            {preview.missing.map((row, index) => (
              <label key={`miss-${index}`} className="check-row">
                <input type="checkbox" checked={Boolean(row.apply)} onChange={() => togglePreview("missing", index)} />
                <span>
                  <Bi en="Missing from the list — mark sold" fa="در لیست نیست — فروخته‌شده" /> · {vehicleLabel(String(row.brand))} {vehicleLabel(String(row.model))}
                </span>
              </label>
            ))}
          </div>
        ) : null}
      </Sheet>

      <Sheet
        open={showAdd}
        onClose={closeForm}
        title={editingId ? <Bi en="Edit vehicle" fa="ویرایش خودرو" /> : <Bi en="Add vehicle" fa="افزودن خودرو" />}
        footer={
          <>
            <Button variant="secondary" onClick={closeForm}>
              <Bi en="Cancel" fa="انصراف" />
            </Button>
            <Button type="submit" form="vehicle-form" disabled={saveMutation.isPending}>
              {editingId ? <Bi en="Save changes" fa="ثبت تغییرات" /> : <Bi en="Save vehicle" fa="ثبت خودرو" />}
            </Button>
          </>
        }
      >
        <form id="vehicle-form" className="form-grid" onSubmit={save}>
          <p className="help-text span-all">
            <Bi
              en="Only the starred fields are required. You can add the rest later."
              fa="فقط فیلدهای ستاره‌دار لازم است. بقیه را بعداً هم می‌توانید اضافه کنید."
            />
          </p>
          {text("brand", "Brand", "برند", { required: true, placeholder: bi("e.g. Hyundai", "مثلاً هیوندای") })}
          {text("model", "Model", "مدل", { required: true, placeholder: bi("e.g. Elantra", "مثلاً النترا") })}
          {text("year", "Year", "سال ساخت", { required: true, placeholder: "2021" })}
          {text("vin", "Chassis number (VIN)", "شماره شاسی", { required: !editingId, span: "span-2" })}
          {text("color", "Color", "رنگ")}
          {text("mileage", "Mileage (km)", "کارکرد (کیلومتر)")}
          {text("sale_price", "Sale price", "قیمت فروش", { disabled: Boolean(editingId) && !canPrice })}
          <Field label={<Bi en="Description" fa="توضیحات" />} className="span-all">
            <TextArea
              rows={3}
              value={form.description}
              onChange={(e) => setField("description", e.target.value)}
              placeholder={bi("Anything a buyer should know", "هر چیزی که خریدار باید بداند")}
            />
          </Field>

          <details className="advanced span-all">
            <summary>
              <Bi en="More details" fa="جزئیات بیشتر" />
              <span className="muted">
                <Bi en="(optional — price, specs, condition)" fa="(اختیاری — قیمت خرید، مشخصات فنی، وضعیت)" />
              </span>
            </summary>
            <div className="advanced-body">
              <div className="form-grid">
                {text("purchase_price", "Purchase price", "قیمت خرید", { disabled: Boolean(editingId) && !canPrice })}
                {text("plate_number", "Plate", "پلاک")}
                {text("stock_number", "Stock #", "شماره انبار")}
                {text("trim", "Trim", "تیپ")}
                {text("body_type", "Body", "بدنه")}
                {text("transmission", "Transmission", "گیربکس")}
                {text("fuel_type", "Fuel", "سوخت")}
                {text("engine", "Engine", "موتور")}
                {text("doors", "Doors", "تعداد در")}
                {text("seats", "Seats", "تعداد صندلی")}
                {text("options", "Options", "آپشن‌ها", { span: "span-all" })}
                {text("exterior_condition", "Body condition", "وضعیت بدنه")}
                {text("interior_condition", "Interior condition", "وضعیت داخل")}
                <Field label={<Bi en="Private note (only staff see it)" fa="یادداشت داخلی (فقط همکاران می‌بینند)" />} className="span-all">
                  <TextArea rows={2} value={form.notes} onChange={(e) => setField("notes", e.target.value)} />
                </Field>
              </div>
            </div>
          </details>
        </form>
      </Sheet>

      <Sheet
        open={showImport}
        onClose={() => setShowImport(false)}
        title={<Bi en="Add many cars from Excel" fa="افزودن چند خودرو از اکسل" />}
      >
        <div className="stack">
          <button
            type="button"
            className="drop-zone"
            disabled={importing}
            onClick={() => fileRef.current?.click()}
          >
            <Icon name="upload" size={22} />
            <strong>
              {importing ? bi("Importing…", "در حال ورود…") : bi("Choose a file", "انتخاب فایل")}
            </strong>
            <span>.xlsx · .csv</span>
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xlsm,.csv"
            hidden
            onChange={(e) => void onImportFile(e.target.files?.[0] ?? null)}
          />
          <Muted>
            <Bi
              en="1. Download the template below.  2. Fill one car per row.  3. Choose the file above. Cars already registered are skipped automatically."
              fa="۱. قالب زیر را دانلود کنید.  ۲. هر خودرو را در یک ردیف پر کنید.  ۳. فایل را از بالا انتخاب کنید. خودروهای تکراری خودکار رد می‌شوند."
            />
          </Muted>
          <div className="row">
            <Button variant="secondary" onClick={() => void api.vehicles.downloadImportTemplate("xlsx")}>
              <Icon name="download" size={14} />
              <Bi en="Excel template" fa="قالب اکسل" />
            </Button>
            <Button variant="secondary" onClick={() => void api.vehicles.downloadImportTemplate("csv")}>
              <Icon name="download" size={14} />
              <Bi en="CSV template" fa="قالب CSV" />
            </Button>
          </div>
        </div>
      </Sheet>
    </>
  );
}

function VehicleOps({ id }: { id: string }) {
  const divar = useQuery({ queryKey: ["vehicle-divar", id], queryFn: () => api.vehicles.divar(id) });
  return (
    <Card>
      <div className="row">
        <Button variant="secondary" onClick={() => void api.vehicles.setStatus(id, "RESERVED", "reserved from the vehicle page")}>
          <Bi en="Reserve" fa="رزرو" />
        </Button>
        <Button variant="secondary" onClick={() => void api.vehicles.setStatus(id, "SOLD", "sold from the vehicle page")}>
          <Bi en="Sold" fa="فروخته شد" />
        </Button>
      </div>
      <div className="muted">
        {(divar.data ?? []).map((row) => (
          <div key={String(row.id)}>
            <StatusLabel status={String(row.status)} />
            {row.last_error ? (
              <span className="muted"> — {String(row.last_error)}</span>
            ) : null}
          </div>
        ))}
      </div>
    </Card>
  );
}

function Spec({
  label,
  value,
  formatValue,
}: {
  label: ReactNode;
  value: unknown;
  formatValue?: (raw: string) => string;
}) {
  if (value == null || value === "") return null;
  const text = formatValue ? formatValue(String(value)) : String(value);
  return (
    <div>
      <dt>{label}</dt>
      <dd>{text}</dd>
    </div>
  );
}

export function VehicleDetailPage() {
  const { id = "" } = useParams();
  const vehicleLabel = useVehicleLabel();
  const historyNote = useVehicleHistoryNote();
  const { has } = useAuth();
  const [inquiryOpen, setInquiryOpen] = useState(false);
  const bi = useBi();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const ctxQuery = useQuery({
    queryKey: queryKeys.vehicleContext(id),
    enabled: Boolean(id),
    queryFn: () => api.vehicles.context(id),
  });
  const ctx = ctxQuery.data ?? null;
  const ctxError = ctxQuery.isError ? String((ctxQuery.error as Error).message) : "";

  const createWorkMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.workItems.create(body),
    onSuccess: (wi) => {
      void qc.invalidateQueries({ queryKey: queryKeys.workItemsRoot });
      navigate(`/work-items/${wi.id}`);
    },
    onError: (e) => setError(String((e as Error).message)),
    onSettled: () => setBusy(false),
  });

  function startSharedWork() {
    if (!ctx) return;
    setBusy(true);
    const v = ctx.vehicle;
    createWorkMutation.mutate({
      title: bi(
        `Sell ${v.brand} ${v.model} #${v.stock_number || ""}`.trim(),
        `فروش ${vehicleLabel(String(v.brand))} ${vehicleLabel(String(v.model))}${v.stock_number ? ` #${v.stock_number}` : ""}`.trim(),
      ),
      vehicle_id: id,
      priority: "HIGH",
    });
  }

  if (error || ctxError) {
    if (!ctx) return <ErrorMessage error={error || ctxError} />;
  }
  if (!ctx) return <LoadingState />;

  const v = ctx.vehicle;
  const money = (n: unknown) => (n != null ? tomanText(Number(n)) : null);
  const margin =
    v.sale_price != null && v.purchase_price != null
      ? Number(v.sale_price) - Number(v.purchase_price)
      : null;

  return (
    <>
      <PageHeader
        title={
          <span className="vehicle-hero">
            <span className="vehicle-thumb">
              <Icon name="car" size={22} />
            </span>
            <span>
              {vehicleLabel(String(v.brand))} {vehicleLabel(String(v.model))}{" "}
              <Muted>{faYear(v.year as number | string)}</Muted>
            </span>
          </span>
        }
        description={
          <span className="meta-line">
            <StatusLabel status={String(v.status)} />
            {v.color ? (
              <>
                <span className="dot" />
                <span>{vehicleLabel(String(v.color))}</span>
              </>
            ) : null}
            {v.trim ? (
              <>
                <span className="dot" />
                <span>{vehicleLabel(String(v.trim))}</span>
              </>
            ) : null}
          </span>
        }
        actions={
          <>
            {has("inventory.write") && String(v.status) === "IN_STOCK" ? (
              <>
                <Button variant="secondary" onClick={() => void api.vehicles.setStatus(id, "RESERVED", "reserved from vehicle page")}>
                  <Bi en="Reserve" fa="رزرو" />
                </Button>
                <Button variant="secondary" onClick={() => void api.vehicles.setStatus(id, "SOLD", "sold from vehicle page")}>
                  <Bi en="Sold" fa="فروخته شد" />
                </Button>
              </>
            ) : null}
            {has("inquiry.create") ? (
              <Button type="button" onClick={() => setInquiryOpen(true)}>
                <Bi en="New inquiry" fa="استعلام جدید" />
              </Button>
            ) : null}
            <Button variant="secondary" to="/vehicles">
              <Bi en="Back" fa="بازگشت" />
            </Button>
            <Button variant="secondary" to={`/agent?q=${encodeURIComponent(`${v.brand} ${v.model} ${v.year}`)}`}>
              <Icon name="sparkles" size={14} />
              <Bi en="Ask the assistant" fa="از دستیار بپرس" />
            </Button>
            {has("work_item.write") && (
              <Button
                disabled={busy}
                onClick={() => void startSharedWork()}
                title={bi("Create a team project to sell or prepare this car", "یک پروژه تیمی برای فروش یا آماده‌سازی این خودرو بسازید")}
              >
                <Icon name="plus" size={14} />
                <Bi en="Start selling this car" fa="شروع فروش این خودرو" />
              </Button>
            )}
          </>
        }
      />

      <ErrorMessage error={error || ctxError} />
      <InquiryDialog
        open={inquiryOpen}
        onClose={() => setInquiryOpen(false)}
        vehicleId={id}
        vehicleLabel={`${vehicleLabel(String(v.brand))} ${vehicleLabel(String(v.model))} ${String(v.year)}`}
      />
      <VehicleOps id={id} />

      <div className="split split--wide-side">
        <div className="stack stack--roomy">
          <Card>
            <SectionHeader icon="layers" title={<Bi en="Specifications" fa="مشخصات" />} />
            <dl className="spec-grid">
              <Spec label={bi("Mileage", "کیلومتر")} value={v.mileage != null ? `${faNum(Number(v.mileage))} کیلومتر` : null} />
              <Spec label={bi("Body", "بدنه")} value={v.body_type} formatValue={vehicleLabel} />
              <Spec label={bi("Transmission", "گیربکس")} value={v.transmission} formatValue={vehicleLabel} />
              <Spec label={bi("Fuel", "سوخت")} value={v.fuel_type} formatValue={vehicleLabel} />
              <Spec label={bi("Engine", "موتور")} value={v.engine} formatValue={formatEngine} />
              <Spec label={bi("Plate", "پلاک")} value={v.plate_number} />
              <Spec label={bi("Doors", "درب")} value={v.doors != null ? faDigits(String(v.doors)) : null} />
              <Spec label={bi("Seats", "صندلی")} value={v.seats != null && v.seats !== "" ? faDigits(String(v.seats)) : null} />
              <Spec label={bi("Exterior", "بیرونی")} value={v.exterior_condition} />
              <Spec label={bi("Interior", "داخلی")} value={v.interior_condition} />
              <Spec label={bi("Chassis (VIN)", "شماره شاسی")} value={v.vin} />
              <Spec label={bi("Stock #", "شماره انبار")} value={v.stock_number} />
            </dl>
            {v.options ? (
              <>
                <SectionHeader title={<Bi en="Options" fa="آپشن‌ها" />} />
                <div className="chips">
                  {String(v.options)
                    .split(/[،,;|]/)
                    .map((o) => o.trim())
                    .filter(Boolean)
                    .map((o) => (
                      <span key={o} className="badge">
                        {o}
                      </span>
                    ))}
                </div>
              </>
            ) : null}
          </Card>

          {Boolean(v.description || v.notes) && (
            <div className="grid grid-2">
              {v.description ? (
                <Card>
                  <SectionHeader title={<Bi en="Description" fa="توضیحات" />} />
                  <p className="prose-block">{String(v.description)}</p>
                </Card>
              ) : null}
              {v.notes ? (
                <Card>
                  <SectionHeader title={<Bi en="Internal notes" fa="یادداشت داخلی" />} />
                  <p className="prose-block">{String(v.notes)}</p>
                </Card>
              ) : null}
            </div>
          )}

          <Card>
            <SectionHeader icon="clock" title={<Bi en="Status history" fa="تاریخچه وضعیت" />} />
            {ctx.history.length === 0 ? (
              <Muted>
                <Bi en="No status changes yet." fa="هنوز تغییری ثبت نشده." />
              </Muted>
            ) : (
              <List variant="timeline">
                {ctx.history.map((h) => (
                  <ListItem key={String(h.id)}>
                    <span className="meta-line">
                      <StatusLabel status={String(h.to_status)} />
                      {h.from_status ? (
                        <>
                          <Bi en="from" fa="از" />
                          <StatusLabel status={String(h.from_status)} />
                        </>
                      ) : null}
                    </span>
                    {h.note ? (
                      <div>
                        <Muted>{historyNote(String(h.note))}</Muted>
                      </div>
                    ) : null}
                  </ListItem>
                ))}
              </List>
            )}
          </Card>
        </div>

        <aside className="side-stack">
          <Card>
            <Button
              variant="secondary"
              to={`/communication?new=1&vehicle=${id}&topic=${encodeURIComponent(
                bi(`Vehicle: ${v.stock_number || v.plate_number || ""}`, `خودرو: ${v.stock_number || v.plate_number || ""}`),
              )}`}
            >
              <Icon name="message" size={14} />
              <Bi en="Message about this vehicle" fa="گفتگو درباره این خودرو" />
            </Button>
          </Card>

          <Card>
            <SectionHeader title={<Bi en="Price" fa="قیمت" />} />
            <div className="price-tag">{money(v.sale_price) || "—"}</div>
            <div className="mini-stats mini-stats--half mt-3">
              <div className="mini-stat">
                <span>
                  <Bi en="Purchase" fa="خرید" />
                </span>
                <strong className="stat-num">
                  {v.purchase_price != null ? tomanText(Number(v.purchase_price)) : "—"}
                </strong>
              </div>
              <div className="mini-stat">
                <span>
                  <Bi en="Margin" fa="حاشیه سود" />
                </span>
                <strong className="stat-num">
                  {margin != null ? tomanText(margin) : "—"}
                </strong>
              </div>
            </div>
          </Card>

          <Card padded={false}>
            <div className="flush-head">
              <SectionHeader
                icon="layers"
                title={<Bi en="Work on this car" fa="کارهای این خودرو" />}
                count={ctx.work_items.length}
              />
            </div>
            {ctx.work_items.length === 0 ? (
              <div className="flush-foot">
                <Muted>
                  <Bi
                    en="No one is working on this car yet. Press “Start selling this car” to involve your team."
                    fa="هنوز کسی روی این خودرو کار نمی‌کند. برای درگیر کردن تیم، «شروع فروش این خودرو» را بزنید."
                  />
                </Muted>
              </div>
            ) : (
              <ul className="rows">
                {ctx.work_items.map((w) => (
                  <li key={String(w.id)} className="row-item">
                    <div className="row-main">
                      <Link to={`/work-items/${w.id}`} className="row-title">
                        {String(w.title)}
                      </Link>
                      {w.status ? (
                        <span className="row-meta">
                          <StatusLabel status={String(w.status)} />
                        </span>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <SectionHeader
              icon="flag"
              title={<Bi en="Follow-ups" fa="پیگیری‌ها" />}
              count={ctx.cases.length}
            />
            {ctx.cases.length === 0 ? (
              <Muted>
                <Bi en="No follow-ups yet." fa="هنوز پیگیری‌ای نیست." />
              </Muted>
            ) : (
              <List>
                {ctx.cases.map((c) => (
                  <ListItem key={String(c.id)}>
                    <span>
                      {String(c.subject)}
                    </span>
                  </ListItem>
                ))}
              </List>
            )}
          </Card>
        </aside>
      </div>
    </>
  );
}

