import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ThemeToggle } from "../components/shell/ThemeToggle";

describe("ThemeToggle", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });
  afterEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("toggles the document's data-theme attribute and persists the choice", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button");

    fireEvent.click(button);
    const firstTheme = document.documentElement.dataset.theme;
    expect(["dark", "light"]).toContain(firstTheme);
    expect(window.localStorage.getItem("recovery-guardian:theme")).toBe(firstTheme);

    fireEvent.click(button);
    const secondTheme = document.documentElement.dataset.theme;
    expect(secondTheme).not.toBe(firstTheme);
    expect(window.localStorage.getItem("recovery-guardian:theme")).toBe(secondTheme);
  });

  it("reflects the toggled state via aria-pressed", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button");
    const before = button.getAttribute("aria-pressed");
    fireEvent.click(button);
    expect(button.getAttribute("aria-pressed")).not.toBe(before);
  });
});
