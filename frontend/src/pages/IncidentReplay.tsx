import { useEffect, useState } from "react";
import { ProvenanceBadge } from "../components/ui/ProvenanceBadge";
import { formatCount, formatPercent, formatRupees } from "../lib/format";
import { useReducedMotion } from "../lib/useReducedMotion";
import { snapshot } from "../data/snapshot";

const CLASS_LABELS: Record<string, string> = {
  INFRASTRUCTURE: "INFRASTRUCTURE",
  CARD_DECLINE: "CARD_DECLINE",
  INSUFFICIENT_FUNDS: "INSUFFICIENT_FUNDS",
  OTP_TIMEOUT: "OTP_TIMEOUT",
  USER_ABANDONMENT: "USER_ABANDONMENT",
  WEBHOOK_AMBIGUITY: "WEBHOOK_AMBIGUITY",
};

function TimelineBlock({
  label,
  windowLabel,
  count,
  density,
  revealed,
  dominant,
  delayMs,
  reducedMotion,
}: {
  label: string;
  windowLabel: string;
  count: number;
  density: number;
  revealed: boolean;
  dominant?: boolean;
  delayMs: number;
  reducedMotion: boolean;
}) {
  return (
    <div
      className={[
        "flex-1 rounded border p-5 transition-all ease-guardian-out",
        reducedMotion ? "duration-0" : "duration-300",
        revealed ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
        dominant ? "border-warning/40 bg-warning/[0.06]" : "border-border bg-bg-surface",
      ].join(" ")}
      style={!reducedMotion ? { transitionDelay: `${delayMs}ms` } : undefined}
    >
      <p className="font-mono text-xs uppercase tracking-wider text-text-muted">{label}</p>
      <p className="mt-1 text-xs text-text-muted">{windowLabel}</p>
      <p className={["mt-3 font-mono text-3xl font-semibold tabular-nums", dominant ? "text-warning" : "text-text-primary"].join(" ")}>
        {formatCount(count)}
      </p>
      <p className="text-xs text-text-muted">failed events</p>
      <p className="mt-2 font-mono text-sm tabular-nums text-text-secondary">
        density {density} / {snapshot.day12.densityUnitMinutes} min
      </p>
    </div>
  );
}

/**
 * Incident Replay (Milestone 3). A HISTORICAL SYNTHETIC REPLAY of the
 * existing Day 12 incident window — never live monitoring, never a
 * production incident detector. Every figure below is sourced from
 * `snapshot.day12` (scripts/generate_frontend_snapshot.py, reading
 * experiments/results/day12_incident_demo.json, unmodified).
 */
