"""
Recovery Guardian — Idempotency helpers (Day 7)

Thin wrapper around the EXISTING `idempotency_log` table (src/db.py). This
is not a second idempotency mechanism — it only knows how to read/write
that one existing table, and keeps that I/O out of
src/policy/engine.py's RulesPolicyEngine.decide() so the policy function
itself stays pure/deterministic (Day 7 spec section 20: no hidden mutable
state, no live DB access inside the decision function itself).
"""

import sqlite3
from typing import FrozenSet

from src.domain.models import RecoveryAction


def get_recorded_actions(conn: sqlite3.Connection, transaction_id: str) -> FrozenSet[RecoveryAction]:
    """Every automated RecoveryAction already recorded for this
    transaction_id in the existing idempotency_log table."""
    rows = conn.execute(
        "SELECT DISTINCT action FROM idempotency_log WHERE transaction_id = ? AND status = 'recorded'",
        (transaction_id,),
    ).fetchall()
    actions = set()
    for row in rows:
        value = row["action"] if isinstance(row, sqlite3.Row) else row[0]
        actions.add(RecoveryAction(value))
    return frozenset(actions)


def record_action(conn: sqlite3.Connection, transaction_id: str, action: RecoveryAction) -> None:
    """Record that `action` was authorized for `transaction_id`, using the
    existing idempotency_log schema. The idempotency_key is derived
    deterministically from transaction_id + action, so recording the same
    pair twice is itself a no-op (INSERT OR IGNORE against the table's
    existing PRIMARY KEY)."""
    idempotency_key = f"{transaction_id}:{action.value}"
    conn.execute(
        """
        INSERT OR IGNORE INTO idempotency_log (idempotency_key, transaction_id, action, status)
        VALUES (?, ?, ?, ?)
        """,
        (idempotency_key, transaction_id, action.value, "recorded"),
    )
    conn.commit()
