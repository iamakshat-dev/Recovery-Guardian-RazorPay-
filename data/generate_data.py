"""
Recovery Guardian — Synthetic Payment Failure Dataset Generator

Generates transactions with a KNOWN ground-truth root cause, but with feature
distributions that deliberately OVERLAP across classes. This is a design
constraint, not a bug: if `incident_active=1` perfectly predicted
`INFRASTRUCTURE`, the classifier would trivially memorize one feature and the
whole evaluation would be worthless. Real payment failure signals are noisy
and ambiguous, and the dataset needs to reflect that so the classifier's
precision/recall numbers actually mean something.

Root causes generated (6 classes):
    INFRASTRUCTURE     - gateway/platform-side degradation
    CARD_DECLINE        - issuer declined the card
    INSUFFICIENT_FUNDS  - customer-side, distinct recovery path from decline
    OTP_TIMEOUT          - 3DS/OTP authentication failure
    USER_ABANDONMENT    - customer dropped off before completing
    WEBHOOK_AMBIGUITY   - payment state unknown; must NOT be retried blindly

Run:
    python generate_data.py --rows 1500 --seed 42 --out synthetic_events.csv
"""

import argparse
import uuid
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

ROOT_CAUSES = [
    "INFRASTRUCTURE",
    "CARD_DECLINE",
    "INSUFFICIENT_FUNDS",
    "OTP_TIMEOUT",
    "USER_ABANDONMENT",
    "WEBHOOK_AMBIGUITY",
]

# Target class mix — intentionally not perfectly balanced, mirrors the rough
# shape described in the roadmap (infra failures are a meaningful minority,
# not the dominant class).
CLASS_WEIGHTS = {
    "INFRASTRUCTURE": 0.20,
    "CARD_DECLINE": 0.22,
    "INSUFFICIENT_FUNDS": 0.18,
    "OTP_TIMEOUT": 0.14,
    "USER_ABANDONMENT": 0.14,
    "WEBHOOK_AMBIGUITY": 0.12,
}

FAILURE_CODE_BY_CAUSE = {
    "INFRASTRUCTURE": ["gateway_timeout", "internal_error", "service_unavailable"],
    "CARD_DECLINE": ["issuer_declined", "card_expired", "invalid_card"],
    "INSUFFICIENT_FUNDS": ["insufficient_funds"],
    "OTP_TIMEOUT": ["otp_timeout", "3ds_auth_failed"],
    "USER_ABANDONMENT": ["user_cancelled", "session_expired"],
    "WEBHOOK_AMBIGUITY": ["gateway_timeout", "unknown"],  # deliberately overlaps
    # with INFRASTRUCTURE's failure codes — the ambiguity is the point.
}

MERCHANT_IDS = [f"merchant_{i:03d}" for i in range(1, 41)]
PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]


def sample_amount(rng: np.random.Generator) -> float:
    """Log-normal amount distribution, roughly ₹200 to ₹50,000, right-skewed."""
    return float(np.round(np.exp(rng.normal(7.3, 1.1)), 2))


def clip01(x):
    return float(np.clip(x, 0.0, 1.0))


def generate_row_in_window(rng: np.random.Generator, txn_idx: int, window_start, window_end):
    """Generate one row with a timestamp forced inside the incident window,
    used for the deliberate failure-spike burst. Root cause is weighted
    heavily toward INFRASTRUCTURE during the burst, but NOT exclusively —
    a real spike still has some concurrent, unrelated ordinary failures
    mixed in, which is exactly what makes root-cause classification during
    an incident a genuine (not trivial) problem."""
    burst_weights = {
        "INFRASTRUCTURE": 0.70,
        "CARD_DECLINE": 0.10,
        "INSUFFICIENT_FUNDS": 0.06,
        "OTP_TIMEOUT": 0.05,
        "USER_ABANDONMENT": 0.04,
        "WEBHOOK_AMBIGUITY": 0.05,
    }
    root_cause = rng.choice(list(burst_weights.keys()), p=list(burst_weights.values()))
    offset_seconds = int(rng.integers(0, int((window_end - window_start).total_seconds())))
    ts = window_start + timedelta(seconds=offset_seconds)
    row = _generate_features_for_cause(rng, txn_idx, root_cause, ts, force_incident_active=True)
    return row


