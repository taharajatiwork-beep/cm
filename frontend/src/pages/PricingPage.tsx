import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Field,
  Input,
  LoadingState,
  PageHeader,
  SectionHeader,
  Select,
  StatCard,
  Table,
} from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { DateText } from "../components/DateText";
import { SheetsSyncCard } from "../components/SheetsSyncCard";
import { Bi, useBi } from "../i18n";

type Slot = {
  id: string;
  vehicle_id: string;
  brand?: string;
  model?: string;
  color?: string;
  post_at?: string;
  status: string;
  confirmed_price?: number | null;
  sale_price?: number | null;
};

type Stock = {
  id: string;
  brand: string;
  model: string;
  color?: string;
  year?: number;
  status: string;
  sale_price?: number | null;
  delivery_note?: string;
  price_updated_at?: string | null;
  price_updated_by?: string | null;
  stock_updated_at?: string | null;
  stock_updated_by?: string | null;
};

type PostFilter = "all" | "waiting" | "ready";

const STATUS: Record<string, [string, string]> = {
  requested: ["Waiting", "منتظر تأیید"],
  confirmed: ["Confirmed", "تأیید شد"],
  needs_recheck: ["Price changed", "قیمت عوض شد"],
  posted: ["Posted", "منتشر شد"],
  cancelled: ["Cancelled", "لغو"],
};

function millions(amount: unknown): string {
  if (amount == null || amount === "") return "—";
  const n = Number(amount);
  if (!Number.isFinite(n)) return "—";
  if (Math.abs(n) >= 1_000_000) return `${Math.round(n / 1_000_000).toLocaleString("fa-IR")} میلیون`;
  return n.toLocaleString("fa-IR");
}

function hoursAgo(iso?: string | null): string {
  if (!iso) return "ثبت نشده";
  const hours = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 3_600_000));
  if (hours < 1) return "همین ساعت";
  return `${hours.toLocaleString("fa-IR")} ساعت پیش`;
}

function stale(iso?: string | null): boolean {
  if (!iso) return true;
  return Date.now() - new Date(iso).getTime() > 24 * 3_600_000;
}

function clockDigits(raw: string, max: number): string {
  const latin = raw
    .replace(/[۰-۹]/g, (digit) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)))
    .replace(/\D/g, "")
    .slice(0, 2);
  if (!latin) return "";
  return Number(latin) > max ? String(max) : latin;
}

function padClock(raw: string, max: number): string {
  const digits = clockDigits(raw, max);
  const n = digits ? Number(digits) : 0;
  return String(Math.min(max, Math.max(0, n))).padStart(2, "0");
}

function tomanFromMillionInput(raw: string): number | null {
  const latin = raw
    .replace(/[,،\s]/g, "")
    .replace(/[۰-۹]/g, (digit) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)));
  if (!latin) return null;
  const million = Number(latin);
  if (!Number.isFinite(million) || million <= 0) return null;
  return million * 1_000_000;
}

function waitingStatus(status: string): boolean {
  return status === "requested" || status === "needs_recheck";
}

