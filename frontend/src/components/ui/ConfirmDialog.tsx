import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { Button } from "./Button";

type Ask = { title: string; body: string; confirm: string; resolve: (ok: boolean) => void };

const ConfirmContext = createContext<(title: string, body: string, confirm?: string) => Promise<boolean>>(
  async () => false,
);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [ask, setAsk] = useState<Ask | null>(null);
  const confirm = useCallback((title: string, body: string, confirmLabel = "تأیید") => {
    return new Promise<boolean>((resolve) => {
      setAsk({ title, body, confirm: confirmLabel, resolve });
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
        <div className="sheet-root" role="dialog" aria-modal>
          <div className="sheet-backdrop" onClick={() => close(false)} />
          <aside className="sheet confirm-sheet">
            <header className="sheet-head">
              <h2>{ask.title}</h2>
            </header>
            <div className="sheet-body">{ask.body}</div>
            <footer className="sheet-foot">
              <Button variant="secondary" onClick={() => close(false)}>
                انصراف
              </Button>
              <Button onClick={() => close(true)}>{ask.confirm}</Button>
            </footer>
          </aside>
        </div>
      ) : null}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  return useContext(ConfirmContext);
}
