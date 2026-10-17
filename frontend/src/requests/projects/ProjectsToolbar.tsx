import { useEffect, useState } from "react";
import { Button, Checkbox, Icon, Input, MoreMenu, Segmented, Select } from "../../components/ui";
import { DateText } from "../../components/DateText";
import { Bi } from "../../i18n";
import type { ProjectsUrlState } from "./useProjectsUrlState";

type Lane = { slug: string; title: string; project_count?: number };

type Props = {
  url: ProjectsUrlState;
  onPatch: (next: Partial<ProjectsUrlState>) => void;
  lanes: Lane[];
  triage: boolean;
  syncPending?: number;
  syncFinishedAt?: string | null;
  syncOk?: boolean;
  syncError?: string;
  onSyncNow?: () => void;
  onReviewChanges?: () => void;
};

export function ProjectsToolbar({
  url,
  onPatch,
  lanes,
  triage,
  syncPending,
  syncFinishedAt,
  syncOk,
  syncError,
  onSyncNow,
  onReviewChanges,
}: Props) {
  const [qInput, setQInput] = useState(url.q);
  useEffect(() => setQInput(url.q), [url.q]);
  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (qInput !== url.q) onPatch({ q: qInput, page: 1 });
    }, 300);
    return () => window.clearTimeout(handle);
  }, [qInput, url.q, onPatch]);

  const pending = syncPending ?? 0;
  const board = url.view === "board";

  return (
    <div className="projects-toolbar">
      {lanes.length > 0 ? (
        <div className="projects-lanes">
          <Segmented
            ariaLabel="دستهٔ میزیتو"
            value={url.lane || lanes[0]?.slug || ""}
            onChange={(lane) => onPatch({ lane, page: 1 })}
            items={lanes.map((lane) => ({ key: lane.slug, label: lane.title, count: lane.project_count }))}
          />
        </div>
      ) : null}
      <div className="projects-toolbar-row">
        <div className="projects-search">
          <Icon name="search" size={14} />
          <Input
            value={qInput}
            onChange={(event) => setQInput(event.target.value)}
            placeholder="جستجوی عنوان یا کد…"
            aria-label="جستجو در پروژه‌ها"
          />
        </div>
        <div className="projects-toolbar-chips">
          <Select aria-label="منبع" value={url.source} onChange={(event) => onPatch({ source: event.target.value, page: 1 })}>
            <option value="">همهٔ منابع</option>
            <option value="mizito">میزیتو</option>
            <option value="cm">CM</option>
          </Select>
          {!board ? (
            <Select aria-label="وضعیت" value={url.status} onChange={(event) => onPatch({ status: event.target.value, page: 1 })}>
              <option value="">همهٔ وضعیت‌ها</option>
              <option value="new">تازه</option>
              <option value="in_progress">در جریان</option>
              <option value="done">تمام</option>
            </Select>
          ) : null}
          <Checkbox
            checked={url.hide_done}
            onChange={(event) => onPatch({ hide_done: event.target.checked, page: 1 })}
            label={<Bi en="Open only" fa="فقط باز" />}
          />
          {board ? (
            <Checkbox
              checked={url.archive}
              onChange={(event) => onPatch({ archive: event.target.checked, page: 1 })}
              label={<Bi en="Archive columns" fa="ستون‌های بایگانی" />}
            />
          ) : null}
        </div>
        <div className="projects-toolbar-end">
          <span className={`projects-sync muted${syncFinishedAt && syncOk === false ? " is-error" : ""}`} title={syncError || undefined}>
            <Icon name="clock" size={12} />
            {syncFinishedAt ? <DateText value={syncFinishedAt} withTime /> : "بدون همگام‌سازی"}
          </span>
          <Segmented
            ariaLabel="نمای پروژه‌ها"
            value={url.view}
            onChange={(view) => onPatch({ view })}
            items={[
              { key: "board", label: "کانبان" },
              { key: "list", label: "فهرست" },
            ]}
          />
          {triage ? (
            <MoreMenu label={<Bi en="More" fa="بیشتر" />}>
              {onSyncNow ? (
                <Button type="button" variant="ghost" onClick={onSyncNow}>
                  همگام‌سازی همین حالا
                </Button>
              ) : null}
              {onReviewChanges ? (
                <Button type="button" variant="ghost" onClick={onReviewChanges} disabled={pending === 0}>
                  تغییرهای منتظر تأیید ({pending})
                </Button>
              ) : null}
            </MoreMenu>
          ) : null}
        </div>
      </div>
    </div>
  );
}
