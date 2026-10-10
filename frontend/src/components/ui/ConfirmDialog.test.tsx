import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { ConfirmProvider, DELETE_CONFIRM_LABEL, useConfirm } from "./ConfirmDialog";

afterEach(() => cleanup());

function Harness({ danger = false }: { danger?: boolean }) {
  const confirm = useConfirm();
  const [answer, setAnswer] = useState("none");
  return (
    <button
      type="button"
      onClick={() => {
        void confirm("حذف", "مطمئن هستید؟", danger ? DELETE_CONFIRM_LABEL : "بله", { danger }).then((ok) =>
          setAnswer(ok ? "yes" : "no"),
        );
      }}
    >
      {answer}
    </button>
  );
}

describe("confirm dialog", () => {
  it("resolves true when confirmed", async () => {
    render(
      <ConfirmProvider>
        <Harness />
      </ConfirmProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "none" }));
    fireEvent.click(await screen.findByRole("button", { name: "بله" }));
    expect(await screen.findByRole("button", { name: "yes" })).toBeTruthy();
  });

  it("delete question: alertdialog, red confirm, Cancel focused, Escape cancels", async () => {
    render(
      <ConfirmProvider>
        <Harness danger />
      </ConfirmProvider>,
    );
    const trigger = screen.getByRole("button", { name: "none" });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = await screen.findByRole("alertdialog", { name: "حذف" });
    expect(dialog.getAttribute("aria-describedby")).toBeTruthy();
    expect(document.getElementById(dialog.getAttribute("aria-describedby") ?? "")?.textContent).toBe("مطمئن هستید؟");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "انصراف" }));
    expect(screen.getByRole("button", { name: DELETE_CONFIRM_LABEL }).className).toContain("btn-danger");
    fireEvent.keyDown(document.activeElement ?? document, { key: "Escape" });
    expect(await screen.findByRole("button", { name: "no" })).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "no" }));
  });
});