export function PricingPage() {
  const { has } = useAuth();
  const bi = useBi();
  const toast = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canPrice = has("price.write");
  const canRequest = has("campaign.write");
  const canPeople = has("user.read");
  const [vehicleId, setVehicleId] = useState("");
  const [hour, setHour] = useState("16");
  const [minute, setMinute] = useState("00");
  const [fresh, setFresh] = useState<Record<string, string>>({});
  const [postFilter, setPostFilter] = useState<PostFilter>("all");
  const [stockFilter, setStockFilter] = useState<"stock" | "stale" | "all">("stock");

  const board = useQuery({
    queryKey: ["pricing-board"],
    queryFn: () => api.pricing.board(),
  });
  const people = useQuery({
    queryKey: ["people"],
    queryFn: () => api.people.list(),
    enabled: canPeople,
  });
  const names = useMemo(() => {
    const map = new Map<string, string>();
    for (const person of people.data ?? []) map.set(String(person.id), String(person.full_name || person.email || ""));
    return map;
  }, [people.data]);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["pricing-board"] });
    void qc.invalidateQueries({ queryKey: ["vehicles"] });
  };

  const request = useMutation({
    mutationFn: () => {
      const when = new Date();
      when.setHours(Number(padClock(hour, 23)), Number(padClock(minute, 59)), 0, 0);
      return api.pricing.requestSlot({ vehicle_id: vehicleId, post_at: when.toISOString(), slot_type: "video" });
    },
    onSuccess: () => {
      toast(bi("Request sent to finance", "درخواست برای مالی فرستاده شد"));
      setVehicleId("");
      refresh();
    },
  });
  const confirm = useMutation({
    mutationFn: (body: { id: string; amount?: number | null }) => api.pricing.confirm(body.id, body.amount),
    onSuccess: () => {
      toast(bi("Price confirmed", "قیمت تأیید شد"));
      refresh();
    },
  });
  const posted = useMutation({
    mutationFn: (id: string) => api.pricing.posted(id),
    onSuccess: () => {
      toast(bi("Marked as posted", "منتشرشده ثبت شد"));
      refresh();
    },
  });

  const data = board.data;
  const slots = ((data?.slots ?? []) as Slot[]).slice().sort((a, b) => String(a.post_at).localeCompare(String(b.post_at)));
  const stock = (data?.vehicles ?? []) as Stock[];
  const waiting = slots.filter((slot) => waitingStatus(slot.status));
  const ready = slots.filter((slot) => slot.status === "confirmed" || slot.status === "posted");
  const staleCars = stock.filter((car) => car.status === "IN_STOCK" && stale(car.price_updated_at));
  const visibleSlots =
    postFilter === "waiting" ? waiting : postFilter === "ready" ? ready : slots;
  const visibleStock = stock.filter((car) => {
    if (stockFilter === "all") return true;
    if (stockFilter === "stale") return car.status === "IN_STOCK" && stale(car.price_updated_at);
    return car.status === "IN_STOCK";
  });

  function person(id?: string | null) {
    if (!id) return null;
    const name = names.get(id);
    if (!name) return null;
    if (!canPeople) return <span>{name}</span>;
    return (
      <Link to={`/people/${id}`} onClick={(e) => e.stopPropagation()}>
        {name}
      </Link>
    );
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Price and posts" fa="قیمت و پست‌ها" />}
        description={
          <Bi
            en="Marketing asks for a price at a time. Finance confirms it. Then marketing can publish."
            fa="مارکتینگ برای یک ساعت قیمت می‌خواهد. مالی همان را تأیید می‌کند یا قیمت تازه می‌گذارد. بعد مارکتینگ منتشر می‌کند."
          />
        }
      />
      <SheetsSyncCard />
      <ErrorMessage
        error={[board.error, request.error, confirm.error, posted.error]
          .filter(Boolean)
          .map((err) => (err instanceof Error ? err.message : String(err)))
          .join(" · ")}
      />
      {board.isLoading ? (
        <LoadingState />
      ) : (
        <>
          <div className="kpi-row kpi-row--3">
            <StatCard
              icon="alert"
              tone={waiting.length > 0 ? "warn" : "ok"}
              label={<Bi en="Need a price" fa="منتظر قیمت" />}
              value={waiting.length}
              hint={<Bi en="open just these" fa="فقط همین‌ها را نشان بده" />}
              onClick={() => setPostFilter(postFilter === "waiting" ? "all" : "waiting")}
            />
            <StatCard
              icon="check"
              tone="ok"
              label={<Bi en="Ready today" fa="امروز آماده‌اند" />}
              value={ready.length}
              hint={<Bi en="confirmed or posted" fa="تأییدشده یا منتشرشده" />}
              onClick={() => setPostFilter(postFilter === "ready" ? "all" : "ready")}
            />
            <StatCard
              icon="car"
              tone={staleCars.length > 0 ? "warn" : "neutral"}
              label={<Bi en="Old prices" fa="قیمت قدیمی" />}
              value={staleCars.length}
              hint={<Bi en="not updated in 24 hours" fa="بیش از ۲۴ ساعت عوض نشده" />}
              onClick={() => setStockFilter(stockFilter === "stale" ? "stock" : "stale")}
            />
          </div>

          {canRequest ? (
            <Card className="price-ask">
              <SectionHeader
                icon="megaphone"
                title={<Bi en="Ask for a price" fa="درخواست قیمت" />}
                hint={
                  <Bi
                    en="Choose the car and the post time. Finance confirms the price, then you can publish."
                    fa="خودرو و ساعت پست را انتخاب کنید. مالی قیمت را تأیید می‌کند و بعد می‌توانید منتشر کنید."
                  />
                }
              />
              <form
                className="price-ask-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (vehicleId) request.mutate();
                }}
              >
                <Field label={<Bi en="Vehicle" fa="خودرو" />}>
                  <Select value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} required>
                    <option value="">{bi("Choose a car", "یک خودرو انتخاب کنید")}</option>
                    {stock
                      .filter((car) => car.status === "IN_STOCK")
                      .map((car) => (
                        <option key={car.id} value={car.id}>
                          {car.brand} {car.model}
                          {car.color ? ` ${car.color}` : ""}
                        </option>
                      ))}
                  </Select>
                </Field>
                <Field className="price-ask-clock" label={<Bi en="Post time" fa="ساعت پست" />}>
                  <span className="price-ask-time">
                    <span className="price-ask-part">
                      <Input
                        value={hour}
                        inputMode="numeric"
                        maxLength={2}
                        aria-label={bi("Hour", "ساعت")}
                        onChange={(e) => setHour(clockDigits(e.target.value, 23))}
                        onBlur={() => setHour((value) => padClock(value, 23))}
                      />
                      <span className="price-ask-caption">
                        <Bi en="Hour" fa="ساعت" />
                      </span>
                    </span>
                    <span className="price-ask-colon" aria-hidden>
                      :
                    </span>
                    <span className="price-ask-part">
                      <Input
                        id="post-minute"
                        value={minute}
                        inputMode="numeric"
                        maxLength={2}
                        aria-label={bi("Minute", "دقیقه")}
                        onChange={(e) => setMinute(clockDigits(e.target.value, 59))}
                        onBlur={() => setMinute((value) => padClock(value, 59))}
                      />
                      <span className="price-ask-caption">
                        <Bi en="Minute" fa="دقیقه" />
                      </span>
                    </span>
                  </span>
                </Field>
                <Button type="submit" disabled={!vehicleId || request.isPending}>
                  <Bi en="Send to finance" fa="بفرست برای مالی" />
                </Button>
              </form>
            </Card>
          ) : null}

          <section>
            <SectionHeader
              icon="megaphone"
              title={<Bi en="Today’s posts" fa="پست‌های امروز" />}
              count={visibleSlots.length}
              hint={
                <Bi
                  en="Click a row to open the car. The buttons on the right stay on this page."
                  fa="روی ردیف بزنید تا خودرو باز شود. دکمه‌های سمت چپ همین‌جا می‌مانند."
                />
              }
            />
            <Card padded={false}>
              <div className="card-bar">
                <div className="chips">
                  {(
                    [
                      ["all", "All", "همه", slots.length],
                      ["waiting", "Waiting", "منتظر", waiting.length],
                      ["ready", "Ready", "آماده", ready.length],
                    ] as const
                  ).map(([key, en, fa, count]) => (
                    <button
                      key={key}
                      type="button"
                      className={`chip${postFilter === key ? " active" : ""}`}
                      onClick={() => setPostFilter(key)}
                    >
                      {bi(en, fa)}
                      <span className="chip-count">{count}</span>
                    </button>
                  ))}
                </div>
              </div>
              {visibleSlots.length === 0 ? (
                <EmptyState
                  titleEn="Nothing in this list"
                  titleFa="در این فهرست چیزی نیست"
                  bodyEn="Ask finance for a price, or switch the filter."
                  bodyFa="از مالی قیمت بخواهید، یا فیلتر را عوض کنید."
                />
              ) : (
                <Table
                  rows={visibleSlots}
                  rowKey={(slot) => slot.id}
                  onRowClick={(slot) => navigate(`/vehicles/${slot.vehicle_id}`)}
                  columns={[
                    {
                      key: "time",
                      header: <Bi en="Date and time" fa="تاریخ و ساعت" />,
                      render: (slot) =>
                        slot.post_at ? <DateText value={slot.post_at} withTime className="num" /> : <span>—</span>,
                    },
                    {
                      key: "car",
                      header: <Bi en="Vehicle" fa="خودرو" />,
                      render: (slot) => (
                        <Link to={`/vehicles/${slot.vehicle_id}`} onClick={(e) => e.stopPropagation()}>
                          <strong>
                            {slot.brand} {slot.model}
                          </strong>
                          {slot.color ? <div className="cell-sub">{slot.color}</div> : null}
                        </Link>
                      ),
                    },
                    {
                      key: "price",
                      header: <Bi en="Price" fa="قیمت" />,
                      render: (slot) => <span className="num">{millions(slot.confirmed_price ?? slot.sale_price)}</span>,
                    },
                    {
                      key: "status",
                      header: <Bi en="Status" fa="وضعیت" />,
                      render: (slot) => {
                        const copy = STATUS[slot.status];
                        return (
                          <Badge tone={waitingStatus(slot.status) ? "warn" : "ok"}>
                            {copy ? <Bi en={copy[0]} fa={copy[1]} /> : slot.status}
                          </Badge>
                        );
                      },
                    },
                    {
                      key: "act",
                      header: <Bi en="Do" fa="کار" />,
                      render: (slot) => (
                        <div className="pricing-actions" onClick={(e) => e.stopPropagation()}>
                          {canPrice && waitingStatus(slot.status) ? (
                            <>
                              <Input
                                value={fresh[slot.id] || ""}
                                onChange={(e) => setFresh((prev) => ({ ...prev, [slot.id]: e.target.value }))}
                                placeholder={bi("New price, million", "قیمت تازه، میلیون")}
                                inputMode="numeric"
                              />
                              <Button
                                onClick={() => {
                                  const typed = tomanFromMillionInput(fresh[slot.id] || "");
                                  confirm.mutate(
                                    { id: slot.id, amount: typed },
                                    { onSuccess: () => setFresh((prev) => ({ ...prev, [slot.id]: "" })) },
                                  );
                                }}
                              >
                                {fresh[slot.id] ? (
                                  <Bi en="Save on the car" fa="ثبت روی خودرو" />
                                ) : (
                                  <Bi en="Confirm this price" fa="تأیید همین قیمت" />
                                )}
                              </Button>
                            </>
                          ) : null}
                          {canRequest && slot.status === "confirmed" ? (
                            <Button variant="secondary" onClick={() => posted.mutate(slot.id)}>
                              <Bi en="Posted" fa="منتشر شد" />
                            </Button>
                          ) : null}
                        </div>
                      ),
                    },
                  ]}
                />
              )}
            </Card>
          </section>

          <section>
            <SectionHeader
              icon="car"
              title={<Bi en="Stock" fa="موجودی" />}
              count={visibleStock.length}
              hint={
                <Bi
                  en="Click a car to open it. A price older than 24 hours is marked old."
                  fa="روی خودرو بزنید تا صفحه‌اش باز شود. قیمتی که ۲۴ ساعت عوض نشده، قدیمی است."
                />
              }
              action={
                <Button variant="ghost" to="/vehicles">
                  <Bi en="All vehicles" fa="همهٔ خودروها" />
                </Button>
              }
            />
            <Card padded={false}>
              <div className="card-bar">
                <div className="chips">
                  {(
                    [
                      ["stock", "In stock", "موجود"],
                      ["stale", "Old price", "قیمت قدیمی"],
                      ["all", "All", "همه"],
                    ] as const
                  ).map(([key, en, fa]) => (
                    <button
                      key={key}
                      type="button"
                      className={`chip${stockFilter === key ? " active" : ""}`}
                      onClick={() => setStockFilter(key)}
                    >
                      {bi(en, fa)}
                    </button>
                  ))}
                </div>
              </div>
              <Table
                rows={visibleStock}
                rowKey={(row) => row.id}
                onRowClick={(row) => navigate(`/vehicles/${row.id}`)}
                empty={
                  <EmptyState
                    titleEn="No cars in this list"
                    titleFa="خودرویی در این فهرست نیست"
                    bodyEn="Switch the filter, or add cars from the vehicles page."
                    bodyFa="فیلتر را عوض کنید، یا از صفحهٔ خودروها موجودی اضافه کنید."
                  />
                }
                columns={[
                  {
                    key: "car",
                    header: <Bi en="Vehicle" fa="خودرو" />,
                    render: (row) => (
                      <Link to={`/vehicles/${row.id}`} onClick={(e) => e.stopPropagation()}>
                        <strong>
                          {row.brand} {row.model}
                        </strong>
                        <div className="cell-sub">
                          {[row.color, row.year, row.delivery_note].filter(Boolean).join(" · ") || "—"}
                        </div>
                      </Link>
                    ),
                  },
                  {
                    key: "price",
                    header: <Bi en="Price" fa="قیمت" />,
                    render: (row) => (
                      <span className="num">
                        {millions(row.sale_price)}{" "}
                        {stale(row.price_updated_at) ? (
                          <Badge tone="warn">
                            <Bi en="Old" fa="قدیمی" />
                          </Badge>
                        ) : null}
                      </span>
                    ),
                  },
                  {
                    key: "price_at",
                    header: <Bi en="Price updated" fa="تغییر قیمت" />,
                    render: (row) => (
                      <span className="cell-sub">
                        {hoursAgo(row.price_updated_at)}
                        {row.price_updated_by ? <> · {person(row.price_updated_by)}</> : null}
                      </span>
                    ),
                  },
                  {
                    key: "stock_at",
                    header: <Bi en="Stock updated" fa="به‌روزرسانی موجودی" />,
                    render: (row) => (
                      <span className="cell-sub">
                        {hoursAgo(row.stock_updated_at)}
                        {row.stock_updated_by ? <> · {person(row.stock_updated_by)}</> : null}
                      </span>
                    ),
                  },
                ]}
              />
            </Card>
          </section>
        </>
      )}
    </>
  );
}
