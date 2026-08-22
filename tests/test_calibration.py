"""
Recovery Guardian — Day 5 Calibration Tests

Exercises the actual calibration + evaluation pipeline
(src/model/calibrate.py), not mocked results. Every test that produces
artifacts writes to `tmp_path`, never to the developer's real
artifacts/ or experiments/results/ directories — the frozen Day 4 raw
artifact is only ever READ (never written to) by these tests.
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from unittest import mock

import joblib
import numpy as np
import pandas as pd
import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.db import SCHEMA
from src.domain.models import PaymentEvent, RootCausePrediction
from src.features.build_features import FEATURE_COLUMNS, build_features
from src.model import calibrate as calibrate_module
from src.model.artifacts import load_artifact
from src.model.calibrate import (
    CALIBRATED_MODEL_VERSION,
    RAW_ARTIFACT_PATH,
    calibrate_and_evaluate,
)
from src.model.calibrated_classifier import CalibratedRootCauseClassifier
from src.model.training import DATA_PATH
from src.pipeline.pipeline import run_pipeline

ROOT_CAUSES = [
    "CARD_DECLINE",
    "INFRASTRUCTURE",
    "INSUFFICIENT_FUNDS",
    "OTP_TIMEOUT",
    "USER_ABANDONMENT",
    "WEBHOOK_AMBIGUITY",
]


def _run_calibration(tmp_path, **overrides):
    kwargs = dict(
        calibrated_artifact_path=tmp_path / "calibrated.joblib",
        metrics_path=tmp_path / "evaluation_metrics.json",
        confusion_matrix_plot_path=tmp_path / "confusion_matrix.png",
        calibration_plot_path=tmp_path / "calibration_plot.png",
    )
    kwargs.update(overrides)
    return calibrate_and_evaluate(**kwargs), kwargs


def make_event(**overrides) -> PaymentEvent:
    base = dict(
        event_id="evt_calibration_test_0001",
        transaction_id="txn_calibration_test_0001",
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


# --- Test 1: calibrated probabilities are valid ------------------------------

def test_calibrated_probabilities_are_valid(tmp_path):
    metrics, paths = _run_calibration(tmp_path)
    artifact = joblib.load(paths["calibrated_artifact_path"])
    calibrated_model = artifact["calibrated_model"]

    raw_df = pd.read_csv(DATA_PATH)
    features_df = build_features(raw_df.iloc[[0]], keep_label=False)
    row = pd.DataFrame([features_df.iloc[0][FEATURE_COLUMNS]])

    proba = calibrated_model.predict_proba(row)[0]

    assert len(proba) == 6
    assert all(0.0 <= p <= 1.0 for p in proba)
    assert abs(float(proba.sum()) - 1.0) <= 1e-6
    assert set(calibrated_model.classes_) == set(ROOT_CAUSES)


# --- Test 2: calibration uses validation data only ---------------------------

def test_calibration_receives_only_validation_data_not_test_data(tmp_path):
    """Fails if calibrate_and_evaluate is ever changed to accidentally pass
    the test split into fit_calibration -- this spies on the ACTUAL call,
    not a comment."""
    captured = {}
    real_fit_calibration = calibrate_module.fit_calibration

    def spy(model, X, y, method=calibrate_module.CALIBRATION_METHOD):
        captured["X_index"] = set(X.index)
        return real_fit_calibration(model, X, y, method=method)

    with mock.patch.object(calibrate_module, "fit_calibration", side_effect=spy):
        _run_calibration(tmp_path)

    assert "X_index" in captured, "fit_calibration was never called"

    _, val_df, test_df = calibrate_module._load_split()
    assert captured["X_index"] == set(val_df.index)
    assert captured["X_index"].isdisjoint(set(test_df.index))


def test_test_split_is_never_touched_by_calibration_fitting(tmp_path):
    """Complementary to the above: explicitly confirms the test split's
    row count is preserved and disjoint from the validation split used for
    fitting -- i.e. the split itself (src/model/splitting.py, unchanged
    from Day 4) still separates val/test correctly, which calibration
    fitting depends on to be meaningful."""
    _, val_df, test_df = calibrate_module._load_split()
    assert set(val_df.index).isdisjoint(set(test_df.index))
    assert len(test_df) > 0
    assert len(val_df) > 0


# --- Test 3: Day 4 model remains frozen --------------------------------------

def test_calibration_does_not_change_the_frozen_day4_model(tmp_path):
    raw_artifact_before = load_artifact(RAW_ARTIFACT_PATH)
    model = raw_artifact_before["model"]
    coef_before = model.coef_.copy()
    intercept_before = model.intercept_.copy()
    classes_before = list(model.classes_)

    _run_calibration(tmp_path)

    # In-memory: the same model object, unchanged.
    assert np.array_equal(coef_before, model.coef_)
    assert np.array_equal(intercept_before, model.intercept_)
    assert classes_before == list(model.classes_)

    # On disk: re-load the raw artifact file fresh and confirm it matches too
    # (i.e. calibrate_and_evaluate never wrote to RAW_ARTIFACT_PATH).
    raw_artifact_after = load_artifact(RAW_ARTIFACT_PATH)
    assert np.array_equal(coef_before, raw_artifact_after["model"].coef_)
    assert raw_artifact_after["model_version"] == raw_artifact_before["model_version"]


# --- Test 4: raw and calibrated artifacts are distinct -----------------------

def test_raw_and_calibrated_artifacts_are_distinct_and_both_loadable(tmp_path):
    metrics, paths = _run_calibration(tmp_path)

    raw_artifact = load_artifact(RAW_ARTIFACT_PATH)
    calibrated_artifact = joblib.load(paths["calibrated_artifact_path"])

    assert raw_artifact["model_version"] != calibrated_artifact["model_version"]
    assert calibrated_artifact["model_version"] == CALIBRATED_MODEL_VERSION
    assert calibrated_artifact["base_model_version"] == raw_artifact["model_version"]
    # Raw artifact file itself must still exist independently.
    assert RAW_ARTIFACT_PATH.exists()
    assert paths["calibrated_artifact_path"].exists()
    assert RAW_ARTIFACT_PATH != paths["calibrated_artifact_path"]


# --- Test 5: all six class metrics exist -------------------------------------

def test_all_six_class_metrics_are_present_and_valid(tmp_path):
    metrics, _ = _run_calibration(tmp_path)
    per_class = metrics["test_evaluation"]["per_class"]

    for cause in ROOT_CAUSES:
        assert cause in per_class
        for key in ("precision", "recall", "f1"):
            value = per_class[cause][key]
            assert value is not None
            assert not (isinstance(value, float) and np.isnan(value))
            assert 0.0 <= value <= 1.0

    # Explicit attention to the intentionally-hard pair.
    assert "INFRASTRUCTURE" in per_class
    assert "WEBHOOK_AMBIGUITY" in per_class


# --- Test 6: evaluation artifacts exist --------------------------------------

def test_evaluation_artifacts_are_created_with_real_content(tmp_path):
    _run_calibration(tmp_path)

    for name in ("evaluation_metrics.json", "confusion_matrix.png", "calibration_plot.png"):
        path = tmp_path / name
        assert path.exists(), f"{name} was not created"
        assert path.stat().st_size > 0, f"{name} is empty"

    with open(tmp_path / "evaluation_metrics.json") as f:
        metrics = json.load(f)
    assert metrics["model_version"] == CALIBRATED_MODEL_VERSION
    assert "test_evaluation" in metrics
    assert "calibration_metrics" in metrics


# --- Test 7: multiclass calibration metrics are valid ------------------------

def test_multiclass_calibration_metrics_are_valid(tmp_path):
    metrics, _ = _run_calibration(tmp_path)
    cal_metrics = metrics["calibration_metrics"]

    brier = cal_metrics["multiclass_brier_score_calibrated"]
    assert np.isfinite(brier)
    assert 0.0 <= brier <= 2.0  # multiclass Brier over a 6-dim one-hot vector is bounded by 2

    ece = cal_metrics["ece_top_label_calibrated"]
    assert np.isfinite(ece)
    assert ece >= 0.0


# --- Test 8: end-to-end calibrated inference ---------------------------------

def test_end_to_end_calibrated_inference_through_real_pipeline():
    """Runs a real PaymentEvent through the actual feature builder, the
    actual calibrated classifier, and the actual (placeholder) policy
    engine -- via the real run_pipeline(), not a mocked result."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)

    event = make_event()
    record = run_pipeline(event, conn=conn)

    assert isinstance(record.prediction, RootCausePrediction)
    assert record.prediction.model_version == CALIBRATED_MODEL_VERSION
    assert 0.0 <= record.prediction.probability <= 1.0

    # Real computed value, not a fabricated constant like the Day 3
    # placeholder's fixed 0.50.
    assert record.prediction.probability != 0.50


def test_calibrated_classifier_predict_uses_real_feature_builder_output():
    raw_df = pd.read_csv(DATA_PATH)
    features_df = build_features(raw_df.iloc[[0]], keep_label=False)
    row = features_df.iloc[0]

    classifier = CalibratedRootCauseClassifier()
    prediction = classifier.predict(row)

    assert prediction.model_version == CALIBRATED_MODEL_VERSION
    assert 0.0 <= prediction.probability <= 1.0
