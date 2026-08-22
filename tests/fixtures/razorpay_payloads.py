"""
Recovery Guardian — Day 11 Representative Razorpay-Shaped Fixtures

Every payload below is REPRESENTATIVE / PRODUCTION-SHAPED, built from
Razorpay's well-documented public API conventions. None of these were
captured from live Razorpay production traffic, and none imply an
official, verified schema guarantee.
"""

VALID_CARD_DECLINE_PAYLOAD = {
    "event": "payment.failed",
    "created_at": 1735689605,  # webhook arrived 5s after payment creation
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_repr_card_decline_0001",
                "amount": 250000,  # paise -> ₹2,500.00
                "currency": "INR",
                "method": "card",
                "status": "failed",
                "error_code": "BAD_REQUEST_ERROR",
                "error_reason": "card_declined",
                "created_at": 1735689600,
                "attempts": 0,
                "notes": {
                    "merchant_id": "merchant_001",
                    "customer_previous_successes": 4,
                    "customer_previous_failures": 1,
                },
            }
        }
    },
}

GATEWAY_TIMEOUT_DURING_INCIDENT_PAYLOAD = {
    "event": "payment.failed",
    "created_at": 1735690003,  # webhook arrived 3s after payment creation
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_repr_gateway_timeout_0002",
                "amount": 500000,  # paise -> ₹5,000.00
                "currency": "INR",
                "method": "upi",
                "status": "failed",
                "error_code": "GATEWAY_ERROR",
                "error_reason": "gateway_timeout",
                "created_at": 1735690000,
                "attempts": 0,
                "notes": {
                    "merchant_id": "merchant_011",
                    "customer_previous_successes": 2,
                    "customer_previous_failures": 0,
                },
            }
        }
    },
}

AMBIGUOUS_WEBHOOK_PAYLOAD = {
    "event": "payment.failed",
    "created_at": 1735690417,  # webhook arrived 17s after payment creation
    # (a materially longer delay than the gateway-timeout fixture above --
    # long webhook delay is one of the signals genuinely associated with
    # WEBHOOK_AMBIGUITY in the frozen training data; see
    # data/generate_data.py's WEBHOOK_AMBIGUITY webhook_delay generation).
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_repr_ambiguous_0003",
                "amount": 150000,  # paise -> ₹1,500.00
                "currency": "INR",
                "method": "card",
                "status": "failed",
                "error_code": None,
                "error_reason": None,  # unrecognized/absent -> canonical "unknown"
                "created_at": 1735690400,
                "attempts": 0,
                "notes": {
                    "merchant_id": "merchant_022",
                    "customer_previous_successes": 5,
                    "customer_previous_failures": 0,
                },
            }
        }
    },
}

MISSING_TRANSACTION_ID_PAYLOAD = {
    "event": "payment.failed",
    "created_at": 1735689605,
    "payload": {
        "payment": {
            "entity": {
                "amount": 100000,
                "created_at": 1735689600,
            }
        }
    },
}

MISSING_AMOUNT_PAYLOAD = {
    "event": "payment.failed",
    "created_at": 1735689605,
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_repr_missing_amount",
                "created_at": 1735689600,
            }
        }
    },
}

NEGATIVE_AMOUNT_PAYLOAD = {
    "event": "payment.failed",
    "created_at": 1735689605,
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_repr_negative_amount",
                "amount": -500,
                "created_at": 1735689600,
            }
        }
    },
}

NON_NUMERIC_AMOUNT_PAYLOAD = {
    "event": "payment.failed",
    "created_at": 1735689605,
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_repr_non_numeric_amount",
                "amount": "not-a-number",
                "created_at": 1735689600,
            }
        }
    },
}

INVALID_TIMESTAMP_PAYLOAD = {
    "event": "payment.failed",
    "created_at": 1735689605,
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_repr_invalid_timestamp",
                "amount": 100000,
                "created_at": "not-a-timestamp",
            }
        }
    },
}

WEBHOOK_BEFORE_PAYMENT_PAYLOAD = {
    "event": "payment.failed",
    "created_at": 1735689500,  # BEFORE the payment's own created_at -- invalid
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_repr_time_travel",
                "amount": 100000,
                "created_at": 1735689600,
            }
        }
    },
}
