"""
Recovery Guardian — Feature Builder (Day 2)

Turns raw PaymentEvent-shaped rows into a numeric feature matrix ready for
the classifier (Day 4). Kept as a pure function operating on a DataFrame so
it can be unit-tested directly and reused identically for training,
evaluation, and single-transaction inference at request time.

Design note on `failure_code`: it's included as a feature and, for most
classes, is close to deterministic (e.g. `insufficient_funds` -> almost
always INSUFFICIENT_FUNDS). That's realistic, not a shortcut — the genuinely
hard part of this problem is the classes where failure_code overlaps
(`gateway_timeout` is shared between INFRASTRUCTURE and WEBHOOK_AMBIGUITY).
Aggregate accuracy will look high because of the easy classes; the
per-class breakdown on the overlapping ones is what actually demonstrates
the model is doing real work. Report both, not just aggregate accuracy.
"""

import numpy as np
import pandas as pd

NUMERIC_PASSTHROUGH_COLS = [
    "retry_count",
    "gateway_error_rate_delta",
    "merchant_failure_rate_delta",
    "cross_merchant_failure_rate",
    "incident_active",
]

# Fixed category lists, not inferred from the data at build time. This
# matters: if categories were inferred per-batch, a single-transaction
# inference call at serving time could produce a differently-shaped feature
# vector than the one the model was trained on. Freezing the category list
# here is what makes train/serve consistency guaranteed rather than hoped for.
FAILURE_CODE_CATEGORIES = [
    "gateway_timeout", "internal_error", "service_unavailable",
    "issuer_declined", "card_expired", "invalid_card",
    "insufficient_funds",
    "otp_timeout", "3ds_auth_failed",
    "user_cancelled", "session_expired",
    "unknown",
]
PAYMENT_METHOD_CATEGORIES = ["card", "upi", "netbanking", "wallet"]

LABEL_COL = "actual_root_cause"
ID_COL = "transaction_id"


def _one_hot(series: pd.Series, categories: list, prefix: str) -> pd.DataFrame:
    """One-hot encode against a FIXED category list (not series.unique()),
    so unseen/out-of-vocabulary values at inference time produce an
    all-zero row instead of crashing or silently shifting column order."""
    cat_series = pd.Categorical(series, categories=categories)
    dummies = pd.get_dummies(cat_series, prefix=prefix)
    # Ensure every expected column exists even if this batch didn't contain
    # every category (important for small ad-hoc single-row inputs).
    expected_cols = [f"{prefix}_{c}" for c in categories]
    for col in expected_cols:
        if col not in dummies.columns:
            dummies[col] = 0
    return dummies[expected_cols].astype(int)


def build_features(df: pd.DataFrame, keep_label: bool = True) -> pd.DataFrame:
    """
    Args:
        df: raw event rows with the PaymentEvent schema columns.
        keep_label: if True and the label column is present, include it
            unchanged in the output (useful for training data). Never
            engineered/transformed — kept as-is for the caller to split off.

    Returns:
        A numeric feature DataFrame, one row per input row, plus
        `transaction_id` and (optionally) the label column for traceability.
        Every column except the id/label is safe to feed directly into
        scikit-learn.
    """
    df = df.copy()
    missing_required = [c for c in NUMERIC_PASSTHROUGH_COLS if c not in df.columns]
    if missing_required:
        raise ValueError(f"Missing required columns: {missing_required}")

    out = pd.DataFrame(index=df.index)
    out[ID_COL] = df[ID_COL]

    # --- Passthrough numeric signals ---
    for col in NUMERIC_PASSTHROUGH_COLS:
        out[col] = df[col].astype(float)

    # --- Derived features ---
    out["amount_log"] = np.log1p(df["amount"].astype(float).clip(lower=0))

    out["webhook_delay_log"] = np.log1p(
        df["webhook_delay_seconds"].astype(float).clip(lower=0)
    )

    successes = df["customer_previous_successes"].fillna(0).astype(float)
    failures = df["customer_previous_failures"].fillna(0).astype(float)
    total_history = successes + failures

    # +1 in the denominator (Laplace-style smoothing) is deliberate: a
    # brand-new customer with 0/0 history should get a neutral success
    # rate (0.0 here, since we're not assuming good faith by default),
    # not a divide-by-zero error and not an artificially confident 1.0 or 0.0.
    out["customer_success_rate"] = successes / (total_history + 1.0)
    out["customer_total_history"] = total_history
    out["is_new_customer"] = (total_history == 0).astype(int)

    # --- Categorical encodings against fixed vocabularies ---
    failure_code_dummies = _one_hot(
        df["failure_code"], FAILURE_CODE_CATEGORIES, prefix="failure_code"
    )
    payment_method_dummies = _one_hot(
        df["payment_method"], PAYMENT_METHOD_CATEGORIES, prefix="payment_method"
    )

    out = pd.concat([out, failure_code_dummies, payment_method_dummies], axis=1)

    if keep_label and LABEL_COL in df.columns:
        out[LABEL_COL] = df[LABEL_COL]

    return out


FEATURE_COLUMNS = (
    NUMERIC_PASSTHROUGH_COLS
    + ["amount_log", "webhook_delay_log", "customer_success_rate",
       "customer_total_history", "is_new_customer"]
    + [f"failure_code_{c}" for c in FAILURE_CODE_CATEGORIES]
    + [f"payment_method_{c}" for c in PAYMENT_METHOD_CATEGORIES]
)


if __name__ == "__main__":
    df = pd.read_csv("data/synthetic_events.csv")
    features = build_features(df)
    print(f"Input rows: {len(df)}, output rows: {len(features)}")
    print(f"Feature columns ({len(FEATURE_COLUMNS)}): {FEATURE_COLUMNS}")
    print("\nFirst 3 rows:")
    print(features.head(3).T)
    features.to_csv("data/features.csv", index=False)
    print("\nSaved to data/features.csv")
