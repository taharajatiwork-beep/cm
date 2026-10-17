import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Badge, Button, Muted } from "../../components/ui";
import { faNum } from "../../fa";
import { requestsApi, type MizitoKanbanCardBrief, type MizitoKanbanColumn } from "../api";
import { KanbanCard } from "./KanbanCard";

type LaneFilters = {
  lane: string;
  source: string;
  q: string;
  hide_done: boolean;
};

type Props = {
  column: MizitoKanbanColumn;
  laneFilters: LaneFilters;
  onOpenCard: (id: string) => void;
};

function splitLabel(open: number, done: number): string {
  const parts: string[] = [];
  if (open > 0) parts.push(`${faNum(open)} باز`);
  if (done > 0) parts.push(`${faNum(done)} تمام`);
  return parts.join(" · ");
}

export function KanbanColumn({ column, laneFilters, onOpenCard }: Props) {
  const [extra, setExtra] = useState<MizitoKanbanCardBrief[]>([]);
  const projects = [...column.projects, ...extra];
  const remaining = Math.max(0, column.total - projects.length);

  const loadMore = useMutation({
    mutationFn: () =>
      requestsApi.mizitoKanbanColumn({
        lane: laneFilters.lane,
        board_id: column.board_id,
        source: laneFilters.source,
        q: laneFilters.q,
        hide_done: laneFilters.hide_done,
        offset: projects.length,
        limit: 20,
      }),
    onSuccess: (page) => setExtra((prev) => [...prev, ...page.projects]),
  });

  const split = splitLabel(column.open_count, column.done_count);

  return (
    <section className="projects-col" aria-label={column.title}>
      <header className="projects-col-head">
        <div className="projects-col-title-row">
          <span className="projects-col-title" title={column.title}>{column.title}</span>
          <Badge className="section-count">{faNum(column.total)}</Badge>
        </div>
        {split ? <Muted as="span" className="projects-col-sub">{split}</Muted> : null}
      </header>
      <div className="projects-col-body">
        {projects.length === 0 ? <Muted as="p" className="projects-col-empty">خالی</Muted> : null}
        {projects.map((row) => (
          <KanbanCard key={row.id} row={row} readOnly={row.source !== "cm"} onOpen={() => onOpenCard(row.id)} />
        ))}
        {remaining > 0 ? (
          <Button
            type="button"
            variant="ghost"
            className="btn-sm projects-col-more"
            disabled={loadMore.isPending}
            onClick={() => loadMore.mutate()}
          >
            {loadMore.isPending ? "در حال بارگذاری…" : `${faNum(Math.min(20, remaining))} کارت بیشتر (${faNum(remaining)} مانده)`}
          </Button>
        ) : null}
      </div>
    </section>
  );
}
