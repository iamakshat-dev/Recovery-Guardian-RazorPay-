interface ExplorerControlsProps {
  query: string;
  onQueryChange: (value: string) => void;
  rootCause: string;
  onRootCauseChange: (value: string) => void;
  action: string;
  onActionChange: (value: string) => void;
  rootCauseOptions: string[];
  actionOptions: string[];
  sortDescending: boolean;
  onToggleSort: () => void;
  resultCount: number;
  totalCount: number;
}

/**
 * Transaction Explorer controls — search by ID, filter by root cause,
 * filter by action, sort by model confidence. Every option list is
 * built from values actually present in the snapshot (see
 * TransactionExplorer.tsx) — never a hardcoded enum that could drift
 * from the data.
 */
export function ExplorerControls({
  query,
  onQueryChange,
  rootCause,
  onRootCauseChange,
  action,
  onActionChange,
  rootCauseOptions,
  actionOptions,
  sortDescending,
  onToggleSort,
  resultCount,
  totalCount,
}: ExplorerControlsProps) {
  return (
    <div className="rounded border border-border bg-bg-surface p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[11px] uppercase tracking-wider text-text-muted">Search transaction ID</span>
          <input
            type="text"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="txn_..."
            className="rounded border border-border bg-bg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus-visible:outline-2 focus-visible:outline-info"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="font-mono text-[11px] uppercase tracking-wider text-text-muted">Root cause</span>
          <select
            value={rootCause}
            onChange={(e) => onRootCauseChange(e.target.value)}
            className="rounded border border-border bg-bg px-3 py-2 text-sm text-text-primary focus-visible:outline-2 focus-visible:outline-info"
          >
            <option value="ALL">All root causes</option>
            {rootCauseOptions.map((rc) => (
              <option key={rc} value={rc}>
                {rc}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="font-mono text-[11px] uppercase tracking-wider text-text-muted">Policy action</span>
          <select
            value={action}
            onChange={(e) => onActionChange(e.target.value)}
            className="rounded border border-border bg-bg px-3 py-2 text-sm text-text-primary focus-visible:outline-2 focus-visible:outline-info"
          >
            <option value="ALL">All actions</option>
            {actionOptions.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-col gap-1">
          <span className="font-mono text-[11px] uppercase tracking-wider text-text-muted">Sort by confidence</span>
          <button
            type="button"
            onClick={onToggleSort}
            className="rounded border border-border bg-bg px-3 py-2 text-left text-sm text-text-primary hover:border-text-muted focus-visible:outline-2 focus-visible:outline-info"
          >
            {sortDescending ? "Highest first ↓" : "Lowest first ↑"}
          </button>
        </div>
      </div>

      <p className="mt-3 font-mono text-xs text-text-muted" role="status">
        Showing {resultCount} of {totalCount} transactions
      </p>
    </div>
  );
}
