import { useId, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Dialog, List, ListItem, Muted, SectionHeader, TitleCode } from "../components/ui";
import { DateText } from "../components/DateText";
import { Bi, useBi } from "../i18n";
import { mizitoCode, mizitoStatus, perfApi, toman, triageLabel, type MizitoCard } from "./api";

/** هر جا فقط بخشی از کارت در دست است، کارت کامل با شناسه از لیست ذخیره‌شدهٔ میزیتو پیدا می‌شود. */
export type MizitoCardLike = Partial<MizitoCard> & { title: string };

const DAY_MS = 24 * 60 * 60 * 1000;

function daysSince(value?: string | null): number | null {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isNaN(time) ? null : Math.max(0, Math.floor((Date.now() - time) / DAY_MS));
}

function Fact({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

function When({ value }: { value?: string | null }) {
  return value ? <DateText value={value} withTime /> : <>—</>;
}

/** عنوان کارت به‌شکل دکمه، تا با صفحه‌کلید هم باز شود. */
export function MizitoOpenButton({ title, onOpen }: { title: string; onOpen: () => void }) {
  return (
    <button
      type="button"
      className="mizito-open cell-clamp"
      onClick={(event) => {
        event.stopPropagation();
        onOpen();
      }}
    >
      {title || "—"}
    </button>
  );
}

export function MizitoCardDialog({ card, flags, onClose }: { card: MizitoCardLike; flags?: string[]; onClose: () => void }) {
  const bi = useBi();
  const titleId = useId();
  const snapshot = useQuery({ queryKey: ["perf", "mizito"], queryFn: perfApi.mizito });
  const campaigns = useQuery({ queryKey: ["perf", "campaigns"], queryFn: perfApi.campaigns });
  const triage = useQuery({ queryKey: ["perf", "mizito", "triage", null], queryFn: () => perfApi.mizitoTriage(null) });

  const full: MizitoCardLike = (card.id ? snapshot.data?.cards.find((row) => row.id === card.id) : undefined) ?? card;
  const code = mizitoCode(full.code);
  const campaign = code ? (campaigns.data ?? []).find((row) => mizitoCode(row.code) === code) : undefined;
  const triageRow = full.id ? triage.data?.cards.find((row) => row.id === full.id) : undefined;
  const shownFlags = flags ?? triageRow?.flags ?? [];
  const stuckDays = triage.data?.days ?? 14;
  const idle = daysSince(full.modified_at);
  const total = full.checklist_total ?? 0;
  const done = full.checklist_done ?? 0;
  const progress = Math.max(0, Math.min(100, full.progress ?? (total ? Math.round((done * 100) / total) : 0)));
  const items = full.checklist_items ?? [];
  const prefix = snapshot.data?.card_url_prefix || "";
  const mizitoHref = prefix && full.id ? `${prefix}${encodeURIComponent(full.id)}` : "";

  return (
    <Dialog onClose={onClose} className="mizito-pop" labelledBy={titleId} closeLabel={bi("Close", "بستن")}>
        <SectionHeader
          icon="briefcase"
          title={<span id={titleId}>{full.title || "—"}</span>}
          action={<button type="button" className="kpi-more" onClick={onClose} data-autofocus><Bi en="Close" fa="بستن" /></button>}
        />
        {shownFlags.length ? (
          <span className="perf-chips">
            {shownFlags.map((flag) => <span key={flag} className="perf-chip">{triageLabel(flag, stuckDays)}</span>)}
          </span>
        ) : null}
        <dl className="mizito-facts">
          <Fact label="کد">
            {full.code ? <>{full.code}{full.code_source === "notes" ? <span className="muted"> (از یادداشت کارت)</span> : full.code_source === "title" ? <span className="muted"> (از عنوان)</span> : null}</> : "—"}
          </Fact>
          <Fact label="کمپین در پنل">
            {campaign ? (
              <Link to={`/perf/campaigns/${campaign.id}`} onClick={onClose}>
                <TitleCode title={campaign.title} code={campaign.code} />
              </Link>
            ) : code ? "این کد در پنل نیست" : "—"}
          </Fact>
          <Fact label="پروژه">{full.project || "—"}</Fact>
          <Fact label="برد">
            {full.board || "—"}
            {full.board_position != null ? <span className="muted"> (ستون {toman(full.board_position + 1)})</span> : null}
          </Fact>
          <Fact label="وضعیت">{mizitoStatus(full)}</Fact>
          <Fact label="تکمیل‌شده">
            {full.completed ? <>بله{full.completed_at ? <> — <When value={full.completed_at} /></> : null}</> : full.completed === false ? "خیر" : "—"}
          </Fact>
          <Fact label="فعال">{full.active === false ? "خیر" : full.active ? "بله" : "—"}</Fact>
          <Fact label="ساخته‌شده"><When value={full.created_at} /></Fact>
          <Fact label="آخرین تغییر">
            <When value={full.modified_at} />
            {idle != null ? <span className="muted"> ({toman(idle)} روز پیش)</span> : null}
          </Fact>
          <Fact label="مهلت"><When value={full.deadline} /></Fact>
          <Fact label="چک‌لیست">
            {total ? (
              <span className="mizito-progress">
                {toman(done)} از {toman(total)}
                <progress max={100} value={progress} aria-label={`پیشرفت ${toman(progress)}٪`} />
                {toman(progress)}٪
              </span>
            ) : "—"}
          </Fact>
          <Fact label="پیوست">{full.attachments != null ? toman(full.attachments) : "—"}</Fact>
          <Fact label="نظر">
            {full.has_comments ? <>دارد{full.last_comment_at ? <> — آخرین: <When value={full.last_comment_at} /></> : null}</> : full.has_comments === false ? "ندارد" : "—"}
          </Fact>
          <Fact label="مسئول">{full.assignees ? (full.assignees.length ? `${toman(full.assignees.length)} نفر` : "ندارد") : "—"}</Fact>
        </dl>
        {items.length ? (
          <>
            <Muted as="p">موارد چک‌لیست</Muted>
            <List>
              {items.map((item, index) => (
                <ListItem key={`${index}-${item.title}`}>
                  <span aria-hidden="true">{item.checked ? "✓ " : "○ "}</span>
                  <span className={item.checked ? "muted" : undefined}>{item.title || "—"}</span>
                  <span className="sr-only">{item.checked ? " (انجام شده)" : " (انجام نشده)"}</span>
                </ListItem>
              ))}
            </List>
          </>
        ) : null}
        {mizitoHref ? (
          <a href={mizitoHref} target="_blank" rel="noreferrer">باز کردن در میزیتو</a>
        ) : null}
        <Muted as="p">از آخرین خواندن میزیتو؛ متن یادداشت و نظرها نگه داشته نمی‌شود.</Muted>
    </Dialog>
  );
}
