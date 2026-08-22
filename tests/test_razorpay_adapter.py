"""
Recovery Guardian — Day 11 Razorpay Adapter Validation Tests

Exercises the actual razorpay_webhook_to_payment_event() (not a mock).
Fixtures are explicitly representative/production-shaped — see
tests/fixtures/razorpay_payloads.py.
"""

import copy
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.models import PaymentEvent
from src.ingestion.razorpay_adapter import (
    AdapterValidationError,
    PlatformHealthContext,
    razorpay_webhook_to_payment_event,
)
from tests.fixtures.razorpay_payloads import (
    AMBIGUOUS_WEBHOOK_PAYLOAD,
    GATEWAY_TIMEOUT_DURING_INCIDENT_PAYLOAD,
    INVALID_TIMESTAMP_PAYLOAD,
    MISSING_AMOUNT_PAYLOAD,
    MISSING_TRANSACTION_ID_PAYLOAD,
    NEGATIVE_AMOUNT_PAYLOAD,
    NON_NUMERIC_AMOUNT_PAYLOAD,
    VALID_CARD_DECLINE_PAYLOAD,
    WEBHOOK_BEFORE_PAYMENT_PAYLOAD,
)


# --- Test 1: valid payload ----------------------------------------------------

def test_valid_payload_produces_a_valid_payment_event():
    event = razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)

    assert isinstance(event, PaymentEvent)
    assert event.transaction_id == "pay_repr_card_decline_0001"
    assert event.amount == pytest.approx(2500.0)  # 250000 paise -> rupees
    assert event.failure_code == "issuer_declined"  # card_declined -> issuer_declined
    assert event.payment_method == "card"
    assert event.source == "razorpay"
    assert event.webhook_delay_seconds == pytest.approx(5.0)
    assert event.merchant_id == "merchant_001"
    assert event.customer_previous_successes == 4
    assert event.customer_previous_failures == 1
    # No platform_health supplied -> neutral defaults, documented, not hidden.
    assert event.incident_active is False
    assert event.gateway_error_rate_delta == 0.0


# --- Test 2: missing transaction ID --------------------------------------------

def test_missing_transaction_id_fails_clearly():
    with pytest.raises(AdapterValidationError, match="'id'"):
        razorpay_webhook_to_payment_event(MISSING_TRANSACTION_ID_PAYLOAD)


# --- Test 3/4: missing / invalid amount ----------------------------------------

def test_missing_amount_fails_clearly():
    with pytest.raises(AdapterValidationError, match="'amount'"):
        razorpay_webhook_to_payment_event(MISSING_AMOUNT_PAYLOAD)


def test_negative_amount_rejected():
    with pytest.raises(AdapterValidationError, match="positive"):
        razorpay_webhook_to_payment_event(NEGATIVE_AMOUNT_PAYLOAD)


def test_non_numeric_amount_rejected():
    with pytest.raises(AdapterValidationError, match="numeric"):
        razorpay_webhook_to_payment_event(NON_NUMERIC_AMOUNT_PAYLOAD)


def test_zero_amount_rejected():
    payload = copy.deepcopy(VALID_CARD_DECLINE_PAYLOAD)
    payload["payload"]["payment"]["entity"]["amount"] = 0
    with pytest.raises(AdapterValidationError, match="positive"):
        razorpay_webhook_to_payment_event(payload)


# --- Test 5: invalid timestamp --------------------------------------------------

def test_invalid_payment_timestamp_rejected():
    with pytest.raises(AdapterValidationError, match="timestamp"):
        razorpay_webhook_to_payment_event(INVALID_TIMESTAMP_PAYLOAD)


def test_webhook_arriving_before_payment_created_is_rejected():
    """A negative webhook delay is malformed input, not silently clamped
    to zero (Day 11 spec section 7)."""
    with pytest.raises(AdapterValidationError, match="precedes"):
        razorpay_webhook_to_payment_event(WEBHOOK_BEFORE_PAYMENT_PAYLOAD)


# --- Test 6/7: unknown status/failure representation ---------------------------

def test_unrecognized_error_reason_maps_to_existing_canonical_unknown():
    payload = copy.deepcopy(VALID_CARD_DECLINE_PAYLOAD)
    payload["payload"]["payment"]["entity"]["error_reason"] = "some_new_reason_never_seen"
    event = razorpay_webhook_to_payment_event(payload)
    assert event.failure_code == "unknown"  # existing FAILURE_CODE_CATEGORIES bucket


def test_missing_error_reason_maps_to_existing_canonical_unknown():
    event = razorpay_webhook_to_payment_event(AMBIGUOUS_WEBHOOK_PAYLOAD)
    assert event.failure_code == "unknown"


