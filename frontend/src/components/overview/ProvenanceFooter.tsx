import { ProvenanceBadge } from "../ui/ProvenanceBadge";

export function ProvenanceFooter() {
  return (
    <section aria-labelledby="provenance-heading" className="px-6 py-14 md:px-10">
      <div className="mx-auto max-w-4xl">
        <h2 id="provenance-heading" className="text-xl font-semibold text-text-primary">
          Provenance &amp; limitations
        </h2>

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded border border-border bg-bg-surface p-4">
            <ProvenanceBadge value="OBSERVED" />
            <p className="mt-2 text-xs text-text-secondary">
              Dataset transaction fields, classifier output, policy
              decisions, code behavior.
            </p>
          </div>
          <div className="rounded border border-border bg-bg-surface p-4">
            <ProvenanceBadge value="SIMULATED" />
            <p className="mt-2 text-xs text-text-secondary">
              Recovery outcomes, amounts recovered, duplicate-charge risk
              (Day 8 counterfactual simulator).
            </p>
          </div>
          <div className="rounded border border-border bg-bg-surface p-4">
            <ProvenanceBadge value="UNAVAILABLE" />
            <p className="mt-2 text-xs text-text-secondary">
              Real Razorpay production recovery, real monitoring, real
              production failure-attribution labels.
            </p>
          </div>
        </div>

        <ul className="mt-8 space-y-2 text-xs text-text-muted">
          <li>
            The Day 12 incident-replay held-out INFRASTRUCTURE result
            (15/15) is a small sample and was never run through this
            project&apos;s own suspicious-performance investigation — an
            open methodological limitation, not a validated invariant.
          </li>
          <li>
            All monetary figures are simulated/counterfactual (Day 8) —
            never observed production revenue.
          </li>
          <li>No live Razorpay traffic, credentials, or network calls exist anywhere in this project.</li>
          <li>
            The explanation layer (Day 13) has no authority over the
            recovery decision — it can only describe an already-computed
            result.
          </li>
        </ul>
      </div>
    </section>
  );
}
