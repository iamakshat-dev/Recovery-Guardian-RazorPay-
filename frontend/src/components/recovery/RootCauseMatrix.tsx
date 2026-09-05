import { formatPercent, formatRupees } from "../../lib/format";

interface StrategyRow {
  transactions: number;
  amountAtRisk: number;
  simulatedAmountRecovered: number;
  recoveryRate: number;
  duplicateChargeRiskCount: number;
  actionDistribution: Record<string, number>;
}

// A loosened, string-indexable shape. `snapshot.day10.rootCauseTable`'s
// `as const` literal type is structurally assignable to this (every
// concrete key it has satisfies `Record<string, ...>`) -- this is purely
// a TypeScript indexing convenience, not a change to the underlying
// (still fully-typed-at-the-source) generated data.
export type RootCauseTable = Record<string, Record<string, StrategyRow>>;

const STRATEGY_LABELS: Record<string, string> = {
  NAIVE_RETRY: "Naive Retry",
  RULES_ONLY: "Rules-only",
  GUARDIAN: "Guardian",
  NO_ACTION: "No Action",
};
const STRATEGY_ORDER = ["NAIVE_RETRY", "RULES_ONLY", "GUARDIAN", "NO_ACTION"] as const;

interface RootCauseMatrixProps {
  table: RootCauseTable;
}

/**
 * A compact matrix, not a grouped bar chart (Milestone 4 spec section
 * 17 permits either; a matrix stays legible with 6 root causes x 4
 * strategies without overcomplicating the page). Every cell is read
 * directly from `snapshot.day10.rootCauseTable`
 * (experiments/results/day10_analysis.json, unmodified).
 */
export function RootCauseMatrix({ table }: RootCauseMatrixProps) {
  const rootCauses = Object.keys(table);

  return (
    // tabIndex + role/aria-label: this container becomes horizontally
    // scrollable below ~640px of available width -- a scrollable region
    // must be reachable by keyboard (found by the Final Polish axe pass,
    // scrollable-region-focusable, at the 768px viewport).
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Root-cause breakdown data table">
      <table className="w-full min-w-[640px] border-collapse text-left text-xs">
        <caption className="sr-only">Simulated recovery rate by root cause and strategy</caption>
        <thead>
          <tr className="border-b border-border text-text-muted">
            <th scope="col" className="py-2 pr-4 font-mono font-normal uppercase tracking-wider">
              Root cause
            </th>
            {STRATEGY_ORDER.map((s) => (
              <th key={s} scope="col" className="py-2 pr-4 font-mono font-normal uppercase tracking-wider">
                {STRATEGY_LABELS[s]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rootCauses.map((rc) => (
            <tr key={rc} className="border-b border-border/60">
              <th scope="row" className="py-2 pr-4 text-left font-mono font-medium text-text-primary">
                {rc}
              </th>
              {STRATEGY_ORDER.map((s) => {
                const cell = table[rc][s];
                return (
                  <td key={s} className="py-2 pr-4 font-mono tabular-nums text-text-secondary">
                    {formatPercent(cell.recoveryRate, 0)}
                    <span className="ml-1 text-text-muted">({formatRupees(cell.simulatedAmountRecovered)})</span>
                    {cell.duplicateChargeRiskCount > 0 ? (
                      <span className="ml-1 text-critical">&middot; {cell.duplicateChargeRiskCount} risk</span>
                    ) : null}
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
