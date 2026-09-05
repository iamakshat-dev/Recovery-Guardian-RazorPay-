import { formatCount, formatPercent, formatRupees } from "../../lib/format";
import { isValidAmount, isValidCount, isValidPercentage } from "../../lib/validate";
import { ProvenanceBadge } from "../ui/ProvenanceBadge";
import { UnavailableMetric } from "../ui/UnavailableMetric";

interface WebhookRow {
  name: string;
  recoveryRate: number;
  duplicateChargeRiskCount: number;
}

interface WebhookAmbiguityCaseProps {
  transactionsEvaluated: number;
  totalAmountAtRisk: number;
  rows: WebhookRow[];
  guardianBlockReconcileCount: number;
}

/**
 * The strongest safety story in the project (Milestone 1 spec section
 * 19): WEBHOOK_AMBIGUITY -> BLOCK_RECONCILE. This is the Day 9
 * strategy-comparison population (25 transactions), NOT the Day 12
 * incident-window population (1 WEBHOOK_AMBIGUITY transaction) — the two
 * are never conflated.
 */
export function WebhookAmbiguityCase({
  transactionsEvaluated,
  totalAmountAtRisk,
  rows,
  guardianBlockReconcileCount,
}: WebhookAmbiguityCaseProps) {
  const validRows = rows.filter((r) => isValidPercentage(r.recoveryRate) && isValidCount(r.duplicateChargeRiskCount));
  const metadataValid = isValidCount(transactionsEvaluated) && isValidAmount(totalAmountAtRisk) && isValidCount(guardianBlockReconcileCount);

  if (!metadataValid || validRows.length === 0) {
    return <UnavailableMetric label="WEBHOOK_AMBIGUITY safety case" reason="Day 9 experiment artifact failed validation." />;
  }

  return (
    <section
      aria-labelledby="webhook-ambiguity-heading"
      className="relative overflow-hidden border-b border-border px-6 py-14 md:px-10"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-24 top-0 h-[320px] w-[320px] rounded-full blur-3xl"
        style={{ background: "radial-gradient(circle, rgb(var(--color-success) / 0.10) 0%, rgb(var(--color-success) / 0) 70%)" }}
      />

      <div className="relative mx-auto max-w-4xl">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Signature safety case</p>
            <h2 id="webhook-ambiguity-heading" className="mt-1 font-mono text-xl font-semibold text-text-primary">
              WEBHOOK_AMBIGUITY
            </h2>
          </div>
          <ProvenanceBadge value="SIMULATED" />
        </div>

        <p className="mt-3 max-w-2xl text-sm text-text-secondary">
          Payment state is genuinely unknown. Retrying risks charging a
          payment that may have already succeeded. {formatCount(transactionsEvaluated)}{" "}
          transactions, {formatRupees(totalAmountAtRisk)} at risk (Day 9
          strategy-comparison population).
        </p>

        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
          {validRows.map((row) => {
            const isGuardian = row.name === "Guardian";
            return (
              <div
                key={row.name}
                className={[
                  "rounded border p-5",
                  isGuardian ? "border-safety/40 bg-safety/[0.05]" : "border-border bg-bg-surface",
                ].join(" ")}
              >
                <p className="font-mono text-xs uppercase tracking-wider text-text-muted">{row.name}</p>
                <p
                  className={[
                    "mt-2 font-mono text-3xl font-semibold tabular-nums",
                    isGuardian ? "text-safety" : "text-text-primary",
                  ].join(" ")}
                >
                  {formatPercent(row.recoveryRate, 0)}
                </p>
                <p className="text-xs text-text-muted">simulated recovery</p>
                <p className="mt-3 font-mono text-sm tabular-nums text-text-secondary">
                  {formatCount(row.duplicateChargeRiskCount)} duplicate-risk outcome
                  {row.duplicateChargeRiskCount === 1 ? "" : "s"}
                </p>
                {isGuardian ? (
                  <p className="mt-3 text-xs font-medium text-safety">
                    {guardianBlockReconcileCount}/{guardianBlockReconcileCount} BLOCK_RECONCILE
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>

        <p className="mt-6 max-w-2xl text-xs text-text-muted">
          Guardian recovers 0% here on purpose — it never authorizes an
          automated retry when payment state is ambiguous. This is the
          trade-off being demonstrated, not a shortcoming.
        </p>
      </div>
    </section>
  );
}