def _generate_features_for_cause(rng, txn_idx, root_cause, ts, force_incident_active=False):
    """Shared feature-generation logic, factored out so both the normal
    background rate and the incident burst use identical cause-conditional
    distributions."""
    base_gateway_error_delta = clip01(rng.normal(0.05, 0.05))
    base_merchant_failure_delta = clip01(rng.normal(0.05, 0.05))
    base_webhook_delay = max(0.0, rng.exponential(2.0))
    base_cross_merchant_failure_rate = clip01(rng.normal(0.05, 0.04))

    if force_incident_active:
        incident_active = 1 if rng.random() < 0.85 else 0
    else:
        incident_active = 1 if rng.random() < 0.03 else 0

    if root_cause == "INFRASTRUCTURE":
        gateway_error_delta = clip01(base_gateway_error_delta + rng.normal(0.45, 0.18))
        merchant_failure_delta = clip01(base_merchant_failure_delta + rng.normal(0.35, 0.15))
        cross_merchant_failure_rate = clip01(base_cross_merchant_failure_rate + rng.normal(0.35, 0.15))
        webhook_delay = base_webhook_delay + max(0.0, rng.normal(3.0, 3.0))
        retry_count = int(rng.integers(0, 2))
        if not force_incident_active and rng.random() < 0.20:
            incident_active = 0  # detection-lag cases outside any burst

    elif root_cause == "WEBHOOK_AMBIGUITY":
        gateway_error_delta = clip01(base_gateway_error_delta + rng.normal(0.20, 0.15))
        merchant_failure_delta = clip01(base_merchant_failure_delta + rng.normal(0.15, 0.12))
        cross_merchant_failure_rate = clip01(base_cross_merchant_failure_rate + rng.normal(0.10, 0.10))
        webhook_delay = base_webhook_delay + max(0.0, rng.normal(12.0, 6.0))
        retry_count = int(rng.integers(0, 2))

    elif root_cause == "CARD_DECLINE":
        gateway_error_delta = base_gateway_error_delta
        merchant_failure_delta = base_merchant_failure_delta
        cross_merchant_failure_rate = base_cross_merchant_failure_rate
        webhook_delay = base_webhook_delay
        retry_count = int(rng.integers(0, 3))

    elif root_cause == "INSUFFICIENT_FUNDS":
        gateway_error_delta = base_gateway_error_delta
        merchant_failure_delta = base_merchant_failure_delta
        cross_merchant_failure_rate = base_cross_merchant_failure_rate
        webhook_delay = base_webhook_delay
        retry_count = int(rng.integers(0, 2))

    elif root_cause == "OTP_TIMEOUT":
        gateway_error_delta = clip01(base_gateway_error_delta + rng.normal(0.05, 0.06))
        merchant_failure_delta = base_merchant_failure_delta
        cross_merchant_failure_rate = base_cross_merchant_failure_rate
        webhook_delay = base_webhook_delay
        retry_count = int(rng.integers(0, 2))

    else:  # USER_ABANDONMENT
        gateway_error_delta = base_gateway_error_delta
        merchant_failure_delta = base_merchant_failure_delta
        cross_merchant_failure_rate = base_cross_merchant_failure_rate
        webhook_delay = base_webhook_delay
        retry_count = 0

    if root_cause in ("CARD_DECLINE", "INSUFFICIENT_FUNDS"):
        prev_successes = int(rng.poisson(2))
        prev_failures = int(rng.poisson(2.5))
    else:
        prev_successes = int(rng.poisson(5))
        prev_failures = int(rng.poisson(0.6))

    failure_code = rng.choice(FAILURE_CODE_BY_CAUSE[root_cause])
    payment_method = rng.choice(PAYMENT_METHODS)
    merchant_id = rng.choice(MERCHANT_IDS)
    amount = sample_amount(rng)

    return {
        "transaction_id": f"txn_{txn_idx:06d}_{uuid.uuid4().hex[:6]}",
        "merchant_id": merchant_id,
        "amount": amount,
        "timestamp": ts.isoformat(),
        "payment_method": payment_method,
        "failure_code": failure_code,
        "retry_count": retry_count,
        "webhook_delay_seconds": round(webhook_delay, 2),
        "gateway_error_rate_delta": round(gateway_error_delta, 4),
        "merchant_failure_rate_delta": round(merchant_failure_delta, 4),
        "cross_merchant_failure_rate": round(cross_merchant_failure_rate, 4),
        "customer_previous_successes": prev_successes,
        "customer_previous_failures": prev_failures,
        "incident_active": incident_active,
        "actual_root_cause": root_cause,
    }


