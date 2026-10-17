import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { Button, Disclosure, ErrorMessage, Field, LoadingState, Muted, SectionHeader, TextArea } from "../components/ui";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { Bi, useBi, useLocale } from "../i18n";
import { formatDeadline } from "../lib/collaboration";
import { WorkParentContext } from "../lib/workContext";

type TaskRow = Record<string, unknown>;

export function TaskDetailSheet({
  taskId,
  data,
  parentLookups,
  canFinish,
  onComplete,
}: {
  taskId: string;
  data: TaskRow;
  parentLookups: ReturnType<typeof import("../lib/workContext").useWorkParentLookups>;
  canFinish: boolean;
  onComplete: () => Promise<void>;
}) {
  const bi = useBi();
  const { locale } = useLocale();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [comment, setComment] = useState("");
  const notes = useQuery({
    queryKey: ["task", taskId, "notes"],
    queryFn: () => api.tasks.notes(taskId),
  });
  const addNote = useMutation({
    mutationFn: (body: { kind?: string; body?: string; url?: string }) => api.tasks.addNote(taskId, body),
    onSuccess: () => {
      setComment("");
      void qc.invalidateQueries({ queryKey: ["task", taskId, "notes"] });
    },
  });
  const upload = useMutation({
    mutationFn: (file: File) => api.tasks.uploadFile(taskId, file, "deliverable"),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["task", taskId, "notes"] }),
  });
  const noteRows = notes.data ?? [];
  const hasDeliverable = noteRows.some((row) => row.kind === "deliverable");
  const project = data.project as
    | { id: string; code: string; title: string; description?: string; request_id?: string | null }
    | undefined;
  const projectAttachments = (data.project_attachments as Array<{ id: string; title: string; url: string }>) ?? [];
  const taskFiles = noteRows.filter((row) => row.kind === "file" || row.kind === "deliverable");

  async function markDone() {
    if (canFinish && !hasDeliverable) {
      const ok = await confirm(
        bi("Finish without an upload?", "بدون آپلود خروجی تمام شود؟"),
        bi("You have not uploaded a deliverable yet.", "هنوز فایل خروجی آپلود نکرده‌اید."),
        bi("Mark done", "انجام شد"),
      );
      if (!ok) return;
    }
    await onComplete();
  }

  return (
    <div className="stack">
      {canFinish ? (
        <div className="stack">
          <SectionHeader icon="upload" title={<Bi en="Finish this task" fa="تمام کردن کار" />} />
          <input
            ref={fileRef}
            type="file"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
              e.target.value = "";
            }}
          />
          <div className="row">
            <Button type="button" variant="secondary" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
              <Bi en="Upload output" fa="آپلود خروجی" />
            </Button>
            <Button type="button" onClick={() => void markDone()}>
              <Bi en="Mark done" fa="انجام شد" />
            </Button>
          </div>
        </div>
      ) : null}
      {data.description ? (
        <p>{String(data.description)}</p>
      ) : (
        <Muted>
          <Bi en="No extra notes on this task." fa="یادداشت اضافه‌ای برای این کار نیست." />
        </Muted>
      )}
      {project?.description ? (
        <div>
          <SectionHeader icon="layers" title={<Bi en="Project brief" fa="بریف پروژه" />} />
          <p>{project.description}</p>
        </div>
      ) : null}
      {formatDeadline(data.deadline, bi, locale) ? (
        <p className="row-meta">
          {formatDeadline(data.deadline, bi, locale)}
        </p>
      ) : null}
      <WorkParentContext
        kind="task"
        {...(() => {
          if (project?.id) {
            return {
              origin: "project" as const,
              projectId: project.id,
              projectCode: project.code,
              projectTitle: project.title,
              requestId: project.request_id ?? null,
            };
          }
          return parentLookups.resolve({
            project_id: data.project_id as string | null,
            request_id: data.request_id as string | null,
          });
        })()}
      />
      {(data.assignees as Array<{ id: string; full_name: string }> | undefined)?.length ? (
        <p className="row-meta">
          <Bi en="Assignees" fa="مسئول‌ها" />:{" "}
          {(data.assignees as Array<{ id: string; full_name: string }>).map((row) => row.full_name || row.id).join("، ")}
        </p>
      ) : null}
      {projectAttachments.length > 0 || taskFiles.length > 0 ? (
        <div>
          <SectionHeader icon="upload" title={<Bi en="Attachments" fa="پیوست‌ها" />} />
          <ul className="rows rows--boxed">
            {projectAttachments.map((item) => (
              <li key={item.id} className="row-item">
                <a href={item.url} target="_blank" rel="noreferrer">{item.title || item.url}</a>
              </li>
            ))}
            {taskFiles.map((item) => (
              <li key={String(item.id)} className="row-item">
                <a href={api.tasks.fileUrl(taskId, String(item.id))} target="_blank" rel="noreferrer">
                  {String(item.file_name || item.kind)}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <Disclosure label={<Bi en="Comments" fa="نظرات" />}>
        {notes.isLoading ? <LoadingState block={false} /> : null}
        {notes.error ? <ErrorMessage error={notes.error} /> : null}
        <ul className="rows rows--boxed">
          {noteRows
            .filter((row) => row.kind === "comment" || row.kind === "link")
            .map((row) => (
              <li key={String(row.id)} className="row-item">
                <strong>{String(row.author_name || "")}</strong>
                {row.kind === "link" && row.url ? (
                  <a href={String(row.url)} target="_blank" rel="noreferrer">{String(row.body || row.url)}</a>
                ) : (
                  <span>{String(row.body)}</span>
                )}
              </li>
            ))}
        </ul>
        <div className="form-grid">
          <Field label={<Bi en="Comment" fa="نظر" />} className="span-2">
            <TextArea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} />
          </Field>
          <Button
            type="button"
            disabled={!comment.trim() || addNote.isPending}
            onClick={() => addNote.mutate({ kind: "comment", body: comment.trim() })}
          >
            <Bi en="Add comment" fa="ثبت نظر" />
          </Button>
        </div>
      </Disclosure>
    </div>
  );
}
