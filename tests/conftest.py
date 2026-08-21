"""
Recovery Guardian — shared pytest fixtures.

Day 4 introduced a production classifier that requires a trained model
artifact to exist before `run_pipeline()`/`RootCauseLogRegClassifier()` can
be used. To keep `pytest -q` reproducible on a fresh clone (no manual
`python -m src.model.training` step required first) and hermetic (never
writing into the developer's real artifacts/ directory), this fixture
trains one real model, once per test session, into a session-scoped temp
directory, and points src.model.classifier's default ARTIFACT_PATH at it
for the duration of the test run.
"""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))


@pytest.fixture(scope="session", autouse=True)
def _day4_trained_model_artifact(tmp_path_factory):
    import src.model.classifier as classifier_module
    from src.model.training import DATA_PATH, train

    artifact_dir = tmp_path_factory.mktemp("day4_model_artifacts")
    artifact_path = artifact_dir / "root_cause_classifier.joblib"
    metrics_path = artifact_dir / "root_cause_classifier_metrics.json"

    train(
        data_path=DATA_PATH,
        artifact_path=artifact_path,
        metrics_path=metrics_path,
        random_state=42,
    )

    original_path = classifier_module.ARTIFACT_PATH
    classifier_module.ARTIFACT_PATH = artifact_path
    yield artifact_path
    classifier_module.ARTIFACT_PATH = original_path
