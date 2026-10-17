import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { Dialog } from "./Dialog";

afterEach(() => cleanup());

function Harness({ busy = false, nested = false, autofocusSecond = false }: { busy?: boolean; nested?: boolean; autofocusSecond?: boolean }) {
  const [open, setOpen] = useState(false);
  const [inner, setInner] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open
      </button>
      <button type="button">outside</button>
      {open ? (
        <Dialog onClose={() => setOpen(false)} labelledBy="t1" describedBy="d1" busy={busy}>
          <h2 id="t1">Sample title</h2>
          <p id="d1">Sample text</p>
          <button type="button">first</button>
          <input aria-label="middle" />
          <button type="button" data-autofocus={autofocusSecond ? "" : undefined} onClick={() => setInner(true)}>
            last
          </button>
          {nested && inner ? (
            <Dialog onClose={() => setInner(false)} label="Inner">
              <button type="button">inner button</button>
            </Dialog>
          ) : null}
        </Dialog>
      ) : null}
    </>
  );
}

function openDialog() {
  const trigger = screen.getByRole("button", { name: "open" });
  trigger.focus();
  fireEvent.click(trigger);
  return trigger;
}

function AutoFocusHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open
      </button>
      {open ? (
        <Dialog onClose={() => setOpen(false)} label="Form">
          <button type="button">close</button>
          <input aria-label="name" autoFocus />
        </Dialog>
      ) : null}
    </>
  );
}

/** Like a detail pop that shows a "loading" dialog first and then a different one with data. */
function SwapHarness() {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const close = () => {
    setOpen(false);
    setLoaded(false);
  };
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open
      </button>
      {open && !loaded ? (
        <Dialog onClose={close} label="Loading">
          <button type="button" onClick={() => setLoaded(true)}>
            load
          </button>
        </Dialog>
      ) : null}
      {open && loaded ? (
        <section>
          <Dialog onClose={close} label="Loaded">
            <button type="button">done</button>
          </Dialog>
        </section>
      ) : null}
    </>
  );
}

describe("Dialog", () => {
  it("is a labelled, described modal dialog", () => {
    render(<Harness />);
    openDialog();
    const dialog = screen.getByRole("dialog", { name: "Sample title" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-describedby")).toBe("d1");
  });

  it("moves focus inside on open, to data-autofocus when present", () => {
    render(<Harness />);
    openDialog();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "first" }));
    cleanup();
    render(<Harness autofocusSecond />);
    openDialog();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "last" }));
  });

  it("keeps Tab and Shift+Tab inside the dialog", () => {
    render(<Harness />);
    openDialog();
    const first = screen.getByRole("button", { name: "first" });
    const close = screen.getByRole("button", { name: "بستن · پنجره" });
    close.focus();
    fireEvent.keyDown(document.activeElement ?? document, { key: "Tab" });
    expect(document.activeElement).toBe(first);
    first.focus();
    fireEvent.keyDown(document.activeElement ?? document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(close);
  });

  it("pulls focus back if something outside gets focus", () => {
    render(<Harness />);
    openDialog();
    act(() => screen.getByRole("button", { name: "outside", hidden: true }).focus());
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("closes on Escape and returns focus to the trigger", () => {
    render(<Harness />);
    const trigger = openDialog();
    fireEvent.keyDown(document.activeElement ?? document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("closes on backdrop click", () => {
    render(<Harness />);
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: "بستن", hidden: true }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("ignores Escape and backdrop while busy", () => {
    render(<Harness busy />);
    openDialog();
    fireEvent.keyDown(document.activeElement ?? document, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "بستن", hidden: true }));
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("locks page scroll while open", () => {
    render(<Harness />);
    openDialog();
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.keyDown(document.activeElement ?? document, { key: "Escape" });
    expect(document.body.style.overflow).toBe("");
  });

  it("with nested dialogs, Escape closes only the top one", () => {
    render(<Harness nested />);
    openDialog();
    const last = screen.getByRole("button", { name: "last" });
    last.focus();
    fireEvent.click(last);
    expect(screen.getByRole("dialog", { name: "Inner" })).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "inner button" }));
    fireEvent.keyDown(document.activeElement ?? document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Inner" })).toBeNull();
    expect(screen.getByRole("dialog", { name: "Sample title" })).toBeTruthy();
    expect(document.activeElement).toBe(last);
  });

  it("keeps an autoFocus field focused and still returns focus to the trigger", () => {
    render(<AutoFocusHarness />);
    const trigger = openDialog();
    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "name" }));
    fireEvent.keyDown(document.activeElement ?? document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("returns focus to the original trigger when one dialog is replaced by another", () => {
    render(<SwapHarness />);
    const trigger = openDialog();
    fireEvent.click(screen.getByRole("button", { name: "load" }));
    expect(screen.getByRole("dialog", { name: "Loaded" })).toBeTruthy();
    fireEvent.keyDown(document.activeElement ?? document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});
