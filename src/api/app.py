"""
Recovery Guardian — FastAPI skeleton (Day 1)

Today this only does plumbing: accept a PaymentEvent, store it, confirm it
was received. The classifier (Day 4-6) and policy engine (Day 7-8) plug in
later without changing this file's shape — that's the point of separating
the domain models the way we have.

Run locally (after `pip install fastapi uvicorn pydantic`):
    uvicorn src.api.app:app --reload
Then:
    curl http://localhost:8000/health
"""

import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, HTTPException
from src.domain.models import PaymentEvent
from src.db import get_connection, init_db

app = FastAPI(
    title="Recovery Guardian",
    description="The decision layer for safe, measured revenue recovery.",
    version="0.1.0",
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "recovery-guardian", "version": "0.1.0"}


@app.post("/events", status_code=201)
def ingest_event(event: PaymentEvent):
    """Accept a payment event (from either adapter — Razorpay or synthetic)
    and store it. No decision is made yet; that arrives with the classifier
    and policy engine in later days."""
    conn = get_connection()
    try:
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
                event.event_id, event.transaction_id, event.merchant_id,
                event.amount, event.timestamp.isoformat(), event.payment_method,
                event.failure_code, event.retry_count, event.webhook_delay_seconds,
                event.gateway_error_rate_delta, event.merchant_failure_rate_delta,
                event.cross_merchant_failure_rate, event.customer_previous_successes,
                event.customer_previous_failures, int(event.incident_active),
                event.source,
            ),
        )
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

    return {"received": True, "event_id": event.event_id, "transaction_id": event.transaction_id}


@app.get("/events/count")
def event_count():
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as n FROM payment_events").fetchone()
    conn.close()
    return {"count": row["n"]}
