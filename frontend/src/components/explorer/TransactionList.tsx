import { formatPercent, formatRupees } from "../../lib/format";
import type { snapshot } from "../../data/snapshot";

export type ExplorerTransaction = (typeof snapshot)["day12"]["transactions"][number];

interface TransactionListProps {
  transactions: ExplorerTransaction[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const ACTION_ACCENT: Record<string, string> = {
  BLOCK_RECONCILE: "text-safety",
  HUMAN_REVIEW: "text-warning",
  DEFER_RETRY: "text-info",
  CUSTOMER_RECOVERY: "text-info",
  NO_ACTION: "text-text-muted",
};

/**
 * The list half of the Explorer's master-detail layout (Final Polish
 * spec section 12 — "an investigation surface, not a spreadsheet").
 * Rows are compact buttons, not a wide table, so the page stays usable
 * at 390px without horizontal scrolling; the full record appears in
 * TransactionDetailPanel once a row is selected.
 */
export function TransactionList({ transactions, selectedId, onSelect }: TransactionListProps) {
  if (transactions.length === 0) {
    return (
      <div className="rounded border border-dashed border-border bg-bg-surface2/50 p-6 text-center">
        <p className="text-sm text-text-secondary">No transactions match the current filters.</p>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-border rounded border border-border bg-bg-surface" role="list">
      {transactions.map((t) => {
        const isSelected = t.transactionId === selectedId;
        return (
          <li key={t.transactionId}>
            <button
              type="button"
              onClick={() => onSelect(t.transactionId)}
              aria-expanded={isSelected}
              aria-controls="transaction-detail-panel"
              className={[
                "grid w-full grid-cols-2 gap-x-3 gap-y-1 px-4 py-3 text-left text-sm transition-colors sm:grid-cols-4",
                isSelected ? "bg-bg-surface2" : "hover:bg-bg-surface2/60",
                "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-info",
              ].join(" ")}
            >
              <span className="col-span-2 truncate font-mono text-xs text-text-primary sm:col-span-1">
                {t.transactionId}
              </span>
              <span className="truncate text-xs text-text-secondary">{t.predictedRootCause}</span>
              <span className={["truncate font-mono text-xs", ACTION_ACCENT[t.policyAction] ?? "text-text-secondary"].join(" ")}>
                {t.policyAction}
              </span>
              <span className="truncate text-xs text-text-muted">
                {formatPercent(t.predictedProbability, 0)} conf. ·{" "}
                {t.simulated.recovered ? formatRupees(t.simulated.amountRecovered) : "not recovered"}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
