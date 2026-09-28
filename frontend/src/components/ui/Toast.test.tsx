import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { ToastProvider, useToast } from "./Toast";

function Harness() {
  const toast = useToast();
  const [seen, setSeen] = useState("");
  return (
    <button
      type="button"
      onClick={() => {
        toast("ثبت شد");
        setSeen("yes");
      }}
    >
      {seen || "go"}
    </button>
  );
}

describe("toast", () => {
  it("shows a message", () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("status").textContent).toContain("ثبت شد");
  });
});
