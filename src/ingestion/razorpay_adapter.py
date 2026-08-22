"""
Recovery Guardian — Day 11 Razorpay-Shaped Adapter

    razorpay_webhook_to_payment_event(webhook_payload, platform_health=None)
        -> PaymentEvent

Mirrors src/ingestion/synthetic_adapter.py's convention exactly: a single,
pure, side-effect-free function that normalizes one external event shape
into the existing canonical `PaymentEvent` contract. Nothing downstream
(feature builder, calibrated classifier, policy engine) needs to know this
event originated from a Razorpay-shaped webhook rather than a synthetic
CSV row — that equivalence is the entire point of the adapter pattern
established on Day 3 and named again in this module's own docstring back
then.

This is a BOUNDARY layer only. It does not:
    - build ML features (that's src/features/build_features.py, untouched)
    - predict anything (that's src/model/, untouched)
    - decide a recovery action (that's src/policy/engine.py, untouched)
    - persist anything (no DB writes anywhere in this module)
    - call a live Razorpay API (no network code anywhere in this module)

IMPORTANT — no verified official Razorpay schema is claimed here. The
payload shape this module accepts is a REPRESENTATIVE, production-shaped
approximation of a Razorpay payment-webhook envelope (a top-level
`event`/`created_at` wrapping a `payload.payment.entity` object), built
from Razorpay's well-documented public conventions (amounts as integers
in the smallest currency subunit; a payment `error_code`/`error_reason`
pair; webhook envelopes carrying their own `created_at`). It is not
captured from live Razorpay production traffic, and no live Razorpay
credentials, API calls, or webhook-signature verification are implemented
or required for Day 11 — see docs/architecture.md's Day 11 section for
the full production-readiness boundary this leaves unaddressed.

============================================================================
THE AGGREGATE-FIELD GAP (Option A selected — see docs/architecture.md)
============================================================================
PaymentEvent's `gateway_error_rate_delta`, `merchant_failure_rate_delta`,
`cross_merchant_failure_rate`, and `incident_active` are platform-wide
operational/incident signals. A single Razorpay payment/webhook payload
cannot legitimately contain real-time cross-merchant failure statistics —
that requires a separate monitoring/observability service this project
does not build. `PlatformHealthContext` below represents exactly that
companion input, explicitly optional and explicitly labeled: if a caller
doesn't supply one, the resulting PaymentEvent carries neutral
(non-incident) values, and INFRASTRUCTURE detection for that event is
correspondingly degraded — this is documented, not hidden (see
docs/architecture.md's "Production Monitoring Boundary" section).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.domain.models import PaymentEvent

# Razorpay's Payment/Order `amount` field is an integer in the smallest
# currency subunit (paise for INR) — a well-documented, verified aspect of
# Razorpay's public API, not a guess. The existing canonical
# PaymentEvent.amount (and every synthetic value it has ever held, e.g.
# 8016.18) is in whole rupees — confirmed from data/generate_data.py's
# `sample_amount()`, which generates values in the ~200-50,000 range with
# fractional paise, i.e. rupees, not paise. This adapter therefore performs
# an explicit, tested unit conversion; it never guesses.
PAISE_PER_RUPEE = 100.0

# Existing canonical vocabulary (src/features/build_features.py's
# FAILURE_CODE_CATEGORIES, frozen — NOT duplicated or extended here).
# "unknown" is already one of those twelve categories; this adapter reuses
# it as the existing canonical fallback rather than inventing a second
# unknown representation.
UNKNOWN_FAILURE_CODE = "unknown"

# Representative Razorpay-style error_reason -> existing canonical
# failure_code. Deliberately small and inspectable (Day 11 spec section
# 13): every value on the right is one of the twelve frozen
# FAILURE_CODE_CATEGORIES. Any error_reason not in this table maps to the
# existing UNKNOWN_FAILURE_CODE bucket -- never guessed into a specific
# class.
RAZORPAY_ERROR_REASON_TO_FAILURE_CODE: Dict[str, str] = {
    "gateway_timeout": "gateway_timeout",
    "gateway_error": "internal_error",
    "server_error": "internal_error",
    "internal_error": "internal_error",
    "service_unavailable": "service_unavailable",
    "card_declined": "issuer_declined",
    "issuer_declined": "issuer_declined",
    "expired_card": "card_expired",
    "card_expired": "card_expired",
    "invalid_card": "invalid_card",
    "insufficient_funds": "insufficient_funds",
    "otp_timeout": "otp_timeout",
    "otp_incorrect_retries_exceeded": "otp_timeout",
    "authentication_failed": "3ds_auth_failed",
    "3ds_auth_failed": "3ds_auth_failed",
    "payment_cancelled": "user_cancelled",
    "user_cancelled": "user_cancelled",
    "session_expired": "session_expired",
}

# Razorpay's real payment_method values are already lowercase strings very
# close to the existing canonical vocabulary (card/upi/netbanking/wallet).
# No second taxonomy is created; unrecognized methods pass through as-is —
# src/features/build_features.py's existing fixed-vocabulary one-hot
# encoding already handles an out-of-vocabulary payment_method safely
# (all-zero row), exactly as it does for failure_code (see Day 2's
# test_unseen_failure_code_produces_all_zero_onehot_not_a_crash).


class AdapterValidationError(ValueError):
    """Raised when a Razorpay-shaped payload cannot be safely normalized
    into a PaymentEvent. Fail-closed: this adapter never silently produces
    a corrupt or guessed PaymentEvent."""


@dataclass(frozen=True)
class PlatformHealthContext:
    """Explicit companion monitoring/observability input (Option A — see
    module and docs/architecture.md docstrings). Represents platform-wide
    signals no single payment payload can legitimately carry. This
    project does NOT build the monitoring service that would compute
    these in production; a real integration must supply them from one.

    The all-neutral default below is what a caller gets when no real
    monitoring context is available — this is an explicit, documented
    limitation (INFRASTRUCTURE detection degrades to "no incident signal"
    for that event), not a silent fabrication of safety."""

    gateway_error_rate_delta: float = 0.0
    merchant_failure_rate_delta: float = 0.0
    cross_merchant_failure_rate: float = 0.0
    incident_active: bool = False


def _require(payload: Dict[str, Any], key: str, context: str) -> Any:
    if key not in payload or payload[key] is None:
        raise AdapterValidationError(f"Razorpay payload missing required field '{key}' in {context}")
    return payload[key]


def _parse_unix_timestamp(value: Any, field_name: str) -> datetime:
    """Razorpay timestamps are Unix epoch seconds (UTC). Deterministic,
    never local-machine-dependent, never datetime.now()."""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError) as exc:
        raise AdapterValidationError(f"Invalid timestamp for '{field_name}': {value!r}") from exc


def _validate_amount(raw_amount: Any) -> float:
    if isinstance(raw_amount, bool) or not isinstance(raw_amount, (int, float)):
        raise AdapterValidationError(f"amount must be numeric, got {raw_amount!r}")
    if raw_amount <= 0:
        raise AdapterValidationError(f"amount must be positive, got {raw_amount!r}")
    return float(raw_amount) / PAISE_PER_RUPEE


def _map_failure_code(error_reason: Optional[str]) -> str:
    if not error_reason:
        return UNKNOWN_FAILURE_CODE
    return RAZORPAY_ERROR_REASON_TO_FAILURE_CODE.get(error_reason, UNKNOWN_FAILURE_CODE)


def razorpay_webhook_to_payment_event(
    webhook_payload: Dict[str, Any],
    *,
    platform_health: Optional[PlatformHealthContext] = None,
) -> PaymentEvent:
    """Normalize one representative Razorpay-shaped payment-failure
    webhook envelope into the canonical PaymentEvent.

    Args:
        webhook_payload: a dict shaped like:
            {
              "event": "payment.failed",
              "created_at": <unix ts>,              # webhook arrival time
              "payload": {"payment": {"entity": {
                  "id": "pay_...",                    # -> transaction_id
                  "amount": <int, paise>,
                  "currency": "INR",
                  "method": "card",
                  "status": "failed",
                  "error_code": "GATEWAY_ERROR",
                  "error_reason": "gateway_timeout",
                  "created_at": <unix ts>,            # payment creation time
                  "attempts": 0,                        # -> retry_count
                  "notes": {"merchant_id": "...",
                            "customer_previous_successes": 0,
                            "customer_previous_failures": 0},
              }}}
            }
        platform_health: optional companion monitoring context (Option A).
            Defaults to all-neutral if omitted — see PlatformHealthContext.

    Returns:
        A validated PaymentEvent (source="razorpay").

    Raises:
        AdapterValidationError: on any missing/malformed required field.
            Never silently fabricates a value for a required field.
    """
    if platform_health is None:
        platform_health = PlatformHealthContext()

    try:
        entity = webhook_payload["payload"]["payment"]["entity"]
    except (KeyError, TypeError) as exc:
        raise AdapterValidationError("Razorpay payload missing payload.payment.entity") from exc

    webhook_created_at_raw = _require(webhook_payload, "created_at", "webhook envelope")
    payment_id = _require(entity, "id", "payment entity")
    raw_amount = _require(entity, "amount", "payment entity")
    payment_created_at_raw = _require(entity, "created_at", "payment entity")

    amount = _validate_amount(raw_amount)
    payment_timestamp = _parse_unix_timestamp(payment_created_at_raw, "payment.created_at")
    webhook_timestamp = _parse_unix_timestamp(webhook_created_at_raw, "webhook.created_at")

    # Webhook delay is CALCULATED, never defaulted to zero (Day 11 spec
    # section 7) -- this is the field WEBHOOK_AMBIGUITY detection depends
    # on most directly. A negative delay (webhook claiming to have arrived
    # before the payment was even created) is treated as malformed input,
    # not silently clamped to zero.
    webhook_delay_seconds = (webhook_timestamp - payment_timestamp).total_seconds()
    if webhook_delay_seconds < 0:
        raise AdapterValidationError(
            f"webhook created_at ({webhook_timestamp}) precedes payment created_at "
            f"({payment_timestamp}) -- cannot compute a valid webhook_delay_seconds"
        )

    failure_code = _map_failure_code(entity.get("error_reason"))

    payment_method = str(entity.get("method") or UNKNOWN_FAILURE_CODE).lower()

    notes = entity.get("notes") or {}
    merchant_id = str(notes.get("merchant_id") or "unknown_merchant")
    # Customer transaction-history counters are a THIRD source category,
    # distinct from both payload-derivable fields and platform-monitoring
    # aggregates: they require a per-customer history lookup (e.g. a
    # merchant's own CRM), which a single webhook payload does not
    # inherently carry either. Unlike the platform aggregate fields, 0/0
    # is the CORRECT, already-designed-for representation for "no history
    # available" -- src/features/build_features.py's Laplace-smoothed
    # customer_success_rate and is_new_customer indicator exist
    # specifically to handle a brand-new/unknown-history customer
    # neutrally (see its own docstring), so this default does not suppress
    # a systemic signal the way defaulting incident_active would.
    customer_previous_successes = int(notes.get("customer_previous_successes", 0))
    customer_previous_failures = int(notes.get("customer_previous_failures", 0))
    retry_count = int(entity.get("attempts", 0))

    return PaymentEvent(
        event_id=f"evt_razorpay_{payment_id}_{int(webhook_timestamp.timestamp())}",
        transaction_id=str(payment_id),
        merchant_id=merchant_id,
        amount=amount,
        timestamp=payment_timestamp,
        payment_method=payment_method,
        failure_code=failure_code,
        retry_count=retry_count,
        webhook_delay_seconds=webhook_delay_seconds,
        gateway_error_rate_delta=platform_health.gateway_error_rate_delta,
        merchant_failure_rate_delta=platform_health.merchant_failure_rate_delta,
        cross_merchant_failure_rate=platform_health.cross_merchant_failure_rate,
        customer_previous_successes=customer_previous_successes,
        customer_previous_failures=customer_previous_failures,
        incident_active=platform_health.incident_active,
        source="razorpay",
    )
