/**
 * Recovery Guardian — Visual Data Integrity (Milestone 1 spec section 34)
 *
 * Every metric is validated before it is allowed to render. On failure,
 * components must show an "unavailable" state instead of a misleading
 * number — never a fabricated zero.
 */

export const KNOWN_PROVENANCE = ["OBSERVED", "SIMULATED", "UNAVAILABLE"] as const;
export type Provenance = (typeof KNOWN_PROVENANCE)[number];

export const KNOWN_RECOVERY_ACTIONS = [
  "DEFER_RETRY",
  "CUSTOMER_RECOVERY",
  "BLOCK_RECONCILE",
  "HUMAN_REVIEW",
  "NO_ACTION",
] as const;
export type RecoveryAction = (typeof KNOWN_RECOVERY_ACTIONS)[number];

function devWarn(message: string): void {
  // eslint-disable-next-line no-console
  console.warn(`[recovery-guardian] data integrity: ${message}`);
}

export function isValidAmount(value: unknown): value is number {
  const ok = typeof value === "number" && Number.isFinite(value) && value >= 0;
  if (!ok) devWarn(`invalid amount: ${JSON.stringify(value)}`);
  return ok;
}

export function isValidPercentage(value: unknown): value is number {
  // Recovery rates in this project are fractions in [0, 1] at the data
  // layer; components format them as percentages for display.
  const ok = typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
  if (!ok) devWarn(`invalid rate/fraction (expected 0-1): ${JSON.stringify(value)}`);
  return ok;
}

export function isValidCount(value: unknown): value is number {
  const ok = typeof value === "number" && Number.isInteger(value) && value >= 0;
  if (!ok) devWarn(`invalid transaction/event count: ${JSON.stringify(value)}`);
  return ok;
}

export function isKnownRecoveryAction(value: unknown): value is RecoveryAction {
  const ok = typeof value === "string" && (KNOWN_RECOVERY_ACTIONS as readonly string[]).includes(value);
  if (!ok) devWarn(`unknown RecoveryAction: ${JSON.stringify(value)}`);
  return ok;
}

export function isKnownProvenance(value: unknown): value is Provenance {
  const ok = typeof value === "string" && (KNOWN_PROVENANCE as readonly string[]).includes(value);
  if (!ok) devWarn(`unknown provenance label: ${JSON.stringify(value)}`);
  return ok;
}
