"""
Recovery Guardian — Day 5 Probability Calibration + Rigorous Evaluation

Loads the FROZEN Day 4 model artifact (never retrains it), fits a
calibration layer using ONLY the validation split of the existing Day 4
70/15/15 split, evaluates the calibrated probabilities on the untouched
test split, and persists a separate calibrated artifact + a machine
readable evaluation report + two plots.

Run:
    python -m src.model.calibrate

Pipeline:
    artifacts/root_cause_classifier.joblib   [frozen Day 4 model, unchanged]
        -> model.predict_proba(X_VALIDATION)
        -> CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid")
           .fit(X_VALIDATION, y_VALIDATION)     <-- validation only, ever
        -> calibrated_model
        -> evaluate calibrated_model on X_TEST / y_TEST (untouched, once)
        -> artifacts/root_cause_classifier_calibrated.joblib
        -> experiments/results/{evaluation_metrics.json, confusion_matrix.png,
                                calibration_plot.png}

Why sklearn.frozen.FrozenEstimator + CalibratedClassifierCV, not a
hand-rolled multiclass Platt scaler:

    sklearn removed CalibratedClassifierCV's old `cv="prefit"` option; the
    current, supported way to calibrate an already-fitted estimator
    without refitting it is to wrap it in FrozenEstimator first.
    FrozenEstimator.fit() is a no-op by construction, so
    CalibratedClassifierCV.fit(X_val, y_val) can only ever fit the
    per-class sigmoid calibration curves against
    (frozen_model.predict_proba(X_val), y_val) -- it is structurally
    incapable of altering the frozen LogisticRegression's coef_/intercept_.
    This was verified empirically before writing this module (coef_,
    intercept_, and classes_ compared before/after byte-for-byte identical)
    and is re-verified by tests/test_calibration.py on every run.

    sklearn's multiclass calibration (one sigmoid curve fit per class in a
    one-vs-rest manner, then renormalized) is a well-tested, already
    mathematically-valid multiclass probability calibration -- safer than
    inventing a custom multiclass Platt-scaling implementation from
    scratch, per the Day 5 spec's explicit caution against doing so.

Why "sigmoid" (Platt) and not "isotonic":

    The validation split has 241 rows across 6 classes (~40/class on
    average, and as few as ~26 for the rarest class). Isotonic
    regression is non-parametric and needs materially more per-class data
    than that to avoid overfitting into a jagged step function; sigmoid
    calibration fits only 2 parameters per class and is the standard
    recommendation for calibration sets this small (Niculescu-Mizil &
    Caruana, 2005). Isotonic was considered and rejected for this dataset
    size specifically -- not chosen by default.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import matplotlib

matplotlib.use("Agg")  # headless: never requires a display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from src.features.build_features import FEATURE_COLUMNS, LABEL_COL, build_features
from src.model.artifacts import DEFAULT_ARTIFACT_PATH, load_artifact, save_artifact
from src.model.splitting import train_val_test_split

CALIBRATION_METHOD = "sigmoid"
CALIBRATED_MODEL_VERSION = "root-cause-logreg-calibrated-v1"
RANDOM_STATE = 42  # must match the Day 4 split's random_state exactly

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_PATH = REPO_ROOT / "data" / "synthetic_events.csv"
RAW_ARTIFACT_PATH = DEFAULT_ARTIFACT_PATH
CALIBRATED_ARTIFACT_PATH = REPO_ROOT / "artifacts" / "root_cause_classifier_calibrated.joblib"
RESULTS_DIR = REPO_ROOT / "experiments" / "results"
METRICS_PATH = RESULTS_DIR / "evaluation_metrics.json"
CONFUSION_MATRIX_PLOT_PATH = RESULTS_DIR / "confusion_matrix.png"
CALIBRATION_PLOT_PATH = RESULTS_DIR / "calibration_plot.png"

N_ECE_BINS = 10


def fit_calibration(model, X_val: pd.DataFrame, y_val: pd.Series, method: str = CALIBRATION_METHOD):
    """Fit ONLY a calibration layer on top of the frozen `model`, using
    validation predictions/labels. `model` is wrapped in
    sklearn.frozen.FrozenEstimator, whose .fit() is a deliberate no-op, so
    this call can only ever fit the calibration curves — it can never
    alter model.coef_ / model.intercept_ / model.classes_. This is the one
    function that must always receive the VALIDATION split, never the
    test split — see tests/test_calibration.py's data-flow test."""
    frozen = FrozenEstimator(model)
    calibrated = CalibratedClassifierCV(frozen, method=method)
    calibrated.fit(X_val, y_val)
    return calibrated


def multiclass_brier_score(y_true_onehot: np.ndarray, proba: np.ndarray) -> float:
    """Multiclass Brier score: (1/N) * sum_i sum_k (p_ik - y_ik)^2 over the
    full K-dimensional probability vector and one-hot true label (Brier,
    1950's original multi-category formulation) — NOT the binary
    top-label-vs-rest reduction. Lower is better; 0 is perfect."""
    return float(np.mean(np.sum((proba - y_true_onehot) ** 2, axis=1)))


