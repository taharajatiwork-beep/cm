import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Badge,
  Button,
  Card,
  Dialog,
  EmptyState,
  ErrorMessage,
  Field,
  Input,
  LoadingState,
  PageHeader,
  SectionHeader,
  Table,
} from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { DateText } from "../components/DateText";
import { SheetsSyncCard } from "../components/SheetsSyncCard";
import { faNum } from "../fa";
import { Bi, useBi } from "../i18n";
import { useVehicleLabel } from "../lib/vehicleLabels";

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

function carLabel(car?: { brand: string; model: string; color?: string | null }): string {
  if (!car) return "";
  return `${car.brand} ${car.model}${car.color ? ` ${car.color}` : ""}`;
}

function waitingStatus(status: string): boolean {
  return status === "requested" || status === "needs_recheck";
}

function defaultPostFilter(canPrice: boolean, canRequest: boolean): PostFilter {
  if (canPrice && !canRequest) return "waiting";
  if (canRequest && !canPrice) return "ready";
  return "all";
}

export function PricingPage() {
  const { has } = useAuth();
  const bi = useBi();
  const vehicleLabel = useVehicleLabel();
  const toast = useToast();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const qc = useQueryClient();
  const canPrice = has("price.approve") || has("price.write");
  const canRequest = has("campaign.write");
  const [vehicleIds, setVehicleIds] = useState<string[]>([]);
  const [carsOpen, setCarsOpen] = useState(false);
  const carsRef = useRef<HTMLDivElement>(null);
  const [hour, setHour] = useState("16");
  const [minute, setMinute] = useState("00");
  const postsParam = searchParams.get("posts");
  const [postFilter, setPostFilter] = useState<PostFilter>(() => {
    if (postsParam === "waiting" || postsParam === "ready" || postsParam === "all") return postsParam;
    return defaultPostFilter(canPrice, canRequest);
  });
  const [confirmSlot, setConfirmSlot] = useState<Slot | null>(null);
  const [confirmAmount, setConfirmAmount] = useState("");
  const [askOpen, setAskOpen] = useState(false);
  const askTitleId = useId();
  const confirmTitleId = useId();

  useEffect(() => {
    const p = searchParams.get("posts");
    if (p === "waiting" || p === "ready" || p === "all") setPostFilter(p);
  }, [searchParams]);

  function setPostFilterUrl(next: PostFilter) {
    setPostFilter(next);
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "all") params.delete("posts");
        else params.set("posts", next);
        return params;
      },
      { replace: true },
    );
  }

  const board = useQuery({
    queryKey: ["pricing-board"],
    queryFn: () => api.pricing.board(),
  });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["pricing-board"] });
    void qc.invalidateQueries({ queryKey: ["vehicles"] });
  };

  const request = useMutation({
    mutationFn: () => {
      const when = new Date();
      when.setHours(Number(padClock(hour, 23)), Number(padClock(minute, 59)), 0, 0);
      return api.pricing.requestSlot({
        vehicle_ids: vehicleIds,
        post_at: when.toISOString(),
        slot_type: "video",
      });
    },
    onSuccess: (result) => {
      const count = Array.isArray(result) ? result.length : 1;
      toast(
        bi(
          count === 1 ? "Request sent to finance" : `${count} requests sent to finance`,
          count === 1 ? "درخواست برای مالی فرستاده شد" : `${count.toLocaleString("fa-IR")} درخواست برای مالی فرستاده شد`,
        ),
      );
      setVehicleIds([]);
      setCarsOpen(false);
      setAskOpen(false);
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
  useEffect(() => {
    if (!carsOpen) return;
    const onPointer = (event: MouseEvent) => {
      if (!carsRef.current?.contains(event.target as Node)) setCarsOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [carsOpen]);

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
  const inStock = stock
    .filter((car) => car.status === "IN_STOCK")
    .slice()
    .sort((a, b) => carLabel(a).localeCompare(carLabel(b), "fa"));
  const waiting = slots.filter((slot) => waitingStatus(slot.status));
  const ready = slots.filter((slot) => slot.status === "confirmed" || slot.status === "posted");
  const staleCars = stock.filter((car) => car.status === "IN_STOCK" && stale(car.price_updated_at));
  const visibleSlots =
    postFilter === "waiting" ? waiting : postFilter === "ready" ? ready : slots;

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
        actions={
          canRequest ? (
            <Button type="button" onClick={() => setAskOpen(true)}>
              <Bi en="Ask for a price" fa="درخواست قیمت" />
            </Button>
          ) : undefined
        }
      />
      <SheetsSyncCard />
      <ErrorMessage
        error={board.error ?? request.error ?? confirm.error ?? posted.error ?? null}
      />
      {board.isLoading ? (
        <LoadingState />
      ) : (
        <>
          {canRequest && askOpen ? (
            <Dialog
              onClose={() => setAskOpen(false)}
              className="form-pop"
              labelledBy={askTitleId}
              closeLabel={bi("Close", "بستن")}
              busy={request.isPending}
            >
            <div className="price-ask stack">
              <SectionHeader
                icon="megaphone"
                title={<span id={askTitleId}><Bi en="Ask for a price" fa="درخواست قیمت" /></span>}
                hint={
                  <Bi
                    en="Choose one or more cars and the post time. Finance confirms each price, then you can publish."
                    fa="یک یا چند خودرو و ساعت پست را انتخاب کنید. مالی قیمت هر کدام را تأیید می‌کند و بعد می‌توانید منتشر کنید."
                  />
                }
              />
              <form
                className="price-ask-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (vehicleIds.length) request.mutate();
                }}
              >
                <Field
                  label={
                    <>
                      <Bi en="Vehicles" fa="خودروها" />
                      {vehicleIds.length > 0 ? (
                        <span className="muted"> · {vehicleIds.length.toLocaleString("fa-IR")}</span>
                      ) : null}
                    </>
                  }
                >
                  <div className="price-ask-cars" ref={carsRef}>
                    <button
                      type="button"
                      className="control price-ask-cars-btn"
                      aria-expanded={carsOpen}
                      onClick={() => setCarsOpen((open) => !open)}
                    >
                      {vehicleIds.length === 0
                        ? bi("Choose one or more cars", "یک یا چند خودرو")
                        : vehicleIds.length === 1
                          ? carLabel(stock.find((car) => car.id === vehicleIds[0]))
                          : bi(
                              `${vehicleIds.length} cars`,
                              `${vehicleIds.length.toLocaleString("fa-IR")} خودرو`,
                            )}
                    </button>
                    {carsOpen ? (
                      <div className="price-ask-cars-panel">
                        {inStock.length === 0 ? (
                          <p className="help-text">
                            <Bi en="No car is in stock." fa="خودروی موجودی نیست." />
                          </p>
                        ) : (
                          <ul className="price-ask-cars-list">
                            {inStock.map((car) => {
                              const on = vehicleIds.includes(car.id);
                              return (
                                <li key={car.id}>
                                  <label className={`price-ask-car${on ? " is-on" : ""}`}>
                                    <input
                                      type="checkbox"
                                      checked={on}
                                      onChange={() =>
                                        setVehicleIds((current) =>
                                          current.includes(car.id)
                                            ? current.filter((id) => id !== car.id)
                                            : [...current, car.id],
                                        )
                                      }
                                    />
                                    <span>{carLabel(car)}</span>
                                  </label>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                      </div>
                    ) : null}
                  </div>
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
                <Button type="submit" disabled={vehicleIds.length === 0 || request.isPending}>
                  <Bi en="Send to finance" fa="بفرست برای مالی" />
                </Button>
              </form>
            </div>
            </Dialog>
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
                      onClick={() => setPostFilterUrl(key)}
                    >
                      {bi(en, fa)}
                      <span className="chip-count">{faNum(count)}</span>
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
                            {vehicleLabel(slot.brand)} {vehicleLabel(slot.model)}
                          </strong>
                          {slot.color ? <div className="cell-sub">{vehicleLabel(slot.color)}</div> : null}
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
                            <Button
                              type="button"
                              onClick={() => {
                                setConfirmSlot(slot);
                                setConfirmAmount("");
                              }}
                            >
                              <Bi en="Confirm price" fa="تأیید قیمت" />
                            </Button>
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

          <Card className="stack">
            <SectionHeader
              icon="car"
              title={<Bi en="Stock and prices" fa="موجودی و قیمت‌ها" />}
              hint={
                <Bi
                  en={`${inStock.length} in stock${staleCars.length ? ` · ${staleCars.length} with old prices` : ""}. Open vehicles to update prices.`}
                  fa={`${inStock.length.toLocaleString("fa-IR")} موجود${staleCars.length ? ` · ${staleCars.length.toLocaleString("fa-IR")} با قیمت قدیمی` : ""}. برای به‌روزرسانی قیمت، خودروها را باز کنید.`}
                />
              }
            />
            <Button to="/vehicles">
              <Bi en="Open vehicles" fa="باز کردن خودروها" />
            </Button>
          </Card>

          {confirmSlot && canPrice ? (
            <Dialog
              onClose={() => {
                if (!confirm.isPending) setConfirmSlot(null);
              }}
              className="form-pop"
              labelledBy={confirmTitleId}
              closeLabel={bi("Close", "بستن")}
              busy={confirm.isPending}
              as="form"
              onSubmit={(event) => {
                event.preventDefault();
                const typed = tomanFromMillionInput(confirmAmount);
                confirm.mutate(
                  { id: confirmSlot.id, amount: typed },
                  { onSuccess: () => setConfirmSlot(null) },
                );
              }}
            >
              <SectionHeader
                title={
                  <span id={confirmTitleId}>
                    <Bi en="Confirm price" fa="تأیید قیمت" />
                    {" — "}
                    {vehicleLabel(confirmSlot.brand)} {vehicleLabel(confirmSlot.model)}
                  </span>
                }
              />
              <Field
                label={
                  <Bi
                    en="New price in million (leave empty to keep current)"
                    fa="قیمت تازه به میلیون (خالی = همان قیمت فعلی)"
                  />
                }
              >
                <Input
                  value={confirmAmount}
                  onChange={(e) => setConfirmAmount(e.target.value)}
                  placeholder={bi("Optional", "اختیاری")}
                  inputMode="numeric"
                />
              </Field>
              <p className="muted num">
                {bi("Current", "فعلی")}: {millions(confirmSlot.confirmed_price ?? confirmSlot.sale_price)}
              </p>
              <Button type="submit" disabled={confirm.isPending}>
                <Bi en="Confirm" fa="تأیید" />
              </Button>
            </Dialog>
          ) : null}
        </>
      )}
    </>
  );
}
