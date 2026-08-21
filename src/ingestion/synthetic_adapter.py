"""
Recovery Guardian — Synthetic CSV → PaymentEvent Adapter (Day 3)

This is the ONLY place that knows how a row of data/synthetic_events.csv
maps onto the domain-level PaymentEvent contract. Nothing else in the
pipeline should know that CSVs or synthetic data exist at all — that's what
keeps src/pipeline/pipeline.py reusable for the Day 11 Razorpay adapter,
which will produce the exact same PaymentEvent shape from a completely
different source (Razorpay test-mode Orders/Webhooks), without touching
the pipeline itself.

Deliberately NOT included here: `actual_root_cause`. That column is the
synthetic ground-truth label used later for training/evaluation — it is
not part of what a real payment system would ever hand back, so it has
no place on PaymentEvent.
"""

from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from src.domain.models import PaymentEvent


def synthetic_to_payment_event(row: Mapping[str, Any]) -> PaymentEvent:
    """Convert one synthetic dataset row (a pandas Series or plain dict with
    the data/generate_data.py column names) into a validated PaymentEvent.

    Args:
        row: a mapping with at least the columns produced by
            data/generate_data.py (transaction_id, merchant_id, amount,
            timestamp, payment_method, failure_code, retry_count,
            webhook_delay_seconds, gateway_error_rate_delta,
            merchant_failure_rate_delta, cross_merchant_failure_rate,
            customer_previous_successes, customer_previous_failures,
            incident_active).

    Returns:
        A PaymentEvent. Construction runs full Pydantic validation, so a
        malformed row raises pydantic.ValidationError here rather than
        silently propagating bad data into the pipeline.
    """
    timestamp = row["timestamp"]
    if not isinstance(timestamp, datetime):
        timestamp = datetime.fromisoformat(str(timestamp))

    return PaymentEvent(
        event_id=f"evt_{uuid4().hex}",
        transaction_id=str(row["transaction_id"]),
        merchant_id=str(row["merchant_id"]),
        amount=float(row["amount"]),
        timestamp=timestamp,
        payment_method=str(row["payment_method"]),
        failure_code=str(row["failure_code"]),
        retry_count=int(row["retry_count"]),
        webhook_delay_seconds=float(row["webhook_delay_seconds"]),
        gateway_error_rate_delta=float(row["gateway_error_rate_delta"]),
        merchant_failure_rate_delta=float(row["merchant_failure_rate_delta"]),
        cross_merchant_failure_rate=float(row["cross_merchant_failure_rate"]),
        customer_previous_successes=int(row["customer_previous_successes"]),
        customer_previous_failures=int(row["customer_previous_failures"]),
        # CSV stores 0/1; PaymentEvent.incident_active is a real bool.
        incident_active=bool(int(row["incident_active"])),
        source="synthetic",
    )
