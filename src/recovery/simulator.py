"""
Recovery Guardian — Day 8 Shared Counterfactual Outcome Estimator

    estimate_outcome(evidence: RecoveryEvidence, action: RecoveryAction)
        -> RecoveryOutcome

This is the ONE shared outcome environment Day 9/10's three-way experiment
will use to compare Guardian against a naive retry-everything baseline and
a rules-only baseline. It is deliberately:

  - Independent of PolicyDecision. It takes a bare `RecoveryAction`, never
    a PolicyDecision object, and never imports src.policy.engine. Guardian's
    production pipeline (src/pipeline/pipeline.py) is the ONLY place that
    decides which action is actually authorized (via the Day 7
    RulesPolicyEngine) — this module has no opinion on that and does not
    call the policy engine internally. Day 9/10 will call this exact same
    function with hypothetical actions a naive or rules-only strategy would
    have chosen instead, INCLUDING actions Guardian's own policy would
    never authorize (e.g. DEFER_RETRY on WEBHOOK_AMBIGUITY evidence) — that
    is intentional and required for a fair comparison; scoring what a
    strategy WOULD have done is not the same as authorizing it to actually
    happen. See docs/architecture.md's Day 8 section for the full
    counterfactual-consistency argument.

  - A pure, deterministic simulation, not a trained model. The project has
    no observed production recovery-outcome labels anywhere (audited: the
    synthetic dataset generator, the recovery_outcomes table, and every
    other data source were inspected and none contain action-taken/
    recovery-success fields) — so this deliberately does NOT fabricate a
    supervised training problem. It is a transparent, explicitly-configured
    synthetic simulator (src/recovery/simulation_config.yaml), and every
    probability in that file is documented as a simulation assumption, not
    a production statistic.

  - Reproducible. Realized outcomes are drawn from a local
    `random.Random(seed)` instance (never the global `random` module). If
    no seed is given, one is derived deterministically from
    (transaction_id, action) so that calling this function twice with the
    same evidence and action — with no seed argument at all — still
    produces the identical result, without requiring every caller to
    manage its own seed.

OBSERVED vs EXPECTED vs SIMULATED (see docs/architecture.md):
    OBSERVED  - an actual recorded payment outcome. The project has none.
    EXPECTED  - a probability-weighted estimate (amount * P(recovery)).
                See `probability_of_recovery()` below.
    SIMULATED - the single realized RecoveryOutcome this function returns
                for one (evidence, action, seed).
Nothing this module produces is an OBSERVED outcome, and nothing here may
be reported as real recovered revenue.
"""

import hashlib
import random
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from src.domain.models import RecoveryAction, RecoveryOutcome, RootCause
from src.recovery.evidence import RecoveryEvidence

CONFIG_PATH = Path(__file__).parent / "simulation_config.yaml"

AUTOMATED_RECOVERY_ACTIONS = frozenset({RecoveryAction.DEFER_RETRY, RecoveryAction.CUSTOMER_RECOVERY})
# BLOCK_RECONCILE, HUMAN_REVIEW, and NO_ACTION never perform automated
# recovery in this Day 8 simulation — see the module docstring's per-action
# semantics and docs/architecture.md.


def _load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f)


_CONFIG = _load_config()


def _stable_seed(transaction_id: str, action: RecoveryAction) -> int:
    """Deterministically derive a seed from (transaction_id, action) when
    the caller doesn't supply one explicitly, so `estimate_outcome` is
    reproducible by default rather than only when a seed happens to be
    passed."""
    digest = hashlib.sha256(f"{transaction_id}:{action.value}".encode()).hexdigest()
    return int(digest[:16], 16)


def probability_of_recovery(evidence: RecoveryEvidence, action: RecoveryAction) -> float:
    """The EXPECTED probability of recovery for this (evidence, action) —
    a probability-weighted estimate, not a realized outcome. Exposed
    separately from estimate_outcome() so callers needing an EXPECTED
    value (amount * this) never confuse it with a SIMULATED realized
    outcome."""
    root_cause_value = evidence.root_cause.value if isinstance(evidence.root_cause, RootCause) else str(evidence.root_cause)

    if action == RecoveryAction.DEFER_RETRY:
        if evidence.root_cause == RootCause.WEBHOOK_AMBIGUITY:
            wa = _CONFIG["webhook_ambiguity"]
            p_already_succeeded = wa["original_payment_already_succeeded_probability"]
            p_genuine_retry_success = wa["genuine_retry_success_probability"]
            # If it already succeeded, "retrying" trivially succeeds again
            # (duplicate charge); otherwise it's a genuine-failure retry.
            return p_already_succeeded * 1.0 + (1 - p_already_succeeded) * p_genuine_retry_success
        table = _CONFIG["recovery_probability"]["DEFER_RETRY"]
        return table.get(root_cause_value, table["default"])

    if action == RecoveryAction.CUSTOMER_RECOVERY:
        table = _CONFIG["recovery_probability"]["CUSTOMER_RECOVERY"]
        return table.get(root_cause_value, table["default"])

    # BLOCK_RECONCILE, HUMAN_REVIEW, NO_ACTION: no automated recovery.
    return 0.0


