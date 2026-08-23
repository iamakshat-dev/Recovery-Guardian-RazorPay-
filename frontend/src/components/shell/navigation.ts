export interface NavItem {
  id: string;
  label: string;
  enabled: boolean;
}

/**
 * The planned product structure (Milestone 1 spec section 11). Only
 * "overview" is functional in this milestone — every other item is a
 * clearly-marked, disabled placeholder for a later milestone. No fake
 * pages pretending functionality exists.
 */
export const NAV_ITEMS: NavItem[] = [
  { id: "overview", label: "Overview", enabled: true },
  { id: "safety", label: "Safety", enabled: true },
  { id: "decision-pipeline", label: "Decision Pipeline", enabled: true },
  { id: "incident-replay", label: "Incident Replay", enabled: true },
  { id: "recovery", label: "Recovery", enabled: false },
  { id: "transactions", label: "Transactions", enabled: false },
  { id: "explainability", label: "Explainability", enabled: true },
  { id: "architecture", label: "Architecture", enabled: false },
];
