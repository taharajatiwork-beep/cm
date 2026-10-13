import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button, Card, Dialog, ErrorMessage, Field, SectionHeader, TextArea } from "../components/ui";
import { Bi, useBi } from "../i18n";
import { requestsApi } from "./api";

export function DeliveryReviewCard({
  projectId,
  onSuccess,
}: {
  projectId: string;
  onSuccess: () => void;
}) {
  const bi = useBi();
  const [returnOpen, setReturnOpen] = useState(false);
  const [returnNote, setReturnNote] = useState("");

  const accept = useMutation({
    mutationFn: () => requestsApi.projectAcceptance(projectId, "accepted"),
    onSuccess: () => onSuccess(),
  });
  const returnForFixes = useMutation({
    mutationFn: () => requestsApi.projectAcceptance(projectId, "returned", returnNote.trim()),
    onSuccess: () => {
      setReturnOpen(false);
      setReturnNote("");
      onSuccess();
    },
  });

  const busy = accept.isPending || returnForFixes.isPending;

  return (
    <>
      <Card className="stack">
        <SectionHeader title={<Bi en="Accept delivery" fa="تأیید تحویل" />} />
        <p>
          <Bi en="Confirm the result or send it back with a note." fa="نتیجه را تأیید کنید یا با یادداشت برای اصلاح برگردانید." />
        </p>
        <ErrorMessage
          error={
            accept.error
              ? accept.error instanceof Error
                ? accept.error.message
                : String(accept.error)
              : returnForFixes.error
                ? returnForFixes.error instanceof Error
                  ? returnForFixes.error.message
                  : String(returnForFixes.error)
                : ""
          }
        />
        <div className="record-actions">
          <Button type="button" disabled={busy} onClick={() => accept.mutate()}>
            {accept.isPending ? <Bi en="Saving…" fa="در حال ثبت…" /> : <Bi en="Accept" fa="تأیید" />}
          </Button>
          <Button type="button" variant="secondary" disabled={busy} onClick={() => setReturnOpen(true)}>
            <Bi en="Return for fixes" fa="برگشت برای اصلاح" />
          </Button>
        </div>
      </Card>
      {returnOpen ? (
        <Dialog
          onClose={() => {
            if (!returnForFixes.isPending) {
              setReturnOpen(false);
            }
          }}
          className="form-pop"
          labelledBy="return-delivery-title"
          busy={returnForFixes.isPending}
          as="form"
          onSubmit={(event) => {
            event.preventDefault();
            if (returnNote.trim()) returnForFixes.mutate();
          }}
        >
          <SectionHeader
            title={
              <span id="return-delivery-title">
                <Bi en="Return for fixes" fa="برگشت برای اصلاح" />
              </span>
            }
          />
          <Field label={<Bi en="Note for the team" fa="یادداشت برای تیم" />}>
            <TextArea
              value={returnNote}
              rows={4}
              data-autofocus
              onChange={(event) => setReturnNote(event.target.value)}
              placeholder={bi("What should change?", "چه چیزی باید اصلاح شود؟")}
            />
          </Field>
          <ErrorMessage
            error={
              returnForFixes.error
                ? returnForFixes.error instanceof Error
                  ? returnForFixes.error.message
                  : String(returnForFixes.error)
                : ""
            }
          />
          <div className="row perf-actions">
            <Button type="submit" disabled={!returnNote.trim() || returnForFixes.isPending}>
              {returnForFixes.isPending ? <Bi en="Sending…" fa="در حال ارسال…" /> : <Bi en="Send back" fa="ارسال برگشت" />}
            </Button>
            <Button type="button" variant="secondary" disabled={returnForFixes.isPending} onClick={() => setReturnOpen(false)}>
              <Bi en="Cancel" fa="انصراف" />
            </Button>
          </div>
        </Dialog>
      ) : null}
    </>
  );
}
