import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StrategyComparison } from "../components/overview/StrategyComparison";
import { SafetyKpi } from "../components/overview/SafetyKpi";
import { WebhookAmbiguityCase } from "../components/overview/WebhookAmbiguityCase";
import { UnavailableMetric } from "../components/ui/UnavailableMetric";
import { ProvenanceBadge } from "../components/ui/ProvenanceBadge";
import {
  isKnownProvenance,
  isKnownRecoveryAction,
  isValidAmount,
  isValidCount,
  isValidPercentage,
} from "../lib/validate";

describe("visual data integrity — unavailable states (spec section 33/34)", () => {
  it("StrategyComparison shows DATA UNAVAILABLE instead of a fabricated zero when the artifact is malformed", () => {
    render(
      <StrategyComparison
        strategies={[
          { name: "Guardian", simulatedAmountRecovered: NaN, recoveryRate: 2, duplicateChargeRiskCount: -1 },
        ]}
      />
    );
    expect(screen.getByText("DATA UNAVAILABLE")).toBeInTheDocument();
    expect(screen.queryByText("₹0.00")).not.toBeInTheDocument();
  });

  it("SafetyKpi shows DATA UNAVAILABLE instead of a fabricated zero when seed data is invalid", () => {
    render(<SafetyKpi duplicateChargeRiskBySeed={{ "42": -5 }} />);
    expect(screen.getByText("DATA UNAVAILABLE")).toBeInTheDocument();
  });

  it("WebhookAmbiguityCase shows DATA UNAVAILABLE instead of a fabricated zero when rows are invalid", () => {
    render(
      <WebhookAmbiguityCase
        transactionsEvaluated={-1}
        totalAmountAtRisk={NaN}
        rows={[]}
        guardianBlockReconcileCount={-1}
      />
    );
    expect(screen.getByText("DATA UNAVAILABLE")).toBeInTheDocument();
  });

  it("UnavailableMetric renders the label and DATA UNAVAILABLE text", () => {
    render(<UnavailableMetric label="Test metric" reason="Artifact missing." />);
    expect(screen.getByText("Test metric")).toBeInTheDocument();
    expect(screen.getByText("DATA UNAVAILABLE")).toBeInTheDocument();
    expect(screen.getByText("Artifact missing.")).toBeInTheDocument();
  });

  it("ProvenanceBadge falls back to UNAVAILABLE for an unrecognized provenance value rather than rendering it as-is", () => {
    render(<ProvenanceBadge value="TOTALLY_MADE_UP" />);
    expect(screen.getByText("UNAVAILABLE")).toBeInTheDocument();
    expect(screen.queryByText("TOTALLY_MADE_UP")).not.toBeInTheDocument();
  });
});

describe("validate.ts — known-value gates", () => {
  it("rejects invalid amounts, percentages, and counts", () => {
    expect(isValidAmount(-1)).toBe(false);
    expect(isValidAmount(NaN)).toBe(false);
    expect(isValidAmount(100)).toBe(true);

    expect(isValidPercentage(1.5)).toBe(false);
    expect(isValidPercentage(0.28)).toBe(true);

    expect(isValidCount(1.5)).toBe(false);
    expect(isValidCount(-1)).toBe(false);
    expect(isValidCount(3)).toBe(true);
  });

  it("only recognizes the five real RecoveryAction values", () => {
    expect(isKnownRecoveryAction("BLOCK_RECONCILE")).toBe(true);
    expect(isKnownRecoveryAction("DEFER_RETRY")).toBe(true);
    expect(isKnownRecoveryAction("MAYBE_RETRY")).toBe(false);
  });

  it("only recognizes OBSERVED / SIMULATED / UNAVAILABLE provenance", () => {
    expect(isKnownProvenance("OBSERVED")).toBe(true);
    expect(isKnownProvenance("SIMULATED")).toBe(true);
    expect(isKnownProvenance("UNAVAILABLE")).toBe(true);
    expect(isKnownProvenance("LIVE")).toBe(false);
  });
});
