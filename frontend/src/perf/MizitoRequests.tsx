import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError } from "../api";
import { Button, Card, ErrorMessage, Muted, SectionHeader, Segmented } from "../components/ui";
import { DateText } from "../components/DateText";
import { Bi } from "../i18n";
import { MIZITO_CHANNEL, MIZITO_REQUEST_KIND, perfApi, toman, type MizitoRequest } from "./api";
import { needsClamp } from "../lib/text";
import { OutcomePop, type Outcome } from "./bits";
import { mizitoRequestsQuery } from "./mizitoQueries";

/** برچسب کوتاه روی هر کارت؛ توضیح کامل یک بار بالای فهرست و در title چیپ است. */
const REQUEST_STATUS: Record<string, { label: string; hint: string; tone: "warn" | "ok" | "danger" }> = {
  new: { label: "جدید", hint: "هنوز تصمیم نگرفته‌اید", tone: "warn" },
  duplicate: { label: "تکراری", hint: "همین متن قبلاً آمده", tone: "warn" },
  approved: { label: "ساخته شد", hint: "کمپین از این درخواست ساخته شده", tone: "ok" },
  rejected: { label: "رد شد", hint: "کنار گذاشته شده", tone: "danger" },
};

type Filter = "new" | "approved" | "rejected" | "all";

const FILTERS: Array<{ id: Filter; label: string }> = [
  { id: "new", label: "باز" },
  { id: "approved", label: "ساخته‌شده" },
  { id: "rejected", label: "ردشده" },
  { id: "all", label: "همه" },
];

function requestStatus(status: string) {
  return REQUEST_STATUS[status] || { label: status, hint: `وضعیت ناشناخته: ${status}`, tone: "warn" as const };
}

const SHOWN = 6;

/** دلیل خطا به فارسی روشن؛ ۴۰۴ اینجا یعنی بک‌اند هنوز مسیرهای تازه را ندارد. */
function requestsError(error: unknown, action: string): string {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return `${action} ناموفق بود: مسیر «درخواست‌های میزیتو» روی سرور پیدا نشد (۴۰۴). احتمالاً بک‌اند پس از به‌روزرسانی کد دوباره راه‌اندازی نشده است.`;
    }
    if (error.status === 403) return `${action} ناموفق بود: دسترسی پرفورمنس برای این کار لازم است (۴۰۳).`;
    return `${action} ناموفق بود (${error.status}): ${error.detail || error.message}`;
  }
  const text = error instanceof Error ? error.message : String(error ?? "");
  if (/failed to fetch|network/i.test(text)) return `${action} ناموفق بود: به سرور پنل وصل نشدیم.`;
  return `${action} ناموفق بود: ${text || "خطای ناشناخته"}`;
}

