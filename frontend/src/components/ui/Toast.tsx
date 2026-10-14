/* Provider file intentionally exports its hook beside the Toast component. */
/* eslint-disable react/only-export-components */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { Button } from "./Button";
import { Bi } from "../../i18n";

type ToastAction = { labelEn: string; labelFa: string; onClick: () => void };

type Toast = { id: number; text: string; action?: ToastAction };

type ToastPush = (text: string, action?: ToastAction) => void;

const ToastContext = createContext<ToastPush>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback<ToastPush>((text, action) => {
    const id = Date.now() + Math.random();
    setItems((prev) => [...prev, { id, text, action }]);
    const ms = action ? 5000 : 3200;
    window.setTimeout(() => setItems((prev) => prev.filter((item) => item.id !== id)), ms);
  }, []);
  const value = useMemo(() => push, [push]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" role="status">
        {items.map((item) => (
          <div className="toast" key={item.id}>
            <span>{item.text}</span>
            {item.action ? (
              <Button
                type="button"
                variant="ghost"
                className="btn-sm toast-action"
                onClick={() => {
                  item.action?.onClick();
                  setItems((prev) => prev.filter((row) => row.id !== item.id));
                }}
              >
                <Bi en={item.action.labelEn} fa={item.action.labelFa} />
              </Button>
            ) : null}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
