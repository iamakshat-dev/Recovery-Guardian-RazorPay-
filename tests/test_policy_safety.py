"""
Recovery Guardian — Day 7 Aggregate Policy Safety Test

Separate from tests/test_policy_engine.py's per-case unit tests. This file
runs a deliberately adversarial BATCH of synthetic policy cases through
the actual RulesPolicyEngine and computes aggregate SAFETY COUNTERS over
the real decisions produced — not hand-asserted per-case expectations.

This is a safety test dataset, not a performance benchmark: no revenue,
recovery-rate, or accuracy numbers are computed or claimed here.
"""

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, FrozenSet
from unittest import mock

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.models import PaymentEvent, RecoveryAction, RootCause, RootCausePrediction
from src.policy.engine import AUTOMATED_ACTIONS, RulesPolicyEngine, load_policy_config

CONFIG = load_policy_config()
NOW = datetime(2026, 8, 1, 12, 0, 0)


def make_event(**overrides) -> PaymentEvent:
    base = dict(
        event_id="evt_safety_0001",
        transaction_id="txn_safety_0001",
        merchant_id="merchant_001",
        amount=1000.0,
        timestamp=NOW,
        payment_method="card",
        failure_code="gateway_timeout",
        retry_count=0,
        webhook_delay_seconds=1.0,
        gateway_error_rate_delta=0.3,
        merchant_failure_rate_delta=0.2,
        cross_merchant_failure_rate=0.15,
        customer_previous_successes=3,
        customer_previous_failures=1,
        incident_active=True,
        source="synthetic",
    )
    base.update(overrides)
    return PaymentEvent(**base)


@dataclass
class AdversarialCase:
    label: str
    prediction: Any  # RootCausePrediction, or a Mock simulating malformed input
    event: PaymentEvent
    already_executed_actions: FrozenSet[RecoveryAction] = frozenset()
    now: datetime = NOW


def _pred(root_cause, probability, transaction_id="txn_safety_0001"):
    return RootCausePrediction(
        transaction_id=transaction_id,
        root_cause=root_cause,
        probability=probability,
        model_version="root-cause-logreg-calibrated-v1",
    )


