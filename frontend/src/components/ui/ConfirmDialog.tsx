/* Provider file intentionally exports its hook beside the ConfirmDialog component. */
/* eslint-disable react/only-export-components */
import { createContext, useCallback, useContext, useId, useState, type ReactNode } from "react";
import { Button } from "./Button";
import { Dialog } from "./Dialog";

export type ConfirmOptions = {
  /** Destructive action (delete, anonymise…): red confirm button, alertdialog, Cancel focused first. */
  danger?: boolean;
};

type Ask = { title: string; body: string; confirm: string; danger: boolean; resolve: (ok: boolean) => void };

type ConfirmFn = (title: string, body: string, confirm?: string, options?: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn>(async () => false);

/** Standard label for the confirm button of a delete question. */
export const DELETE_CONFIRM_LABEL = "بله، حذف کن";

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [ask, setAsk] = useState<Ask | null>(null);
  const titleId = useId();
  const bodyId = useId();
  const confirm = useCallback<ConfirmFn>((title, body, confirmLabel = "تأیید", options) => {
    return new Promise<boolean>((resolve) => {
      setAsk({ title, body, confirm: confirmLabel, danger: Boolean(options?.danger), resolve });
    });
  }, []);
  function close(ok: boolean) {
    ask?.resolve(ok);
    setAsk(null);
  }
  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {ask ? (
        <Dialog
          onClose={() => close(false)}
          role={ask.danger ? "alertdialog" : "dialog"}
          labelledBy={titleId}
          describedBy={bodyId}
          className="form-pop confirm-pop"
        >
          <h2 id={titleId} className="confirm-title">
            {ask.title}
          </h2>
          <p id={bodyId} className="confirm-body">
            {ask.body}
          </p>
          <div className="confirm-actions">
            <Button variant="secondary" onClick={() => close(false)} data-autofocus={ask.danger ? "" : undefined}>
              انصراف
            </Button>
            <Button variant={ask.danger ? "danger" : "primary"} onClick={() => close(true)}>
              {ask.confirm}
            </Button>
          </div>
        </Dialog>
      ) : null}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  return useContext(ConfirmContext);
}
