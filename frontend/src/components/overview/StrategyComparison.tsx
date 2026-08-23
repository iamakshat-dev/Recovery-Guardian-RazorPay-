import { formatCount, formatPercent, formatRupees } from "../../lib/format";
import { isValidAmount, isValidCount, isValidPercentage } from "../../lib/validate";
import { ProvenanceBadge } from "../ui/ProvenanceBadge";
import { UnavailableMetric } from "../ui/UnavailableMetric";

interface StrategyRow {
  name: string;
  simulatedAmountRecovered: number;
  recoveryRate: number;
  duplicateChargeRiskCount: number;
  isGuardian?: boolean;
}

interface StrategyComparisonProps {
  strategies: StrategyRow[];
}

export function StrategyComparison({ strategies }: StrategyComparisonProps) {
  const valid = strategies.filter(
    (s) =>
      isValidAmount(s.simulatedAmountRecovered) &&
      isValidPercentage(s.recoveryRate) &&
      isValidCount(s.duplicateChargeRiskCount)
  );

  if (valid.length === 0) {
    return <UnavailableMetric label="Strategy comparison" reason="Day 9 experiment artifact failed validation." />;
  }

  const maxRecovered = Math.max(...valid.map((s) => s.simulatedAmountRecovered));
  const maxRisk = Math.max(1, ...valid.map((s) => s.duplicateChargeRiskCount));

  return (
    <section aria-labelledby="strategy-comparison-heading" className="border-b border-border px-6 py-14 md:px-10">
      <div className="mx-auto max-w-4xl">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 id="strategy-comparison-heading" className="text-xl font-semibold text-text-primary">
            Strategy comparison
          </h2>
          <ProvenanceBadge value="SIMULATED" />
        </div>
        <p className="mt-2 max-w-2xl text-sm text-text-secondary">
          Four strategies scored through one shared counterfactual
          environment using Common Random Numbers — recovery and safety
          are shown together. Guardian does not recover the most simulated
          revenue; Rules-only does.
        </p>

        <div className="mt-8 space-y-5">
          {valid.map((s) => (
            <div
              key={s.name}
              className={[
                "rounded border p-4",
                s.isGuardian ? "border-safety/30 bg-safety/[0.04]" : "border-border bg-bg-surface",
              ].join(" ")}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-mono text-sm font-medium text-text-primary">{s.name}</span>
                <span className="font-mono text-xs text-text-muted">
                  {formatCount(s.duplicateChargeRiskCount)} duplicate-risk outcome
                  {s.duplicateChargeRiskCount === 1 ? "" : "s"}
                </span>
              </div>

              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <div className="flex items-baseline justify-between text-xs text-text-muted">
                    <span>Simulated recovery</span>
                    <span className="font-mono tabular-nums">
                      {formatRupees(s.simulatedAmountRecovered)} &middot; {formatPercent(s.recoveryRate, 2)}
                    </span>
                  </div>
                  <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-bg-surface2">
                    <div
                      className="h-full rounded-full bg-info transition-all duration-500 ease-guardian-out"
                      style={{ width: `${(s.simulatedAmountRecovered / maxRecovered) * 100}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-baseline justify-between text-xs text-text-muted">
                    <span>Duplicate-charge risk</span>
                    <span className="font-mono tabular-nums">{formatCount(s.duplicateChargeRiskCount)}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-bg-surface2">
                    <div
                      className={[
                        "h-full rounded-full transition-all duration-500 ease-guardian-out",
                        s.duplicateChargeRiskCount === 0 ? "bg-safety" : "bg-critical/70",
                      ].join(" ")}
                      style={{
                        width: `${Math.max(2, (s.duplicateChargeRiskCount / maxRisk) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        <p className="mt-4 text-xs text-text-muted">
          Recovery rate is count-based (recovered transactions / transactions
          evaluated), not amount-weighted.
        </p>
      </div>
    </section>
  );
}
