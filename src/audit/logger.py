"""
Recovery Guardian — Audit / Decision Persistence (Day 3)

Writes a DecisionRecord into the existing SQLite schema (src/db.py). This
module does not define its own database abstraction and does not alter the
schema — it only knows how to translate the typed domain objects into the
existing `payment_events` / `decisions` tables.

Note on Day 3 rerun semantics: every call to the pipeline generates a new
`event_id` (src/ingestion/synthetic_adapter.py) and a new `decision_id`
(src/pipeline/pipeline.py), so persisting is a plain INSERT — there is
nothing to deduplicate against yet. This is intentionally NOT the Day 7
idempotency mechanism (idempotency_key + retry-cap + cooldown enforcement);
running the same underlying transaction through the CLI twice today
produces two independent observations by design, not two conflicting
writes of "the same" decision.
"""

import json
import sqlite3

from src.domain.models import DecisionRecord, RecoveryOutcome


def persist_decision_record(record: DecisionRecord, conn: sqlite3.Connection) -> None:
    """Persist one DecisionRecord's event + decision into the given
    connection's `payment_events` and `decisions` tables. Does not persist
    `outcome` — that's Day 8-10 (recovery simulator) work, and Day 3
    DecisionRecords never carry one (outcome=None).

    The caller owns the connection's lifecycle (commit/close) is delegated
    here for convenience (this function commits), but opening/closing the
    connection is the caller's responsibility so tests can point this at an
    isolated database instead of the developer's real recovery_guardian.db.
    """
    event = record.event
    prediction = record.prediction
    policy = record.policy

    conn.execute(
        """
        INSERT INTO payment_events (
            event_id, transaction_id, merchant_id, amount, timestamp,
            payment_method, failure_code, retry_count, webhook_delay_seconds,
            gateway_error_rate_delta, merchant_failure_rate_delta,
            cross_merchant_failure_rate, customer_previous_successes,
            customer_previous_failures, incident_active, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id,
            event.transaction_id,
            event.merchant_id,
            event.amount,
            event.timestamp.isoformat(),
            event.payment_method,
            event.failure_code,
            event.retry_count,
            event.webhook_delay_seconds,
            event.gateway_error_rate_delta,
            event.merchant_failure_rate_delta,
            event.cross_merchant_failure_rate,
            event.customer_previous_successes,
            event.customer_previous_failures,
            int(event.incident_active),
            event.source,
        ),
    )

    conn.execute(
        """
        INSERT INTO decisions (
            decision_id, transaction_id, root_cause, probability,
            model_version, action, reason_codes, policy_version,
            requires_human_review
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.decision_id,
            prediction.transaction_id,
            prediction.root_cause.value,
            prediction.probability,
            prediction.model_version,
            policy.action.value,
            json.dumps([rc.value for rc in policy.reason_codes]),
            policy.policy_version,
            int(policy.requires_human_review),
        ),
    )

    conn.commit()


def persist_recovery_outcome(outcome: RecoveryOutcome, conn: sqlite3.Connection) -> None:
    """Persist one RecoveryOutcome (Day 8's shared estimator output) into
    the existing recovery_outcomes table — reuses the schema/connection
    exactly as persist_decision_record does; no second persistence
    mechanism. `recovery_outcomes.transaction_id` is the table's existing
    PRIMARY KEY (a Day 1/2 schema decision, not changed here), so this
    uses INSERT OR REPLACE: re-simulating an outcome for a transaction
    that already has one updates it to the latest, rather than raising a
    primary-key conflict on Day 3's normal "rerun = new observation"
    semantics."""
    conn.execute(
        """
        INSERT OR REPLACE INTO recovery_outcomes (
            transaction_id, decision_id, action_taken, recovered,
            amount_recovered, timestamp, duplicate_charge_risk, outcome_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            outcome.transaction_id,
            outcome.decision_id,
            outcome.action_taken.value,
            int(outcome.recovered),
            outcome.amount_recovered,
            outcome.timestamp.isoformat(),
            int(outcome.duplicate_charge_risk),
            outcome.outcome_reason,
        ),
    )
    conn.commit()
