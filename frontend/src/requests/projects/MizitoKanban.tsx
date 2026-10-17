import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { EmptyState, Muted, QueryState } from "../../components/ui";
import { faNum } from "../../fa";
import { requestsApi, type MizitoKanbanCardBrief, type MizitoKanbanResponse, type WorkProject } from "../api";
import { CM_STATUS_COLUMNS } from "./constants";
import { KanbanCard } from "./KanbanCard";
import { KanbanColumn } from "./KanbanColumn";
import type { ProjectsUrlState } from "./useProjectsUrlState";

type Props = {
  url: ProjectsUrlState;
  onOpenCard: (id: string) => void;
  cmMode?: boolean;
  laneCount?: number;
  onShowArchive?: () => void;
};

function KanbanSkeleton() {
  return (
    <div className="projects-board" aria-hidden>
      {[1, 2, 3, 4].map((n) => (
        <div key={n} className="projects-col">
          <div className="projects-skel projects-skel-head" />
          <div className="projects-skel projects-skel-card" />
          <div className="projects-skel projects-skel-card" />
          <div className="projects-skel projects-skel-card" />
        </div>
      ))}
    </div>
  );
}

function briefFromProject(row: WorkProject): MizitoKanbanCardBrief {
  return {
    id: row.id,
    code: row.code,
    title: row.title,
    status: row.status,
    source: row.source ?? "cm",
    due: row.mizito_deadline ?? row.due_date,
    checklist_done: row.mizito_checklist_done ?? 0,
    checklist_total: row.mizito_checklist_total ?? 0,
    attachments: row.mizito_attachments ?? 0,
    has_comments: Boolean(row.mizito_has_comments),
    modified_at: row.mizito_modified_at,
  };
}

function CmStatusBoard({
  lane,
  q,
  hide_done,
  onOpenCard,
  onStatusChange,
}: {
  lane: string;
  q: string;
  hide_done: boolean;
  onOpenCard: (id: string) => void;
  onStatusChange: (id: string, status: string) => void;
}) {
  const list = useQuery({
    queryKey: ["requests", "cm-status-board", lane, q, hide_done],
    queryFn: () =>
      requestsApi.projectsPage({
        mizito_lane: lane === "none" ? "none" : lane || undefined,
        source: "cm",
        q,
        limit: 200,
        offset: 0,
      }),
    enabled: true,
  });
  const grouped = useMemo(() => {
    const map: Record<string, MizitoKanbanCardBrief[]> = { new: [], in_progress: [], done: [] };
    for (const row of list.data?.items ?? []) {
      if (hide_done && row.status === "done") continue;
      const key = row.status in map ? row.status : "new";
      map[key].push(briefFromProject(row));
    }
    return map;
  }, [list.data, hide_done]);

  const [overCol, setOverCol] = useState<string | null>(null);

  return (
    <QueryState isLoading={list.isLoading} error={list.error} isEmpty={false}>
      <div className="kanban projects-cm-board">
        {CM_STATUS_COLUMNS.map((col) => (
          <section
            key={col.key}
            className={`kanban-col${overCol === col.key ? " is-over" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setOverCol(col.key);
            }}
            onDragLeave={() => setOverCol(null)}
            onDrop={(event) => {
              event.preventDefault();
              setOverCol(null);
              const id = event.dataTransfer.getData("text/project-id");
              if (id) onStatusChange(id, col.key);
            }}
          >
            <h3>
              {col.label}
              <span className="section-count">{faNum(grouped[col.key].length)}</span>
            </h3>
            {grouped[col.key].map((row) => (
              <KanbanCard
                key={row.id}
                row={row}
                readOnly={false}
                draggable
                onDragStart={(event) => event.dataTransfer.setData("text/project-id", row.id)}
                onOpen={() => onOpenCard(row.id)}
              />
            ))}
          </section>
        ))}
      </div>
    </QueryState>
  );
}

export function MizitoKanban({ url, onOpenCard, cmMode, laneCount, onShowArchive }: Props) {
  const qc = useQueryClient();
  const kanban = useQuery({
    queryKey: [
      "requests",
      "mizito-kanban",
      url.lane,
      url.source,
      url.q,
      url.hide_done,
      url.archive,
    ],
    queryFn: () =>
      requestsApi.mizitoKanban({
        lane: url.lane,
        source: url.source,
        q: url.q,
        hide_done: url.hide_done,
        include_archive: url.archive,
        per_column: 20,
      }),
    enabled: Boolean(url.lane) && !cmMode,
  });

  const patchStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => requestsApi.patchProject(id, { status }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["requests", "cm-status-board"] });
      void qc.invalidateQueries({ queryKey: ["requests", "projects-page"] });
    },
  });

  if (cmMode) {
    return (
      <CmStatusBoard
        lane={url.lane}
        q={url.q}
        hide_done={url.hide_done}
        onOpenCard={onOpenCard}
        onStatusChange={(id, status) => patchStatus.mutate({ id, status })}
      />
    );
  }

  if (!url.lane) {
    return (
      <EmptyState
        titleEn="Choose a Mizito lane"
        titleFa="دستهٔ میزیتو را انتخاب کنید"
        bodyEn="Kanban columns come from that Mizito project's boards."
        bodyFa="ستون‌های کانبان از بردهای همان پروژه در میزیتو ساخته می‌شوند."
      />
    );
  }

  const data = kanban.data as MizitoKanbanResponse | undefined;

  const hiddenByArchive =
    data && laneCount != null && !url.archive && !url.q.trim() && !url.hide_done && !url.source
      ? Math.max(0, laneCount - data.lane_total)
      : 0;

  return (
    <div className="projects-page">
      {data && !data.import_ready ? (
        <Muted as="p">روش ورود کارت‌های این دسته هنوز تعریف نشده؛ فقط بردها ذخیره می‌شوند.</Muted>
      ) : null}
      {data ? (
        <p className="projects-summary">
          <strong>{data.lane_title}</strong>
          <Muted as="span">{faNum(data.lane_total)} کارت در {faNum(data.columns.length)} ستون</Muted>
          {hiddenByArchive > 0 && onShowArchive ? (
            <Muted as="span">
              · {faNum(hiddenByArchive)} کارت در ستون‌های بایگانی{" "}
              <button type="button" className="projects-link-btn" onClick={onShowArchive}>نمایش</button>
            </Muted>
          ) : null}
        </p>
      ) : null}
      {kanban.isLoading ? <KanbanSkeleton /> : null}
      {!kanban.isLoading ? (
        <QueryState
          isLoading={false}
          error={kanban.error}
          isEmpty={(data?.columns.length ?? 0) === 0}
          empty={
            <EmptyState
              titleEn="No cards match"
              titleFa="کارت مطابق فیلتر نیست"
              bodyEn="Try search or filters."
              bodyFa="جستجو یا فیلترها را عوض کنید."
            />
          }
        >
          {data && data.columns.length > 0 ? (
            <div className="projects-board">
              {data.columns.map((col) => (
                <KanbanColumn
                  key={`${col.board_id}|${url.q}|${url.hide_done}|${url.source}`}
                  column={col}
                  laneFilters={{
                    lane: url.lane,
                    source: url.source,
                    q: url.q,
                    hide_done: url.hide_done,
                  }}
                  onOpenCard={onOpenCard}
                />
              ))}
            </div>
          ) : null}
        </QueryState>
      ) : null}
    </div>
  );
}