def build_adversarial_cases() -> list:
    cases = []
    high = CONFIG.confidence_thresholds["INFRASTRUCTURE"] + 0.15
    low = CONFIG.confidence_thresholds["INFRASTRUCTURE"] - 0.25
    cap = CONFIG.max_automated_retries
    cooldown = CONFIG.cooldown_minutes
    max_amount = CONFIG.max_automated_recovery_amount

    # --- duplicate webhook events / repeated ambiguous predictions ----------
    for i in range(3):
        cases.append(AdversarialCase(
            f"duplicate_webhook_event_{i}",
            _pred(RootCause.WEBHOOK_AMBIGUITY, 0.6 + i * 0.1),
            make_event(transaction_id=f"txn_webhook_dup_{i}", failure_code="gateway_timeout"),
        ))
    cases.append(AdversarialCase(
        "webhook_ambiguity_already_block_reconciled_once",
        _pred(RootCause.WEBHOOK_AMBIGUITY, 0.95),
        make_event(transaction_id="txn_webhook_repeat"),
        already_executed_actions=frozenset({RecoveryAction.BLOCK_RECONCILE}),
    ))
    cases.append(AdversarialCase(
        "webhook_ambiguity_extreme_confidence_with_high_retry_count",
        _pred(RootCause.WEBHOOK_AMBIGUITY, 0.999),
        make_event(transaction_id="txn_webhook_extreme", retry_count=cap + 5),
    ))

    # --- repeated retry attempts / retry-limit-exceeded ----------------------
    for rc in (0, cap - 1, cap, cap + 1, cap + 10):
        cases.append(AdversarialCase(
            f"infrastructure_retry_count_{rc}",
            _pred(RootCause.INFRASTRUCTURE, high),
            make_event(transaction_id=f"txn_retry_{rc}", retry_count=rc),
        ))

    # --- opted-out customers, across every root cause -----------------------
    for cause in RootCause:
        cases.append(AdversarialCase(
            f"opted_out_{cause.value}",
            _pred(cause, 0.99),
            make_event(transaction_id=f"txn_optout_{cause.value}", customer_opted_out=True),
        ))

    # --- high-value payments, across a few root causes -----------------------
    for cause in (RootCause.CARD_DECLINE, RootCause.INFRASTRUCTURE, RootCause.INSUFFICIENT_FUNDS):
        cases.append(AdversarialCase(
            f"high_value_{cause.value}",
            _pred(cause, 0.99),
            make_event(transaction_id=f"txn_highvalue_{cause.value}", amount=max_amount + 1.0),
        ))
    cases.append(AdversarialCase(
        "high_value_exactly_at_threshold",
        _pred(RootCause.CARD_DECLINE, 0.99),
        make_event(transaction_id="txn_highvalue_exact", amount=max_amount),
    ))

    # --- ambiguous payment states with conflicting signals -------------------
    cases.append(AdversarialCase(
        "webhook_ambiguity_conflicting_incident_flag_off",
        _pred(RootCause.WEBHOOK_AMBIGUITY, 0.7),
        make_event(transaction_id="txn_conflict_1", incident_active=False, failure_code="unknown"),
    ))
    cases.append(AdversarialCase(
        "webhook_ambiguity_conflicting_high_success_history",
        _pred(RootCause.WEBHOOK_AMBIGUITY, 0.8),
        make_event(
            transaction_id="txn_conflict_2",
            customer_previous_successes=50,
            customer_previous_failures=0,
        ),
    ))

    # --- low-confidence predictions across all six classes -------------------
    for cause in RootCause:
        cases.append(AdversarialCase(
            f"low_confidence_{cause.value}",
            _pred(cause, low if cause != RootCause.WEBHOOK_AMBIGUITY else 0.05),
            make_event(transaction_id=f"txn_lowconf_{cause.value}"),
        ))

    # --- invalid probabilities ------------------------------------------------
    for i, bad_prob in enumerate([float("nan"), -0.1, 1.5, float("inf"), float("-inf")]):
        cases.append(AdversarialCase(
            f"invalid_probability_{i}",
            mock.Mock(
                transaction_id=f"txn_invalid_prob_{i}",
                root_cause=RootCause.INFRASTRUCTURE,
                probability=bad_prob,
            ),
            make_event(transaction_id=f"txn_invalid_prob_{i}"),
        ))

    # --- unknown / malformed root cause ---------------------------------------
    cases.append(AdversarialCase(
        "unknown_root_cause_string",
        mock.Mock(transaction_id="txn_unknown_rc", root_cause="SOMETHING_ELSE", probability=0.9),
        make_event(transaction_id="txn_unknown_rc"),
    ))
    cases.append(AdversarialCase(
        "missing_root_cause_none",
        mock.Mock(transaction_id="txn_missing_rc", root_cause=None, probability=0.9),
        make_event(transaction_id="txn_missing_rc"),
    ))

    # --- malformed amount / retry_count on the event ---------------------------
    cases.append(AdversarialCase(
        "malformed_amount_zero",
        _pred(RootCause.CARD_DECLINE, 0.99),
        make_event(transaction_id="txn_bad_amount", amount=0.0),
    ))
    cases.append(AdversarialCase(
        "malformed_amount_negative",
        _pred(RootCause.CARD_DECLINE, 0.99),
        make_event(transaction_id="txn_bad_amount_2", amount=-500.0),
    ))
    cases.append(AdversarialCase(
        "malformed_retry_count_negative",
        _pred(RootCause.INFRASTRUCTURE, 0.99),
        make_event(transaction_id="txn_bad_retry", retry_count=-3),
    ))

    # --- duplicate action attempts (idempotency) across automated actions -----
    for cause, action in [
        (RootCause.INFRASTRUCTURE, RecoveryAction.DEFER_RETRY),
        (RootCause.CARD_DECLINE, RecoveryAction.CUSTOMER_RECOVERY),
        (RootCause.INSUFFICIENT_FUNDS, RecoveryAction.CUSTOMER_RECOVERY),
        (RootCause.WEBHOOK_AMBIGUITY, RecoveryAction.BLOCK_RECONCILE),
    ]:
        cases.append(AdversarialCase(
            f"duplicate_action_{cause.value}_{action.value}",
            _pred(cause, 0.95),
            make_event(transaction_id=f"txn_dup_{cause.value}"),
            already_executed_actions=frozenset({action}),
        ))

    # --- cooldown-active transactions -----------------------------------------
    for minutes_ago, label in [
        (cooldown - 1, "just_before_expiry"),
        (cooldown, "exactly_at_expiry"),
        (cooldown + 1, "just_after_expiry"),
    ]:
        cases.append(AdversarialCase(
            f"cooldown_{label}",
            _pred(RootCause.INFRASTRUCTURE, high),
            make_event(
                transaction_id=f"txn_cooldown_{label}",
                last_recovery_action_at=NOW - timedelta(minutes=minutes_ago),
            ),
        ))

    # --- combined adversarial stress cases (multiple guards at once) ----------
    cases.append(AdversarialCase(
        "opted_out_AND_high_value_AND_webhook_ambiguity",
        _pred(RootCause.WEBHOOK_AMBIGUITY, 0.999),
        make_event(
            transaction_id="txn_stress_1",
            customer_opted_out=True,
            amount=max_amount + 5000,
            retry_count=cap + 1,
        ),
    ))
    cases.append(AdversarialCase(
        "retry_cap_AND_cooldown_AND_infrastructure_high_confidence",
        _pred(RootCause.INFRASTRUCTURE, 0.999),
        make_event(
            transaction_id="txn_stress_2",
            retry_count=cap + 1,
            last_recovery_action_at=NOW - timedelta(minutes=1),
        ),
    ))
    cases.append(AdversarialCase(
        "opted_out_low_confidence_otp_timeout",
        _pred(RootCause.OTP_TIMEOUT, low),
        make_event(transaction_id="txn_stress_3", customer_opted_out=True),
    ))

    return cases


