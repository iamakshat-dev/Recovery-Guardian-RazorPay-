interface UnavailableMetricProps {
  label: string;
  reason?: string;
}

/**
 * Rendered instead of a metric whenever validation fails or a source
 * artifact is missing (Milestone 1 spec sections 33/34). Never a
 * fabricated zero.
 */
export function UnavailableMetric({ label, reason }: UnavailableMetricProps) {
  return (
    <div className="rounded border border-dashed border-border bg-bg-surface2/50 p-4">
      <p className="font-mono text-xs uppercase tracking-wider text-text-muted">{label}</p>
      <p className="mt-1 font-mono text-sm text-text-secondary">DATA UNAVAILABLE</p>
      {reason ? <p className="mt-1 text-xs text-text-muted">{reason}</p> : null}
    </div>
  );
}
