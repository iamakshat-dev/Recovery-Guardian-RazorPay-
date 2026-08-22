"""
Recovery Guardian — Day 9 Action-Selection Strategies

Four strategies, one common interface:

    select_action(payment_event: PaymentEvent) -> RecoveryAction

Strategies ONLY select an action. None of them simulate outcomes,
calculate recovery amounts, or calculate duplicate-charge risk — that is
exclusively src.recovery.simulator.estimate_outcome()'s job (Day 8,
unmodified). There is no simulate_naive_outcome() /
simulate_rules_outcome() / simulate_guardian_outcome() anywhere in this
module, by design (Day 9 spec section 12).

All four strategies receive the exact same PaymentEvent for a given
transaction — the shared "same evidence" contract (Day 9 spec section
13/15). Only Guardian additionally derives a calibrated root-cause
prediction from it, because doing so is Guardian's actual architecture.
"""

from datetime import datetime

import pandas as pd

from src.domain.models import PaymentEvent, RecoveryAction, RootCausePrediction
from src.features.build_features import build_features
from src.model.calibrated_classifier import CalibratedRootCauseClassifier
from src.policy.engine import RulesPolicyEngine

# Fixed, not wall-clock: guarantees byte-identical cross-process
# reproducibility (Day 9 spec section 52). RulesPolicyEngine.decide()
# accepts an explicit `now` specifically so callers never have to depend
# on the real clock — Day 9 holds it fixed for every evaluation.
EXPERIMENT_EVALUATION_TIME = datetime(2026, 1, 1, 0, 0, 0)


class NaiveRetryStrategy:
    """The roadmap's "naive retry-everything" baseline. Selects
    DEFER_RETRY unconditionally, for every transaction, regardless of
    evidence — including WEBHOOK_AMBIGUITY, where this is unsafe. That is
    the deliberate point of this baseline: it inspects nothing and uses no
    root-cause information, no ML, no Day 7 policy, and no failure_code
    logic at all. It never selects anything other than DEFER_RETRY."""

    def select_action(self, payment_event: PaymentEvent) -> RecoveryAction:
        return RecoveryAction.DEFER_RETRY


# --- Rules-only ---------------------------------------------------------
#
# Frozen BEFORE the Day 9 experiment was run (see docs/architecture.md's
# Day 9 section for the full rationale — this file is the single source
# of truth for the frozen mapping). Uses ONLY failure_code — the Day 1
# dataset's existing vocabulary (src/features/build_features.py's
# FAILURE_CODE_CATEGORIES / data/generate_data.py's FAILURE_CODE_BY_CAUSE).
# Never inspects true root-cause labels, ML predictions, or Day 7 policy.
#
# `gateway_timeout` and `unknown` are DELIBERATELY non-unique by Day 1
# dataset design — both occur under INFRASTRUCTURE and under
# WEBHOOK_AMBIGUITY. Rules-only cannot distinguish those two root causes
# using failure_code alone, so each gets exactly one frozen default:
#
#   gateway_timeout -> DEFER_RETRY
#       Reads as a transient network/gateway issue to a naive, ML-free
#       rule-writer. This is the natural, defensible naive judgment call —
#       and it is precisely what makes this baseline unsafe on the
#       WEBHOOK_AMBIGUITY share of transactions carrying this code: a
#       retry there risks a duplicate charge. That risk is an intentional,
#       measured part of this baseline, not a bug.
#   unknown -> HUMAN_REVIEW
#       The code carries no signal at all; the safest default when a
#       naive rule genuinely cannot tell what happened.
RULES_ONLY_FAILURE_CODE_MAPPING = {
    "gateway_timeout": RecoveryAction.DEFER_RETRY,
    "internal_error": RecoveryAction.DEFER_RETRY,
    "service_unavailable": RecoveryAction.DEFER_RETRY,
    "issuer_declined": RecoveryAction.CUSTOMER_RECOVERY,
    "card_expired": RecoveryAction.CUSTOMER_RECOVERY,
    "invalid_card": RecoveryAction.CUSTOMER_RECOVERY,
    "insufficient_funds": RecoveryAction.CUSTOMER_RECOVERY,
    "otp_timeout": RecoveryAction.HUMAN_REVIEW,
    "3ds_auth_failed": RecoveryAction.HUMAN_REVIEW,
    "user_cancelled": RecoveryAction.HUMAN_REVIEW,
    "session_expired": RecoveryAction.HUMAN_REVIEW,
    "unknown": RecoveryAction.HUMAN_REVIEW,
}
# Safe fallback for any failure_code not in the frozen table above.
RULES_ONLY_DEFAULT_ACTION = RecoveryAction.HUMAN_REVIEW


class RulesOnlyStrategy:
    """Deterministic failure_code -> action baseline. Never touches ML,
    calibrated probability, Guardian's Day 7 policy engine, or true
    root-cause labels — only `payment_event.failure_code`, via the frozen
    RULES_ONLY_FAILURE_CODE_MAPPING above."""

    def select_action(self, payment_event: PaymentEvent) -> RecoveryAction:
        return RULES_ONLY_FAILURE_CODE_MAPPING.get(payment_event.failure_code, RULES_ONLY_DEFAULT_ACTION)


class GuardianStrategy:
    """Uses the ACTUAL production decision logic — the real feature
    builder, the real frozen calibrated classifier, and the real Day 7
    RulesPolicyEngine — exactly as src/pipeline/pipeline.py does, EXCEPT
    that no persistence/audit/idempotency-write side effect occurs here.

    This is Option A from the Day 9 spec's section 10A: only the
    persistence layer is bypassed. Feature construction, calibrated
    prediction, policy rules, confidence thresholds, and every safety
    guard are byte-for-byte identical to production — nothing about
    Guardian's decision logic is reimplemented or approximated.

    `already_executed_actions` is always passed as an empty frozenset, and
    `now` is always the fixed EXPERIMENT_EVALUATION_TIME. Both exactly
    match what production's real idempotency_log/cooldown checks would see
    for a transaction with no prior recorded actions — true for every
    dataset row Day 9 evaluates (none has ever been through a real
    pipeline run). This is what guarantees GuardianStrategy returns the
    same action no matter how many times, in what order, or across how
    many separate processes it is invoked for the same transaction — there
    is no persistent state anywhere in this class for one call to leak
    into another."""

    def __init__(self):
        self._classifier = CalibratedRootCauseClassifier()
        self._policy_engine = RulesPolicyEngine()

    def predict(self, payment_event: PaymentEvent) -> RootCausePrediction:
        """The real calibrated prediction — exposed separately so the
        experiment runner can reuse the exact same prediction for building
        the shared RecoveryEvidence, rather than silently deriving a
        second, potentially-different one."""
        features_df = build_features(pd.DataFrame([payment_event.model_dump()]), keep_label=False)
        return self._classifier.predict(features_df.iloc[0])

    def select_action(self, payment_event: PaymentEvent) -> RecoveryAction:
        prediction = self.predict(payment_event)
        decision = self._policy_engine.decide(
            prediction,
            payment_event,
            already_executed_actions=frozenset(),
            now=EXPERIMENT_EVALUATION_TIME,
        )
        return decision.action


class NoActionStrategy:
    """The explicit fourth baseline: NO_ACTION for every transaction,
    unconditionally. Inspects nothing — no ML, no failure_code rules, no
    policy."""

    def select_action(self, payment_event: PaymentEvent) -> RecoveryAction:
        return RecoveryAction.NO_ACTION