/** درخواست‌های تبلیغ که از میزیتو خوانده شده‌اند. هیچ‌کدام خودکار کمپین نمی‌شود؛ «ساخت کمپین» فرم را باز می‌کند. */
export function MizitoRequestsBlock({ onCreate }: { onCreate: (row: MizitoRequest) => void }) {
  const qc = useQueryClient();
  const [all, setAll] = useState(false);
  const [filter, setFilter] = useState<Filter>("new");
  const [notice, setNotice] = useState("");
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const list = useQuery(mizitoRequestsQuery(filter));
  const refresh = () => qc.invalidateQueries({ queryKey: ["perf", "mizito", "requests"] });
  const check = useMutation({
    mutationFn: perfApi.checkMizitoRequests,
    onSuccess: (result) => {
      if (!result.checked) {
        const detail = `میزیتو خوانده نشد: ${result.reason || "دلیل نامشخص"}`;
        setNotice(detail);
        setOutcome({ ok: false, title: "بررسی درخواست‌ها ناموفق بود", detail });
      } else {
        setNotice("");
        const detail = result.added
          ? `${toman(result.added)} درخواست تازه از گفتگوها و بردها پیدا شد و به فهرست باز اضافه شد.`
          : "گفتگوها و بردها خوانده شدند. نسبت به بررسی قبلی درخواست تازه‌ای نبود.";
        setOutcome({ ok: true, title: "بررسی درخواست‌ها موفق بود", detail });
      }
      refresh();
    },
    onError: (error: unknown) => {
      const detail = requestsError(error, "بررسی میزیتو");
      setNotice(detail);
      setOutcome({ ok: false, title: "بررسی درخواست‌ها ناموفق بود", detail });
    },
  });
  const reject = useMutation({
    mutationFn: (id: string) => perfApi.rejectMizitoRequest(id),
    onSuccess: () => {
      refresh();
      setOutcome({
        ok: true,
        title: "رد درخواست موفق بود",
        detail: "درخواست کنار گذاشته شد. در فیلتر «ردشده» می‌ماند و دیگر در فهرست باز نیست.",
      });
    },
    onError: (error: unknown) => setOutcome({ ok: false, title: "رد درخواست ناموفق بود", detail: requestsError(error, "رد") }),
  });

  // باکس همیشه دیده می‌شود: در حال خواندن، خطا و خالی هر کدام پیام خودشان را دارند.
  const rows = list.data?.requests ?? [];
  const shown = all ? rows : rows.slice(0, SHOWN);
  return (
    <Card>
      <SectionHeader
        icon="megaphone"
        title={<Bi en="New requests from Mizito" fa="درخواست‌های جدید از میزیتو" />}
        count={rows.length}
        hint={
          <Bi
            en="Ad requests read (read-only) from the tracked Mizito chats and boards. Nothing becomes a campaign until you create it; nothing is written to Mizito."
            fa="درخواست‌های تبلیغ که فقط‌خواندنی از گفتگوها و بردهای پیگیری‌شدهٔ میزیتو خوانده شده‌اند. هیچ‌کدام تا شما نسازید کمپین نمی‌شود و چیزی در میزیتو نوشته نمی‌شود."
          />
        }
        action={
          <Button type="button" variant="secondary" onClick={() => check.mutate()} disabled={check.isPending}>
            {check.isPending ? "در حال بررسی…" : "بررسی دوباره"}
          </Button>
        }
      />
      <Segmented<Filter>
        ariaLabel="وضعیت درخواست‌ها"
        value={filter}
        onChange={(next) => { setFilter(next); setAll(false); }}
        items={FILTERS.map((item) => ({
          key: item.id,
          label: item.label,
          count: list.data
            ? item.id === "new"
              ? (list.data.counts.new ?? 0) + (list.data.counts.duplicate ?? 0)
              : item.id === "all"
                ? Object.values(list.data.counts ?? {}).reduce((sum, value) => sum + value, 0)
                : list.data.counts[item.id] ?? 0
            : undefined,
        }))}
      />
      <Muted as="p">
        باز یعنی هنوز تصمیم نگرفته‌اید (جدید یا تکراری). ساخته‌شده یعنی کمپین از آن درخواست ساخته شده. ردشده کنار گذاشته شده و دوباره کمپین نمی‌شود.
      </Muted>
      {notice ? <ErrorMessage message={notice} friendly={false} /> : null}
      {list.error ? <ErrorMessage message={requestsError(list.error, "خواندن درخواست‌ها")} friendly={false} /> : null}
      {list.data ? (
        <Muted as="p">
          {list.data.checked_at ? (
            <>
              آخرین بررسی: <DateText value={list.data.checked_at} withTime />
            </>
          ) : (
            "هنوز بررسی نشده است."
          )}
        </Muted>
      ) : null}
      {!list.data ? (
        list.isFetching ? <Muted as="p">در حال خواندن درخواست‌ها…</Muted> : null
      ) : rows.length === 0 ? (
        <Muted as="p">درخواست تازه‌ای نیست.</Muted>
      ) : (
        <ul className="mizito-requests">
          {shown.map((row) => (
            <RequestItem
              key={row.id}
              row={row}
              busy={reject.isPending}
              onCreate={() => onCreate(row)}
              onReject={() => reject.mutate(row.id)}
            />
          ))}
        </ul>
      )}
      {rows.length > SHOWN ? (
        <button type="button" className="kpi-more" onClick={() => setAll((value) => !value)}>
          {all ? "فقط چند تای اول" : `نمایش همه (${toman(rows.length)})`}
        </button>
      ) : null}
      <OutcomePop outcome={outcome} onClose={() => setOutcome(null)} />
    </Card>
  );
}

