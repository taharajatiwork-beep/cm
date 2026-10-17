import { Badge, Button, EmptyState, Muted, QueryState, Table, type Column } from "../../components/ui";
import { DateText } from "../../components/DateText";
import type { WorkProject } from "../api";
import { LIST_PAGE_SIZE, PROJECT_STATUS_LABEL, STATUS_TONE } from "./constants";
import type { ProjectsUrlState } from "./useProjectsUrlState";

type Props = {
  url: ProjectsUrlState;
  onPatch: (next: Partial<ProjectsUrlState>) => void;
  rows: WorkProject[];
  total: number;
  isLoading: boolean;
  error: Error | null;
  onRowOpen: (id: string) => void;
};

function SortHeader({
  label,
  field,
  url,
  onPatch,
}: {
  label: string;
  field: string;
  url: ProjectsUrlState;
  onPatch: (next: Partial<ProjectsUrlState>) => void;
}) {
  const active = url.sort === field;
  const nextOrder = active && url.order === "desc" ? "asc" : "desc";
  return (
    <button
      type="button"
      className={`projects-sort-head${active ? " is-active" : ""}`}
      onClick={() => onPatch({ sort: field, order: nextOrder, page: 1 })}
    >
      {label}
      {active ? (url.order === "asc" ? " ↑" : " ↓") : ""}
    </button>
  );
}

export function ProjectsTable({ url, onPatch, rows, total, isLoading, error, onRowOpen }: Props) {
  const pageCount = Math.max(1, Math.ceil(total / LIST_PAGE_SIZE));
  const columns: Column<WorkProject>[] = [
    {
      key: "code",
      header: "کد",
      render: (row) => <span dir="ltr">{row.code}</span>,
    },
    {
      key: "title",
      header: <SortHeader label="عنوان" field="title" url={url} onPatch={onPatch} />,
      render: (row) => row.title,
    },
    {
      key: "board",
      header: "برد",
      render: (row) => row.mizito_board || "—",
    },
    {
      key: "status",
      header: <SortHeader label="وضعیت" field="status" url={url} onPatch={onPatch} />,
      render: (row) => (
        <Badge tone={STATUS_TONE[row.status] || "warn"}>
          {PROJECT_STATUS_LABEL[row.status] || row.status}
        </Badge>
      ),
    },
    {
      key: "due",
      header: "مهلت",
      render: (row) =>
        row.mizito_deadline || row.due_date ? (
          <DateText value={row.mizito_deadline || row.due_date || ""} />
        ) : (
          "—"
        ),
    },
    {
      key: "checklist",
      header: "چک‌لیست",
      render: (row) => {
        const totalCl = row.mizito_checklist_total ?? 0;
        if (totalCl === 0) return "—";
        const done = row.mizito_checklist_done ?? 0;
        return `${Math.round((done / totalCl) * 100)}٪`;
      },
    },
    {
      key: "team",
      header: "تیم",
      render: (row) => row.team_name || "—",
    },
    {
      key: "updated",
      header: <SortHeader label="به‌روزرسانی" field="updated_at" url={url} onPatch={onPatch} />,
      render: (row) => (row.updated_at ? <DateText value={row.updated_at} withTime /> : "—"),
    },
  ];

  const hasFilters = Boolean(url.q || url.source || url.status || url.hide_done);

  return (
    <QueryState
      isLoading={isLoading}
      error={error}
      isEmpty={rows.length === 0 && !isLoading}
      empty={
        <EmptyState
          titleEn="No projects match"
          titleFa="پروژه‌ای پیدا نشد"
          bodyEn="Try another lane or clear filters."
          bodyFa="دسته یا فیلتر دیگری امتحان کنید."
          onClearFilters={
            hasFilters
              ? () => onPatch({ q: "", source: "", status: "", hide_done: false, page: 1 })
              : undefined
          }
        />
      }
    >
      <Table columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={(row) => onRowOpen(row.id)} />
      {total > LIST_PAGE_SIZE ? (
        <div className="projects-pager meta-row">
          <Muted as="span">
            {(url.page - 1) * LIST_PAGE_SIZE + 1}–{Math.min(url.page * LIST_PAGE_SIZE, total)} از {total}
          </Muted>
          <Button
            type="button"
            variant="secondary"
            className="btn-sm"
            disabled={url.page <= 1}
            onClick={() => onPatch({ page: url.page - 1 })}
          >
            قبلی
          </Button>
          <Button
            type="button"
            variant="secondary"
            className="btn-sm"
            disabled={url.page >= pageCount}
            onClick={() => onPatch({ page: url.page + 1 })}
          >
            بعدی
          </Button>
        </div>
      ) : null}
    </QueryState>
  );
}
