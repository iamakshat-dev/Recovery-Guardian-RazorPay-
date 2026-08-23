import { Hero } from "../components/overview/Hero";
import { PipelinePreview } from "../components/overview/PipelinePreview";
import { ProvenanceFooter } from "../components/overview/ProvenanceFooter";
import { SafetyKpi } from "../components/overview/SafetyKpi";
import { StrategyComparison } from "../components/overview/StrategyComparison";
import { WebhookAmbiguityCase } from "../components/overview/WebhookAmbiguityCase";
import { snapshot } from "../data/snapshot";

const STRATEGY_LABELS: Record<string, string> = {
  GUARDIAN: "Guardian",
  RULES_ONLY: "Rules-only",
  NAIVE_RETRY: "Naive Retry",
  NO_ACTION: "No Action",
};

export function Overview() {
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
      <Hero />
      <SafetyKpi duplicateChargeRiskBySeed={snapshot.day9.guardianDuplicateChargeRiskBySeed} />
      <StrategyComparison strategies={strategyRows} />
      <WebhookAmbiguityCase
        transactionsEvaluated={snapshot.day9.webhookAmbiguity.comparison.GUARDIAN.transactionsEvaluated}
        totalAmountAtRisk={snapshot.day9.webhookAmbiguity.comparison.GUARDIAN.totalAmountAtRisk}
        rows={webhookRows}
        guardianBlockReconcileCount={snapshot.day9.webhookAmbiguity.guardianBlockReconcileCount}
      />
      <PipelinePreview />
      <ProvenanceFooter />
    </div>
  );
}
