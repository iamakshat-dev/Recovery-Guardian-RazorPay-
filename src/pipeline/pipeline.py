"""
Recovery Guardian — Core Pipeline (Day 3, classifier updated Day 4)

    PaymentEvent -> feature builder -> real Logistic Regression classifier
                 -> placeholder policy engine -> DecisionRecord -> SQLite

This module is the single reusable entry point every caller goes through:
today's CLI (run_pipeline.py), the existing FastAPI skeleton, the Day 3
synthetic adapter, and the future (Day 11) Razorpay adapter. It therefore
must not contain:
    - CSV-specific logic (that's src/ingestion/synthetic_adapter.py)
    - Razorpay-specific logic (that's the future razorpay adapter)
    - any LLM/network dependency (the explanation layer is Day 13 and is
      never on this path — see src/explain/, not imported here)

`run_pipeline` operates purely on the typed domain objects in
src/domain/models.py; it never sees a raw CSV row or an HTTP payload.

Day 4 update: the classifier stage now uses the real, trained Logistic
Regression model (src/model/classifier.py) instead of the Day 3
structural placeholder (src/model/placeholder_classifier.py). The
placeholder remains in the codebase as a reference/test fixture but is no
longer used in this production path. The policy engine is UNCHANGED —
still the Day 3 placeholder (policy_version="placeholder-v1") — real
policy logic is later work (Day 7).
"""

import sqlite3
from typing import Optional
from uuid import uuid4

import pandas as pd

from src.audit.logger import persist_decision_record
from src.db import SCHEMA, get_connection
from src.domain.models import DecisionRecord, PaymentEvent
from src.features.build_features import build_features
from src.model.classifier import RootCauseLogRegClassifier
from src.policy.placeholder_engine import PolicyEngine


def run_pipeline(
    event: PaymentEvent,
    conn: Optional[sqlite3.Connection] = None,
) -> DecisionRecord:
    """Run one PaymentEvent through the full Day 3 pipeline and persist the
    resulting decision.

    Args:
        event: an already-validated PaymentEvent (validation happens at
            construction time via its Pydantic model — see the adapter that
            built it).
        conn: an optional SQLite connection. Tests should pass an isolated
            connection here so pytest never touches the real
            recovery_guardian.db. When omitted, a connection to the
            project's real database (src/db.py) is opened and closed for
            this single call.

    Returns:
        The full DecisionRecord: event, prediction, policy decision, and
        (for Day 3) outcome=None — outcome is Day 8-10 (recovery simulator)
        work and doesn't exist yet.
    """
    if not isinstance(event, PaymentEvent):
        raise TypeError(f"run_pipeline requires a PaymentEvent, got {type(event)!r}")

    # 1. PaymentEvent is already validated (Pydantic validated it at
    #    construction). 2. Build features via the existing, unit-tested
    #    feature builder — the exact same function training/eval will use.
    features_df = build_features(pd.DataFrame([event.model_dump()]), keep_label=False)
    features_row = features_df.iloc[0]

    # 3-4. Real, trained Logistic Regression classifier -> RootCausePrediction.
    classifier = RootCauseLogRegClassifier()
    prediction = classifier.predict(features_row)

    # 5-6. Placeholder policy engine -> PolicyDecision.
    policy_engine = PolicyEngine()
    policy_decision = policy_engine.decide(prediction, event)

    # 7. Assemble the audit record.
    record = DecisionRecord(
        decision_id=f"dec_{uuid4().hex}",
        event=event,
        prediction=prediction,
        policy=policy_decision,
        outcome=None,
    )

    # 8. Persist via the existing SQLite schema/connection helper.
    owns_conn = conn is None
    if conn is None:
        conn = get_connection()
    try:
        conn.executescript(SCHEMA)  # idempotent (CREATE TABLE IF NOT EXISTS)
        persist_decision_record(record, conn)
    finally:
        if owns_conn:
            conn.close()

    # 9. Return the complete result.
    return record
