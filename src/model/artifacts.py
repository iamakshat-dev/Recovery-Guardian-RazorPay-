"""
Recovery Guardian — Model Artifact Persistence (Day 4)

Isolates "how a trained model + its metadata get saved and loaded" from
both training (src/model/training.py) and inference
(src/model/classifier.py), so neither has to know the on-disk artifact
format directly. Uses joblib, the standard format for persisting
scikit-learn estimators.

The persisted artifact is a single dict containing, at minimum:
    model            - the fitted sklearn estimator
    model_version     - e.g. "root-cause-logreg-v1"
    feature_columns  - the EXACT ordered list the model was trained on
                        (src.features.build_features.FEATURE_COLUMNS at
                        training time)
    class_labels      - the ordered class labels the model predicts over
    random_state      - the seed used for training/splitting

It deliberately never includes the raw training dataset.
"""

from pathlib import Path
from typing import Any, Dict

import joblib

DEFAULT_ARTIFACT_PATH = (
    Path(__file__).parent.parent.parent / "artifacts" / "root_cause_classifier.joblib"
)


def save_artifact(artifact: Dict[str, Any], artifact_path: Path = DEFAULT_ARTIFACT_PATH) -> None:
    """Persist a trained-model artifact dict to disk, creating the parent
    directory if needed."""
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, artifact_path)


def load_artifact(artifact_path: Path = DEFAULT_ARTIFACT_PATH) -> Dict[str, Any]:
    """Load a previously-saved artifact dict. Raises FileNotFoundError with
    a plain message if nothing has been trained yet — callers that want a
    more actionable message (e.g. src.model.classifier) should catch this
    and re-raise their own error."""
    if not artifact_path.exists():
        raise FileNotFoundError(f"No model artifact found at {artifact_path}")
    return joblib.load(artifact_path)
