import { useEffect, useRef, useState, type FormEventHandler, type ReactNode } from "react";
import { Icon } from "./Icon";

/**
 * One shared modal dialog.
 *
 * - role="dialog" (or "alertdialog"), aria-modal, labelled by a title id or an aria-label.
 * - Focus moves in on open: an element marked `data-autofocus`, an element that already took focus
 *   (React `autoFocus`), or the first focusable element. Tab / Shift+Tab stay inside.
 * - Esc and a backdrop click close it, except while `busy` (e.g. a delete is running).
 * - On close, focus goes back to whatever had it before (usually the button that opened it).
 * - The page behind does not scroll while any dialog is open.
 * - Nested dialogs work: only the top one reacts to Esc and Tab.
 *
 * Layout "pop" keeps the existing `.detail-pop` look (a bottom sheet on small screens);
 * layout "sheet" keeps the side `.sheet` look.
 */
export type DialogProps = {
  onClose: () => void;
  children: ReactNode;
  /** id of the visible title. Use this or `label`. */
  labelledBy?: string;
  /** Accessible name when there is no visible title element. */
  label?: string;
  describedBy?: string;
  role?: "dialog" | "alertdialog";
  layout?: "pop" | "sheet";
  /** Extra class on the outer layer, e.g. "form-pop" or "mizito-pop". */
  className?: string;
  /** Extra class on the panel itself. */
  panelClassName?: string;
  /** Render the panel as a form (Enter submits) or an aside. */
  as?: "div" | "form" | "aside";
  onSubmit?: FormEventHandler<HTMLFormElement>;
  /** While true, Esc and the backdrop do nothing. Buttons inside decide for themselves. */
  busy?: boolean;
  closeOnBackdrop?: boolean;
  /** Accessible name of the backdrop (mouse-only close target). */
  closeLabel?: string;
};

const FOCUSABLE = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  'input:not([disabled]):not([type="hidden"])',
  "select:not([disabled])",
  "textarea:not([disabled])",
  "iframe",
  "summary",
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(",");

function focusableIn(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => !el.closest("[hidden], [inert], [aria-hidden='true']") && el.tabIndex >= 0,
  );
}

/**
 * Last element that had focus anywhere. Used as the "trigger" when focus was already lost
 * at open time (e.g. the button became disabled while its request ran).
 */
let lastFocused: HTMLElement | null = null;
if (typeof document !== "undefined") {
  document.addEventListener(
    "focusin",
    (event) => {
      if (event.target instanceof HTMLElement) lastFocused = event.target;
    },
    true,
  );
}

function currentTrigger(): HTMLElement | null {
  if (typeof document === "undefined") return null;
  const active = document.activeElement;
  if (active instanceof HTMLElement && active !== document.body) return active;
  return lastFocused && lastFocused.isConnected ? lastFocused : null;
}

/** Open dialogs, oldest first. Only the last one handles keys. */
const openStack: symbol[] = [];
let scrollLocks = 0;
let savedOverflow = "";

