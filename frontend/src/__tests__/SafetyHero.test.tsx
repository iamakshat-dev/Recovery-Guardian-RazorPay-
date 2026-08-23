import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SafetyHero } from "../pages/SafetyHero";
import { snapshot } from "../data/snapshot";

describe("SafetyHero", () => {
  it("states plainly that Guardian recovered less than Rules-only", () => {
    render(<SafetyHero />);
    expect(screen.getByText(/Guardian recovered/)).toBeInTheDocument();
    expect(screen.getByText("less")).toBeInTheDocument();
    const guardianRecovered = snapshot.day9.strategyComparison.GUARDIAN.simulatedAmountRecovered;
    const rulesOnlyRecovered = snapshot.day9.strategyComparison.RULES_ONLY.simulatedAmountRecovered;
    expect(rulesOnlyRecovered).toBeGreaterThan(guardianRecovered);
  });

  it("never claims maximum recovery, highest revenue, or production guarantees", () => {
    render(<SafetyHero />);
    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/maximum recovery/i);
    expect(body).not.toMatch(/highest revenue/i);
    expect(body).not.toMatch(/guarantees? (payment )?recovery/i);
    expect(body).not.toMatch(/100% production accuracy/i);
    expect(body).not.toMatch(/zero duplicate charges in production/i);
  });

  it("reuses the same strategy comparison and WEBHOOK_AMBIGUITY components as the Overview", () => {
    render(<SafetyHero />);
    expect(screen.getByRole("heading", { name: /strategy comparison/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "WEBHOOK_AMBIGUITY" })).toBeInTheDocument();
    expect(screen.getByText(/25\/25 BLOCK_RECONCILE/)).toBeInTheDocument();
  });

  it("renders the primary safety KPI", () => {
    render(<SafetyHero />);
    expect(screen.getByRole("heading", { name: /primary safety result/i })).toBeInTheDocument();
  });
});
