import { formatPercent, formatRupees } from "../../lib/format";
import { ProvenanceBadge } from "../ui/ProvenanceBadge";
import type { ExplorerTransaction } from "./TransactionList";

interface TransactionDetailPanelProps {
  transaction: ExplorerTransaction | null;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/60 py-2 text-sm last:border-b-0">
      <span className="text-text-muted">{label}</span>
      <span className="font-mono text-text-primary">{value}</span>
    </div>
  );
}

/**
 * Inline expansion below the list, not a modal — matching the same
 * pattern NodeDetailPanel already established on the Decision Pipeline
 * page (Milestone 2 spec section 18).
 *
 * Ground-truth firewall (Final Polish spec section 9): "Predicted root
 * cause" and "Known root cause" are rendered as two clearly distinct
 * rows with different labels. This is a synthetic incident replay, so
 * the true label is knowable — but it must never be presented as
 * something the model itself inferred.
 */
export function TransactionDetailPanel({ transaction }: TransactionDetailPanelProps) {
  if (!transaction) return null;
  const t = transaction;
  const matches = t.predictedRootCause === t.actualRootCause;

  return (
    <div
      id="transaction-detail-panel"
      role="region"
      aria-live="polite"
      aria-label={`Detail for transaction ${t.transactionId}`}
      className="mt-4 rounded border border-border bg-bg-surface p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-mono text-sm font-semibold text-text-primary">{t.transactionId}</h3>
        <ProvenanceBadge value="OBSERVED" />
      </div>

      <div className="mt-4">
        <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">Event</p>
        <Row label="Timestamp" value={t.timestamp} />
        <Row label="Amount" value={formatRupees(t.amount)} />
        <Row label="Payment method" value={t.paymentMethod} />
        <Row label="Failure code" value={t.failureCode} />
        <Row label="Webhook delay" value={`${t.webhookDelaySeconds}s`} />
        <Row label="Incident-window transaction" value={t.incidentActive ? "Yes" : "No"} />
      </div>

      <div className="mt-4">
        <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">Root cause</p>
        <Row label="Predicted root cause (model)" value={`${t.predictedRootCause} — ${formatPercent(t.predictedProbability, 2)} confidence`} />
        <Row label="Known root cause (synthetic label)" value={t.actualRootCause} />
        <p className="mt-2 text-xs text-text-muted">
          {matches
            ? "Model prediction matches the known synthetic label for this transaction."
            : "Model prediction differs from the known synthetic label for this transaction."}{" "}
          The known label exists only because this is a synthetic replay with a generated ground truth — it is
          never available to the model or the policy engine at decision time.
        </p>
      </div>

      <div className="mt-4">
        <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">Policy decision</p>
        <Row label="Policy action" value={t.policyAction} />
        <Row label="Policy reason code" value={t.policyReasonCode} />
        <Row label="Dataset split" value={t.splitMembership} />
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between gap-3 border-b border-border/60 py-2 text-sm">
          <span className="text-text-muted">Simulated outcome</span>
          <ProvenanceBadge value="SIMULATED" />
        </div>
        <Row label="Recovered (simulated)" value={t.simulated.recovered ? "Yes" : "No"} />
        <Row label="Amount recovered (simulated)" value={formatRupees(t.simulated.amountRecovered)} />
        <Row label="Duplicate-charge risk (simulated)" value={t.simulated.duplicateChargeRisk ? "Yes" : "No"} />
      </div>
    </div>
  );
}
