"""
Recovery Guardian — Day 8 Policy -> Outcome Production Integration Test

Exercises the real boundary end to end:

    PaymentEvent -> build_features() -> CalibratedRootCauseClassifier
        -> RootCausePrediction -> RulesPolicyEngine -> authorized action
        -> estimate_outcome(evidence, authorized action) -> RecoveryOutcome
        -> persisted into recovery_outcomes

via the real run_pipeline(), proving Guardian's production path uses
exactly the Day-7-authorized action (never a hypothetical one) when
calling the shared Day 8 estimator.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.db import SCHEMA
from src.domain.models import PaymentEvent, RecoveryAction
from src.features.build_features import build_features
from src.model.training import DATA_PATH
from src.pipeline.pipeline import run_pipeline


def fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _find_real_row_predicted_as(root_cause_label: str) -> dict:
    from src.model.calibrated_classifier import CalibratedRootCauseClassifier

    classifier = CalibratedRootCauseClassifier()
    raw_df = pd.read_csv(DATA_PATH)
    for idx in range(len(raw_df)):
        row = raw_df.iloc[[idx]]
        features_df = build_features(row, keep_label=False)
        prediction = classifier.predict(features_df.iloc[0])
        if prediction.root_cause.value == root_cause_label and prediction.probability >= 0.75:
            return raw_df.iloc[idx].to_dict()
    pytest.fail(f"No row predicted as {root_cause_label} with probability >= 0.75")


def _payment_event_from_raw_row(raw_row: dict, transaction_suffix: str) -> PaymentEvent:
    return PaymentEvent(
        event_id=f"evt_{uuid4().hex}",
        transaction_id=f"{raw_row['transaction_id']}_{transaction_suffix}",
        merchant_id=str(raw_row["merchant_id"]),
        amount=float(raw_row["amount"]),
        timestamp=datetime.fromisoformat(str(raw_row["timestamp"])),
        payment_method=str(raw_row["payment_method"]),
        failure_code=str(raw_row["failure_code"]),
        retry_count=int(raw_row["retry_count"]),
        webhook_delay_seconds=float(raw_row["webhook_delay_seconds"]),
        gateway_error_rate_delta=float(raw_row["gateway_error_rate_delta"]),
        merchant_failure_rate_delta=float(raw_row["merchant_failure_rate_delta"]),
        cross_merchant_failure_rate=float(raw_row["cross_merchant_failure_rate"]),
        customer_previous_successes=int(raw_row["customer_previous_successes"]),
        customer_previous_failures=int(raw_row["customer_previous_failures"]),
        incident_active=bool(int(raw_row["incident_active"])),
        source="synthetic",
    )


def test_real_webhook_ambiguity_outcome_is_never_scored_as_defer_retry():
    """The critical safety-adjacent proof: even the Day 8 OUTCOME layer,
    fed the real Day-7-authorized action for a real WEBHOOK_AMBIGUITY
    prediction, never ends up scoring a DEFER_RETRY -- because Guardian's
    policy never authorizes one for this root cause (Day 7), and the
    pipeline never asks the estimator to evaluate a hypothetical action."""
    raw_row = _find_real_row_predicted_as("WEBHOOK_AMBIGUITY")
    event = _payment_event_from_raw_row(raw_row, "outcome_it")

    record = run_pipeline(event, conn=fresh_conn())

    assert record.policy.action == RecoveryAction.BLOCK_RECONCILE
    assert record.outcome is not None
    assert record.outcome.action_taken == RecoveryAction.BLOCK_RECONCILE
    assert record.outcome.action_taken != RecoveryAction.DEFER_RETRY
    assert record.outcome.recovered is False
    assert record.outcome.duplicate_charge_risk is False


def test_real_infrastructure_outcome_is_persisted_into_recovery_outcomes():
    raw_row = _find_real_row_predicted_as("INFRASTRUCTURE")
    event = _payment_event_from_raw_row(raw_row, "persist_it")
    conn = fresh_conn()

    record = run_pipeline(event, conn=conn)

    assert record.policy.action == RecoveryAction.DEFER_RETRY
    assert record.outcome.action_taken == RecoveryAction.DEFER_RETRY
    assert record.outcome.decision_id == record.decision_id

    row = conn.execute(
        "SELECT * FROM recovery_outcomes WHERE transaction_id = ?", (event.transaction_id,)
    ).fetchone()
    assert row is not None
    assert row["action_taken"] == "DEFER_RETRY"
    assert row["decision_id"] == record.decision_id
    assert 0.0 <= row["amount_recovered"] <= event.amount


def test_outcome_action_taken_always_matches_the_policy_decision_action():
    """Guardian's production path must use actual_policy_decision.action
    when calling the estimator -- Day 8 must never choose its own action."""
    raw_row = _find_real_row_predicted_as("CARD_DECLINE")
    event = _payment_event_from_raw_row(raw_row, "match_it")

    record = run_pipeline(event, conn=fresh_conn())

    assert record.outcome.action_taken == record.policy.action