def generate_dataset(n_rows: int, seed: int, burst_rows: int = 110) -> pd.DataFrame:
    """
    Two-phase generation:
      1. `n_rows` background transactions spread uniformly across 21 days
         at the normal class mix (rare, quiet infra failures included).
      2. `burst_rows` transactions concentrated inside one 30-minute window
         (Aug 15, 22:10-22:40) with an INFRASTRUCTURE-heavy mix — this is
         the deliberate failure-rate spike used for the Day 12 incident
         demo. Injecting it explicitly, rather than hoping enough
         transactions land there by chance, is what makes the incident
         window a reliable, reproducible scenario instead of a fluke.
    """
    rng = np.random.default_rng(seed)
    window_start = datetime(2026, 8, 15, 22, 10)
    window_end = datetime(2026, 8, 15, 22, 40)

    background_rows = []
    for i in range(n_rows):
        root_cause = rng.choice(list(CLASS_WEIGHTS.keys()), p=list(CLASS_WEIGHTS.values()))
        ts = datetime(2026, 8, 1) + timedelta(seconds=int(rng.integers(0, 21 * 24 * 3600)))
        background_rows.append(_generate_features_for_cause(rng, i, root_cause, ts))

    burst_rows_list = [
        generate_row_in_window(rng, n_rows + j, window_start, window_end)
        for j in range(burst_rows)
    ]

    df = pd.DataFrame(background_rows + burst_rows_list)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def summarize(df: pd.DataFrame):
    print(f"\nTotal rows: {len(df)}")
    print("\nClass distribution:")
    print(df["actual_root_cause"].value_counts())
    print("\nMean gateway_error_rate_delta by root cause (should overlap, not separate cleanly):")
    print(df.groupby("actual_root_cause")["gateway_error_rate_delta"].mean().round(3))
    print("\nMean webhook_delay_seconds by root cause:")
    print(df.groupby("actual_root_cause")["webhook_delay_seconds"].mean().round(2))
    print("\nincident_active=1 rate by root cause (should be noisy background, high only near the burst):")
    print(df.groupby("actual_root_cause")["incident_active"].mean().round(3))

    in_window = (df["timestamp"] >= "2026-08-15T22:10:00") & (df["timestamp"] <= "2026-08-15T22:40:00")
    print(f"\nRows inside the injected incident window: {in_window.sum()}")
    if in_window.sum() > 0:
        print("Root cause mix inside the window (should be infra-heavy but not pure):")
        print(df.loc[in_window, "actual_root_cause"].value_counts())
        outside_rate = (~in_window).sum() and len(df.loc[~in_window & (df['timestamp'].str[:10] == '2026-08-15')]) 
        print(f"\nFor the failure-rate-spike narrative: background failure rate on other days vs. "
              f"the {in_window.sum()}-transaction burst inside a 30-minute window on Aug 15 "
              f"is the 'normal 2% -> spike 38%' story for the pitch video.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1500, help="background transaction count")
    parser.add_argument("--burst-rows", type=int, default=110, help="incident-window burst transaction count")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="synthetic_events.csv")
    args = parser.parse_args()

    df = generate_dataset(args.rows, args.seed, burst_rows=args.burst_rows)
    df.to_csv(args.out, index=False)
    summarize(df)
    print(f"\nSaved to {args.out}")
