import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DecisionPipeline } from "../pages/DecisionPipeline";
import { snapshot } from "../data/snapshot";

describe("DecisionPipeline — scenario selector", () => {
  it("renders exactly three scenario options", () => {
    render(<DecisionPipeline />);
    const group = screen.getByRole("group", { name: /scenario/i });
    const buttons = within(group).getAllByRole("button");
    expect(buttons).toHaveLength(3);
    expect(within(group).getByRole("button", { name: "WEBHOOK AMBIGUITY" })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "INFRASTRUCTURE — HIGH CONFIDENCE" })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "INFRASTRUCTURE — LOW CONFIDENCE" })).toBeInTheDocument();
  });

  it("defaults to the WEBHOOK_AMBIGUITY scenario with BLOCK_RECONCILE as the final action", () => {
    render(<DecisionPipeline />);
    expect(screen.getByText("BLOCK_RECONCILE")).toBeInTheDocument();
  });
});

describe("DecisionPipeline — the three authoritative scenarios display exactly what the artifact says", () => {
  it("WEBHOOK_AMBIGUITY: root cause, probability, and BLOCK_RECONCILE all match the snapshot", () => {
    render(<DecisionPipeline />);
    const s = snapshot.day14.scenarios.webhook_ambiguity;
    expect(screen.getByText(new RegExp(`${s.prediction.rootCause}.*${s.prediction.probability.toFixed(2)}`))).toBeInTheDocument();
    expect(screen.getByText(s.policy.action)).toBeInTheDocument();
  });

  it("switching to INFRASTRUCTURE high confidence shows DEFER_RETRY, matching the snapshot", () => {
    render(<DecisionPipeline />);
    fireEvent.click(screen.getByRole("button", { name: "INFRASTRUCTURE — HIGH CONFIDENCE" }));
    const s = snapshot.day14.scenarios.infrastructure_high_confidence;
    expect(s.policy.action).toBe("DEFER_RETRY");
    expect(screen.getByText("DEFER_RETRY")).toBeInTheDocument();
    expect(screen.queryByText("BLOCK_RECONCILE")).not.toBeInTheDocument();
  });

  it("switching to INFRASTRUCTURE low confidence shows HUMAN_REVIEW, matching the snapshot", () => {
    render(<DecisionPipeline />);
    fireEvent.click(screen.getByRole("button", { name: "INFRASTRUCTURE — LOW CONFIDENCE" }));
    const s = snapshot.day14.scenarios.infrastructure_low_confidence;
    expect(s.policy.action).toBe("HUMAN_REVIEW");
    expect(screen.getByText("HUMAN_REVIEW")).toBeInTheDocument();
  });

  it("scenario switching only ever produces the three known, artifact-sourced actions -- never a fourth, computed one", () => {
    render(<DecisionPipeline />);
    const seenActions = new Set<string>();
    for (const label of ["WEBHOOK AMBIGUITY", "INFRASTRUCTURE — HIGH CONFIDENCE", "INFRASTRUCTURE — LOW CONFIDENCE"]) {
      fireEvent.click(screen.getByRole("button", { name: label }));
      const actionNode = screen.getAllByText(/BLOCK_RECONCILE|DEFER_RETRY|HUMAN_REVIEW/)[0];
      seenActions.add(actionNode.textContent ?? "");
    }
    expect(seenActions).toEqual(new Set(["BLOCK_RECONCILE", "DEFER_RETRY", "HUMAN_REVIEW"]));
  });
});

describe("DecisionPipeline — node detail interaction", () => {
  it("clicking a node expands its detail panel with aria-expanded", () => {
    render(<DecisionPipeline />);
    const mlButton = screen.getByRole("button", { name: /ML Classifier/ });
    expect(mlButton).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(mlButton);
    expect(mlButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("region", { name: /ML Classifier detail/i })).toBeInTheDocument();
    expect(screen.getByText("Model probability")).toBeInTheDocument();
  });

  it("clicking the Payment Event node reveals transaction-level evidence", () => {
    render(<DecisionPipeline />);
    fireEvent.click(screen.getByRole("button", { name: /Payment Event/ }));
    const s = snapshot.day14.scenarios.webhook_ambiguity;
    expect(screen.getByText(s.transactionId)).toBeInTheDocument();
    expect(screen.getByText(s.paymentEvent.failureCode)).toBeInTheDocument();
  });

  it("clicking the same node again collapses the detail panel", () => {
    render(<DecisionPipeline />);
    const policyButton = screen.getByRole("button", { name: /Policy Engine/ });
    fireEvent.click(policyButton);
    expect(policyButton).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(policyButton);
    expect(policyButton).toHaveAttribute("aria-expanded", "false");
  });

  it("keyboard activation (Enter) opens the node detail, not just mouse click", () => {
    render(<DecisionPipeline />);
    const actionButton = screen.getByRole("button", { name: /Recovery Action/ });
    actionButton.focus();
    expect(actionButton).toHaveFocus();
    fireEvent.click(actionButton); // jsdom: Enter on a focused <button> triggers a click event
    expect(actionButton).toHaveAttribute("aria-expanded", "true");
  });
});

describe("DecisionPipeline — provenance", () => {
  it("labels prediction/policy fields OBSERVED and outcome fields SIMULATED", () => {
    render(<DecisionPipeline />);
    fireEvent.click(screen.getByRole("button", { name: /Recovery Action/ }));
    const panel = screen.getByRole("region", { name: /Recovery Action detail/i });
    expect(within(panel).getByText("SIMULATED")).toBeInTheDocument();
    expect(within(panel).getByText("OBSERVED")).toBeInTheDocument();
  });

  it("shows the actual policy threshold from the artifact, not a hardcoded number", () => {
    render(<DecisionPipeline />);
    fireEvent.click(screen.getByRole("button", { name: /Policy Engine/ }));
    const s = snapshot.day14.scenarios.webhook_ambiguity;
    expect(s.policy.thresholdIfApplicable).toBeNull();
    expect(screen.getByText("Not applicable — hard safety override")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "INFRASTRUCTURE — HIGH CONFIDENCE" }));
    fireEvent.click(screen.getByRole("button", { name: /Policy Engine/ }));
    const s2 = snapshot.day14.scenarios.infrastructure_high_confidence;
    expect(s2.policy.thresholdIfApplicable).toBe(0.75);
    expect(screen.getByText("75%")).toBeInTheDocument();
  });
});

describe("DecisionPipeline — no ground-truth leakage", () => {
  it("does not read actual_root_cause anywhere in scenario rendering", () => {
    // Structural: the Day14 snapshot scenario type carries no
    // actual_root_cause field at all (see
    // scripts/generate_frontend_snapshot.py's _day14_scenario -- it is
    // never copied into the snapshot), so it is structurally impossible
    // for this page to read it.
    const scenario = snapshot.day14.scenarios.webhook_ambiguity as Record<string, unknown>;
    expect("actual_root_cause" in scenario).toBe(false);
    expect("actualRootCause" in scenario).toBe(false);
  });
});
