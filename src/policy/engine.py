"""
Recovery Guardian — Day 7 Deterministic Policy Engine

    RootCausePrediction + PaymentEvent (+ policy context)
        -> RulesPolicyEngine.decide()
        -> PolicyDecision

The ML answers "what is most likely happening?" (frozen — see
src/model/classifier.py, src/model/calibrated_classifier.py). This module
answers "what are we permitted to do about it?" It is deterministic,
config-driven (src/policy/rules.yaml), and never trains, retrains, or
otherwise touches the ML model.

This REPLACES src/policy/placeholder_engine.py in the production pipeline.
The placeholder is left completely untouched and remains importable as a
reference/test fixture, exactly as the Day 3 classifier placeholder was
kept after Day 4 replaced it.

--------------------------------------------------------------------------
SAFETY-FIRST EVALUATION ORDER (see docs/architecture.md for the full
rationale). A permissive root-cause rule can never bypass a
higher-priority guard:

    1. Validate input                      -> HUMAN_REVIEW / INVALID_POLICY_INPUT
    2. Enforce opt-out                     -> HUMAN_REVIEW / CUSTOMER_OPTED_OUT
    3. Enforce amount threshold             -> HUMAN_REVIEW / HIGH_VALUE_ESCALATION
    4. WEBHOOK_AMBIGUITY safety override    -> BLOCK_RECONCILE / WEBHOOK_STATE_UNKNOWN
    5. Enforce retry cap                     -> HUMAN_REVIEW / RETRY_LIMIT_REACHED
    6. Enforce cooldown                      -> HUMAN_REVIEW / COOLDOWN_ACTIVE
    7. Enforce idempotency                   -> HUMAN_REVIEW / IDEMPOTENCY_BLOCK
    8. Evaluate root cause + confidence      -> the mapped action, or
                                                 HUMAN_REVIEW / LOW_MODEL_CONFIDENCE

Two deliberate design choices, both documented here so they are never
mistaken for oversights:

  - Guards 5-7 (retry cap, cooldown, idempotency) are applied UNIFORMLY
    to every root cause, not only to INFRASTRUCTURE's DEFER_RETRY. Section
    8 of the Day 7 spec places them structurally before root-cause
    evaluation; applying them universally is the literal, simplest, and
    strictly more conservative reading (it can only ever make the policy
    MORE cautious, never less).

  - Idempotency (guard 7) blocks on ANY previously-recorded automated
    action for the transaction, not only an identical repeat of the
    specific action about to be chosen. This sidesteps the chicken-and-egg
    problem of needing to know the candidate action before checking
    whether "that action" was already recorded, and is a strictly more
    conservative reading of "same transaction + same action cannot be
    executed twice."

WEBHOOK_AMBIGUITY -> BLOCK_RECONCILE (guard 4) is a hard safety invariant,
not a confidence-gated business rule: it is evaluated BEFORE the retry
cap / cooldown / idempotency guards specifically so nothing downstream —
high confidence, retry count, cooldown state, or a prior recorded action —
can ever turn it into DEFER_RETRY. Only opt-out and the amount threshold
(both strictly safer than BLOCK_RECONCILE — they escalate to a human
instead) are permitted to override it. There is NO code path anywhere in
this module that maps WEBHOOK_AMBIGUITY to DEFER_RETRY.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import FrozenSet, Optional

import yaml

from src.domain.models import (
    PaymentEvent,
    PolicyDecision,
    ReasonCode,
    RecoveryAction,
    RootCause,
    RootCausePrediction,
)

RULES_PATH = Path(__file__).parent / "rules.yaml"

# Actions that represent the system actually DOING something automated —
# used to decide what idempotency should guard against, and what counts
# as an "automated action" for the aggregate safety counters in
# tests/test_policy_safety.py.
AUTOMATED_ACTIONS = frozenset(
    {RecoveryAction.DEFER_RETRY, RecoveryAction.CUSTOMER_RECOVERY, RecoveryAction.BLOCK_RECONCILE}
)


@dataclass(frozen=True)
class PolicyConfig:
    policy_version: str
    confidence_thresholds: dict
    max_automated_retries: int
    cooldown_minutes: int
    max_automated_recovery_amount: float


def load_policy_config(rules_path: Path = RULES_PATH) -> PolicyConfig:
    with open(rules_path) as f:
        raw = yaml.safe_load(f)
    return PolicyConfig(
        policy_version=raw["policy_version"],
        confidence_thresholds=dict(raw["confidence_thresholds"]),
        max_automated_retries=int(raw["safety_limits"]["max_automated_retries"]),
        cooldown_minutes=int(raw["safety_limits"]["cooldown_minutes"]),
        max_automated_recovery_amount=float(raw["safety_limits"]["max_automated_recovery_amount"]),
    )


def _decision(
    transaction_id: str, action: RecoveryAction, reason: ReasonCode, policy_version: str
) -> PolicyDecision:
    return PolicyDecision(
        transaction_id=transaction_id,
        action=action,
        reason_codes=[reason],
        policy_version=policy_version,
        requires_human_review=(action == RecoveryAction.HUMAN_REVIEW),
    )


class RulesPolicyEngine:
    """The real, deterministic, config-driven Day 7 policy engine."""

    def __init__(self, config: Optional[PolicyConfig] = None, rules_path: Path = RULES_PATH):
        self._config = config or load_policy_config(rules_path)

    def decide(
        self,
        prediction: RootCausePrediction,
        payment_event: PaymentEvent,
        *,
        already_executed_actions: FrozenSet[RecoveryAction] = frozenset(),
        now: Optional[datetime] = None,
    ) -> PolicyDecision:
        """Args:
            prediction: the frozen calibrated classifier's output.
            payment_event: the transaction under evaluation.
            already_executed_actions: every automated RecoveryAction already
                recorded for this transaction_id in the existing
                idempotency_log (src/db.py) — see src/policy/idempotency.py
                for the helper that computes this from the real database.
                Deliberately NOT a live DB connection: keeps this function
                pure and deterministic (Day 7 spec section 20).
            now: the instant to evaluate cooldown against. Defaults to the
                real current time in production use; tests must always
                pass an explicit value for determinism.
        """
        cfg = self._config
        txn_id = getattr(prediction, "transaction_id", None) or getattr(
            payment_event, "transaction_id", "unknown"
        )

        # --- 1. Validate input -------------------------------------------------
        if not self._is_valid_input(prediction, payment_event):
            return _decision(
                str(txn_id), RecoveryAction.HUMAN_REVIEW, ReasonCode.INVALID_POLICY_INPUT, cfg.policy_version
            )

        # From here on, prediction/payment_event are known-valid.
        if now is None:
            # Naive UTC, not the deprecated datetime.utcnow() -- kept naive
            # to match PaymentEvent.last_recovery_action_at's convention.
            now = datetime.now(timezone.utc).replace(tzinfo=None)

        # --- 2. Opt-out ---------------------------------------------------------
        if payment_event.customer_opted_out:
            return _decision(
                prediction.transaction_id,
                RecoveryAction.HUMAN_REVIEW,
                ReasonCode.CUSTOMER_OPTED_OUT,
                cfg.policy_version,
            )

        # --- 3. Amount threshold --------------------------------------------------
        if payment_event.amount > cfg.max_automated_recovery_amount:
            return _decision(
                prediction.transaction_id,
                RecoveryAction.HUMAN_REVIEW,
                ReasonCode.HIGH_VALUE_ESCALATION,
                cfg.policy_version,
            )

        # --- 4. WEBHOOK_AMBIGUITY hard safety override -----------------------------
        # Always BLOCK_RECONCILE, regardless of confidence. See module
        # docstring: this must never become DEFER_RETRY under any condition.
        if prediction.root_cause == RootCause.WEBHOOK_AMBIGUITY:
            return _decision(
                prediction.transaction_id,
                RecoveryAction.BLOCK_RECONCILE,
                ReasonCode.WEBHOOK_STATE_UNKNOWN,
                cfg.policy_version,
            )

        # --- 5. Retry cap (uniform across all remaining root causes) -----------
        if payment_event.retry_count >= cfg.max_automated_retries:
            return _decision(
                prediction.transaction_id,
                RecoveryAction.HUMAN_REVIEW,
                ReasonCode.RETRY_LIMIT_REACHED,
                cfg.policy_version,
            )

        # --- 6. Cooldown ----------------------------------------------------------
        if payment_event.last_recovery_action_at is not None:
            elapsed = now - payment_event.last_recovery_action_at
            if elapsed < timedelta(minutes=cfg.cooldown_minutes):
                return _decision(
                    prediction.transaction_id,
                    RecoveryAction.HUMAN_REVIEW,
                    ReasonCode.COOLDOWN_ACTIVE,
                    cfg.policy_version,
                )

        # --- 7. Idempotency ---------------------------------------------------------
        if already_executed_actions & AUTOMATED_ACTIONS:
            return _decision(
                prediction.transaction_id,
                RecoveryAction.HUMAN_REVIEW,
                ReasonCode.IDEMPOTENCY_BLOCK,
                cfg.policy_version,
            )

        # --- 8. Root cause + confidence -------------------------------------------
        return self._decide_by_root_cause(prediction, cfg)

    def _decide_by_root_cause(self, prediction: RootCausePrediction, cfg: PolicyConfig) -> PolicyDecision:
        root_cause = prediction.root_cause
        probability = prediction.probability

        if root_cause == RootCause.INFRASTRUCTURE:
            threshold = cfg.confidence_thresholds["INFRASTRUCTURE"]
            if probability >= threshold:
                return _decision(
                    prediction.transaction_id, RecoveryAction.DEFER_RETRY, ReasonCode.INFRA_CLUSTER_HIGH, cfg.policy_version
                )
            return _decision(
                prediction.transaction_id, RecoveryAction.HUMAN_REVIEW, ReasonCode.LOW_MODEL_CONFIDENCE, cfg.policy_version
            )

        if root_cause in (RootCause.CARD_DECLINE, RootCause.INSUFFICIENT_FUNDS):
            threshold = cfg.confidence_thresholds[root_cause.value]
            if probability >= threshold:
                # CUSTOMER_RECOVERY authorizes routing the customer toward a
                # permitted alternate recovery path. It never means
                # automatically re-charging the same instrument, and no
                # messaging/execution happens here — see module docstring
                # and docs/architecture.md.
                return _decision(
                    prediction.transaction_id,
                    RecoveryAction.CUSTOMER_RECOVERY,
                    ReasonCode.CUSTOMER_SIDE_FAILURE,
                    cfg.policy_version,
                )
            return _decision(
                prediction.transaction_id, RecoveryAction.HUMAN_REVIEW, ReasonCode.LOW_MODEL_CONFIDENCE, cfg.policy_version
            )

        if root_cause in (RootCause.OTP_TIMEOUT, RootCause.USER_ABANDONMENT):
            # No explicit automated recovery action for these two is
            # specified anywhere in the project's roadmap/spec (only
            # INFRASTRUCTURE, CARD_DECLINE/INSUFFICIENT_FUNDS, and
            # WEBHOOK_AMBIGUITY have documented mappings). Per the Day 7
            # spec's explicit instruction not to invent an aggressive
            # recovery in that situation, both deliberately resolve to
            # NO_ACTION when confidence is sufficient (the customer either
            # already abandoned the flow or will typically retry the OTP/
            # payment themselves — there is no clear automated recovery
            # for the SYSTEM to take) and HUMAN_REVIEW otherwise. This is a
            # documented assumption, not a discovered specification.
            threshold = cfg.confidence_thresholds[root_cause.value]
            if probability >= threshold:
                return _decision(
                    prediction.transaction_id,
                    RecoveryAction.NO_ACTION,
                    ReasonCode.NO_AUTOMATED_ACTION_DEFINED,
                    cfg.policy_version,
                )
            return _decision(
                prediction.transaction_id, RecoveryAction.HUMAN_REVIEW, ReasonCode.LOW_MODEL_CONFIDENCE, cfg.policy_version
            )

        # Defense in depth: RootCause is a strict enum, so this should be
        # unreachable through the normal typed path. Fail closed anyway,
        # rather than assume the type system is never bypassed (e.g. a
        # test or a future caller constructing a malformed object).
        return _decision(
            prediction.transaction_id, RecoveryAction.HUMAN_REVIEW, ReasonCode.INVALID_POLICY_INPUT, cfg.policy_version
        )

    @staticmethod
    def _is_valid_input(prediction: RootCausePrediction, payment_event: PaymentEvent) -> bool:
        transaction_id = getattr(prediction, "transaction_id", None)
        if not transaction_id or not isinstance(transaction_id, str):
            return False

        root_cause = getattr(prediction, "root_cause", None)
        if not isinstance(root_cause, RootCause) or root_cause not in set(RootCause):
            return False

        probability = getattr(prediction, "probability", None)
        if not isinstance(probability, (int, float)) or isinstance(probability, bool):
            return False
        if not math.isfinite(probability) or probability < 0.0 or probability > 1.0:
            return False

        amount = getattr(payment_event, "amount", None)
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            return False
        if not math.isfinite(amount) or amount <= 0:
            return False

        retry_count = getattr(payment_event, "retry_count", None)
        if not isinstance(retry_count, int) or isinstance(retry_count, bool) or retry_count < 0:
            return False

        opted_out = getattr(payment_event, "customer_opted_out", None)
        if not isinstance(opted_out, bool):
            return False

        return True
