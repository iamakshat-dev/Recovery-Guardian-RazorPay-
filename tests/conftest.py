"""
Recovery Guardian — shared pytest fixtures.

Day 4 introduced a production classifier that requires a trained model
artifact to exist before `run_pipeline()`/`RootCauseLogRegClassifier()` can
be used. Day 5 introduced a calibrated classifier on top of that, which
requires its own calibrated artifact. To keep `pytest -q` reproducible on
a fresh clone (no manual `python -m src.model.training` /
`python -m src.model.calibrate` steps required first) and hermetic (never
writing into the developer's real artifacts/ directory), this fixture
trains one real raw model AND fits calibration on top of it, once per test
session, into a session-scoped temp directory, and points both
src.model.classifier's and src.model.calibrated_classifier's default
ARTIFACT_PATH at them for the duration of the test run.
"""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))


@pytest.fixture(scope="session", autouse=True)
def _day4_and_day5_trained_model_artifacts(tmp_path_factory):
    import src.model.calibrated_classifier as calibrated_classifier_module
    import src.model.classifier as classifier_module
    from src.model.calibrate import calibrate_and_evaluate
    from src.model.training import DATA_PATH, train

    artifact_dir = tmp_path_factory.mktemp("day4_day5_model_artifacts")

    raw_artifact_path = artifact_dir / "root_cause_classifier.joblib"
    raw_metrics_path = artifact_dir / "root_cause_classifier_metrics.json"
    train(
        data_path=DATA_PATH,
        artifact_path=raw_artifact_path,
        metrics_path=raw_metrics_path,
        random_state=42,
    )

    calibrated_artifact_path = artifact_dir / "root_cause_classifier_calibrated.joblib"
    calibrated_metrics_path = artifact_dir / "evaluation_metrics.json"
    confusion_matrix_plot_path = artifact_dir / "confusion_matrix.png"
    calibration_plot_path = artifact_dir / "calibration_plot.png"
    calibrate_and_evaluate(
        raw_artifact_path=raw_artifact_path,
        calibrated_artifact_path=calibrated_artifact_path,
        metrics_path=calibrated_metrics_path,
        confusion_matrix_plot_path=confusion_matrix_plot_path,
        calibration_plot_path=calibration_plot_path,
    )

    original_raw_path = classifier_module.ARTIFACT_PATH
    original_calibrated_path = calibrated_classifier_module.ARTIFACT_PATH
    classifier_module.ARTIFACT_PATH = raw_artifact_path
    calibrated_classifier_module.ARTIFACT_PATH = calibrated_artifact_path
    yield {"raw": raw_artifact_path, "calibrated": calibrated_artifact_path}
    classifier_module.ARTIFACT_PATH = original_raw_path
    calibrated_classifier_module.ARTIFACT_PATH = original_calibrated_path
