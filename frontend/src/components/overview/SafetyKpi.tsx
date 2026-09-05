import { useCountUp } from "../../lib/useCountUp";
import { isValidCount } from "../../lib/validate";
import { ProvenanceBadge } from "../ui/ProvenanceBadge";
import { UnavailableMetric } from "../ui/UnavailableMetric";

interface SafetyKpiProps {
  duplicateChargeRiskBySeed: Record<string, number>;
}

/**
 * The single strongest verified Guardian result (Milestone 1 spec
 * section 15): zero simulated duplicate-charge-risk outcomes across
 * every tested seed. Uses the restrained "Safety Glow" motif — a
 * localized, low-opacity emerald radial, not a decorative neon effect.
 */
export function SafetyKpi({ duplicateChargeRiskBySeed }: SafetyKpiProps) {
  const seeds = Object.keys(duplicateChargeRiskBySeed);
  const values = Object.values(duplicateChargeRiskBySeed);
  const allValid = values.length > 0 && values.every(isValidCount);
  const allZero = allValid && values.every((v) => v === 0);
  const displayValue = useCountUp(allValid ? values[0] : 0, 700);

  if (!allValid) {
    return <UnavailableMetric label="Duplicate-charge risk" reason="Seed sensitivity data failed validation." />;
  }

  return (
    <section
      aria-labelledby="safety-kpi-heading"
      className="relative overflow-hidden border-b border-border px-6 py-14 md:px-10"
    >
      {allZero ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-1/2 top-1/2 h-[420px] w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl"
          style={{ background: "radial-gradient(circle, rgb(var(--color-success) / 0.12) 0%, rgb(var(--color-success) / 0) 70%)" }}
        />
      ) : null}

      <div className="relative mx-auto max-w-4xl text-center">
        <h2 id="safety-kpi-heading" className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">
          Primary safety result
        </h2>
        <p className="mt-6 font-mono text-7xl font-semibold tabular-nums text-safety md:text-8xl">
          {Math.round(displayValue)}
        </p>
        <p className="mt-3 text-lg font-medium text-text-primary">Duplicate-charge risk</p>
        <p className="mt-2 text-sm text-text-secondary">
          Guardian &middot; seeds {seeds.join(", ")}
        </p>
        <p className="mx-auto mt-4 max-w-md text-sm text-text-muted">
          Zero simulated duplicate-charge-risk outcomes across every tested
          seed.
        </p>
        <div className="mt-5 flex justify-center">
          <ProvenanceBadge value="SIMULATED" />
        </div>
      </div>
    </section>
  );
}
