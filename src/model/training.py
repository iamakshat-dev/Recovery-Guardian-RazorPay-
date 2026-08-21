"""
Recovery Guardian — Day 4 Model Training

Trains the real Logistic Regression root-cause classifier and persists it
as the artifact src/model/classifier.py loads for inference.

Run:
    python -m src.model.training

Pipeline:
    data/synthetic_events.csv
        -> build_features(..., keep_label=True)      [existing, unmodified]
        -> X = features_df[FEATURE_COLUMNS]            [authoritative schema]
        -> y = features_df["actual_root_cause"]
        -> train_val_test_split(random_state=42)        [70/15/15, stratified]
        -> LogisticRegression(random_state=42).fit(X_train, y_train)
        -> evaluate on validation + test
        -> save_artifact(...)

Does NOT perform calibration (Day 6) and does NOT claim the resulting
probabilities are calibrated — these are raw LogisticRegression.predict_proba()
outputs, reported as such.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from src.features.build_features import FEATURE_COLUMNS, LABEL_COL, build_features
from src.model.artifacts import DEFAULT_ARTIFACT_PATH, save_artifact
from src.model.splitting import train_val_test_split

MODEL_VERSION = "root-cause-logreg-v1"
RANDOM_STATE = 42

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "synthetic_events.csv"
ARTIFACT_PATH = DEFAULT_ARTIFACT_PATH
METRICS_PATH = (
    Path(__file__).parent.parent.parent / "artifacts" / "root_cause_classifier_metrics.json"
)


def _evaluate(model: LogisticRegression, X: pd.DataFrame, y: pd.Series, class_labels, split_name: str) -> Dict[str, Any]:
    y_pred = model.predict(X)
    report = classification_report(
        y, y_pred, labels=class_labels, output_dict=True, zero_division=0
    )
    cm = confusion_matrix(y, y_pred, labels=class_labels)
    return {
        "split": split_name,
        "n": int(len(y)),
        "accuracy": float(accuracy_score(y, y_pred)),
        "macro_f1": float(f1_score(y, y_pred, average="macro", zero_division=0)),
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


def train(
    data_path: Path = DATA_PATH,
    artifact_path: Path = ARTIFACT_PATH,
    metrics_path: Path = METRICS_PATH,
    random_state: int = RANDOM_STATE,
) -> Dict[str, Any]:
    """Train the Logistic Regression root-cause classifier end to end and
    persist both the model artifact and an evaluation metrics report.
    Returns the metrics dict (also written to `metrics_path`)."""
    raw_df = pd.read_csv(data_path)
    features_df = build_features(raw_df, keep_label=True)

    train_df, val_df, test_df = train_val_test_split(
        features_df, label_col=LABEL_COL, random_state=random_state
    )

    X_train, y_train = train_df[FEATURE_COLUMNS], train_df[LABEL_COL]
    X_val, y_val = val_df[FEATURE_COLUMNS], val_df[LABEL_COL]
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df[LABEL_COL]

    model = LogisticRegression(max_iter=1000, random_state=random_state)
    model.fit(X_train, y_train)

    class_labels = list(model.classes_)

    validation_metrics = _evaluate(model, X_val, y_val, class_labels, "validation")
    test_metrics = _evaluate(model, X_test, y_test, class_labels, "test")

    artifact = {
        "model": model,
        "model_version": MODEL_VERSION,
        "feature_columns": list(FEATURE_COLUMNS),
        "class_labels": class_labels,
        "random_state": random_state,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "train_rows": int(len(train_df)),
        "val_rows": int(len(val_df)),
        "test_rows": int(len(test_df)),
    }
    save_artifact(artifact, artifact_path)

    metrics = {
        "model_version": MODEL_VERSION,
        "random_state": random_state,
        "train_rows": int(len(train_df)),
        "val_rows": int(len(val_df)),
        "test_rows": int(len(test_df)),
        "class_labels": class_labels,
        "validation": validation_metrics,
        "test": test_metrics,
        "note": "Raw LogisticRegression.predict_proba() probabilities. "
        "NOT calibrated — calibration is Day 6 work.",
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    return metrics


if __name__ == "__main__":
    result = train()
    print(json.dumps(result, indent=2))
