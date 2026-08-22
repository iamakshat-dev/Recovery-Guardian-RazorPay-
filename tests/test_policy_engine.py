"""
Recovery Guardian — Day 7 Policy Engine Unit + Boundary Tests

Exercises the real, deterministic RulesPolicyEngine (src/policy/engine.py)
directly. The Day 3 placeholder (src/policy/placeholder_engine.py) is
untouched and covered separately by tests/test_policy_scope_guard.py.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.models import (
    PaymentEvent,
    RecoveryAction,
    ReasonCode,
    RootCause,
    RootCausePrediction,
)
from src.policy.engine import RulesPolicyEngine, load_policy_config

CONFIG = load_policy_config()
NOW = datetime(2026, 8, 1, 12, 0, 0)


def make_event(**overrides) -> PaymentEvent:
    base = dict(
        event_id="evt_policy_0001",
        transaction_id="txn_policy_0001",
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


def make_prediction(root_cause: RootCause, probability: float, **overrides) -> RootCausePrediction:
    base = dict(
        transaction_id="txn_policy_0001",
        root_cause=root_cause,
        probability=probability,
        model_version="root-cause-logreg-calibrated-v1",
    )
    base.update(overrides)
    return RootCausePrediction(**base)


@pytest.fixture
def engine():
    return RulesPolicyEngine()


# --- Test 1/2: INFRASTRUCTURE ------------------------------------------------

def test_infrastructure_high_confidence_defers_retry(engine):
    threshold = CONFIG.confidence_thresholds["INFRASTRUCTURE"]
    prediction = make_prediction(RootCause.INFRASTRUCTURE, threshold + 0.1)
    decision = engine.decide(prediction, make_event(), now=NOW)

    assert decision.action == RecoveryAction.DEFER_RETRY
    assert ReasonCode.INFRA_CLUSTER_HIGH in decision.reason_codes


def test_infrastructure_low_confidence_goes_to_human_review(engine):
    threshold = CONFIG.confidence_thresholds["INFRASTRUCTURE"]
    prediction = make_prediction(RootCause.INFRASTRUCTURE, threshold - 0.2)
    decision = engine.decide(prediction, make_event(), now=NOW)

    assert decision.action == RecoveryAction.HUMAN_REVIEW
    assert ReasonCode.LOW_MODEL_CONFIDENCE in decision.reason_codes


# --- Test 3/4: CARD_DECLINE / INSUFFICIENT_FUNDS -----------------------------

def test_card_decline_sufficient_confidence_customer_recovery(engine):
    threshold = CONFIG.confidence_thresholds["CARD_DECLINE"]
    prediction = make_prediction(RootCause.CARD_DECLINE, threshold + 0.1)
    decision = engine.decide(prediction, make_event(), now=NOW)

    assert decision.action == RecoveryAction.CUSTOMER_RECOVERY
    assert ReasonCode.CUSTOMER_SIDE_FAILURE in decision.reason_codes


def test_insufficient_funds_sufficient_confidence_customer_recovery(engine):
    threshold = CONFIG.confidence_thresholds["INSUFFICIENT_FUNDS"]
    prediction = make_prediction(RootCause.INSUFFICIENT_FUNDS, threshold + 0.1)
    decision = engine.decide(prediction, make_event(), now=NOW)

    assert decision.action == RecoveryAction.CUSTOMER_RECOVERY
    assert ReasonCode.CUSTOMER_SIDE_FAILURE in decision.reason_codes


# --- Test 5/6/7: WEBHOOK_AMBIGUITY hard safety invariant ---------------------

def test_webhook_ambiguity_normal_confidence_blocks_and_reconciles(engine):
    prediction = make_prediction(RootCause.WEBHOOK_AMBIGUITY, 0.55)
    decision = engine.decide(prediction, make_event(), now=NOW)

    assert decision.action == RecoveryAction.BLOCK_RECONCILE
    assert ReasonCode.WEBHOOK_STATE_UNKNOWN in decision.reason_codes


@pytest.mark.parametrize("probability", [0.99, 0.999, 1.0])
def test_webhook_ambiguity_extreme_confidence_still_blocks_and_reconciles(engine, probability):
    prediction = make_prediction(RootCause.WEBHOOK_AMBIGUITY, probability)
    decision = engine.decide(prediction, make_event(), now=NOW)

    assert decision.action == RecoveryAction.BLOCK_RECONCILE


@pytest.mark.parametrize("probability", [0.0, 0.3, 0.55, 0.75, 0.9, 0.99, 1.0])
def test_webhook_ambiguity_never_defers_retry_at_any_confidence(engine, probability):
    prediction = make_prediction(RootCause.WEBHOOK_AMBIGUITY, probability)
    decision = engine.decide(prediction, make_event(), now=NOW)

    assert decision.action != RecoveryAction.DEFER_RETRY


def test_webhook_ambiguity_never_defers_retry_regardless_of_retry_count(engine):
    """High confidence AND a retry count that would otherwise trip the
    retry cap -- WEBHOOK_AMBIGUITY must still never become DEFER_RETRY."""
    prediction = make_prediction(RootCause.WEBHOOK_AMBIGUITY, 0.99)
    decision = engine.decide(prediction, make_event(retry_count=10), now=NOW)

    assert decision.action == RecoveryAction.BLOCK_RECONCILE
    assert decision.action != RecoveryAction.DEFER_RETRY


# --- Test 8/9: OTP_TIMEOUT / USER_ABANDONMENT --------------------------------

def test_otp_timeout_sufficient_confidence_configured_action_is_no_action(engine):
    threshold = CONFIG.confidence_thresholds["OTP_TIMEOUT"]
    prediction = make_prediction(RootCause.OTP_TIMEOUT, threshold + 0.1)
    decision = engine.decide(prediction, make_event(), now=NOW)

    # Documented Day 7 assumption (src/policy/engine.py): no explicit
    # automated recovery is specified for OTP_TIMEOUT anywhere in the
    # project roadmap, so it deliberately resolves to NO_ACTION rather
    # than an invented aggressive recovery.
    assert decision.action == RecoveryAction.NO_ACTION
    assert ReasonCode.NO_AUTOMATED_ACTION_DEFINED in decision.reason_codes


def test_user_abandonment_sufficient_confidence_configured_action_is_no_action(engine):
    threshold = CONFIG.confidence_thresholds["USER_ABANDONMENT"]
    prediction = make_prediction(RootCause.USER_ABANDONMENT, threshold + 0.1)
    decision = engine.decide(prediction, make_event(), now=NOW)

    assert decision.action == RecoveryAction.NO_ACTION
    assert ReasonCode.NO_AUTOMATED_ACTION_DEFINED in decision.reason_codes


# --- Test 10: opt-out ---------------------------------------------------------

def test_opted_out_customer_never_gets_automated_recovery(engine):
    prediction = make_prediction(RootCause.INFRASTRUCTURE, 0.99)
    decision = engine.decide(prediction, make_event(customer_opted_out=True), now=NOW)

    assert decision.action in (RecoveryAction.HUMAN_REVIEW, RecoveryAction.NO_ACTION)
    assert ReasonCode.CUSTOMER_OPTED_OUT in decision.reason_codes


def test_opt_out_overrides_even_high_confidence_infrastructure(engine):
    """Opt-out must override root cause, confidence, amount, and retry
    eligibility -- confirmed directly, not just for a low-confidence case."""
    prediction = make_prediction(RootCause.INFRASTRUCTURE, 1.0)
    decision = engine.decide(
        prediction, make_event(customer_opted_out=True, amount=1.0, retry_count=0), now=NOW
    )
    assert decision.action != RecoveryAction.DEFER_RETRY
    assert ReasonCode.CUSTOMER_OPTED_OUT in decision.reason_codes


# --- Test 11: amount threshold -----------------------------------------------

def test_high_value_payment_forces_human_review(engine):
    prediction = make_prediction(RootCause.CARD_DECLINE, 0.99)
    decision = engine.decide(
        prediction,
        make_event(amount=CONFIG.max_automated_recovery_amount + 1.0),
        now=NOW,
    )

    assert decision.action == RecoveryAction.HUMAN_REVIEW
    assert ReasonCode.HIGH_VALUE_ESCALATION in decision.reason_codes


# --- Test 12: retry cap -------------------------------------------------------

@pytest.mark.parametrize(
    "retry_count,expect_blocked",
    [(0, False), (CONFIG.max_automated_retries - 1, False),
     (CONFIG.max_automated_retries, True), (CONFIG.max_automated_retries + 1, True)],
)
def test_retry_cap_boundary(engine, retry_count, expect_blocked):
    prediction = make_prediction(RootCause.INFRASTRUCTURE, 0.99)
    decision = engine.decide(prediction, make_event(retry_count=retry_count), now=NOW)

    if expect_blocked:
        assert decision.action == RecoveryAction.HUMAN_REVIEW
        assert ReasonCode.RETRY_LIMIT_REACHED in decision.reason_codes
    else:
        assert decision.action == RecoveryAction.DEFER_RETRY


# --- Test 13: cooldown ---------------------------------------------------------

def test_cooldown_just_before_expiry_blocks(engine):
    last_action = NOW - timedelta(minutes=CONFIG.cooldown_minutes - 1)
    prediction = make_prediction(RootCause.INFRASTRUCTURE, 0.99)
    decision = engine.decide(
        prediction, make_event(last_recovery_action_at=last_action), now=NOW
    )
    assert decision.action == RecoveryAction.HUMAN_REVIEW
    assert ReasonCode.COOLDOWN_ACTIVE in decision.reason_codes


def test_cooldown_exactly_at_expiry_is_no_longer_active(engine):
    last_action = NOW - timedelta(minutes=CONFIG.cooldown_minutes)
    prediction = make_prediction(RootCause.INFRASTRUCTURE, 0.99)
    decision = engine.decide(
        prediction, make_event(last_recovery_action_at=last_action), now=NOW
    )
    # elapsed == cooldown window exactly: comparison is strict "<", so at
    # exactly the boundary the cooldown has expired (documented semantics).
    assert decision.action == RecoveryAction.DEFER_RETRY


def test_cooldown_just_after_expiry_is_not_active(engine):
    last_action = NOW - timedelta(minutes=CONFIG.cooldown_minutes + 1)
    prediction = make_prediction(RootCause.INFRASTRUCTURE, 0.99)
    decision = engine.decide(
        prediction, make_event(last_recovery_action_at=last_action), now=NOW
    )
    assert decision.action == RecoveryAction.DEFER_RETRY


def test_no_prior_action_means_no_cooldown(engine):
    prediction = make_prediction(RootCause.INFRASTRUCTURE, 0.99)
    decision = engine.decide(
        prediction, make_event(last_recovery_action_at=None), now=NOW
    )
    assert decision.action == RecoveryAction.DEFER_RETRY


# --- Test 14: idempotency -----------------------------------------------------

def test_existing_recorded_action_prevents_duplicate_automated_action(engine):
    prediction = make_prediction(RootCause.INFRASTRUCTURE, 0.99)
    decision = engine.decide(
        prediction,
        make_event(),
        already_executed_actions=frozenset({RecoveryAction.DEFER_RETRY}),
        now=NOW,
    )
    assert decision.action == RecoveryAction.HUMAN_REVIEW
    assert ReasonCode.IDEMPOTENCY_BLOCK in decision.reason_codes


def test_no_recorded_action_allows_automated_action(engine):
    prediction = make_prediction(RootCause.INFRASTRUCTURE, 0.99)
    decision = engine.decide(
        prediction, make_event(), already_executed_actions=frozenset(), now=NOW
    )
    assert decision.action == RecoveryAction.DEFER_RETRY


# --- Test 15/16: invalid input fails closed ----------------------------------

def test_invalid_probability_nan_fails_closed(engine):
    bad_prediction = mock.Mock(
        transaction_id="txn_policy_0001", root_cause=RootCause.INFRASTRUCTURE, probability=float("nan")
    )
    decision = engine.decide(bad_prediction, make_event(), now=NOW)
    assert decision.action not in (RecoveryAction.DEFER_RETRY, RecoveryAction.CUSTOMER_RECOVERY)
    assert ReasonCode.INVALID_POLICY_INPUT in decision.reason_codes


@pytest.mark.parametrize("probability", [-0.1, 1.1, -1.0, 2.0])
def test_out_of_range_probability_fails_closed(engine, probability):
    bad_prediction = mock.Mock(
        transaction_id="txn_policy_0001", root_cause=RootCause.INFRASTRUCTURE, probability=probability
    )
    decision = engine.decide(bad_prediction, make_event(), now=NOW)
    assert decision.action not in (RecoveryAction.DEFER_RETRY, RecoveryAction.CUSTOMER_RECOVERY)
    assert ReasonCode.INVALID_POLICY_INPUT in decision.reason_codes


def test_unknown_root_cause_fails_closed(engine):
    bad_prediction = mock.Mock(
        transaction_id="txn_policy_0001", root_cause="NOT_A_REAL_ROOT_CAUSE", probability=0.9
    )
    decision = engine.decide(bad_prediction, make_event(), now=NOW)
    assert decision.action not in (RecoveryAction.DEFER_RETRY, RecoveryAction.CUSTOMER_RECOVERY)
    assert ReasonCode.INVALID_POLICY_INPUT in decision.reason_codes


def test_missing_transaction_id_fails_closed(engine):
    bad_prediction = mock.Mock(transaction_id="", root_cause=RootCause.INFRASTRUCTURE, probability=0.9)
    decision = engine.decide(bad_prediction, make_event(), now=NOW)
    assert decision.action not in (RecoveryAction.DEFER_RETRY, RecoveryAction.CUSTOMER_RECOVERY)
    assert ReasonCode.INVALID_POLICY_INPUT in decision.reason_codes


def test_malformed_amount_fails_closed(engine):
    prediction = make_prediction(RootCause.CARD_DECLINE, 0.99)
    bad_event = make_event(amount=0.0)  # amount must be > 0
    decision = engine.decide(prediction, bad_event, now=NOW)
    assert decision.action not in (RecoveryAction.DEFER_RETRY, RecoveryAction.CUSTOMER_RECOVERY)
    assert ReasonCode.INVALID_POLICY_INPUT in decision.reason_codes


def test_malformed_negative_retry_count_fails_closed(engine):
    prediction = make_prediction(RootCause.INFRASTRUCTURE, 0.99)
    bad_event = make_event(retry_count=-1)
    decision = engine.decide(prediction, bad_event, now=NOW)
    assert decision.action not in (RecoveryAction.DEFER_RETRY, RecoveryAction.CUSTOMER_RECOVERY)
    assert ReasonCode.INVALID_POLICY_INPUT in decision.reason_codes


# --- Determinism --------------------------------------------------------------

def test_policy_is_deterministic_for_identical_input(engine):
    prediction = make_prediction(RootCause.INFRASTRUCTURE, 0.9)
    event = make_event()

    decision_a = engine.decide(prediction, event, now=NOW)
    decision_b = engine.decide(prediction, event, now=NOW)

    assert decision_a.action == decision_b.action
    assert decision_a.reason_codes == decision_b.reason_codes