def expected_calibration_error(
    confidences: np.ndarray, correct: np.ndarray, n_bins: int = N_ECE_BINS
) -> float:
    """TOP-LABEL Expected Calibration Error (Guo et al., 2017): bins the
    model's confidence in its OWN predicted class (max probability across
    all 6 classes) into `n_bins` equal-width bins over [0, 1], and computes
    the sample-weighted average gap between each bin's mean confidence and
    its actual accuracy. This is the top-label definition specifically —
    NOT a class-wise/multiclass ECE variant — documented here so the two
    are never conflated."""
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    n = len(confidences)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (confidences >= lo) & (confidences <= hi if i == n_bins - 1 else confidences < hi)
        count = int(mask.sum())
        if count == 0:
            continue
        bin_confidence = float(confidences[mask].mean())
        bin_accuracy = float(correct[mask].mean())
        ece += (count / n) * abs(bin_confidence - bin_accuracy)
    return float(ece)


def _classification_metrics(y_true, y_pred, class_labels) -> Dict[str, Any]:
    report = classification_report(
        y_true, y_pred, labels=class_labels, output_dict=True, zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=class_labels)
    return {
        "n": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_precision": float(report["macro avg"]["precision"]),
        "macro_recall": float(report["macro avg"]["recall"]),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "per_class": {
            cls: {
                "precision": report[cls]["precision"],
                "recall": report[cls]["recall"],
                "f1": report[cls]["f1-score"],
                "support": report[cls]["support"],
            }
            for cls in class_labels
        },
        "confusion_matrix": cm.tolist(),
        "confusion_matrix_labels": list(class_labels),
    }


def _reliability_curve(confidences: np.ndarray, correct: np.ndarray, n_bins: int = N_ECE_BINS):
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_centers, bin_accuracies, bin_counts = [], [], []
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (confidences >= lo) & (confidences <= hi if i == n_bins - 1 else confidences < hi)
        count = int(mask.sum())
        if count == 0:
            continue
        bin_centers.append(float(confidences[mask].mean()))
        bin_accuracies.append(float(correct[mask].mean()))
        bin_counts.append(count)
    return np.array(bin_centers), np.array(bin_accuracies), np.array(bin_counts)


def _load_split() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw_df = pd.read_csv(DATA_PATH)
    features_df = build_features(raw_df, keep_label=True)
    return train_val_test_split(features_df, label_col=LABEL_COL, random_state=RANDOM_STATE)