def test_aggregate_policy_safety_over_adversarial_batch():
    cases = build_adversarial_cases()
    assert 20 <= len(cases) <= 50, f"expected 20-50 adversarial cases, built {len(cases)}"

    engine = RulesPolicyEngine()

    duplicate_retries = 0
    opt_out_violations = 0
    ambiguous_state_retries = 0
    retry_limit_violations = 0
    high_value_automated_actions = 0
    invalid_input_automated_actions = 0

    for case in cases:
        decision = engine.decide(
            case.prediction,
            case.event,
            already_executed_actions=case.already_executed_actions,
            now=case.now,
        )
        is_automated = decision.action in AUTOMATED_ACTIONS

        # duplicate_retries: a DEFER_RETRY (specifically) was authorized
        # despite DEFER_RETRY already being recorded for this transaction
        # -- the actual duplicate-CHARGE-risk scenario this counter exists
        # to catch. Deliberately NOT "any repeated automated action": a
        # repeated BLOCK_RECONCILE carries no duplicate-charge risk (it
        # authorizes no payment attempt at all), and WEBHOOK_AMBIGUITY's
        # BLOCK_RECONCILE mapping is a hard safety invariant that idempotency
        # is explicitly NOT permitted to override (Day 7 spec section 14
        # lists only opt-out and the amount threshold as guards allowed to
        # override it) -- so a case pairing WEBHOOK_AMBIGUITY with a prior
        # recorded BLOCK_RECONCILE re-authorizing BLOCK_RECONCILE is
        # correct engine behavior, not a duplicate retry.
        if (
            decision.action == RecoveryAction.DEFER_RETRY
            and RecoveryAction.DEFER_RETRY in case.already_executed_actions
        ):
            duplicate_retries += 1

        # opt_out_violations: an opted-out customer received ANY automated
        # action.
        if case.event.customer_opted_out and is_automated:
            opt_out_violations += 1

        # ambiguous_state_retries: a WEBHOOK_AMBIGUITY case resulted in
        # DEFER_RETRY specifically -- the hard safety invariant.
        root_cause = getattr(case.prediction, "root_cause", None)
        if root_cause == RootCause.WEBHOOK_AMBIGUITY and decision.action == RecoveryAction.DEFER_RETRY:
            ambiguous_state_retries += 1

        # retry_limit_violations: retry_count at/over the cap still resulted
        # in DEFER_RETRY specifically -- the actual "unlimited retries" risk
        # this counter exists to catch (Day 7 spec section 11: "never permit
        # unlimited DEFER_RETRY actions"). Not "any automated action": the
        # retry cap is, like idempotency, not among the guards Day 7 spec
        # section 14 permits to override WEBHOOK_AMBIGUITY's BLOCK_RECONCILE
        # mapping, so a high-retry-count WEBHOOK_AMBIGUITY case correctly
        # still gets BLOCK_RECONCILE (never a retry) regardless of retry_count.
        if case.event.retry_count >= CONFIG.max_automated_retries and decision.action == RecoveryAction.DEFER_RETRY:
            retry_limit_violations += 1

        # high_value_automated_actions: amount over the configured ceiling
        # still got an automated action.
        if case.event.amount > CONFIG.max_automated_recovery_amount and is_automated:
            high_value_automated_actions += 1

        # invalid_input_automated_actions: a malformed/invalid prediction
        # still produced an automated action.
        probability = getattr(case.prediction, "probability", None)
        is_invalid_probability = (
            not isinstance(probability, (int, float))
            or probability != probability  # NaN
            or probability < 0.0
            or probability > 1.0
        )
        is_invalid_root_cause = not isinstance(root_cause, RootCause)
        if (is_invalid_probability or is_invalid_root_cause) and is_automated:
            invalid_input_automated_actions += 1

    # --- Mandatory safety counters (Day 7 spec section 23) --------------------
    assert duplicate_retries == 0, f"duplicate_retries={duplicate_retries}"
    assert opt_out_violations == 0, f"opt_out_violations={opt_out_violations}"
    assert ambiguous_state_retries == 0, f"ambiguous_state_retries={ambiguous_state_retries}"

    # --- Additional aggregate safety properties (Day 7 spec section 24) -------
    assert retry_limit_violations == 0, f"retry_limit_violations={retry_limit_violations}"
    assert high_value_automated_actions == 0, f"high_value_automated_actions={high_value_automated_actions}"
    assert invalid_input_automated_actions == 0, f"invalid_input_automated_actions={invalid_input_automated_actions}"
