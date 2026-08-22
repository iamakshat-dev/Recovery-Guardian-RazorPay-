"""
Recovery Guardian — Day 3 End-to-End Pipeline Tests

Exercises the actual pipeline (PaymentEvent -> features -> placeholder
classifier -> placeholder policy -> DecisionRecord -> SQLite), not just
isolated functions. Every test uses an isolated in-memory SQLite connection
so pytest never touches the developer's real recovery_guardian.db.
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.append(str(Path(__file__).parent.parent))

from src.db import SCHEMA
from src.domain.models import (
    DecisionRecord,
    PaymentEvent,
    PolicyDecision,
    RootCausePrediction,
)
from src.ingestion.synthetic_adapter import synthetic_to_payment_event
from src.pipeline.pipeline import run_pipeline


def fresh_conn() -> sqlite3.Connection:
    """An isolated, schema-initialized in-memory database, unrelated to the
    developer's real recovery_guardian.db file."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def make_event(**overrides) -> PaymentEvent:
    base = dict(
        event_id="evt_test_0001",
        transaction_id="txn_test_0001",
        merchant_id="merchant_001",
        amount=1000.0,
        timestamp=datetime(2026, 8, 1, 0, 0, 0),
        payment_method="card",
        failure_code="insufficient_funds",
        retry_count=0,
        webhook_delay_seconds=0.5,
        gateway_error_rate_delta=0.05,
        merchant_failure_rate_delta=0.05,
        cross_merchant_failure_rate=0.05,
        customer_previous_successes=3,
        customer_previous_failures=1,
        incident_active=False,
        source="synthetic",
    )
    base.update(overrides)
    return PaymentEvent(**base)


def make_synthetic_row(**overrides) -> dict:
    """A raw CSV-row-shaped dict, matching data/generate_data.py's columns."""
    base = dict(
        transaction_id="txn_csv_0001",
        merchant_id="merchant_017",
        amount=2500.50,
        timestamp="2026-08-01T00:00:00",
        payment_method="upi",
        failure_code="gateway_timeout",
        retry_count=1,
        webhook_delay_seconds=3.2,
        gateway_error_rate_delta=0.4,
        merchant_failure_rate_delta=0.3,
        cross_merchant_failure_rate=0.35,
        customer_previous_successes=4,
        customer_previous_failures=0,
        incident_active=1,
        actual_root_cause="INFRASTRUCTURE",
    )
    base.update(overrides)
    return base


# --- Test 1: complete pipeline ---------------------------------------------

def test_complete_pipeline_produces_a_decision_record():
    event = make_event()
    record = run_pipeline(event, conn=fresh_conn())

    assert isinstance(record, DecisionRecord)
    assert record.event.transaction_id == event.transaction_id
    assert record.prediction.transaction_id == event.transaction_id
    assert record.policy.transaction_id == event.transaction_id
    assert record.outcome is None  # not Day 3's job — recovery simulator is Day 8-10


# --- Test 2: database persistence ------------------------------------------

def test_processing_an_event_persists_the_expected_sqlite_rows():
    conn = fresh_conn()
    event = make_event(transaction_id="txn_persist_check")
    record = run_pipeline(event, conn=conn)

    event_row = conn.execute(
        "SELECT * FROM payment_events WHERE event_id = ?", (event.event_id,)
    ).fetchone()
    assert event_row is not None
    assert event_row["transaction_id"] == "txn_persist_check"
    assert event_row["source"] == "synthetic"

    decision_row = conn.execute(
        "SELECT * FROM decisions WHERE decision_id = ?", (record.decision_id,)
    ).fetchone()
    assert decision_row is not None
    assert decision_row["transaction_id"] == "txn_persist_check"
    assert decision_row["root_cause"] == record.prediction.root_cause.value
    assert decision_row["action"] == record.policy.action.value
    assert json.loads(decision_row["reason_codes"]) == [
        rc.value for rc in record.policy.reason_codes
    ]


# --- Test 3: typed outputs ---------------------------------------------------

def test_classifier_and_policy_engine_produce_valid_typed_outputs():
    event = make_event()
    record = run_pipeline(event, conn=fresh_conn())

    assert isinstance(record.prediction, RootCausePrediction)
    assert isinstance(record.policy, PolicyDecision)
    assert 0.0 <= record.prediction.probability <= 1.0


# --- Test 4: version tracking -------------------------------------------------

def test_model_version_and_policy_version_are_recorded():
    event = make_event()
    record = run_pipeline(event, conn=fresh_conn())

    # Day 4: the production pipeline's classifier stage became the real,
    # trained Logistic Regression model, not the Day 3 placeholder.
    # Day 5: the pipeline now serves the CALIBRATED classifier instead —
    # this assertion is the one intentional Day 4 -> Day 5 contract update
    # (see src/model/calibrated_classifier.py, src/pipeline/pipeline.py).
    assert record.prediction.model_version == "root-cause-logreg-calibrated-v1"
    # Day 7: the production pipeline's policy stage became the real,
    # deterministic, config-driven RulesPolicyEngine, not the Day 3
    # placeholder — this is the one intentional Day 3 -> Day 7 policy
    # contract update (see src/policy/engine.py, src/policy/rules.yaml).
    assert record.policy.policy_version == "rules-v1"


# --- Test 5: LLM independence -------------------------------------------------

def test_pipeline_requires_no_llm_or_network_dependency(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # The pipeline module must never have pulled in an LLM client.
    assert "anthropic" not in sys.modules

    event = make_event()
    record = run_pipeline(event, conn=fresh_conn())
    # Day 5: calibrated model, but still ran fully offline, no LLM/network call.
    assert record.prediction.model_version == "root-cause-logreg-calibrated-v1"


# --- Test 6: invalid input ------------------------------------------------------

def test_invalid_payment_event_is_rejected():
    with pytest.raises(ValidationError):
        # gateway_error_rate_delta is constrained to [0.0, 1.0]
        make_event(gateway_error_rate_delta=1.5)

    with pytest.raises(ValidationError):
        # missing every required field
        PaymentEvent()


def test_run_pipeline_rejects_non_payment_event_input():
    with pytest.raises(TypeError):
        run_pipeline({"transaction_id": "not_a_payment_event"}, conn=fresh_conn())


# --- Test 7: synthetic adapter --------------------------------------------------

def test_synthetic_to_payment_event_produces_a_valid_event():
    row = make_synthetic_row()
    event = synthetic_to_payment_event(row)

    assert isinstance(event, PaymentEvent)
    assert event.event_id  # generated, non-empty
    assert event.event_id != ""
    assert event.source == "synthetic"
    assert isinstance(event.incident_active, bool)
    assert event.incident_active is True
    assert event.transaction_id == "txn_csv_0001"


def test_synthetic_to_payment_event_converts_incident_active_zero_to_false():
    row = make_synthetic_row(incident_active=0)
    event = synthetic_to_payment_event(row)
    assert event.incident_active is False


def test_synthetic_to_payment_event_generates_unique_event_ids():
    row = make_synthetic_row()
    event_a = synthetic_to_payment_event(row)
    event_b = synthetic_to_payment_event(row)
    assert event_a.event_id != event_b.event_id
