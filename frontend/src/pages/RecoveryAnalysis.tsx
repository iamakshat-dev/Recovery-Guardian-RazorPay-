import { SafetyKpi } from "../components/overview/SafetyKpi";
import { StrategyComparison } from "../components/overview/StrategyComparison";
import { WebhookAmbiguityCase } from "../components/overview/WebhookAmbiguityCase";
import { RecoveryVsSafetyChart } from "../components/recovery/RecoveryVsSafetyChart";
import { RootCauseMatrix } from "../components/recovery/RootCauseMatrix";
import { SeedSensitivityTable } from "../components/recovery/SeedSensitivityTable";
import { ProvenanceBadge } from "../components/ui/ProvenanceBadge";
import { formatCount, formatPercent, formatRupees } from "../lib/format";
import { snapshot } from "../data/snapshot";

const STRATEGY_LABELS: Record<string, string> = {
  NAIVE_RETRY: "Naive Retry",
  RULES_ONLY: "Rules-only",
  GUARDIAN: "Guardian",
  NO_ACTION: "No Action",
};

// Experiment order, not a Guardian-first ranking (Milestone 4 spec
// section 13): Naive Retry, Rules-only, Guardian, No Action.
const STRATEGY_ORDER = ["NAIVE_RETRY", "RULES_ONLY", "GUARDIAN", "NO_ACTION"] as const;

/**
 * Recovery Analysis (Day 15 Milestone 4). The safety-constrained-
 * recovery narrative: Guardian does not maximize raw simulated
 * recovery, and this page does not imply otherwise anywhere. Every
 * number is read from `snapshot.day10` (experiments/results/
 * day10_analysis.json, unmodified) or `snapshot.day9` (Day 9's
 * WEBHOOK_AMBIGUITY population) — nothing here is computed by the
 * frontend.
 */
