"""
Recovery Guardian — Core Pipeline (Day 3, classifier updated Day 4/5, policy updated Day 7)

    PaymentEvent -> feature builder -> calibrated Logistic Regression classifier
                 -> deterministic policy engine -> DecisionRecord -> SQLite

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

Day 4 update: the classifier stage used the real, trained Logistic
Regression model (src/model/classifier.py) instead of the Day 3
structural placeholder (src/model/placeholder_classifier.py).

Day 5 update: the classifier stage now uses the CALIBRATED classifier
(src/model/calibrated_classifier.py), which wraps the same frozen Day 4
model with a validation-fit sigmoid calibration layer — the underlying
Logistic Regression is unchanged (see src/model/calibrate.py).

Day 7 update: the policy stage now uses the real, deterministic,
config-driven RulesPolicyEngine (src/policy/engine.py) instead of the Day
3 structural placeholder (src/policy/placeholder_engine.py). Idempotency
is enforced using the EXISTING idempotency_log table (src/db.py, wrapped
by src/policy/idempotency.py) — recorded actions for this transaction are
read before deciding, and any newly-authorized automated action is
recorded afterward, all on the same connection/transaction as the rest of
this pipeline run.

Day 8 update: after the Day 7-authorized action is decided, this pipeline
calls the shared counterfactual estimator
(src/recovery/simulator.py::estimate_outcome) with EXACTLY that authorized
action — never a hypothetical one — and persists the resulting
RecoveryOutcome via the existing recovery_outcomes table. Day 8's
estimator has no knowledge of PolicyDecision and cannot itself choose an
action; only this pipeline (i.e. Day 7's policy output) decides which
action gets scored. The same estimator is reused unmodified by Day 9/10 to
score purely hypothetical actions for the naive/rules-only baselines.

The Day 3 policy placeholder and the Day 4 raw classifier both remain in
the codebase, fully intact and independently loadable, as
reference/comparison fixtures — neither was modified to make these swaps.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import pandas as pd

from src.audit.logger import persist_decision_record, persist_recovery_outcome
from src.db import SCHEMA, get_connection
from src.domain.models import DecisionRecord, PaymentEvent
from src.features.build_features import build_features
from src.model.calibrated_classifier import CalibratedRootCauseClassifier
from src.policy.engine import AUTOMATED_ACTIONS, RulesPolicyEngine
from src.policy.idempotency import get_recorded_actions, record_action
from src.recovery.evidence import RecoveryEvidence
from src.recovery.simulator import estimate_outcome


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
        (as of Day 8) a simulated RecoveryOutcome scored by the shared
        counterfactual estimator against the Day-7-authorized action.
    """
    if not isinstance(event, PaymentEvent):
        raise TypeError(f"run_pipeline requires a PaymentEvent, got {type(event)!r}")

    # 1. PaymentEvent is already validated (Pydantic validated it at
    #    construction). 2. Build features via the existing, unit-tested
    #    feature builder — the exact same function training/eval will use.
    features_df = build_features(pd.DataFrame([event.model_dump()]), keep_label=False)
    features_row = features_df.iloc[0]

    # 3-4. Calibrated Logistic Regression classifier -> RootCausePrediction.
    classifier = CalibratedRootCauseClassifier()
    prediction = classifier.predict(features_row)

    # 5-6. Real, deterministic policy engine -> PolicyDecision. Idempotency
    #      is read from and written to the existing idempotency_log table
    #      on the SAME connection this pipeline run persists everything
    #      else through.
    owns_conn = conn is None
    if conn is None:
        conn = get_connection()
    conn.executescript(SCHEMA)  # idempotent (CREATE TABLE IF NOT EXISTS)

    recorded_actions = get_recorded_actions(conn, event.transaction_id)
    policy_engine = RulesPolicyEngine()
    # Naive UTC (not datetime.utcnow(), which is deprecated) -- kept naive
    # to match the rest of the project's datetime convention (PaymentEvent
    # .timestamp/.last_recovery_action_at are naive throughout), so cooldown
    # arithmetic (now - last_recovery_action_at) never raises on
    # naive/aware mismatch.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    policy_decision = policy_engine.decide(
        prediction, event, already_executed_actions=recorded_actions, now=now
    )
    if policy_decision.action in AUTOMATED_ACTIONS:
        record_action(conn, event.transaction_id, policy_decision.action)

    # 7. Score the Day-7-authorized action through the shared Day 8
    #    counterfactual estimator — never a hypothetical action; this is
    #    Guardian's real production path, constrained entirely by what
    #    policy just decided.
    decision_id = f"dec_{uuid4().hex}"
    evidence = RecoveryEvidence.from_payment_event_and_prediction(event, prediction)
    outcome = estimate_outcome(evidence, policy_decision.action, decision_id=decision_id)

    # 8. Assemble the audit record.
    record = DecisionRecord(
        decision_id=decision_id,
        event=event,
        prediction=prediction,
        policy=policy_decision,
        outcome=outcome,
    )

    # 9. Persist via the existing SQLite schema/connection helper (same
    #    connection already opened above for the idempotency check).
    try:
        persist_decision_record(record, conn)
        persist_recovery_outcome(outcome, conn)
    finally:
        if owns_conn:
            conn.close()

    # 10. Return the complete result.
    return record
