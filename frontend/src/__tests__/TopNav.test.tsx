import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TopNav } from "../components/shell/TopNav";
import { NAV_ITEMS } from "../components/shell/navigation";

describe("TopNav — active state and semantics", () => {
  it("marks the active section with aria-current=page, and only that one", () => {
    const ref = createRef<HTMLButtonElement>();
    render(
      <TopNav
        activeSection="recovery"
        onNavigate={() => {}}
        onOpenMobileMenu={() => {}}
        mobileMenuOpen={false}
        menuTriggerRef={ref}
      />
    );
    const current = screen.getAllByRole("button", { name: "Recovery" }).filter(
      (b) => b.getAttribute("aria-current") === "page"
    );
    expect(current).toHaveLength(1);

    for (const item of NAV_ITEMS) {
      if (item.id === "recovery" || !item.enabled) continue;
      const btn = screen.getByRole("button", { name: item.label });
      expect(btn.getAttribute("aria-current")).toBeNull();
    }
  });

  it("renders every enabled nav item as a real, distinctly-labeled route (no invented routes)", () => {
    const ref = createRef<HTMLButtonElement>();
    render(
      <TopNav
        activeSection="overview"
        onNavigate={() => {}}
        onOpenMobileMenu={() => {}}
        mobileMenuOpen={false}
        menuTriggerRef={ref}
      />
    );
    for (const item of NAV_ITEMS) {
      expect(screen.getByRole("button", { name: item.label })).toBeInTheDocument();
    }
  });

  it("stays visible via a sticky header, not a scroll-hijacking pinned section", () => {
    const ref = createRef<HTMLButtonElement>();
    render(
      <TopNav
        activeSection="overview"
        onNavigate={() => {}}
        onOpenMobileMenu={() => {}}
        mobileMenuOpen={false}
        menuTriggerRef={ref}
      />
    );
    const header = document.querySelector("header");
    expect(header?.className).toMatch(/sticky/);
  });
});
