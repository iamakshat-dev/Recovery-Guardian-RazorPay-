"""
Recovery Guardian — Day 4 Model Tests

Covers the real Logistic Regression root-cause classifier: deterministic
splitting, the FEATURE_COLUMNS contract, leakage guards, artifact
save/load, feature-schema-mismatch enforcement, and end-to-end pipeline
integration using the real trained artifact.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.db import SCHEMA
from src.domain.models import PaymentEvent, RootCausePrediction
from src.features.build_features import FEATURE_COLUMNS, LABEL_COL, build_features
from src.model.classifier import (
    FeatureSchemaMismatchError,
    ModelArtifactNotFoundError,
    RootCauseLogRegClassifier,
)
from src.model.splitting import train_val_test_split
from src.model.training import DATA_PATH, train
from src.pipeline.pipeline import run_pipeline

ROOT_CAUSES = [
    "INFRASTRUCTURE",
    "CARD_DECLINE",
    "INSUFFICIENT_FUNDS",
    "OTP_TIMEOUT",
    "USER_ABANDONMENT",
    "WEBHOOK_AMBIGUITY",
]


def make_small_features_df(rows_per_class: int = 20) -> pd.DataFrame:
    """A small, self-contained features_df with enough rows per class for a
    70/15/15 stratified split to succeed, used for split/leakage tests that
    don't need the real (slower) dataset."""
    rng = np.random.default_rng(7)
    rows = []
    for cause in ROOT_CAUSES:
        for j in range(rows_per_class):
            rows.append(
                {
                    "transaction_id": f"txn_{cause}_{j:03d}",
                    "merchant_id": "merchant_001",
                    "amount": float(rng.uniform(100, 5000)),
                    "timestamp": "2026-08-01T00:00:00",
                    "payment_method": "card",
                    "failure_code": "gateway_timeout"
                    if cause in ("INFRASTRUCTURE", "WEBHOOK_AMBIGUITY")
                    else "issuer_declined",
                    "retry_count": int(rng.integers(0, 3)),
                    "webhook_delay_seconds": float(rng.uniform(0, 20)),
                    "gateway_error_rate_delta": float(rng.uniform(0, 1)),
                    "merchant_failure_rate_delta": float(rng.uniform(0, 1)),
                    "cross_merchant_failure_rate": float(rng.uniform(0, 1)),
                    "customer_previous_successes": int(rng.integers(0, 10)),
                    "customer_previous_failures": int(rng.integers(0, 5)),
                    "incident_active": int(rng.integers(0, 2)),
                    "actual_root_cause": cause,
                }
            )
    raw_df = pd.DataFrame(rows)
    return build_features(raw_df, keep_label=True)


def make_event(**overrides) -> PaymentEvent:
    base = dict(
        event_id="evt_model_test_0001",
        transaction_id="txn_model_test_0001",
        merchant_id="merchant_001",
        amount=1500.0,
        timestamp=datetime(2026, 8, 1),
        payment_method="card",
        failure_code="insufficient_funds",
        retry_count=0,
        webhook_delay_seconds=0.5,
        gateway_error_rate_delta=0.05,
        merchant_failure_rate_delta=0.05,
        cross_merchant_failure_rate=0.05,
        customer_previous_successes=3,
        customer_previous_failures=1,
        incident_active=False,
        source="synthetic",
    )
    base.update(overrides)
    return PaymentEvent(**base)


def one_real_features_row():
    raw_df = pd.read_csv(DATA_PATH)
    features_df = build_features(raw_df.iloc[[0]], keep_label=False)
    return features_df.iloc[0]


# --- Test 2: deterministic split, Test 3: no overlap, stratification --------

def test_split_is_70_15_15_and_stratified():
    df = make_small_features_df(rows_per_class=20)  # 120 rows total
    train_df, val_df, test_df = train_val_test_split(df, label_col=LABEL_COL, random_state=42)

    total = len(df)
    assert len(train_df) == pytest.approx(total * 0.70, abs=2)
    assert len(val_df) == pytest.approx(total * 0.15, abs=2)
    assert len(test_df) == pytest.approx(total * 0.15, abs=2)

    for cause in ROOT_CAUSES:
        assert (train_df[LABEL_COL] == cause).sum() > 0
        assert (val_df[LABEL_COL] == cause).sum() > 0
        assert (test_df[LABEL_COL] == cause).sum() > 0


def test_split_has_no_overlap():
    df = make_small_features_df(rows_per_class=20)
    train_df, val_df, test_df = train_val_test_split(df, label_col=LABEL_COL, random_state=42)

    train_ids = set(train_df["transaction_id"])
    val_ids = set(val_df["transaction_id"])
    test_ids = set(test_df["transaction_id"])

    assert train_ids.isdisjoint(val_ids)
    assert train_ids.isdisjoint(test_ids)
    assert val_ids.isdisjoint(test_ids)
    assert len(train_ids) + len(val_ids) + len(test_ids) == len(df)


def test_split_is_deterministic():
    df = make_small_features_df(rows_per_class=20)
    train_a, val_a, test_a = train_val_test_split(df, label_col=LABEL_COL, random_state=42)
    train_b, val_b, test_b = train_val_test_split(df, label_col=LABEL_COL, random_state=42)

    assert list(train_a["transaction_id"]) == list(train_b["transaction_id"])
    assert list(val_a["transaction_id"]) == list(val_b["transaction_id"])
    assert list(test_a["transaction_id"]) == list(test_b["transaction_id"])


# --- Test 4: feature contract, Test 5: no target/id leakage -----------------

def test_feature_contract_matches_feature_columns():
    df = make_small_features_df(rows_per_class=5)
    X = df[FEATURE_COLUMNS]
    assert list(X.columns) == list(FEATURE_COLUMNS)


