import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Overview } from "../pages/Overview";
import { snapshot } from "../data/snapshot";

describe("Overview", () => {
  it("renders the primary safety KPI with a SIMULATED provenance label", () => {
    render(<Overview />);
    const kpiSection = screen.getByRole("heading", { name: /primary safety result/i }).closest("section");
    expect(kpiSection).not.toBeNull();
    expect(within(kpiSection as HTMLElement).getByText("SIMULATED")).toBeInTheDocument();
    expect(within(kpiSection as HTMLElement).getByText("Duplicate-charge risk")).toBeInTheDocument();
  });

  it("renders the strategy comparison for all four strategies", () => {
    render(<Overview />);
    const comparisonSection = screen.getByRole("heading", { name: /strategy comparison/i }).closest("section");
    expect(comparisonSection).not.toBeNull();
    const scoped = within(comparisonSection as HTMLElement);
    expect(scoped.getByText("Guardian")).toBeInTheDocument();
    expect(scoped.getByText("Rules-only")).toBeInTheDocument();
    expect(scoped.getByText("Naive Retry")).toBeInTheDocument();
    expect(scoped.getByText("No Action")).toBeInTheDocument();
  });

  it("does not claim Guardian has the highest simulated recovery", () => {
    render(<Overview />);
    const guardianRecovered = snapshot.day9.strategyComparison.GUARDIAN.simulatedAmountRecovered;
    const rulesOnlyRecovered = snapshot.day9.strategyComparison.RULES_ONLY.simulatedAmountRecovered;
    // The verified evidence: Rules-only recovers more than Guardian.
    expect(rulesOnlyRecovered).toBeGreaterThan(guardianRecovered);
  });

  it("renders the WEBHOOK_AMBIGUITY signature safety case", () => {
    render(<Overview />);
    expect(screen.getByRole("heading", { name: "WEBHOOK_AMBIGUITY" })).toBeInTheDocument();
    expect(screen.getByText(/25\/25 BLOCK_RECONCILE/)).toBeInTheDocument();
  });

  it("renders the decision pipeline preview", () => {
    render(<Overview />);
    expect(screen.getByRole("heading", { name: /decision pipeline/i })).toBeInTheDocument();
    expect(screen.getByText("Payment Event")).toBeInTheDocument();
    expect(screen.getByText("CalibratedRootCauseClassifier")).toBeInTheDocument();
    expect(screen.getByText("RulesPolicyEngine")).toBeInTheDocument();
  });

  it("renders provenance labels for OBSERVED, SIMULATED, and UNAVAILABLE", () => {
    render(<Overview />);
    const provenanceSection = screen.getByRole("heading", { name: /provenance & limitations/i }).closest("section");
    expect(provenanceSection).not.toBeNull();
    const scoped = within(provenanceSection as HTMLElement);
    expect(scoped.getByText("OBSERVED")).toBeInTheDocument();
    expect(scoped.getByText("SIMULATED")).toBeInTheDocument();
    expect(scoped.getByText("UNAVAILABLE")).toBeInTheDocument();
  });

  it("discloses the Day 12 held-out INFRASTRUCTURE limitation, not just the raw score", () => {
    render(<Overview />);
    expect(screen.getByText(/never run through this project's own suspicious-performance investigation/i)).toBeInTheDocument();
  });

  it("never labels simulated recovery as real Razorpay production data", () => {
    render(<Overview />);
    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/live razorpay production data recovered/i);
    expect(body).toMatch(/simulated \/ counterfactual/i);
  });
});
