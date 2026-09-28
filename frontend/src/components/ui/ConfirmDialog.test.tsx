import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { ConfirmProvider, useConfirm } from "./ConfirmDialog";

function Harness() {
  const confirm = useConfirm();
  const [answer, setAnswer] = useState("none");
  return (
    <button
      type="button"
      onClick={() => {
        void confirm("حذف", "مطمئن هستید؟", "بله").then((ok) => setAnswer(ok ? "yes" : "no"));
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
});