export function IncidentReplay() {
  const reducedMotion = useReducedMotion();
  const [revealed, setRevealed] = useState(reducedMotion);

  useEffect(() => {
    if (reducedMotion) {
      setRevealed(true);
      return;
    }
    const t = window.setTimeout(() => setRevealed(true), 30);
    return () => window.clearTimeout(t);
  }, [reducedMotion]);

  const d12 = snapshot.day12;
  const totalWindowTransactions = Object.values(d12.classDistribution).reduce((a, b) => a + b, 0);
  const maxClassCount = Math.max(...Object.values(d12.classDistribution));
  const splitTotal = d12.splitMembership.trainCount + d12.splitMembership.validationCount + d12.splitMembership.testCount;
  const trainMajority = d12.splitMembership.trainCount > splitTotal / 2;

  return (
    <div className="px-6 py-14 md:px-10">
      <div className="mx-auto max-w-4xl">
        <div className="flex flex-wrap items-center gap-3">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Incident Replay</p>
          <span className="rounded border border-warning/30 bg-warning/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-warning">
            Historical synthetic replay
          </span>
        </div>
        <h1 className="mt-2 text-2xl font-semibold text-text-primary md:text-3xl">
          A synthetic infrastructure incident, replayed through the real pipeline
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-text-secondary">
          This is <span className="font-medium text-text-primary">not</span> live monitoring and{" "}
          <span className="font-medium text-text-primary">not</span> real-time telemetry. It replays an existing,
          deliberately-injected synthetic incident burst ({d12.incidentWindow.start} – {d12.incidentWindow.end})
          through the unmodified feature builder, classifier, and policy engine.
        </p>

        {/* Timeline */}
        <section aria-labelledby="timeline-heading" className="mt-10 border-t border-border pt-8">
          <div className="flex flex-wrap items-center gap-3">
            <h2 id="timeline-heading" className="text-lg font-semibold text-text-primary">
              Before → incident → after
            </h2>
            <span className="rounded border border-border bg-bg-surface2 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-text-secondary">
              Metric: Failure density
            </span>
          </div>
          <div className="mt-6 flex flex-col gap-3 md:flex-row">
            <TimelineBlock
              label="Before"
              windowLabel={`${d12.beforeWindow.start} – ${d12.beforeWindow.end}`}
              count={d12.before.failedEventCount}
              density={d12.before.failureDensityPerUnit}
              revealed={revealed}
              delayMs={0}
              reducedMotion={reducedMotion}
            />
            <TimelineBlock
              label="Incident burst"
              windowLabel={`${d12.incidentWindow.start} – ${d12.incidentWindow.end}`}
              count={d12.incident.failedEventCount}
              density={d12.incident.failureDensityPerUnit}
              revealed={revealed}
              dominant
              delayMs={80}
              reducedMotion={reducedMotion}
            />
            <TimelineBlock
              label="After"
              windowLabel={`${d12.afterWindow.start} – ${d12.afterWindow.end}`}
              count={d12.after.failedEventCount}
              density={d12.after.failureDensityPerUnit}
              revealed={revealed}
              delayMs={160}
              reducedMotion={reducedMotion}
            />
          </div>
          <p className="mt-4 text-xs text-text-muted">
            <strong className="font-medium text-text-secondary">Why density, not rate:</strong> the synthetic
            dataset contains only failed-payment events — there is no successful-transaction denominator, so a
            percentage &ldquo;failure rate&rdquo; would be fabricated. Density is failed events per{" "}
            {d12.densityUnitMinutes}-minute unit, a directly comparable count across windows of different lengths.
          </p>
        </section>

        {/* Root-cause distribution */}
        <section aria-labelledby="distribution-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="distribution-heading" className="text-lg font-semibold text-text-primary">
            Root-cause distribution in the incident window
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            {formatCount(d12.incidentCount)} transactions, deliberately impure — not every transaction during the
            burst is INFRASTRUCTURE.
          </p>
          <div className="mt-5 space-y-3">
            {Object.entries(d12.classDistribution).map(([cls, count]) => (
              <div key={cls}>
                <div className="flex items-baseline justify-between text-xs">
                  <span className="font-mono text-text-secondary">{CLASS_LABELS[cls] ?? cls}</span>
                  <span className="font-mono tabular-nums text-text-muted">
                    {formatCount(count)} ({formatPercent(count / totalWindowTransactions, 1)})
                  </span>
                </div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-bg-surface2">
                  <div
                    className="h-full rounded-full bg-info transition-all duration-500 ease-guardian-out"
                    style={{ width: `${(count / maxClassCount) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Classifier + policy result */}
        <section aria-labelledby="classifier-result-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="classifier-result-heading" className="text-lg font-semibold text-text-primary">
            Classifier and policy result
          </h2>
          <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded border border-border bg-bg-surface p-4">
              <p className="font-mono text-xs uppercase tracking-wider text-text-muted">Full incident window</p>
              <p className="mt-2 font-mono text-2xl font-semibold text-text-primary">
                {d12.fullWindowInfrastructure.correct}/{d12.fullWindowInfrastructure.total}
              </p>
              <p className="text-xs text-text-muted">INFRASTRUCTURE correctly predicted</p>
            </div>
            <div className="rounded border border-border bg-bg-surface p-4">
              <p className="font-mono text-xs uppercase tracking-wider text-text-muted">Held-out TEST subset</p>
              <p className="mt-2 font-mono text-2xl font-semibold text-text-primary">
                {d12.heldOutTestInfrastructure.correct}/{d12.heldOutTestInfrastructure.total}
              </p>
              <p className="text-xs text-text-muted">INFRASTRUCTURE correctly predicted</p>
            </div>
          </div>
          <div className="mt-4 rounded border border-warning/30 bg-warning/[0.05] p-4">
            <p className="text-xs text-text-secondary">
              <strong className="font-medium text-warning">Disclosed limitation:</strong> the held-out subset is only{" "}
              {d12.heldOutTestInfrastructure.total} transactions. This perfect{" "}
              {d12.heldOutTestInfrastructure.correct}/{d12.heldOutTestInfrastructure.total} result was{" "}
              <strong className="font-medium text-text-primary">not independently investigated</strong> for
              leakage or generalization plausibility. It remains an open methodological limitation, not a validated
              invariant.
            </p>
          </div>
          <p className="mt-4 text-sm text-text-secondary">
            Policy response for INFRASTRUCTURE-predicted transactions (threshold{" "}
            {formatPercent(d12.infrastructureConfidenceThreshold, 0)}):{" "}
            {Object.entries(d12.infrastructurePolicyActionDistribution)
              .map(([action, count]) => `${count} ${action}`)
              .join(", ")}
            .
          </p>
        </section>

        {/* Train/validation/test disclosure */}
        <section aria-labelledby="split-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="split-heading" className="text-lg font-semibold text-text-primary">
            Train / validation / test membership
          </h2>
          <div className="mt-5 grid grid-cols-3 gap-4">
            <div className="rounded border border-border bg-bg-surface p-4 text-center">
              <p className="font-mono text-xl font-semibold text-text-primary">{d12.splitMembership.trainCount}</p>
              <p className="mt-1 font-mono text-xs uppercase tracking-wider text-text-muted">Train</p>
            </div>
            <div className="rounded border border-border bg-bg-surface p-4 text-center">
              <p className="font-mono text-xl font-semibold text-text-primary">{d12.splitMembership.validationCount}</p>
              <p className="mt-1 font-mono text-xs uppercase tracking-wider text-text-muted">Validation</p>
            </div>
            <div className="rounded border border-border bg-bg-surface p-4 text-center">
              <p className="font-mono text-xl font-semibold text-text-primary">{d12.splitMembership.testCount}</p>
              <p className="mt-1 font-mono text-xs uppercase tracking-wider text-text-muted">Test</p>
            </div>
          </div>
          {trainMajority ? (
            <p className="mt-4 text-xs text-text-muted">
              A majority ({formatPercent(d12.splitMembership.trainCount / splitTotal, 1)}) of the incident window's
              transactions are in the classifier's TRAIN split. The full-window result above is therefore a replay
              demonstration, not an out-of-sample generalization claim — the held-out TEST subset is the defensible
              view.
            </p>
          ) : null}
        </section>

        {/* WEBHOOK_AMBIGUITY: Day 12 population, explicitly distinct from Day 9 */}
        <section aria-labelledby="webhook-safety-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="webhook-safety-heading" className="text-lg font-semibold text-text-primary">
            WEBHOOK_AMBIGUITY safety, incident-window population
          </h2>
          <p className="mt-2 text-xs text-text-muted">
            This is the <strong className="font-medium text-text-secondary">Day 12 incident-window population</strong>{" "}
            ({d12.webhookAmbiguitySafety.caseCount} transaction) — a different, separate population from the{" "}
            <strong className="font-medium text-text-secondary">Day 9 held-out test population</strong> (25
            transactions) shown on the Safety page. The two are never combined.
          </p>
          <div className="mt-4 rounded border border-safety/30 bg-safety/[0.05] p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-mono text-sm text-text-primary">
                {d12.webhookAmbiguitySafety.blockReconcileCount}/{d12.webhookAmbiguitySafety.caseCount} BLOCK_RECONCILE
              </span>
              <span className="font-mono text-xs text-text-muted">
                {d12.webhookAmbiguitySafety.deferRetryCount} DEFER_RETRY
              </span>
            </div>
            <p className="mt-2 text-xs text-text-muted">
              The safety invariant held during the incident too — no WEBHOOK_AMBIGUITY transaction in this window
              was authorized for an automated retry.
            </p>
          </div>
        </section>

        {/* Simulated recovery */}
        <section aria-labelledby="simulated-recovery-heading" className="mt-10 border-t border-border pt-8">
          <div className="flex items-center justify-between gap-3">
            <h2 id="simulated-recovery-heading" className="text-lg font-semibold text-text-primary">
              Simulated recovery
            </h2>
            <ProvenanceBadge value="SIMULATED" />
          </div>
          <p className="mt-2 text-sm text-text-secondary">
            {formatCount(d12.simulatedRecoverySummary.recoveredCount)} of{" "}
            {formatCount(d12.simulatedRecoverySummary.transactionsEvaluated)} incident-window transactions
            recovered under simulation, {formatRupees(d12.simulatedRecoverySummary.totalAmountRecovered)}{" "}
            counterfactual amount, {formatCount(d12.simulatedRecoverySummary.duplicateChargeRiskCount)}{" "}
            duplicate-charge-risk outcomes. This is a counterfactual estimate from the frozen Day 8 simulator — never
            observed production revenue.
          </p>
        </section>
      </div>
    </div>
  );
}
