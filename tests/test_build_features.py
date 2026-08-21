"""
Recovery Guardian — Feature Builder Unit Tests (Day 2)

Covers edge cases the feature builder must handle correctly even if they
don't happen to appear in the current synthetic dataset by chance:
zero customer history, an unseen/out-of-vocabulary failure_code at
inference time, a single-row DataFrame (the shape used for live API
requests, not just batch training), and missing required columns.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.features.build_features import build_features, FEATURE_COLUMNS


def make_row(**overrides):
    base = {
        "transaction_id": "txn_test_0001",
        "merchant_id": "merchant_001",
        "amount": 1000.0,
        "timestamp": "2026-08-01T00:00:00",
        "payment_method": "card",
        "failure_code": "insufficient_funds",
        "retry_count": 0,
        "webhook_delay_seconds": 0.5,
        "gateway_error_rate_delta": 0.05,
        "merchant_failure_rate_delta": 0.05,
        "cross_merchant_failure_rate": 0.05,
        "customer_previous_successes": 3,
        "customer_previous_failures": 1,
        "incident_active": 0,
        "actual_root_cause": "INSUFFICIENT_FUNDS",
    }
    base.update(overrides)
    return base


def test_output_shape_matches_input_rows():
    df = pd.DataFrame([make_row(), make_row(transaction_id="txn_test_0002")])
    out = build_features(df)
    assert len(out) == 2


def test_all_feature_columns_present_and_numeric():
    df = pd.DataFrame([make_row()])
    out = build_features(df)
    for col in FEATURE_COLUMNS:
        assert col in out.columns, f"missing feature column: {col}"
    assert out[FEATURE_COLUMNS].select_dtypes(exclude="number").empty


def test_no_nulls_produced():
    df = pd.DataFrame([make_row(), make_row(transaction_id="txn_test_0002")])
    out = build_features(df)
    assert out[FEATURE_COLUMNS].isnull().sum().sum() == 0


def test_zero_customer_history_does_not_crash_or_produce_nan():
    """The exact edge case the roadmap flagged: a brand-new customer with
    0 successes and 0 failures must not cause a divide-by-zero."""
    df = pd.DataFrame([make_row(
        customer_previous_successes=0, customer_previous_failures=0
    )])
    out = build_features(df)
    assert out.loc[0, "is_new_customer"] == 1
    assert out.loc[0, "customer_success_rate"] == 0.0
    assert not np.isnan(out.loc[0, "customer_success_rate"])


def test_zero_retry_count():
    df = pd.DataFrame([make_row(retry_count=0)])
    out = build_features(df)
    assert out.loc[0, "retry_count"] == 0


def test_unseen_failure_code_produces_all_zero_onehot_not_a_crash():
    """A failure_code the training vocabulary never saw (e.g. a new Razorpay
    error code introduced after the model was trained) must not crash
    inference — it should fall back to an all-zero encoding rather than
    silently shifting every other column's meaning."""
    df = pd.DataFrame([make_row(failure_code="some_brand_new_error_code_v2")])
    out = build_features(df)
    fc_cols = [c for c in out.columns if c.startswith("failure_code_")]
    assert (out.loc[0, fc_cols] == 0).all()


def test_single_row_dataframe_same_shape_as_batch():
    """This is the shape a live API request produces — one row, not a
    batch — and it must produce identical column structure to training."""
    single = pd.DataFrame([make_row()])
    batch = pd.DataFrame([make_row(), make_row(transaction_id="txn_test_0002")])

    single_out = build_features(single)
    batch_out = build_features(batch)

    assert list(single_out.columns) == list(batch_out.columns)


def test_missing_required_column_raises_clear_error():
    df = pd.DataFrame([make_row()]).drop(columns=["gateway_error_rate_delta"])
    with pytest.raises(ValueError, match="Missing required columns"):
        build_features(df)


def test_label_column_passthrough_when_present():
    df = pd.DataFrame([make_row(actual_root_cause="INFRASTRUCTURE")])
    out = build_features(df, keep_label=True)
    assert out.loc[0, "actual_root_cause"] == "INFRASTRUCTURE"


def test_label_column_excluded_when_requested():
    df = pd.DataFrame([make_row()])
    out = build_features(df, keep_label=False)
    assert "actual_root_cause" not in out.columns


def test_high_retry_count_and_extreme_amount_do_not_break_transforms():
    """Amounts and retry counts at the edge of plausibility (a very
    high-value transaction, a maxed-out retry count) should still produce
    finite, sane feature values, not inf/nan from the log transform."""
    df = pd.DataFrame([make_row(amount=999999.0, retry_count=50)])
    out = build_features(df)
    assert np.isfinite(out.loc[0, "amount_log"])
    assert out.loc[0, "retry_count"] == 50
