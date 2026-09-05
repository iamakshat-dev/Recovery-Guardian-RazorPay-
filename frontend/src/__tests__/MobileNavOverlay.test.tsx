import { useRef, useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MobileNavOverlay } from "../components/shell/MobileNavOverlay";

function Harness() {
  const [open, setOpen] = useState(true);
  const triggerRef = useRef<HTMLButtonElement>(null);
  return (
    <div>
      <button ref={triggerRef} type="button">
        Menu
      </button>
      <MobileNavOverlay
        activeSection="overview"
        onNavigate={() => {}}
        open={open}
        onClose={() => setOpen(false)}
        triggerRef={triggerRef}
      />
    </div>
  );
}

describe("MobileNavOverlay — keyboard behavior", () => {
  it("is a labeled dialog when open, and absent from the DOM when closed", () => {
    render(<Harness />);
    expect(screen.getByRole("dialog", { name: /navigation menu/i })).toBeInTheDocument();
  });

  it("closes on Escape", () => {
    render(<Harness />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("moves initial focus into the panel when opened", () => {
    render(<Harness />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("returns focus to the trigger button after closing", () => {
    render(<Harness />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Menu" }));
  });
});
