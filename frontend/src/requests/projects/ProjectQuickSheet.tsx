import { useQuery } from "@tanstack/react-query";
import { Badge, Button, Muted } from "../../components/ui";
import { Sheet } from "../../components/ui/Extras";
import { Bi } from "../../i18n";
import { requestsApi } from "../api";
import { mizitoLaneLabel } from "../mizitoLanes";
import { PROJECT_STATUS_LABEL, STATUS_TONE } from "./constants";

type Props = {
  projectId: string;
  open: boolean;
  onClose: () => void;
  cardUrlPrefix?: string;
};

export function ProjectQuickSheet({ projectId, open, onClose, cardUrlPrefix }: Props) {
  const detail = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => requestsApi.project(projectId),
    enabled: open && Boolean(projectId),
  });

  const row = detail.data ?? {};
  const isCm = !row.mizito_card_id;
  const mizitoUrl =
    row.mizito_url ||
    (row.mizito_card_id && cardUrlPrefix ? `${cardUrlPrefix}${row.mizito_card_id}` : "");

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={
        <span>
          <span dir="ltr" className="record-code">{String(row.code || "")}</span>
          <span className="record-title"> {String(row.title || "")}</span>
        </span>
      }
      footer={
        <div className="record-actions">
          <Button to={`/projects/${projectId}`}>
            <Bi en="Open full page" fa="صفحهٔ کامل" />
          </Button>
          {mizitoUrl ? (
            <a className="btn btn-secondary" href={String(mizitoUrl)} target="_blank" rel="noreferrer">
              میزیتو
            </a>
          ) : null}
        </div>
      }
    >
      {detail.isLoading ? <Muted>بارگذاری…</Muted> : null}
      {detail.data ? (
        <div className="projects-sheet stack">
          <div className="meta-row">
            <Badge tone={STATUS_TONE[String(row.status)] || "warn"}>
              {PROJECT_STATUS_LABEL[String(row.status)] || String(row.status)}
            </Badge>
            <span className="meta-chip">{isCm ? "CM" : "میزیتو"}</span>
            {row.mizito_lane ? <span className="meta-chip">{mizitoLaneLabel(String(row.mizito_lane))}</span> : null}
          </div>
          {row.mizito_card_id ? (
            <Muted as="p">
              چک‌لیست {String(row.mizito_checklist_done ?? 0)}/{String(row.mizito_checklist_total ?? 0)}
              {row.mizito_attachments ? ` · ${String(row.mizito_attachments)} پیوست` : ""}
            </Muted>
          ) : null}
        </div>
      ) : null}
    </Sheet>
  );
}
