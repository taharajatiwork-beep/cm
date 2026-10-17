import type { DragEvent } from "react";
import { Icon } from "../../components/ui";
import { Avatar } from "../../components/ui/Extras";
import { DateText } from "../../components/DateText";
import { faNum } from "../../fa";
import type { MizitoKanbanCardBrief } from "../api";

type Props = {
  row: MizitoKanbanCardBrief;
  readOnly?: boolean;
  onOpen: () => void;
  draggable?: boolean;
  onDragStart?: (event: DragEvent) => void;
};

export function KanbanCard({ row, readOnly = true, onOpen, draggable, onDragStart }: Props) {
  const checklistTotal = row.checklist_total ?? 0;
  const checklistDone = row.checklist_done ?? 0;
  const checklistPct = checklistTotal > 0 ? Math.round((checklistDone / checklistTotal) * 100) : 0;
  const attachments = row.attachments ?? 0;
  const assignees = row.assignee_names ?? [];
  const hasFoot = Boolean(row.due) || checklistTotal > 0 || attachments > 0 || row.has_comments || assignees.length > 0;

  return (
    <button
      type="button"
      className={`projects-card${readOnly ? " is-readonly" : ""}`}
      onClick={onOpen}
      draggable={draggable}
      onDragStart={onDragStart}
      title={readOnly ? "فقط خواندنی؛ از میزیتو می‌آید" : undefined}
    >
      {readOnly ? <Icon name="lock" size={12} className="projects-card-lock" /> : null}
      <span className="projects-card-code" dir="ltr">{row.code}</span>
      <span className="projects-card-title">{row.title}</span>
      {hasFoot ? (
        <span className="projects-card-foot">
          {row.due ? (
            <span className={`projects-card-meta projects-card-due${row.overdue ? " is-overdue" : ""}`}>
              <Icon name="calendar" size={12} />
              <DateText value={row.due} />
            </span>
          ) : null}
          {checklistTotal > 0 ? (
            <span className="projects-card-check" title={`چک‌لیست ${faNum(checklistDone)} از ${faNum(checklistTotal)}`}>
              <span className="projects-card-check-track">
                <span className="projects-card-check-bar" style={{ width: `${checklistPct}%` }} />
              </span>
              {faNum(checklistDone)}/{faNum(checklistTotal)}
            </span>
          ) : null}
          {attachments > 0 ? (
            <span className="projects-card-meta" title="پیوست">
              <Icon name="paperclip" size={12} />
              {faNum(attachments)}
            </span>
          ) : null}
          {row.has_comments ? (
            <span className="projects-card-meta" title="نظر دارد">
              <Icon name="chat" size={12} />
            </span>
          ) : null}
          {assignees.length > 0 ? (
            <span className="projects-card-avatars">
              {assignees.slice(0, 3).map((name) => (
                <Avatar key={name} name={name} size={20} />
              ))}
              {(row.assignee_extra ?? 0) > 0 ? <span>+{faNum(row.assignee_extra ?? 0)}</span> : null}
            </span>
          ) : null}
        </span>
      ) : null}
    </button>
  );
}
