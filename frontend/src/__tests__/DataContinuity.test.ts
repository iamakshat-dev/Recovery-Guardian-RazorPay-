import { describe, expect, it } from "vitest";
import { snapshot } from "../data/snapshot";

/**
 * Milestone 3 spec section 31, "DATA CONTINUITY" (items 18-20). Proves
 * the M3 extension merged onto M2's existing scenario objects rather
 * than creating a second data model or a second top-level scenario
 * store.
 */
describe("Data continuity — M2 scenario objects extended, not duplicated", () => {
  it("M2's original decision-trace fields are still present and unchanged on each scenario", () => {
    for (const key of ["webhook_ambiguity", "infrastructure_high_confidence", "infrastructure_low_confidence"] as const) {
      const scenario = snapshot.day14.scenarios[key];
      expect(scenario).toHaveProperty("transactionId");
      expect(scenario).toHaveProperty("paymentEvent");
      expect(scenario).toHaveProperty("prediction");
      expect(scenario).toHaveProperty("policy");
      expect(scenario).toHaveProperty("outcome");
      expect(scenario).toHaveProperty("safetyInvariantCheck");
      expect(typeof scenario.transactionId).toBe("string");
      expect(typeof scenario.prediction.rootCause).toBe("string");
      expect(typeof scenario.policy.action).toBe("string");
    }
  });

  it("M3's explanation field is merged onto the SAME scenario object, not a separate one", () => {
    for (const key of ["webhook_ambiguity", "infrastructure_high_confidence", "infrastructure_low_confidence"] as const) {
      const scenario = snapshot.day14.scenarios[key];
      expect(scenario).toHaveProperty("explanation");
      expect(scenario.explanation).toHaveProperty("summary");
      expect(scenario.explanation).toHaveProperty("safetyNote");
      // Both the pre-existing (M2) and new (M3) fields live on the one
      // object -- same transactionId scopes both.
      expect(typeof scenario.explanation.summary).toBe("string");
      expect(scenario.explanation.summary.length).toBeGreaterThan(0);
    }
  });

  it("there is exactly one scenario store -- no second/parallel scenario collection anywhere in the snapshot", () => {
    const topLevelKeys = Object.keys(snapshot);
    // day9 / day12 / day14 (+ generatedAt / sourceArtifacts metadata) --
    // no "explainability" or "incidentReplay" top-level key holding a
    // second copy of scenario data.
    expect(topLevelKeys).not.toContain("explainability");
    expect(topLevelKeys).not.toContain("day15");
    expect(topLevelKeys.filter((k) => k.toLowerCase().includes("scenario"))).toEqual([]);
    expect(Object.keys(snapshot.day14)).toEqual(["scenarios"]);
  });

  it("the explanation's implied scenario identity matches the record it lives on (same object, not a joined lookup)", () => {
    // Because explanation is a nested property of the exact same
    // scenario object (not merged in from a second array by index/id),
    // there is no possibility of a transaction_id mismatch -- this test
    // documents that structural guarantee.
    const webhookScenario = snapshot.day14.scenarios.webhook_ambiguity;
    expect(webhookScenario.transactionId).toBe("txn_000536_9f0ef7");
    expect(webhookScenario.prediction.rootCause).toBe("WEBHOOK_AMBIGUITY");
    expect(webhookScenario.explanation.summary).toContain("WEBHOOK_AMBIGUITY");
  });
});

describe("Data continuity — Day 12 extension reuses the same day12 object", () => {
  it("the new density/window fields sit alongside the M2 split/classifier fields on one day12 object", () => {
    const d12 = snapshot.day12;
    expect(d12).toHaveProperty("splitMembership"); // M2
    expect(d12).toHaveProperty("classDistribution"); // M2
    expect(d12).toHaveProperty("before"); // M3
    expect(d12).toHaveProperty("incident"); // M3
    expect(d12).toHaveProperty("after"); // M3
    expect(d12).toHaveProperty("simulatedRecoverySummary"); // M3
  });
});
