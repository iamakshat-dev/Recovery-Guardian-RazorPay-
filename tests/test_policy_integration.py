"""
Recovery Guardian — Day 7 Real ML -> Policy Integration Tests

Exercises the actual boundary end to end:

    PaymentEvent -> build_features() -> CalibratedRootCauseClassifier
        -> RootCausePrediction -> RulesPolicyEngine -> RecoveryAction

via the real run_pipeline(), not a bypassed/faked assertion. No retraining,
no classifier modification — the frozen calibrated model (Day 4/5) is used
exactly as-is.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

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
    """Scans the real synthetic dataset for a row the classifier actually
    predicts as `root_cause_label`, so this test exercises real feature
    building + real inference rather than a hand-crafted fixture designed
    to force a particular answer."""
    from src.model.calibrated_classifier import CalibratedRootCauseClassifier

    classifier = CalibratedRootCauseClassifier()
    raw_df = pd.read_csv(DATA_PATH)

    for idx in range(len(raw_df)):
        row = raw_df.iloc[[idx]]
        features_df = build_features(row, keep_label=False)
        prediction = classifier.predict(features_df.iloc[0])
        if prediction.root_cause.value == root_cause_label and prediction.probability >= 0.75:
            return raw_df.iloc[idx].to_dict()

    pytest.fail(f"No row in the real synthetic dataset was predicted as {root_cause_label} "
                f"with probability >= 0.75 -- cannot run this integration test.")


def _payment_event_from_raw_row(raw_row: dict, transaction_suffix: str) -> PaymentEvent:
    from uuid import uuid4

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


def test_real_infrastructure_prediction_defers_retry_through_full_pipeline():
    raw_row = _find_real_row_predicted_as("INFRASTRUCTURE")
    event = _payment_event_from_raw_row(raw_row, "infra_it")

    record = run_pipeline(event, conn=fresh_conn())

    assert record.prediction.root_cause.value == "INFRASTRUCTURE"
    assert record.policy.action == RecoveryAction.DEFER_RETRY
    assert record.policy.policy_version == "rules-v1"


def test_real_webhook_ambiguity_prediction_blocks_and_reconciles_through_full_pipeline():
    raw_row = _find_real_row_predicted_as("WEBHOOK_AMBIGUITY")
    event = _payment_event_from_raw_row(raw_row, "webhook_it")

    record = run_pipeline(event, conn=fresh_conn())

    assert record.prediction.root_cause.value == "WEBHOOK_AMBIGUITY"
    assert record.policy.action == RecoveryAction.BLOCK_RECONCILE
    assert record.policy.action != RecoveryAction.DEFER_RETRY


def test_real_card_decline_prediction_authorizes_customer_recovery_through_full_pipeline():
    raw_row = _find_real_row_predicted_as("CARD_DECLINE")
    event = _payment_event_from_raw_row(raw_row, "card_it")

    record = run_pipeline(event, conn=fresh_conn())

    assert record.prediction.root_cause.value == "CARD_DECLINE"
    assert record.policy.action == RecoveryAction.CUSTOMER_RECOVERY


def test_real_insufficient_funds_prediction_authorizes_customer_recovery_through_full_pipeline():
    raw_row = _find_real_row_predicted_as("INSUFFICIENT_FUNDS")
    event = _payment_event_from_raw_row(raw_row, "insuff_it")

    record = run_pipeline(event, conn=fresh_conn())

    assert record.prediction.root_cause.value == "INSUFFICIENT_FUNDS"
    assert record.policy.action == RecoveryAction.CUSTOMER_RECOVERY


def test_repeated_pipeline_run_for_same_transaction_is_blocked_by_idempotency():
    """Real end-to-end idempotency: running the same transaction through
    run_pipeline() twice on the same connection must not authorize the
    same automated action twice."""
    raw_row = _find_real_row_predicted_as("INFRASTRUCTURE")
    conn = fresh_conn()

    event_1 = _payment_event_from_raw_row(raw_row, "idem_it")
    # Force both runs to reference the exact same transaction_id so the
    # idempotency_log lookup actually matches.
    from src.domain.models import PaymentEvent as PE
    event_1 = PE(**{**event_1.model_dump(), "transaction_id": "txn_idempotency_it_0001", "event_id": "evt_a"})
    record_1 = run_pipeline(event_1, conn=conn)
    assert record_1.policy.action == RecoveryAction.DEFER_RETRY

    event_2 = PE(**{**event_1.model_dump(), "event_id": "evt_b"})
    record_2 = run_pipeline(event_2, conn=conn)

    assert record_2.policy.action == RecoveryAction.HUMAN_REVIEW