def _duplicate_charge_risk_probability(evidence: RecoveryEvidence, action: RecoveryAction) -> float:
    """P(this hypothetical action carries duplicate-charge risk). Only
    DEFER_RETRY on WEBHOOK_AMBIGUITY evidence carries this risk in the
    current simulation — a retry on a payment whose state was never
    resolved may be charging a payment that already succeeded. Every other
    action/root_cause combination has zero risk under this model (a
    genuine, non-ambiguous retry doesn't risk double-charging because the
    original payment is known to have failed)."""
    if action == RecoveryAction.DEFER_RETRY and evidence.root_cause == RootCause.WEBHOOK_AMBIGUITY:
        return _CONFIG["webhook_ambiguity"]["original_payment_already_succeeded_probability"]
    return 0.0


def estimate_outcome(
    evidence: RecoveryEvidence,
    action: RecoveryAction,
    *,
    seed: Optional[int] = None,
    decision_id: str = "",
    timestamp=None,
) -> RecoveryOutcome:
    """The shared counterfactual outcome environment. Evaluates ANY of the
    five RecoveryAction values against `evidence` using exactly the same
    underlying simulation logic — there is no per-strategy branching here;
    Day 9/10's naive, rules-only, and Guardian strategies will all call
    this exact function, differing only in which `action` they pass.

    Does NOT call src.policy.engine and does NOT consult what Guardian's
    real policy would have chosen — `action` is evaluated exactly as
    requested (see module docstring's counterfactual-consistency point).

    Args:
        evidence: pre-action RecoveryEvidence.
        action: the hypothetical (or, for Guardian's real pipeline, the
            actually Day-7-authorized) RecoveryAction to evaluate.
        seed: optional explicit seed for the realized draw. If omitted, a
            seed is derived deterministically from
            (evidence.transaction_id, action) so results are reproducible
            by default.
        decision_id: optional pass-through to link this outcome back to a
            DecisionRecord's audit trail (src/domain/models.py). Purely
            bookkeeping — never affects the simulated outcome itself.
        timestamp: optional explicit timestamp; defaults to now (UTC,
            naive, matching the project's existing datetime convention).

    Returns:
        A RecoveryOutcome. `recovered`/`amount_recovered` are a single
        SIMULATED realization, not an expected value — see
        probability_of_recovery() for the expected-value form.
    """
    from datetime import datetime, timezone

    if timestamp is None:
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None)

    if seed is None:
        seed = _stable_seed(evidence.transaction_id, action)
    rng = random.Random(seed)

    if action not in AUTOMATED_RECOVERY_ACTIONS:
        # BLOCK_RECONCILE, HUMAN_REVIEW, NO_ACTION: never an automated
        # recovery in this Day 8 simulation (see module docstring).
        reason = {
            RecoveryAction.BLOCK_RECONCILE: "BLOCK_RECONCILE_NO_AUTOMATIC_RETRY",
            RecoveryAction.HUMAN_REVIEW: "HUMAN_REVIEW_NOT_AUTOMATED",
            RecoveryAction.NO_ACTION: "NO_ACTION_TAKEN",
        }[action]
        return RecoveryOutcome(
            transaction_id=evidence.transaction_id,
            action_taken=action,
            recovered=False,
            amount_recovered=0.0,
            decision_id=decision_id,
            timestamp=timestamp,
            duplicate_charge_risk=False,
            outcome_reason=reason,
        )

    p_recovery = probability_of_recovery(evidence, action)
    p_duplicate_risk = _duplicate_charge_risk_probability(evidence, action)

    recovered = rng.random() < p_recovery
    duplicate_charge_risk = rng.random() < p_duplicate_risk

    amount_recovered = evidence.amount if recovered else 0.0
    # Invariant: 0 <= amount_recovered <= evidence.amount, by construction
    # (binary all-or-nothing recovery — a deliberate simplification of
    # this synthetic simulation, documented in docs/architecture.md).

    if action == RecoveryAction.DEFER_RETRY and evidence.root_cause == RootCause.WEBHOOK_AMBIGUITY:
        reason = "WEBHOOK_AMBIGUITY_RETRY_DUPLICATE_CHARGE" if duplicate_charge_risk else "WEBHOOK_AMBIGUITY_RETRY_GENUINE"
    elif action == RecoveryAction.DEFER_RETRY:
        reason = "DEFER_RETRY_" + ("SUCCESS" if recovered else "FAILURE")
    else:  # CUSTOMER_RECOVERY
        reason = "CUSTOMER_RECOVERY_" + ("SUCCESS" if recovered else "FAILURE")

    return RecoveryOutcome(
        transaction_id=evidence.transaction_id,
        action_taken=action,
        recovered=recovered,
        amount_recovered=amount_recovered,
        decision_id=decision_id,
        timestamp=timestamp,
        duplicate_charge_risk=duplicate_charge_risk,
        outcome_reason=reason,
    )


def unrecovered_amount(transaction_amount: float, outcome: RecoveryOutcome) -> float:
    """Derived, not stored: transaction_amount - outcome.amount_recovered.
    Kept as a small pure helper rather than a persisted RecoveryOutcome
    field, so RecoveryOutcome doesn't need to redundantly carry the
    original transaction amount (already available on PaymentEvent /
    RecoveryEvidence) just to support this one derived invariant."""
    return transaction_amount - outcome.amount_recovered