def test_no_target_or_id_leakage_in_feature_columns():
    assert "actual_root_cause" not in FEATURE_COLUMNS
    assert "transaction_id" not in FEATURE_COLUMNS

    df = make_small_features_df(rows_per_class=5)
    X = df[FEATURE_COLUMNS]
    assert "actual_root_cause" not in X.columns
    assert "transaction_id" not in X.columns


# --- Test 1: training succeeds on the real dataset --------------------------

def test_training_succeeds_on_real_dataset(tmp_path):
    artifact_path = tmp_path / "model.joblib"
    metrics_path = tmp_path / "metrics.json"

    metrics = train(
        data_path=DATA_PATH,
        artifact_path=artifact_path,
        metrics_path=metrics_path,
        random_state=42,
    )

    assert artifact_path.exists()
    assert metrics_path.exists()
    assert set(metrics["class_labels"]) == set(ROOT_CAUSES)
    assert 0.0 <= metrics["test"]["accuracy"] <= 1.0
    assert 0.0 <= metrics["test"]["macro_f1"] <= 1.0
    # all six classes must have precision/recall reported
    for cause in ROOT_CAUSES:
        assert cause in metrics["test"]["per_class"]
        assert "precision" in metrics["test"]["per_class"][cause]
        assert "recall" in metrics["test"]["per_class"][cause]


# --- Test 6: artifact save/load, Test 7: feature schema persistence --------

def test_artifact_save_and_load_round_trip(tmp_path):
    artifact_path = tmp_path / "model.joblib"
    train(data_path=DATA_PATH, artifact_path=artifact_path, metrics_path=tmp_path / "metrics.json", random_state=42)

    classifier = RootCauseLogRegClassifier(artifact_path=artifact_path)
    assert classifier._model_version == "root-cause-logreg-v1"
    assert classifier._model_version != "placeholder-v1"


def test_feature_schema_is_persisted_exactly(tmp_path):
    artifact_path = tmp_path / "model.joblib"
    train(data_path=DATA_PATH, artifact_path=artifact_path, metrics_path=tmp_path / "metrics.json", random_state=42)

    artifact = joblib.load(artifact_path)
    assert artifact["feature_columns"] == list(FEATURE_COLUMNS)
    assert artifact["random_state"] == 42
    assert set(artifact["class_labels"]) == set(ROOT_CAUSES)


# --- Test 8: schema mismatch fails clearly -----------------------------------

def test_schema_mismatch_raises_clear_error(tmp_path):
    artifact_path = tmp_path / "model.joblib"
    train(data_path=DATA_PATH, artifact_path=artifact_path, metrics_path=tmp_path / "metrics.json", random_state=42)

    artifact = joblib.load(artifact_path)
    artifact["feature_columns"] = artifact["feature_columns"] + ["a_feature_that_did_not_exist_at_train_time"]
    joblib.dump(artifact, artifact_path)

    with pytest.raises(FeatureSchemaMismatchError):
        RootCauseLogRegClassifier(artifact_path=artifact_path)


# --- Test 13: missing artifact fails clearly --------------------------------

def test_missing_artifact_raises_clear_error(tmp_path):
    missing_path = tmp_path / "does_not_exist.joblib"
    with pytest.raises(ModelArtifactNotFoundError):
        RootCauseLogRegClassifier(artifact_path=missing_path)


# --- Test 9/10/11: prediction contract, probability validity, real version -

def test_prediction_contract_and_probability_validity(tmp_path):
    artifact_path = tmp_path / "model.joblib"
    train(data_path=DATA_PATH, artifact_path=artifact_path, metrics_path=tmp_path / "metrics.json", random_state=42)
    classifier = RootCauseLogRegClassifier(artifact_path=artifact_path)

    prediction = classifier.predict(one_real_features_row())

    assert isinstance(prediction, RootCausePrediction)
    assert 0.0 <= prediction.probability <= 1.0
    assert prediction.model_version == "root-cause-logreg-v1"
    assert prediction.model_version != "placeholder-v1"


# --- Test 12: deterministic model behavior -----------------------------------

def test_classifier_is_deterministic_given_same_training_config(tmp_path):
    path_a = tmp_path / "a.joblib"
    path_b = tmp_path / "b.joblib"
    train(data_path=DATA_PATH, artifact_path=path_a, metrics_path=tmp_path / "a_metrics.json", random_state=42)
    train(data_path=DATA_PATH, artifact_path=path_b, metrics_path=tmp_path / "b_metrics.json", random_state=42)

    clf_a = RootCauseLogRegClassifier(artifact_path=path_a)
    clf_b = RootCauseLogRegClassifier(artifact_path=path_b)

    row = one_real_features_row()
    pred_a = clf_a.predict(row)
    pred_b = clf_b.predict(row)

    assert pred_a.root_cause == pred_b.root_cause
    assert pred_a.probability == pytest.approx(pred_b.probability)


# --- Test 14: pipeline integration -------------------------------------------

def test_pipeline_integration_uses_real_model_version(tmp_path, monkeypatch):
    import src.model.classifier as classifier_module

    artifact_path = tmp_path / "model.joblib"
    train(data_path=DATA_PATH, artifact_path=artifact_path, metrics_path=tmp_path / "metrics.json", random_state=42)
    monkeypatch.setattr(classifier_module, "ARTIFACT_PATH", artifact_path)

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)

    event = make_event()
    record = run_pipeline(event, conn=conn)

    assert record.prediction.model_version == "root-cause-logreg-v1"
    assert record.prediction.model_version != "placeholder-v1"
    assert record.policy.policy_version == "placeholder-v1"  # policy untouched in Day 4