function bits(row: MizitoRequest): string[] {
  const fields = row.fields ?? {};
  const offer = fields.offer ?? {};
  const out: string[] = [];
  if (offer.no_price) out.push("بدون قیمت");
  if (offer.delivery_days) out.push(`تحویل ${toman(offer.delivery_days)} روز`);
  if (offer.prepayment) out.push(`پیش‌پرداخت ${offer.prepayment}`);
  for (const price of offer.prices ?? []) out.push(price);
  if (offer.installments) out.push("اقساطی");
  if (offer.no_budget_limit) out.push("بدون محدودیت بودجه");
  for (const channel of fields.channels ?? []) out.push(MIZITO_CHANNEL[channel] ?? channel);
  for (const branch of fields.branches ?? []) out.push(`شعبه ${branch}`);
  for (const date of fields.dates ?? []) out.push(date);
  return out;
}

/** متن درخواست تا سه خط؛ بلندتر با «بیشتر» باز می‌شود. */
function Excerpt({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = needsClamp(text);
  return (
    <>
      <p className={long && !open ? "mizito-request-excerpt is-clamped" : "mizito-request-excerpt"}>{text}</p>
      {long ? (
        <button type="button" className="kpi-more" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? "کمتر" : "بیشتر"}
        </button>
      ) : null}
    </>
  );
}

function RequestItem({ row, busy, onCreate, onReject }: { row: MizitoRequest; busy: boolean; onCreate: () => void; onReject: () => void }) {
  const fields = row.fields ?? {};
  const subject = [fields.brand, ...(fields.cars ?? [])].filter(Boolean).join(" · ") || fields.card_title || "بدون برند";
  const matched = row.matched_campaign;
  const source = row.source_title || (row.source_kind === "task" ? "کال سنتر" : "میزیتو");
  const status = requestStatus(row.status);
  const chips = bits(row);
  return (
    <li className="mizito-request">
      <div className="mizito-request-head">
        <span className={`perf-chip mizito-kind mizito-kind-${row.kind}`}>{MIZITO_REQUEST_KIND[row.kind] ?? row.kind}</span>
        <span className={`badge ${status.tone} mizito-status`} title={status.hint}>{status.label}</span>
        <strong>{subject}</strong>
        {fields.code ? <span className="perf-chip">کد {fields.code}</span> : null}
        <span className="muted mizito-request-meta">
          {source}
          {row.happened_at ? (
            <>
              {" · "}
              <DateText value={row.happened_at} withTime />
            </>
          ) : null}
        </span>
      </div>
      {chips.length ? (
        <span className="perf-chips">
          {chips.map((item, index) => (
            <span key={`${item}-${index}`} className="perf-chip">{item}</span>
          ))}
        </span>
      ) : null}
      {row.excerpt ? <Excerpt text={row.excerpt} /> : null}
      {row.kind === "stop" ? (
        <Muted as="p">
          {matched ? (
            <>
              درخواست توقف برای <Link to={`/perf/campaigns/${matched.id}`}>{matched.code}</Link> — پنل دکمهٔ توقف کمپین ندارد؛ فقط برای اطلاع.
            </>
          ) : (
            "درخواست توقف؛ کمپین متناظری در پنل پیدا نشد. فقط برای اطلاع."
          )}
        </Muted>
      ) : matched ? (
        <Muted as="p">
          کد {matched.code} در پنل هست: <Link to={`/perf/campaigns/${matched.id}`}>{matched.title}</Link>
        </Muted>
      ) : null}
      <div className="row mizito-request-actions">
        {row.kind === "stop" ? null : matched ? (
          <Button variant="secondary" className="btn-sm" to={`/perf/campaigns/${matched.id}`}>باز کردن {matched.code}</Button>
        ) : (
          <Button type="button" className="btn-sm" onClick={onCreate}>
            ساخت کمپین
          </Button>
        )}
        <Button type="button" variant="secondary" className="btn-sm" onClick={onReject} disabled={busy}>
          {row.kind === "stop" ? "دیدم، بستن" : "رد"}
        </Button>
      </div>
    </li>
  );
}