def calibrate_and_evaluate(
    raw_artifact_path: Path = RAW_ARTIFACT_PATH,
    calibrated_artifact_path: Path = CALIBRATED_ARTIFACT_PATH,
    metrics_path: Path = METRICS_PATH,
    confusion_matrix_plot_path: Path = CONFUSION_MATRIX_PLOT_PATH,
    calibration_plot_path: Path = CALIBRATION_PLOT_PATH,
) -> Dict[str, Any]:
    """Full Day 5 procedure. Loads the frozen Day 4 artifact (never
    retrains it), fits calibration on validation only, evaluates on test
    only, and writes the calibrated artifact + evaluation_metrics.json +
    both plots. Returns the metrics dict."""
    raw_artifact = load_artifact(raw_artifact_path)
    model = raw_artifact["model"]
    feature_columns = list(raw_artifact["feature_columns"])
    class_labels = list(raw_artifact["class_labels"])

    if feature_columns != list(FEATURE_COLUMNS):
        raise RuntimeError(
            "The frozen Day 4 artifact's feature_columns no longer match "
            "src.features.build_features.FEATURE_COLUMNS. Day 5 calibration "
            "requires the exact frozen Day 4 feature contract; retrain Day 4 "
            "(python -m src.model.training) before calibrating."
        )

    _, val_df, test_df = _load_split()
    X_val, y_val = val_df[FEATURE_COLUMNS], val_df[LABEL_COL]
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df[LABEL_COL]

    # Snapshot the frozen model's learned parameters BEFORE calibration, to
    # prove afterward that fitting the calibration layer never touched them.
    coef_before = model.coef_.copy()
    intercept_before = model.intercept_.copy()
    classes_before = list(model.classes_)

    calibrated_model = fit_calibration(model, X_val, y_val, method=CALIBRATION_METHOD)

    assert np.array_equal(coef_before, model.coef_), "Day 4 model coef_ changed by calibration!"
    assert np.array_equal(
        intercept_before, model.intercept_
    ), "Day 4 model intercept_ changed by calibration!"
    assert classes_before == list(model.classes_), "Day 4 model classes_ changed by calibration!"

    # --- Rigorous evaluation on the untouched test set, post-calibration ---
    calibrated_proba_test = calibrated_model.predict_proba(X_test)
    calibrated_pred_test = calibrated_model.classes_[calibrated_proba_test.argmax(axis=1)]
    raw_proba_test = model.predict_proba(X_test)  # for the calibration-plot comparison only

    test_metrics = _classification_metrics(y_test, calibrated_pred_test, class_labels)

    # One-hot encode y_test in the SAME class order as calibrated_model.classes_.
    class_index = {c: i for i, c in enumerate(calibrated_model.classes_)}
    y_test_onehot = np.zeros((len(y_test), len(class_labels)))
    for row_i, label in enumerate(y_test):
        y_test_onehot[row_i, class_index[label]] = 1.0

    brier_calibrated = multiclass_brier_score(y_test_onehot, calibrated_proba_test)
    brier_raw = multiclass_brier_score(y_test_onehot, raw_proba_test)

    calibrated_confidence = calibrated_proba_test.max(axis=1)
    calibrated_correct = (calibrated_pred_test == y_test.to_numpy()).astype(float)
    ece_calibrated = expected_calibration_error(calibrated_confidence, calibrated_correct)

    raw_pred_test = model.classes_[raw_proba_test.argmax(axis=1)]
    raw_confidence = raw_proba_test.max(axis=1)
    raw_correct = (raw_pred_test == y_test.to_numpy()).astype(float)
    ece_raw = expected_calibration_error(raw_confidence, raw_correct)

    # --- Persist the calibrated artifact (separate from the raw one) -----
    calibrated_artifact = {
        "calibrated_model": calibrated_model,
        "model_version": CALIBRATED_MODEL_VERSION,
        "base_model_version": raw_artifact["model_version"],
        "calibration_method": CALIBRATION_METHOD,
        "calibration_sample_count": int(len(val_df)),
        "feature_columns": feature_columns,
        "class_labels": class_labels,
        "random_state": RANDOM_STATE,
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_artifact(calibrated_artifact, calibrated_artifact_path)

    # --- Machine-readable metrics artifact --------------------------------
    metrics = {
        "model_version": CALIBRATED_MODEL_VERSION,
        "base_model_version": raw_artifact["model_version"],
        "calibration_method": CALIBRATION_METHOD,
        "calibration_sample_count": int(len(val_df)),
        "test_sample_count": int(len(test_df)),
        "class_labels": class_labels,
        "feature_count": len(feature_columns),
        "test_evaluation": test_metrics,
        "calibration_metrics": {
            "multiclass_brier_score_calibrated": brier_calibrated,
            "multiclass_brier_score_raw": brier_raw,
            "ece_top_label_calibrated": ece_calibrated,
            "ece_top_label_raw": ece_raw,
            "ece_definition": "top-label (max-probability) confidence, "
            f"{N_ECE_BINS} equal-width bins over [0, 1]",
            "brier_definition": "multiclass Brier score over the full "
            "K-dimensional probability vector vs. one-hot true label",
        },
        "note": "Calibration was fit on the validation split ONLY; the test "
        "split above was never used for calibration fitting, model "
        "fitting, or method selection.",
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    _plot_confusion_matrix(test_metrics["confusion_matrix"], class_labels, confusion_matrix_plot_path)
    _plot_calibration(
        raw_confidence, raw_correct, calibrated_confidence, calibrated_correct, calibration_plot_path
    )

    return metrics


def _plot_confusion_matrix(cm, class_labels, out_path: Path) -> None:
    cm = np.array(cm)
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(class_labels)))
    ax.set_yticks(range(len(class_labels)))
    ax.set_xticklabels(class_labels, rotation=45, ha="right")
    ax.set_yticklabels(class_labels)
    ax.set_xlabel("Predicted root cause")
    ax.set_ylabel("Actual root cause")
    ax.set_title("Recovery Guardian — Day 5 Test-Set Confusion Matrix\n(calibrated model predictions)")
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(
                j, i, str(cm[i, j]), ha="center", va="center",
                color="white" if cm[i, j] > cm.max() / 2 else "black",
            )
    fig.colorbar(im, ax=ax, label="count")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_calibration(raw_conf, raw_correct, cal_conf, cal_correct, out_path: Path) -> None:
    raw_centers, raw_acc, raw_counts = _reliability_curve(raw_conf, raw_correct)
    cal_centers, cal_acc, cal_counts = _reliability_curve(cal_conf, cal_correct)

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="perfect calibration")
    ax.plot(raw_centers, raw_acc, marker="o", label="raw (uncalibrated)", color="tab:orange")
    ax.plot(cal_centers, cal_acc, marker="o", label="calibrated (sigmoid)", color="tab:blue")
    ax.set_xlabel("Mean predicted confidence (top-label, binned)")
    ax.set_ylabel("Observed accuracy in bin")
    ax.set_title(
        "Recovery Guardian — Day 5 Reliability Diagram (test set)\n"
        "Top-label confidence vs. accuracy, raw vs. calibrated"
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    result = calibrate_and_evaluate()
    print(json.dumps(result, indent=2))
