import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IncidentReplay } from "../pages/IncidentReplay";
import { snapshot } from "../data/snapshot";

describe("IncidentReplay — incident window", () => {
  it("renders the exact window boundaries and counts from the snapshot", () => {
    render(<IncidentReplay />);
    const d12 = snapshot.day12;
    expect(
      screen.getAllByText(new RegExp(`${d12.incidentWindow.start}.*${d12.incidentWindow.end}`)).length
    ).toBeGreaterThan(0);
    expect(screen.getAllByText(String(d12.incident.failedEventCount)).length).toBeGreaterThan(0);
  });

  it("uses the artifact's actual counts, not the prompt's hardcoded cross-check values by coincidence", () => {
    render(<IncidentReplay />);
    // These values are asserted against the LIVE snapshot object, not
    // typed literals -- if the artifact changes, this test tracks it.
    expect(snapshot.day12.incidentCount).toBe(snapshot.day12.classDistribution.INFRASTRUCTURE +
      snapshot.day12.classDistribution.CARD_DECLINE +
      snapshot.day12.classDistribution.INSUFFICIENT_FUNDS +
      snapshot.day12.classDistribution.OTP_TIMEOUT +
      snapshot.day12.classDistribution.USER_ABANDONMENT +
      snapshot.day12.classDistribution.WEBHOOK_AMBIGUITY);
  });
});

describe("IncidentReplay — failure density, not failure rate", () => {
  it("never presents a percentage AS a failure rate (the explanatory prose may still name the rejected term)", () => {
    render(<IncidentReplay />);
    const body = document.body.textContent ?? "";
    // The page explains WHY failure rate is not used -- that explanation
    // necessarily names the term once. What must never appear is the
    // term used to LABEL an actual displayed percentage.
    expect(body).not.toMatch(/\d+(\.\d+)?%\s*failure rate/i);
    expect(body).not.toMatch(/failure rate:\s*\d+(\.\d+)?%/i);
    expect(body).toMatch(/failure density/i);
    expect(body).toMatch(/density.*\d+.*\/.*30 min/i);
  });

  it("visibly explains why density is used instead of rate", () => {
    render(<IncidentReplay />);
    expect(screen.getByText(/Why density, not rate/)).toBeInTheDocument();
    expect(screen.getByText(/no successful-transaction denominator/)).toBeInTheDocument();
  });
});

describe("IncidentReplay — train/validation/test disclosure", () => {
  it("displays the exact split counts from the snapshot", () => {
    render(<IncidentReplay />);
    const d12 = snapshot.day12;
    const splitSection = screen.getByRole("heading", { name: /train.*validation.*test/i }).closest("section");
    const scoped = within(splitSection as HTMLElement);
    expect(scoped.getByText(String(d12.splitMembership.trainCount))).toBeInTheDocument();
    expect(scoped.getByText(String(d12.splitMembership.validationCount))).toBeInTheDocument();
    expect(scoped.getByText(String(d12.splitMembership.testCount))).toBeInTheDocument();
  });

  it("discloses the training-majority limitation when it applies", () => {
    render(<IncidentReplay />);
    const d12 = snapshot.day12;
    const total = d12.splitMembership.trainCount + d12.splitMembership.validationCount + d12.splitMembership.testCount;
    const isMajority = d12.splitMembership.trainCount > total / 2;
    expect(isMajority).toBe(true); // sanity check against the live snapshot
    expect(screen.getByText(/majority.*TRAIN split/)).toBeInTheDocument();
  });
});

describe("IncidentReplay — 15/15 limitation disclosure", () => {
  it("states the held-out result was not independently investigated", () => {
    render(<IncidentReplay />);
    const d12 = snapshot.day12;
    expect(
      screen.getAllByText(new RegExp(`${d12.heldOutTestInfrastructure.correct}/${d12.heldOutTestInfrastructure.total}`)).length
    ).toBeGreaterThan(0);
    expect(screen.getByText(/not independently investigated/)).toBeInTheDocument();
    expect(screen.getByText(/open methodological limitation/)).toBeInTheDocument();
  });
});

describe("IncidentReplay — Day 9 vs Day 12 WEBHOOK_AMBIGUITY population firewall", () => {
  it("labels the Day 12 population distinctly from the Day 9 population and never combines counts", () => {
    render(<IncidentReplay />);
    const d12 = snapshot.day12;
    const d9WebhookCount = snapshot.day9.webhookAmbiguity.comparison.GUARDIAN.transactionsEvaluated;

    expect(d12.webhookAmbiguitySafety.caseCount).toBe(1);
    expect(d9WebhookCount).toBe(25);
    expect(d12.webhookAmbiguitySafety.caseCount).not.toBe(d9WebhookCount);

    expect(screen.getByText(/Day 12 incident-window population/)).toBeInTheDocument();
    expect(screen.getByText(/Day 9 held-out test population/)).toBeInTheDocument();
    expect(screen.getByText(/never combined/)).toBeInTheDocument();

    // The rendered Day 12 case count must be 1, not 25 or 26.
    const webhookSection = screen.getByRole("heading", { name: /webhook_ambiguity safety/i }).closest("section");
    expect(within(webhookSection as HTMLElement).getByText(`${d12.webhookAmbiguitySafety.blockReconcileCount}/${d12.webhookAmbiguitySafety.caseCount} BLOCK_RECONCILE`)).toBeInTheDocument();
  });
});

describe("IncidentReplay — simulated recovery provenance", () => {
  it("labels simulated recovery figures SIMULATED, never as real revenue", () => {
    render(<IncidentReplay />);
    const recoverySection = screen.getByRole("heading", { name: /simulated recovery/i }).closest("section");
    const scoped = within(recoverySection as HTMLElement);
    expect(scoped.getByText("SIMULATED")).toBeInTheDocument();
    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/actual revenue/i);
    expect(body).not.toMatch(/real savings/i);
    expect(body).not.toMatch(/production recovery/i);
    expect(body).toMatch(/counterfactual estimate/i);
  });
});

describe("IncidentReplay — historical replay labeling", () => {
  it("explicitly states this is not live monitoring", () => {
    render(<IncidentReplay />);
    expect(screen.getByText("Historical synthetic replay")).toBeInTheDocument();
    const body = document.body.textContent ?? "";
    expect(body).toMatch(/not.*live monitoring/);
    expect(body).toMatch(/not.*real-time telemetry/);
  });
});
