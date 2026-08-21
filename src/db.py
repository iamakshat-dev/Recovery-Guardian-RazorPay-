"""
Recovery Guardian — SQLite schema and connection helper.

SQLite, not Postgres: for a hackathon prototype, zero-setup reproducibility
for a judge cloning the repo matters more than production scalability. This
is a documented design choice (see README), not an oversight.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "recovery_guardian.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_events (
    event_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    amount REAL NOT NULL,
    timestamp TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    failure_code TEXT NOT NULL,
    retry_count INTEGER NOT NULL,
    webhook_delay_seconds REAL NOT NULL,
    gateway_error_rate_delta REAL NOT NULL,
    merchant_failure_rate_delta REAL NOT NULL,
    cross_merchant_failure_rate REAL NOT NULL,
    customer_previous_successes INTEGER NOT NULL,
    customer_previous_failures INTEGER NOT NULL,
    incident_active INTEGER NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    probability REAL NOT NULL,
    model_version TEXT NOT NULL,
    action TEXT NOT NULL,
    reason_codes TEXT NOT NULL,          -- JSON-encoded list
    policy_version TEXT NOT NULL,
    requires_human_review INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES payment_events (transaction_id)
);

CREATE TABLE IF NOT EXISTS recovery_outcomes (
    transaction_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    recovered INTEGER NOT NULL,
    amount_recovered REAL NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions (decision_id)
);

CREATE TABLE IF NOT EXISTS idempotency_log (
    idempotency_key TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"Initialized database at {DB_PATH}")


if __name__ == "__main__":
    init_db()
