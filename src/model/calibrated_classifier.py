"""
Recovery Guardian — Day 5 Calibrated Root-Cause Classifier (production)

Loads the persisted CALIBRATED artifact (produced by
`python -m src.model.calibrate`) and serves predictions through the exact
same RootCausePrediction contract as both the Day 3 placeholder and the
Day 4 raw classifier (src/model/classifier.py), so the pipeline swap
required no redesign — only an import change in src/pipeline/pipeline.py.

This module is deliberately separate from src/model/classifier.py: Day 4's
`RootCauseLogRegClassifier` (the frozen raw model) is left completely
untouched and remains independently loadable/testable. This class only
adds the calibration layer on top; it does not modify, retrain, or replace
anything Day 4 produced.

Same two guarantees as the Day 4 classifier, applied to the calibrated
artifact:
1. Missing artifact -> ModelArtifactNotFoundError.
2. Feature-schema drift -> FeatureSchemaMismatchError.
"""

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from src.domain.models import RootCause, RootCausePrediction
from src.features.build_features import FEATURE_COLUMNS
from src.model.artifacts import load_artifact
from src.model.calibrate import CALIBRATED_ARTIFACT_PATH

# Module-level default, looked up dynamically (not bound as a function
# default) inside __init__ so it can be monkeypatched per-test — mirrors
# src/model/classifier.py's ARTIFACT_PATH pattern exactly.
ARTIFACT_PATH = CALIBRATED_ARTIFACT_PATH


class ModelArtifactNotFoundError(RuntimeError):
    """Raised when no calibrated model artifact exists at the expected path."""


class FeatureSchemaMismatchError(RuntimeError):
    """Raised when the live FEATURE_COLUMNS no longer matches the schema
    the calibrated model was built against."""


class CalibratedRootCauseClassifier:
    """Production Day 5 classifier. Loads the calibrated artifact once at
    construction, validates the feature schema before ever predicting, and
    exposes the same `.predict(features) -> RootCausePrediction` contract
    used by the Day 3 placeholder and the Day 4 raw classifier."""

    def __init__(self, artifact_path: Path = None):
        if artifact_path is None:
            artifact_path = ARTIFACT_PATH  # dynamic global lookup, not a bound default

        try:
            artifact = load_artifact(artifact_path)
        except FileNotFoundError as exc:
            raise ModelArtifactNotFoundError(
                f"No calibrated model artifact found at {artifact_path}. "
                f"Run `python -m src.model.calibrate` to fit and persist one "
                f"before running inference. The pipeline will not silently "
                f"fall back to the Day 4 raw classifier."
            ) from exc

        persisted_columns = list(artifact["feature_columns"])
        current_columns = list(FEATURE_COLUMNS)
        if persisted_columns != current_columns:
            raise FeatureSchemaMismatchError(
                "The feature schema this calibrated model was built against "
                "no longer matches src.features.build_features.FEATURE_COLUMNS.\n"
                f"Trained on ({len(persisted_columns)} cols): {persisted_columns}\n"
                f"Current    ({len(current_columns)} cols): {current_columns}\n"
                "Retrain Day 4 and re-run `python -m src.model.calibrate` "
                "before this can serve predictions."
            )

        self._model = artifact["calibrated_model"]
        self._model_version = artifact["model_version"]
        self._feature_columns = persisted_columns
        self._class_labels = list(artifact["class_labels"])

    def predict(self, features: Mapping[str, Any]) -> RootCausePrediction:
        """Args:
            features: one row of the feature-builder output (must contain
                `transaction_id`). Only the persisted, ordered
                FEATURE_COLUMNS are ever passed into the model.
        """
        transaction_id = str(features["transaction_id"])

        row = pd.DataFrame([{col: features[col] for col in self._feature_columns}])
        probabilities = self._model.predict_proba(row)[0]

        best_idx = int(probabilities.argmax())
        predicted_label = self._model.classes_[best_idx]
        predicted_probability = float(probabilities[best_idx])

        return RootCausePrediction(
            transaction_id=transaction_id,
            root_cause=RootCause(predicted_label),
            probability=predicted_probability,
            model_version=self._model_version,
        )
