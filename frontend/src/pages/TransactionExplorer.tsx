import { useMemo, useState } from "react";
import { ExplorerControls } from "../components/explorer/ExplorerControls";
import { TransactionDetailPanel } from "../components/explorer/TransactionDetailPanel";
import { TransactionList } from "../components/explorer/TransactionList";
import { ProvenanceBadge } from "../components/ui/ProvenanceBadge";
import { snapshot } from "../data/snapshot";

/**
 * Transaction Explorer (Final Polish pass). Built ONLY because the
 * data-availability audit (Final Polish spec section 7) confirmed
 * genuine transaction-level records exist: `snapshot.day12.transactions`
 * — 110 real records read straight through
 * scripts/generate_frontend_snapshot.py from
 * experiments/results/day12_incident_demo.json's own `transactions`
 * array (no new artifact, no recomputation).
 *
 * Population firewall (spec section 14): this is the Day 12
 * incident-window population (110 transactions, 1 WEBHOOK_AMBIGUITY
 * case) — the SAME population already summarized on Incident Replay,
 * shown here at row level. It is never combined with, or presented as,
 * the separate Day 9 population (242 transactions, 25 WEBHOOK_AMBIGUITY
 * cases) used on Recovery Analysis.
 */
export function TransactionExplorer() {
  const transactions = snapshot.day12.transactions;
  const totalCount = transactions.length;

  const [query, setQuery] = useState("");
  const [rootCause, setRootCause] = useState("ALL");
  const [action, setAction] = useState("ALL");
  const [sortDescending, setSortDescending] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const rootCauseOptions = useMemo(
    () => Array.from(new Set(transactions.map((t) => t.predictedRootCause))).sort(),
    [transactions],
  );
  const actionOptions = useMemo(
    () => Array.from(new Set(transactions.map((t) => t.policyAction))).sort(),
    [transactions],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return transactions
      .filter((t) => (q ? t.transactionId.toLowerCase().includes(q) : true))
      .filter((t) => (rootCause === "ALL" ? true : t.predictedRootCause === rootCause))
      .filter((t) => (action === "ALL" ? true : t.policyAction === action))
      .sort((a, b) =>
        sortDescending ? b.predictedProbability - a.predictedProbability : a.predictedProbability - b.predictedProbability,
      );
  }, [transactions, query, rootCause, action, sortDescending]);

  const selected = filtered.find((t) => t.transactionId === selectedId) ?? null;

  return (
    <div className="px-6 py-14 md:px-10">
      <div className="mx-auto max-w-4xl">
        {/* Hero */}
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Transaction Explorer</p>
        <h1 className="mt-2 text-2xl font-semibold text-text-primary md:text-3xl">
          What happened to one transaction, and why.
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-text-secondary">
          Every transaction from the Day 12 incident-window replay, inspectable individually: the model&rsquo;s
          prediction, the policy engine&rsquo;s decision, and the simulated outcome — never a live feed, never a
          production system.
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <ProvenanceBadge value="OBSERVED" />
          <p className="text-xs text-text-muted">
            Day 12 incident-window population — {totalCount} of {totalCount} transactions available. Distinct from
            the Day 9 test-set population (242 transactions) shown on Recovery Analysis; the two are never combined.
          </p>
        </div>

        <div className="mt-8">
          <ExplorerControls
            query={query}
            onQueryChange={setQuery}
            rootCause={rootCause}
            onRootCauseChange={setRootCause}
            action={action}
            onActionChange={setAction}
            rootCauseOptions={rootCauseOptions}
            actionOptions={actionOptions}
            sortDescending={sortDescending}
            onToggleSort={() => setSortDescending((v) => !v)}
            resultCount={filtered.length}
            totalCount={totalCount}
          />
        </div>

        <div className="mt-4">
          <TransactionList transactions={filtered} selectedId={selectedId} onSelect={setSelectedId} />
        </div>

        <TransactionDetailPanel transaction={selected} />

        {/* Provenance + limitations */}
        <section aria-labelledby="explorer-provenance-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="explorer-provenance-heading" className="text-lg font-semibold text-text-primary">
            Provenance &amp; limitations
          </h2>
          <ul className="mt-4 space-y-2 text-xs text-text-muted">
            <li>Dataset fields (event, prediction, policy decision) are read directly from the Day 12 replay artifact.</li>
            <li>Recovery outcomes are simulated by the Day 8 counterfactual simulator — never observed production recovery.</li>
            <li>
              &ldquo;Known root cause&rdquo; is a synthetic label generated with the dataset, available only because
              this is a replay — never available to the model or policy engine at decision time, and never shown as
              if it were.
            </li>
            <li>This is a 110-transaction synthetic incident window, not a general claim about model accuracy in production.</li>
            <li>No live Razorpay traffic, credentials, or network calls exist anywhere in this project.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
