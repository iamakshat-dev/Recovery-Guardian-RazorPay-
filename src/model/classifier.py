"""
Recovery Guardian — Day 4 Real Root-Cause Classifier (production)

Loads the persisted Logistic Regression artifact (produced by
`python -m src.model.training`) and serves predictions through the exact
same RootCausePrediction contract the Day 3 placeholder used
(src/model/placeholder_classifier.py), so the pipeline swap required no
redesign — only an import change in src/pipeline/pipeline.py.

Two guarantees this module enforces, deliberately without silent fallback:

1. Missing artifact -> ModelArtifactNotFoundError. Never silently
   instantiates the Day 3 placeholder instead.
2. Feature-schema drift (the live FEATURE_COLUMNS no longer matches what
   the persisted model was trained on) -> FeatureSchemaMismatchError.
   Never silently reorders, pads, or truncates features to make a stale
   model "work" — that would be exactly the kind of train/serve skew this
   check exists to catch.
"""

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from src.domain.models import RootCause, RootCausePrediction
from src.features.build_features import FEATURE_COLUMNS
from src.model.artifacts import DEFAULT_ARTIFACT_PATH, load_artifact

# Module-level default, looked up dynamically (not bound as a function
# default) inside __init__ so it can be monkeypatched per-test without
# needing to change every call site — see tests/conftest.py.
ARTIFACT_PATH = DEFAULT_ARTIFACT_PATH


class ModelArtifactNotFoundError(RuntimeError):
    """Raised when no trained model artifact exists at the expected path."""


class FeatureSchemaMismatchError(RuntimeError):
    """Raised when the live FEATURE_COLUMNS no longer matches the schema
    the persisted model was trained against. The model must be retrained;
    this is never silently reconciled."""


class RootCauseLogRegClassifier:
    """Production Day 4 classifier. Loads the trained artifact once at
    construction, validates the feature schema before ever predicting, and
    exposes the same `.predict(features) -> RootCausePrediction` contract
    used by the Day 3 placeholder."""

    def __init__(self, artifact_path: Path = None):
        if artifact_path is None:
            artifact_path = ARTIFACT_PATH  # dynamic global lookup, not a bound default

        try:
            artifact = load_artifact(artifact_path)
        except FileNotFoundError as exc:
            raise ModelArtifactNotFoundError(
                f"No trained model artifact found at {artifact_path}. "
                f"Run `python -m src.model.training` to train and persist one "
                f"before running inference. The pipeline will not silently "
                f"fall back to the Day 3 placeholder classifier."
            ) from exc

        persisted_columns = list(artifact["feature_columns"])
        current_columns = list(FEATURE_COLUMNS)
        if persisted_columns != current_columns:
            raise FeatureSchemaMismatchError(
                "The feature schema this model was trained against no longer "
                "matches src.features.build_features.FEATURE_COLUMNS.\n"
                f"Trained on ({len(persisted_columns)} cols): {persisted_columns}\n"
                f"Current    ({len(current_columns)} cols): {current_columns}\n"
                "The model must be retrained against the current feature "
                "schema (`python -m src.model.training`) before it can serve "
                "predictions. Features are never silently reordered, padded, "
                "or dropped to paper over schema drift."
            )

        self._model = artifact["model"]
        self._model_version = artifact["model_version"]
        self._feature_columns = persisted_columns
        self._class_labels = list(artifact["class_labels"])

    def predict(self, features: Mapping[str, Any]) -> RootCausePrediction:
        """Args:
            features: one row of the feature-builder output (must contain
                `transaction_id`). Only the persisted, ordered
                FEATURE_COLUMNS are ever passed into the model — never
                `transaction_id`, never `actual_root_cause`.
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
