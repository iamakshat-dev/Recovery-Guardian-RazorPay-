import { SafetyKpi } from "../components/overview/SafetyKpi";
import { StrategyComparison } from "../components/overview/StrategyComparison";
import { WebhookAmbiguityCase } from "../components/overview/WebhookAmbiguityCase";
import { ProvenanceBadge } from "../components/ui/ProvenanceBadge";
import { snapshot } from "../data/snapshot";

const STRATEGY_LABELS: Record<string, string> = {
  GUARDIAN: "Guardian",
  RULES_ONLY: "Rules-only",
  NAIVE_RETRY: "Naive Retry",
  NO_ACTION: "No Action",
};

/**
 * Dedicated Safety Hero (Milestone 2 spec sections 13-15). Reuses the
 * exact StrategyComparison and WebhookAmbiguityCase components already
 * built and tested in Milestone 1 (fed the same snapshot data) rather
 * than reimplementing the same comparison a second time — one source of
 * truth for both the Overview's summary and this dedicated page's
 * deeper framing.
 */
export function SafetyHero() {
  const strategyRows = (["GUARDIAN", "RULES_ONLY", "NAIVE_RETRY", "NO_ACTION"] as const).map((key) => ({
    name: STRATEGY_LABELS[key],
    simulatedAmountRecovered: snapshot.day9.strategyComparison[key].simulatedAmountRecovered,
    recoveryRate: snapshot.day9.strategyComparison[key].recoveryRate,
    duplicateChargeRiskCount: snapshot.day9.strategyComparison[key].duplicateChargeRiskCount,
    isGuardian: key === "GUARDIAN",
  }));

  const webhookRows = (["NAIVE_RETRY", "RULES_ONLY", "GUARDIAN"] as const).map((key) => ({
    name: STRATEGY_LABELS[key],
    recoveryRate: snapshot.day9.webhookAmbiguity.comparison[key].recoveryRate,
    duplicateChargeRiskCount: snapshot.day9.webhookAmbiguity.comparison[key].duplicateChargeRiskCount,
  }));

  return (
    <div>
      <section className="border-b border-border px-6 py-14 md:px-10 md:py-20">
        <div className="mx-auto max-w-4xl">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Safety</p>
          <h1 className="mt-4 text-3xl font-semibold leading-tight tracking-tight text-text-primary md:text-5xl">
            Safety is enforced before recovery is optimized.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-text-secondary">
            Guardian recovered <span className="font-mono text-text-primary">less</span> simulated revenue than
            Rules-only in this experiment. It nevertheless produced{" "}
            <span className="font-mono text-safety">zero</span> duplicate-charge-risk outcomes across every tested
            seed. That trade-off is the product, not a caveat.
          </p>
          <div className="mt-8">
            <ProvenanceBadge value="SIMULATED" />
          </div>
        </div>
      </section>

      <SafetyKpi duplicateChargeRiskBySeed={snapshot.day9.guardianDuplicateChargeRiskBySeed} />
      <StrategyComparison strategies={strategyRows} />
      <WebhookAmbiguityCase
        transactionsEvaluated={snapshot.day9.webhookAmbiguity.comparison.GUARDIAN.transactionsEvaluated}
        totalAmountAtRisk={snapshot.day9.webhookAmbiguity.comparison.GUARDIAN.totalAmountAtRisk}
        rows={webhookRows}
        guardianBlockReconcileCount={snapshot.day9.webhookAmbiguity.guardianBlockReconcileCount}
      />
    </div>
  );
}