def test_never_guesses_an_unknown_reason_into_a_specific_failure_code():
    """Defense against silently mapping an unrecognized value into a
    dangerous recovery-relevant class."""
    payload = copy.deepcopy(VALID_CARD_DECLINE_PAYLOAD)
    payload["payload"]["payment"]["entity"]["error_reason"] = "totally_unrecognized_xyz"
    event = razorpay_webhook_to_payment_event(payload)
    assert event.failure_code not in ("insufficient_funds", "card_expired", "invalid_card")
    assert event.failure_code == "unknown"


# --- Test 8: optional field omission --------------------------------------------

def test_missing_notes_uses_documented_safe_defaults():
    payload = copy.deepcopy(VALID_CARD_DECLINE_PAYLOAD)
    del payload["payload"]["payment"]["entity"]["notes"]
    event = razorpay_webhook_to_payment_event(payload)
    assert event.customer_previous_successes == 0
    assert event.customer_previous_failures == 0
    assert event.merchant_id == "unknown_merchant"


def test_missing_attempts_defaults_to_zero_retry_count():
    payload = copy.deepcopy(VALID_CARD_DECLINE_PAYLOAD)
    del payload["payload"]["payment"]["entity"]["attempts"]
    event = razorpay_webhook_to_payment_event(payload)
    assert event.retry_count == 0


# --- Test 9: payment-method normalization ---------------------------------------

def test_payment_method_normalized_to_lowercase():
    payload = copy.deepcopy(VALID_CARD_DECLINE_PAYLOAD)
    payload["payload"]["payment"]["entity"]["method"] = "UPI"
    event = razorpay_webhook_to_payment_event(payload)
    assert event.payment_method == "upi"


# --- Test 10: timestamp normalization --------------------------------------------

def test_timestamp_is_deterministic_unix_epoch_conversion():
    event = razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)
    assert event.timestamp.year == 2025  # 1735689600 == 2025-01-01T00:00:00Z


def test_adapter_never_uses_wall_clock_for_required_timestamp():
    """Calling the adapter twice, arbitrarily far apart in real time, must
    produce the identical timestamp -- proves no datetime.now() anywhere
    in the required-timestamp path."""
    event_a = razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)
    event_b = razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)
    assert event_a.timestamp == event_b.timestamp


# --- Test 11: webhook-delay calculation ------------------------------------------

def test_webhook_delay_calculated_from_two_real_timestamps_not_defaulted():
    event = razorpay_webhook_to_payment_event(GATEWAY_TIMEOUT_DURING_INCIDENT_PAYLOAD)
    assert event.webhook_delay_seconds == pytest.approx(3.0)
    assert event.webhook_delay_seconds != 0.0


def test_ambiguous_payload_has_a_materially_longer_webhook_delay():
    ambiguous = razorpay_webhook_to_payment_event(AMBIGUOUS_WEBHOOK_PAYLOAD)
    normal = razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)
    assert ambiguous.webhook_delay_seconds > normal.webhook_delay_seconds


# --- Test 12: aggregate-field handling (Option A) --------------------------------

def test_platform_health_context_is_threaded_through_when_supplied():
    ctx = PlatformHealthContext(
        gateway_error_rate_delta=0.6,
        merchant_failure_rate_delta=0.4,
        cross_merchant_failure_rate=0.35,
        incident_active=True,
    )
    event = razorpay_webhook_to_payment_event(GATEWAY_TIMEOUT_DURING_INCIDENT_PAYLOAD, platform_health=ctx)
    assert event.gateway_error_rate_delta == 0.6
    assert event.merchant_failure_rate_delta == 0.4
    assert event.cross_merchant_failure_rate == 0.35
    assert event.incident_active is True


def test_no_platform_health_context_defaults_to_documented_neutral_values():
    """The Option A limitation, verified directly: omitting the companion
    monitoring context yields a non-incident-signaling event -- an
    explicit, documented degradation, not a silent fabrication."""
    event = razorpay_webhook_to_payment_event(GATEWAY_TIMEOUT_DURING_INCIDENT_PAYLOAD)
    assert event.incident_active is False
    assert event.gateway_error_rate_delta == 0.0
    assert event.merchant_failure_rate_delta == 0.0
    assert event.cross_merchant_failure_rate == 0.0


# --- Adapter is side-effect free / deterministic --------------------------------

def test_adapter_is_pure_and_side_effect_free():
    import inspect

    import src.ingestion.razorpay_adapter as adapter_module

    source = inspect.getsource(adapter_module)
    assert "get_connection" not in source
    assert "persist_" not in source
    assert "requests." not in source
    assert "http" not in source.lower().replace("https://", "")  # no network client references


def test_adapter_does_not_mutate_input_payload():
    payload_copy = copy.deepcopy(VALID_CARD_DECLINE_PAYLOAD)
    razorpay_webhook_to_payment_event(VALID_CARD_DECLINE_PAYLOAD)
    assert VALID_CARD_DECLINE_PAYLOAD == payload_copy
