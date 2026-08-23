interface ComingSoonProps {
  label: string;
}

/**
 * Rendered only as a defensive fallback — every disabled nav item is
 * unclickable (see components/shell/Sidebar.tsx), so this should not
 * normally be reachable. It exists so an unexpected route never
 * silently renders a blank page or fake functionality.
 */
export function ComingSoon({ label }: ComingSoonProps) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Later milestone</p>
      <h1 className="mt-3 text-2xl font-semibold text-text-primary">{label}</h1>
      <p className="mt-2 max-w-sm text-sm text-text-secondary">
        This section is planned but not implemented in this milestone.
      </p>
    </div>
  );
}