export function RecoveryAnalysis() {
  const d10 = snapshot.day10;
  const d9 = snapshot.day9;

  const chartPoints = STRATEGY_ORDER.map((key) => ({
    strategy: STRATEGY_LABELS[key],
    simulatedAmountRecovered: d10.strategyTable[key].simulatedAmountRecovered,
    duplicateChargeRiskCount: d10.strategyTable[key].duplicateChargeRiskCount,
    recoveryRate: d10.strategyTable[key].recoveryRate,
    isGuardian: key === "GUARDIAN",
  }));

  const strategyRows = STRATEGY_ORDER.map((key) => ({
    name: STRATEGY_LABELS[key],
    simulatedAmountRecovered: d10.strategyTable[key].simulatedAmountRecovered,
    recoveryRate: d10.strategyTable[key].recoveryRate,
    duplicateChargeRiskCount: d10.strategyTable[key].duplicateChargeRiskCount,
    isGuardian: key === "GUARDIAN",
  }));

  const webhookRows = (["NAIVE_RETRY", "RULES_ONLY", "GUARDIAN"] as const).map((key) => ({
    name: STRATEGY_LABELS[key],
    recoveryRate: d9.webhookAmbiguity.comparison[key].recoveryRate,
    duplicateChargeRiskCount: d9.webhookAmbiguity.comparison[key].duplicateChargeRiskCount,
  }));

  const combined = d10.combinedCardDeclineInsufficientFunds;
  const infra = d10.rootCauseTable.INFRASTRUCTURE;
  const seeds = [String(d10.primarySeed), ...d10.sensitivitySeeds.map(String)];

  return (
    <div className="px-6 py-14 md:px-10">
      <div className="mx-auto max-w-4xl">
        {/* Hero */}
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Recovery Analysis</p>
        <h1 className="mt-2 text-2xl font-semibold text-text-primary md:text-3xl">
          Recovery, constrained by safety.
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-text-secondary">
          Four strategies trade simulated recovery against duplicate-charge risk under identical evidence, outcomes,
          and controlled randomness (Common Random Numbers, Day 9). Guardian does not maximize raw recovery — it is
          the safety-constrained strategy.
        </p>
        <div className="mt-6">
          <ProvenanceBadge value="SIMULATED" />
        </div>

        {/* Primary headline metric — reused SafetyKpi, not a recovery-amount headline */}
        <div className="-mx-6 mt-8 md:-mx-10">
          <SafetyKpi duplicateChargeRiskBySeed={d9.guardianDuplicateChargeRiskBySeed} />
        </div>

        {/* Recovery vs Safety chart */}
        <section aria-labelledby="recovery-safety-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="recovery-safety-heading" className="text-lg font-semibold text-text-primary">
            Recovery vs safety
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-text-secondary">
            One aggregate point per strategy — not a per-transaction or per-seed view. Further right is more
            simulated recovery; lower is safer.
          </p>
          <div className="mt-6">
            <RecoveryVsSafetyChart points={chartPoints} />
          </div>
        </section>

        {/* Strategy comparison — experiment order, not Guardian-first.
            StrategyComparison renders its own complete section (heading +
            provenance badge) -- not wrapped in a redundant one here. */}
        <div className="-mx-6 mt-10 border-t border-border md:-mx-10">
          <StrategyComparison strategies={strategyRows} />
        </div>

        {/* Interpretation */}
        <section aria-labelledby="interpretation-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="interpretation-heading" className="text-lg font-semibold text-text-primary">
            Interpretation
          </h2>
          <ul className="mt-4 space-y-2 text-sm text-text-secondary">
            <li>
              <strong className="font-medium text-text-primary">Rules-only</strong> achieved the highest raw
              simulated recovery ({formatRupees(d10.strategyTable.RULES_ONLY.simulatedAmountRecovered)}).
            </li>
            <li>
              <strong className="font-medium text-text-primary">Guardian</strong> achieved lower raw simulated
              recovery ({formatRupees(d10.strategyTable.GUARDIAN.simulatedAmountRecovered)}) than both Rules-only
              and Naive Retry, and produced{" "}
              <strong className="font-medium text-safety">zero</strong> duplicate-charge risk across seeds{" "}
              {seeds.join(", ")}.
            </li>
            <li>
              <strong className="font-medium text-text-primary">Naive Retry</strong> was more aggressive (blanket
              retry) but did not outperform Rules-only on aggregate recovery, while carrying the highest duplicate-
              charge risk ({formatCount(d10.strategyTable.NAIVE_RETRY.duplicateChargeRiskCount)}).
            </li>
            <li>Higher recovery is not automatically better when the additional recovery carries safety exposure.</li>
            <li className="text-xs text-text-muted">
              Transaction-level paired analysis (Day 10): Guardian vs Rules-only differ on{" "}
              {d10.mcnemarGuardianVsRulesOnly.discordantN} of {d10.strategyTable.GUARDIAN.transactions} transactions
              (McNemar exact, p={d10.mcnemarGuardianVsRulesOnly.pValue.toFixed(4)}) — reported as measured, not as a
              claim of production effectiveness.
            </li>
          </ul>
        </section>

        {/* WEBHOOK_AMBIGUITY deep dive — Day 9, 25 transactions */}
        <section aria-labelledby="webhook-deep-dive-label" className="mt-10 border-t border-border pt-8">
          <p id="webhook-deep-dive-label" className="font-mono text-xs uppercase tracking-wider text-text-muted">
            Day 9 test-set safety analysis — 25 transactions
          </p>
          <div className="mt-4">
            <WebhookAmbiguityCase
              transactionsEvaluated={d9.webhookAmbiguity.comparison.GUARDIAN.transactionsEvaluated}
              totalAmountAtRisk={d9.webhookAmbiguity.comparison.GUARDIAN.totalAmountAtRisk}
              rows={webhookRows}
              guardianBlockReconcileCount={d9.webhookAmbiguity.guardianBlockReconcileCount}
            />
          </div>
          <p className="mt-3 text-xs text-text-muted">
            This is the Day 9 held-out test population (25 transactions) — a different, separate population from
            the Day 12 incident-window population (1 transaction) shown on Incident Replay. The two are never
            combined.
          </p>
        </section>

        {/* Root-cause breakdown */}
        <section aria-labelledby="root-cause-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="root-cause-heading" className="text-lg font-semibold text-text-primary">
            Root-cause breakdown
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-text-secondary">
            Recovery rate (and simulated amount) by root cause and strategy — showing why aggregate recovery
            differs, not just that it does.
          </p>
          <div className="mt-6">
            <RootCauseMatrix table={d10.rootCauseTable} />
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded border border-border bg-bg-surface p-4">
              <p className="font-mono text-xs uppercase tracking-wider text-text-muted">
                CARD_DECLINE + INSUFFICIENT_FUNDS
              </p>
              <p className="mt-2 text-sm text-text-secondary">
                {formatCount(combined.GUARDIAN.transactions)} transactions (
                {formatPercent(combined.GUARDIAN.transactions / d10.strategyTable.GUARDIAN.transactions, 1)} of{" "}
                {formatCount(d10.strategyTable.GUARDIAN.transactions)}). Naive Retry's blanket DEFER_RETRY recovered{" "}
                {formatPercent(combined.NAIVE_RETRY.recoveryRate, 1)} here, versus{" "}
                {formatPercent(combined.GUARDIAN.recoveryRate, 1)} for Guardian and Rules-only's targeted
                CUSTOMER_RECOVERY action. Aggression is not automatically effectiveness.
              </p>
            </div>
            <div className="rounded border border-border bg-bg-surface p-4">
              <p className="font-mono text-xs uppercase tracking-wider text-text-muted">INFRASTRUCTURE</p>
              <p className="mt-2 text-sm text-text-secondary">
                {formatCount(infra.GUARDIAN.transactions)} transactions. Guardian:{" "}
                {infra.GUARDIAN.actionDistribution.DEFER_RETRY} DEFER_RETRY,{" "}
                {infra.GUARDIAN.actionDistribution.HUMAN_REVIEW} HUMAN_REVIEW, at the real{" "}
                {formatPercent(snapshot.day12.infrastructureConfidenceThreshold, 0)} confidence threshold
                (src/policy/rules.yaml). Lower-confidence predictions are routed to human review by policy design —
                not a model failure.
              </p>
            </div>
          </div>
        </section>

        {/* Seed sensitivity */}
        <section aria-labelledby="seed-sensitivity-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="seed-sensitivity-heading" className="text-lg font-semibold text-text-primary">
            Seed sensitivity
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-text-secondary">
            Three seeds ({seeds.join(", ")}) — qualitative sensitivity only, not a statistical confidence interval.
            Guardian's duplicate-charge risk is zero across every tested seed.
          </p>
          <div className="mt-6">
            <SeedSensitivityTable seedSensitivity={d10.seedSensitivity} seeds={seeds} />
          </div>
        </section>

        {/* Provenance + limitations */}
        <section aria-labelledby="recovery-provenance-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="recovery-provenance-heading" className="text-lg font-semibold text-text-primary">
            Provenance &amp; limitations
          </h2>
          <p className="mt-3 text-sm text-text-secondary">
            These recovery outcomes are generated by the Day 8 synthetic outcome simulator under controlled
            experiment conditions — never observed Razorpay production recovery.
          </p>
          <ul className="mt-4 space-y-2 text-xs text-text-muted">
            <li>Recovery rate is count-based (recovered transactions / transactions evaluated), not amount-weighted.</li>
            <li>All monetary figures are simulated/counterfactual — never actual revenue or production savings.</li>
            <li>Seed sensitivity (n=3) is qualitative; no confidence interval or significance test is computed here.</li>
            <li>
              The Day 10 McNemar result describes transaction-level paired outcomes under simulation, not proof of
              production effectiveness.
            </li>
            <li>No live Razorpay traffic, credentials, or network calls exist anywhere in this project.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
