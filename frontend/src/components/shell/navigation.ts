export interface NavItem {
  id: string;
  label: string;
  enabled: boolean;
}

/**
 * The full product structure (originally planned in Milestone 1 spec
 * section 11). As of the Final Polish pass every item is functional —
 * `enabled` is kept on each entry rather than removed so a future
 * placeholder can still be added the same way M1 did: no fake pages
 * pretending functionality exists ahead of real data support.
 */
export const NAV_ITEMS: NavItem[] = [
  { id: "overview", label: "Overview", enabled: true },
  { id: "safety", label: "Safety", enabled: true },
  { id: "decision-pipeline", label: "Decision Pipeline", enabled: true },
  { id: "incident-replay", label: "Incident Replay", enabled: true },
  { id: "recovery", label: "Recovery", enabled: true },
  { id: "transactions", label: "Transactions", enabled: true },
  { id: "explainability", label: "Explainability", enabled: true },
  { id: "architecture", label: "Architecture", enabled: true },
];
