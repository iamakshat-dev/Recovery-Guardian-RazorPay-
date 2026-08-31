import { formatCount, formatPercent, formatRupees } from "../../lib/format";

interface StrategyRow {
  transactions: number;
  amountAtRisk: number;
  simulatedAmountRecovered: number;
  recoveryRate: number;
  duplicateChargeRiskCount: number;
  actionDistribution: Record<string, number>;
}

// See RootCauseMatrix.tsx for why this is a loosened, string-indexable
// alias rather than the exact `as const` snapshot type.
export type SeedSensitivity = Record<string, Record<string, StrategyRow>>;

const STRATEGY_LABELS: Record<string, string> = {
  NAIVE_RETRY: "Naive Retry",
  RULES_ONLY: "Rules-only",
  GUARDIAN: "Guardian",
  NO_ACTION: "No Action",
};
const STRATEGY_ORDER = ["NAIVE_RETRY", "RULES_ONLY", "GUARDIAN", "NO_ACTION"] as const;

interface SeedSensitivityTableProps {
  seedSensitivity: SeedSensitivity;
  seeds: string[];
}

/**
 * Full 3-seed x 4-strategy recovery table (Milestone 4 spec section
 * 20). This is shown in full because the data-granularity audit
 * confirmed `day10_analysis.json`'s `seed_sensitivity` genuinely
 * contains complete, schema-consistent recovery figures for every seed
 * and every strategy -- not just Guardian's duplicate-risk count. n=3
 * seeds remains qualitative only; no confidence interval or
 * significance test is computed or implied here.
 */
export function SeedSensitivityTable({ seedSensitivity, seeds }: SeedSensitivityTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-left text-xs">
        <caption className="sr-only">Simulated recovery and duplicate-charge risk by seed and strategy</caption>
        <thead>
          <tr className="border-b border-border text-text-muted">
            <th scope="col" className="py-2 pr-4 font-mono font-normal uppercase tracking-wider">
              Strategy
            </th>
            {seeds.map((seed) => (
              <th key={seed} scope="col" className="py-2 pr-4 font-mono font-normal uppercase tracking-wider">
                Seed {seed}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {STRATEGY_ORDER.map((strategy) => (
            <tr key={strategy} className="border-b border-border/60">
              <th scope="row" className="py-2 pr-4 text-left font-mono font-medium text-text-primary">
                {STRATEGY_LABELS[strategy]}
              </th>
              {seeds.map((seed) => {
                const cell = seedSensitivity[seed][strategy];
                return (
                  <td key={seed} className="py-2 pr-4 font-mono tabular-nums text-text-secondary">
                    <div>{formatRupees(cell.simulatedAmountRecovered)}</div>
                    <div className="text-text-muted">
                      {formatPercent(cell.recoveryRate, 1)} &middot;{" "}
                      <span className={cell.duplicateChargeRiskCount === 0 ? "text-safety" : "text-critical"}>
                        {formatCount(cell.duplicateChargeRiskCount)} risk
                      </span>
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
