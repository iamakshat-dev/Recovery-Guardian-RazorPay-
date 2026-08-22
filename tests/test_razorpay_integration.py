"""
Recovery Guardian — Day 11 End-to-End Razorpay Integration Tests

Uses REAL downstream components throughout (no mocks): the real feature
builder, the real frozen calibrated classifier, and the real Day 7
RulesPolicyEngine — via the real run_pipeline() where a full pipeline run
is needed, and directly where isolating one stage is clearer.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.db import SCHEMA
from src.domain.models import PaymentEvent, RecoveryAction, RootCausePrediction
from src.features.build_features import FEATURE_COLUMNS, build_features
from src.ingestion.razorpay_adapter import PlatformHealthContext, razorpay_webhook_to_payment_event
from src.ingestion.synthetic_adapter import synthetic_to_payment_event
from src.model.calibrated_classifier import CalibratedRootCauseClassifier
from src.model.training import DATA_PATH
from src.pipeline.pipeline import run_pipeline
from src.policy.engine import RulesPolicyEngine
from tests.fixtures.razorpay_payloads import VALID_CARD_DECLINE_PAYLOAD


def fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# --- Reverse failure_code -> representative error_reason, for building twins ----

_FAILURE_CODE_TO_ERROR_REASON = {
    "gateway_timeout": "gateway_timeout",
    "internal_error": "internal_error",
    "service_unavailable": "service_unavailable",
    "issuer_declined": "issuer_declined",
    "card_expired": "card_expired",
    "invalid_card": "invalid_card",
    "insufficient_funds": "insufficient_funds",
    "otp_timeout": "otp_timeout",
    "3ds_auth_failed": "authentication_failed",
    "user_cancelled": "user_cancelled",
    "session_expired": "session_expired",
    "unknown": None,  # no error_reason at all -> adapter maps absence to "unknown"
}


def _build_razorpay_twin_payload(row: dict, rounded_webhook_delay: int) -> dict:
    """Builds a Razorpay-shaped payload reproducing the same underlying
    values as `row` (a real synthetic dataset row). Razorpay's real
    timestamps are integer Unix seconds, so `rounded_webhook_delay` (an
    int) is used for both sides of the comparison -- an honest,
    documented precision limitation (see docs/architecture.md's Day 11
    section), not a fabricated value."""
    payment_created_at = 1735689600
    webhook_created_at = payment_created_at + rounded_webhook_delay
    error_reason = _FAILURE_CODE_TO_ERROR_REASON[row["failure_code"]]
    entity = {
        "id": row["transaction_id"],
        "amount": round(row["amount"] * 100),  # rupees -> paise
        "currency": "INR",
        "method": row["payment_method"],
        "status": "failed",
        "error_code": "N/A",
        "error_reason": error_reason,
        "created_at": payment_created_at,
        "attempts": int(row["retry_count"]),
        "notes": {
            "merchant_id": row["merchant_id"],
            "customer_previous_successes": int(row["customer_previous_successes"]),
            "customer_previous_failures": int(row["customer_previous_failures"]),
        },
    }
    if error_reason is None:
        del entity["error_reason"]
    return {
        "event": "payment.failed",
        "created_at": webhook_created_at,
        "payload": {"payment": {"entity": entity}},
    }


def _find_real_row_predicted_as(root_cause_label: str, min_probability: float = 0.75) -> dict:
    classifier = CalibratedRootCauseClassifier()
    raw_df = pd.read_csv(DATA_PATH)
    for idx in range(len(raw_df)):
        row = raw_df.iloc[[idx]]
        features_df = build_features(row, keep_label=False)
        prediction = classifier.predict(features_df.iloc[0])
        if prediction.root_cause.value == root_cause_label and prediction.probability >= min_probability:
            return raw_df.iloc[idx].to_dict()
    pytest.fail(f"No row predicted as {root_cause_label} with probability >= {min_probability}")


def _predict_from_payment_event(event: PaymentEvent) -> RootCausePrediction:
    classifier = CalibratedRootCauseClassifier()
    features_df = build_features(pd.DataFrame([event.model_dump()]), keep_label=False)
    return classifier.predict(features_df.iloc[0])


# --- Test 13/14/15/16/17: full real pipeline, unmocked -------------------------

def test_adapter_to_payment_event():
    event = razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)
    assert isinstance(event, PaymentEvent)


def test_payment_event_to_feature_builder():
    event = razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)
    features_df = build_features(pd.DataFrame([event.model_dump()]), keep_label=False)
    assert list(features_df[FEATURE_COLUMNS].columns) == list(FEATURE_COLUMNS)
    assert not features_df[FEATURE_COLUMNS].isnull().values.any()


def test_features_to_calibrated_model():
    event = razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)
    prediction = _predict_from_payment_event(event)
    assert isinstance(prediction, RootCausePrediction)
    assert 0.0 <= prediction.probability <= 1.0
    assert prediction.model_version == "root-cause-logreg-calibrated-v1"


def test_model_to_policy():
    event = razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)
    prediction = _predict_from_payment_event(event)
    decision = RulesPolicyEngine().decide(prediction, event, now=datetime(2026, 1, 1))
    assert decision.action in RecoveryAction


def test_full_pipeline_end_to_end_via_real_run_pipeline():
    """The real, unmocked, full production pipeline -- feature builder,
    calibrated classifier, and Day 7 policy engine, exactly as production
    uses them -- accepts a Razorpay-adapted event."""
    event = razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)
    record = run_pipeline(event, conn=fresh_conn())

    assert record.event.source == "razorpay"
    assert record.prediction.model_version == "root-cause-logreg-calibrated-v1"
    assert record.policy.policy_version == "rules-v1"
    assert record.policy.action in RecoveryAction


# --- Test 18/19: synthetic/canonical convergence ---------------------------------

def test_synthetic_and_razorpay_twins_converge_on_webhook_ambiguity():
    """A real WEBHOOK_AMBIGUITY dataset row, expressed BOTH as a synthetic
    CSV row and as an equivalent Razorpay-shaped payload, must produce the
    identical RootCausePrediction and identical PolicyDecision.action.
    Razorpay's real timestamps are integer-second precision, so the
    webhook delay is rounded identically on both sides -- an honest,
    documented limitation, not a fabricated value (see
    docs/architecture.md)."""
    row = _find_real_row_predicted_as("WEBHOOK_AMBIGUITY")
    rounded_delay = round(row["webhook_delay_seconds"])
    row = dict(row)
    row["webhook_delay_seconds"] = float(rounded_delay)

    synthetic_event = synthetic_to_payment_event(row)
    razorpay_payload = _build_razorpay_twin_payload(row, rounded_delay)
    platform_health = PlatformHealthContext(
        gateway_error_rate_delta=row["gateway_error_rate_delta"],
        merchant_failure_rate_delta=row["merchant_failure_rate_delta"],
        cross_merchant_failure_rate=row["cross_merchant_failure_rate"],
        incident_active=bool(int(row["incident_active"])),
    )
    razorpay_event = razorpay_webhook_to_payment_event(razorpay_payload, platform_health=platform_health)

    # Feature-relevant fields converge exactly.
    assert razorpay_event.amount == pytest.approx(synthetic_event.amount)
    assert razorpay_event.failure_code == synthetic_event.failure_code
    assert razorpay_event.webhook_delay_seconds == synthetic_event.webhook_delay_seconds
    assert razorpay_event.retry_count == synthetic_event.retry_count
    assert razorpay_event.gateway_error_rate_delta == synthetic_event.gateway_error_rate_delta
    assert razorpay_event.incident_active == synthetic_event.incident_active

    synthetic_prediction = _predict_from_payment_event(synthetic_event)
    razorpay_prediction = _predict_from_payment_event(razorpay_event)

    assert razorpay_prediction.root_cause == synthetic_prediction.root_cause
    assert razorpay_prediction.probability == pytest.approx(synthetic_prediction.probability, abs=1e-9)

    policy = RulesPolicyEngine()
    synthetic_decision = policy.decide(synthetic_prediction, synthetic_event, now=datetime(2026, 1, 1))
    razorpay_decision = policy.decide(razorpay_prediction, razorpay_event, now=datetime(2026, 1, 1))

    assert razorpay_decision.action == synthetic_decision.action

    # Test 19 + safety verification: the frozen hard invariant holds for
    # the Razorpay-sourced event too.
    assert razorpay_prediction.root_cause.value == "WEBHOOK_AMBIGUITY"
    assert razorpay_decision.action == RecoveryAction.BLOCK_RECONCILE
    assert razorpay_decision.action != RecoveryAction.DEFER_RETRY


def test_synthetic_and_razorpay_twins_converge_on_infrastructure():
    row = _find_real_row_predicted_as("INFRASTRUCTURE")
    rounded_delay = round(row["webhook_delay_seconds"])
    row = dict(row)
    row["webhook_delay_seconds"] = float(rounded_delay)

    synthetic_event = synthetic_to_payment_event(row)
    razorpay_payload = _build_razorpay_twin_payload(row, rounded_delay)
    platform_health = PlatformHealthContext(
        gateway_error_rate_delta=row["gateway_error_rate_delta"],
        merchant_failure_rate_delta=row["merchant_failure_rate_delta"],
        cross_merchant_failure_rate=row["cross_merchant_failure_rate"],
        incident_active=bool(int(row["incident_active"])),
    )
    razorpay_event = razorpay_webhook_to_payment_event(razorpay_payload, platform_health=platform_health)

    synthetic_prediction = _predict_from_payment_event(synthetic_event)
    razorpay_prediction = _predict_from_payment_event(razorpay_event)

    assert razorpay_prediction.root_cause == synthetic_prediction.root_cause
    assert razorpay_prediction.probability == pytest.approx(synthetic_prediction.probability, abs=1e-9)

    policy = RulesPolicyEngine()
    synthetic_decision = policy.decide(synthetic_prediction, synthetic_event, now=datetime(2026, 1, 1))
    razorpay_decision = policy.decide(razorpay_prediction, razorpay_event, now=datetime(2026, 1, 1))
    assert razorpay_decision.action == synthetic_decision.action


# --- Test 20: adapter has no persistence side effects ---------------------------

def test_adapter_alone_never_touches_the_database():
    """Confirms the adapter call itself (not the downstream pipeline)
    creates no DB state -- the adapter is purely a normalization
    function."""
    import os

    real_db_path = Path(__file__).parent.parent / "recovery_guardian.db"
    existed_before = real_db_path.exists()
    mtime_before = real_db_path.stat().st_mtime if existed_before else None

    razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)

    if existed_before:
        assert real_db_path.stat().st_mtime == mtime_before
    else:
        assert not real_db_path.exists()
