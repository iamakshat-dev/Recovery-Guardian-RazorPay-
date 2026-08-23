import { isKnownProvenance, type Provenance } from "../../lib/validate";

const LABELS: Record<Provenance, string> = {
  OBSERVED: "OBSERVED",
  SIMULATED: "SIMULATED",
  UNAVAILABLE: "UNAVAILABLE",
};

const STYLES: Record<Provenance, string> = {
  OBSERVED: "text-info border-info/30 bg-info/10",
  SIMULATED: "text-warning border-warning/30 bg-warning/10",
  UNAVAILABLE: "text-text-muted border-border bg-bg-surface2",
};

interface ProvenanceBadgeProps {
  value: string;
  className?: string;
}

/**
 * Renders one of exactly OBSERVED / SIMULATED / UNAVAILABLE (Milestone 1
 * spec section 21). An unrecognized value never silently renders as if
 * it were valid — it renders UNAVAILABLE and logs a diagnostic (see
 * lib/validate.ts).
 */
export function ProvenanceBadge({ value, className = "" }: ProvenanceBadgeProps) {
  const provenance: Provenance = isKnownProvenance(value) ? value : "UNAVAILABLE";
  return (
    <span
      role="status"
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wider ${STYLES[provenance]} ${className}`}
    >
      <span aria-hidden="true" className="h-1 w-1 rounded-full bg-current" />
      {LABELS[provenance]}
    </span>
  );
}
