import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Field, Muted, Select } from "../../components/ui";
import { Sheet } from "../../components/ui/Extras";
import { DateText } from "../../components/DateText";
import { Bi } from "../../i18n";
import { requestsApi } from "../api";
import { mizitoLaneLabel } from "../mizitoLanes";
import { PROJECT_STATUS_LABEL, STATUS_TONE } from "./constants";

type Props = {
  projectId: string;
  open: boolean;
  onClose: () => void;
  triage: boolean;
  cardUrlPrefix?: string;
};

export function ProjectQuickSheet({ projectId, open, onClose, triage, cardUrlPrefix }: Props) {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => requestsApi.project(projectId),
    enabled: open && Boolean(projectId),
  });
  const history = useQuery({
    queryKey: ["requests", "mizito-changes", projectId],
    queryFn: () => requestsApi.mizitoChanges("", projectId),
    enabled: open && Boolean(projectId) && Boolean(detail.data?.mizito_card_id),
  });
  const patch = useMutation({
    mutationFn: (status: string) => requestsApi.patchProject(projectId, { status }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["project", projectId] });
      void qc.invalidateQueries({ queryKey: ["requests"] });
    },
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
            {row.mizito_board ? <span className="meta-chip">{String(row.mizito_board)}</span> : null}
          </div>
          {row.mizito_card_id ? (
            <dl className="projects-facts">
              <div><dt>کد میزیتو</dt><dd dir="ltr">{String(row.mizito_code || "—")}</dd></div>
              <div>
                <dt>مهلت</dt>
                <dd>{row.mizito_deadline ? <DateText value={String(row.mizito_deadline)} /> : "—"}</dd>
              </div>
              <div>
                <dt>چک‌لیست</dt>
                <dd>{String(row.mizito_checklist_done ?? 0)} از {String(row.mizito_checklist_total ?? 0)}</dd>
              </div>
              <div><dt>پیوست</dt><dd>{String(row.mizito_attachments ?? 0)}</dd></div>
              <div>
                <dt>آخرین تغییر میزیتو</dt>
                <dd>
                  {row.mizito_modified_at ? <DateText value={String(row.mizito_modified_at)} withTime /> : "—"}
                </dd>
              </div>
            </dl>
          ) : null}
          {(history.data ?? []).length > 0 ? (
            <div>
              <h3 className="projects-sheet-sub">تاریخچه</h3>
              <ul className="projects-history-list">
                {(history.data ?? []).slice(0, 5).map((change) => (
                  <li key={change.id}>
                    <Muted>{change.field}: {change.old_value} → {change.new_value}</Muted>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <Muted as="p">
            اعضا: {((row.members as Array<{ full_name: string }>) ?? []).length} · کمپین:{" "}
            {((row.campaigns as Array<unknown>) ?? []).length}
          </Muted>
          {triage && isCm ? (
            <Field label={<Bi en="Status" fa="وضعیت" />}>
              <Select
                value={String(row.status || "new")}
                onChange={(event) => patch.mutate(event.target.value)}
                disabled={patch.isPending}
              >
                {Object.entries(PROJECT_STATUS_LABEL).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </Select>
            </Field>
          ) : null}
        </div>
      ) : null}
    </Sheet>
  );
}