function lockScroll() {
  if (scrollLocks === 0) {
    savedOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  scrollLocks += 1;
}

function unlockScroll() {
  scrollLocks = Math.max(0, scrollLocks - 1);
  if (scrollLocks === 0) document.body.style.overflow = savedOverflow;
}

export function Dialog({
  onClose,
  children,
  labelledBy,
  label,
  describedBy,
  role = "dialog",
  layout = "pop",
  className = "",
  panelClassName = "",
  as = "div",
  onSubmit,
  busy = false,
  closeOnBackdrop = true,
  closeLabel = "بستن",
}: DialogProps) {
  const panelRef = useRef<HTMLElement | null>(null);
  /** Who had focus when the dialog was first rendered (before any autoFocus inside it ran). */
  const [trigger] = useState<HTMLElement | null>(currentTrigger);
  const onCloseRef = useRef(onClose);
  const busyRef = useRef(busy);
  /** Element that got focus on open; kept so a dev re-run of the effect lands on it again. */
  const startRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    onCloseRef.current = onClose;
    busyRef.current = busy;
  });

  useEffect(() => {
    const id = Symbol("dialog");
    openStack.push(id);
    const isTop = () => openStack[openStack.length - 1] === id;
    lockScroll();

    const panel = panelRef.current;
    // The trigger seen at first render, unless it has gone away since (e.g. another dialog that
    // was replaced by this one); then whatever has focus now, before we move focus inside.
    const atRender = trigger && trigger.isConnected && !panel?.contains(trigger) ? trigger : null;
    const now = currentTrigger();
    const restoreTo = atRender ?? (now && !panel?.contains(now) ? now : null);
    if (panel) {
      const active = document.activeElement;
      if (active instanceof HTMLElement && active !== document.body && panel.contains(active)) {
        startRef.current = active;
      } else {
        const remembered = startRef.current && panel.contains(startRef.current) ? startRef.current : null;
        const target =
          remembered ?? panel.querySelector<HTMLElement>("[data-autofocus]") ?? focusableIn(panel)[0] ?? panel;
        startRef.current = target;
        target.focus();
      }
    }

    function onKey(event: KeyboardEvent) {
      if (!panel || !isTop()) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (!busyRef.current) onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusableIn(panel);
      if (items.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      const inside = active instanceof Node && panel.contains(active);
      if (event.shiftKey && (!inside || active === first || active === panel)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (!inside || active === last)) {
        event.preventDefault();
        first.focus();
      }
    }

    function onFocusIn(event: FocusEvent) {
      if (!panel || !isTop()) return;
      if (event.target instanceof Node && !panel.contains(event.target)) {
        (focusableIn(panel)[0] ?? panel).focus();
      }
    }

    document.addEventListener("keydown", onKey);
    document.addEventListener("focusin", onFocusIn);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("focusin", onFocusIn);
      const at = openStack.indexOf(id);
      if (at >= 0) openStack.splice(at, 1);
      unlockScroll();
      if (restoreTo && restoreTo.isConnected) restoreTo.focus();
    };
  }, [trigger]);

  function onBackdrop() {
    if (closeOnBackdrop && !busyRef.current) onCloseRef.current();
  }

  const setPanel = (node: HTMLElement | null) => {
    panelRef.current = node;
  };
  const sheet = layout === "sheet";
  const panelProps = {
    className: `${sheet ? "sheet" : "detail-pop-card"} ${panelClassName}`.trim(),
    role,
    "aria-modal": true,
    "aria-labelledby": labelledBy,
    "aria-label": labelledBy ? undefined : label,
    "aria-describedby": describedBy,
    "aria-busy": busy || undefined,
    tabIndex: -1,
  } as const;

  const closeBtn =
    !busy && !sheet ? (
      <button
        type="button"
        className="detail-pop-close"
        onClick={() => onCloseRef.current()}
        aria-label={`${closeLabel} · پنجره`}
        title={closeLabel}
      >
        <Icon name="x" size={18} />
      </button>
    ) : null;

  const panel =
    as === "form" ? (
      <form ref={setPanel} {...panelProps} onSubmit={onSubmit}>
        {children}
        {closeBtn}
      </form>
    ) : as === "aside" ? (
      <aside ref={setPanel} {...panelProps}>
        {children}
        {closeBtn}
      </aside>
    ) : (
      <div ref={setPanel} {...panelProps}>
        {children}
        {closeBtn}
      </div>
    );

  return (
    <div className={`${sheet ? "sheet-root" : "detail-pop"} ${className}`.trim()}>
      {sheet ? (
        <div className="sheet-backdrop" onClick={onBackdrop} aria-hidden="true" />
      ) : (
        <button
          type="button"
          className="detail-pop-backdrop"
          onClick={onBackdrop}
          aria-label={closeLabel}
          tabIndex={-1}
        />
      )}
      {panel}
    </div>
  );
}
