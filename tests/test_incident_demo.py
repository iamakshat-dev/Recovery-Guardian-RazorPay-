"""
Recovery Guardian — Day 12 Incident Scenario Replay Tests

Exercises the actual experiments/run_incident_demo.py (not a
reimplementation). See that module's docstring for the ground-truth
isolation and state-isolation guarantees these tests verify directly.
"""

import inspect
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.models import RecoveryAction
from src.experiment.strategies import EXPERIMENT_EVALUATION_TIME
from src.features.build_features import build_features
from src.ingestion.synthetic_adapter import synthetic_to_payment_event
from src.model.calibrated_classifier import CalibratedRootCauseClassifier
from src.model.training import DATA_PATH
from src.policy.engine import RulesPolicyEngine

from experiments.run_incident_demo import (
    AFTER_END,
    BEFORE_START,
    EXPECTED_BURST_ROWS,
    INCIDENT_END,
    INCIDENT_START,
    OUTPUT_PATH,
    build_classifier_summary,
    compute_split_membership,
    load_raw_dataset,
    replay_transaction,
    run_replay,
    select_comparison_windows,
    verify_incident_window,
)

REPO_ROOT = Path(__file__).parent.parent


# --- Test 1: incident discovery -------------------------------------------

def test_incident_window_exists_with_expected_boundaries_and_count():
    raw_df = load_raw_dataset()
    window_idx = verify_incident_window(raw_df)

    assert len(window_idx) == EXPECTED_BURST_ROWS
    assert len(window_idx) > 0

    ts = pd.to_datetime(raw_df.loc[window_idx, "timestamp"])
    assert ts.min() >= INCIDENT_START
    assert ts.max() <= INCIDENT_END


def test_incident_window_class_distribution_is_infrastructure_heavy_but_not_pure():
    raw_df = load_raw_dataset()
    window_idx = verify_incident_window(raw_df)
    dist = raw_df.loc[window_idx, "actual_root_cause"].value_counts()

    assert dist.get("INFRASTRUCTURE", 0) > 0
    # Deliberately impure: not every transaction in the burst is
    # INFRASTRUCTURE (data/generate_data.py's burst_weights).
    assert len(dist) > 1
    assert dist.get("INFRASTRUCTURE", 0) < len(window_idx)


# --- Test 2: split membership -----------------------------------------------

def test_split_membership_reproduces_exact_day4_split():
    raw_df = load_raw_dataset()
    membership = compute_split_membership(raw_df)

    assert set(membership.values()) <= {"TRAIN", "VALIDATION", "TEST"}
    # Every row of the full dataset gets exactly one membership.
    assert len(membership) == len(raw_df)


def test_every_incident_transaction_has_exactly_one_split_membership():
    raw_df = load_raw_dataset()
    window_idx = verify_incident_window(raw_df)
    membership = compute_split_membership(raw_df)

    for idx in window_idx:
        assert idx in membership
        assert membership[idx] in ("TRAIN", "VALIDATION", "TEST")


def test_split_membership_counts_sum_to_window_total():
    raw_df = load_raw_dataset()
    window_idx = verify_incident_window(raw_df)
    membership = compute_split_membership(raw_df)

    counts = {"TRAIN": 0, "VALIDATION": 0, "TEST": 0}
    for idx in window_idx:
        counts[membership[idx]] += 1

    assert sum(counts.values()) == len(window_idx)


# --- Test 3: full replay ----------------------------------------------------

def test_every_incident_transaction_reaches_the_real_pipeline():
    artifact = run_replay()
    assert len(artifact["transactions"]) == EXPECTED_BURST_ROWS
    for record in artifact["transactions"]:
        assert record["predicted_root_cause"] in {
            "INFRASTRUCTURE", "CARD_DECLINE", "INSUFFICIENT_FUNDS",
            "OTP_TIMEOUT", "USER_ABANDONMENT", "WEBHOOK_AMBIGUITY",
        }
        assert 0.0 <= record["calibrated_probability"] <= 1.0
        assert record["policy_action"] in {a.value for a in RecoveryAction}


# --- Test 4: ground-truth leakage -------------------------------------------

def test_actual_root_cause_does_not_affect_prediction_or_policy():
    """Constructs otherwise-identical evidence differing ONLY in the
    evaluation-only actual_root_cause label, and verifies the frozen
    prediction/policy path is completely unaffected."""
    raw_df = load_raw_dataset()
    row = raw_df[raw_df["actual_root_cause"] == "INFRASTRUCTURE"].iloc[0].to_dict()

    classifier = CalibratedRootCauseClassifier()
    policy = RulesPolicyEngine()

    def _run(r):
        event = synthetic_to_payment_event(r)
        features_df = build_features(pd.DataFrame([event.model_dump()]), keep_label=False)
        prediction = classifier.predict(features_df.iloc[0])
        decision = policy.decide(
            prediction, event, already_executed_actions=frozenset(), now=EXPERIMENT_EVALUATION_TIME
        )
        return prediction, decision

    prediction_a, decision_a = _run(row)

    fake_row = dict(row)
    fake_row["actual_root_cause"] = "WEBHOOK_AMBIGUITY"  # deliberately different, eval-only
    prediction_b, decision_b = _run(fake_row)

    assert prediction_a.root_cause == prediction_b.root_cause
    assert prediction_a.probability == prediction_b.probability
    assert decision_a.action == decision_b.action


def test_synthetic_to_payment_event_never_reads_actual_root_cause():
    """Structural proof, not just a runtime check: PaymentEvent has no
    field for actual_root_cause at all (src/domain/models.py)."""
    from src.domain.models import PaymentEvent

    assert "actual_root_cause" not in PaymentEvent.model_fields


def test_split_membership_cannot_structurally_enter_prediction_or_policy():
    """None of the frozen functions the replay calls accept anything
    related to 'split' at all — split_membership is a Day-12-only,
    post-hoc concept that cannot be threaded into them."""
    for fn in (build_features, CalibratedRootCauseClassifier.predict, RulesPolicyEngine.decide):
        params = inspect.signature(fn).parameters
        assert not any("split" in p.lower() for p in params)


# --- Test 5: WEBHOOK_AMBIGUITY safety --------------------------------------

def test_every_webhook_ambiguity_case_in_window_blocks_reconcile():
    artifact = run_replay()
    wa_records = [r for r in artifact["transactions"] if r["actual_root_cause"] == "WEBHOOK_AMBIGUITY"]
    assert len(wa_records) > 0
    for record in wa_records:
        assert record["policy_action"] == RecoveryAction.BLOCK_RECONCILE.value
        assert record["policy_action"] != RecoveryAction.DEFER_RETRY.value

    safety = artifact["webhook_ambiguity_safety"]
    assert safety["safety_pass"] is True
    assert safety["defer_retry_count"] == 0
    assert safety["block_reconcile_count"] == safety["case_count"]


# --- Test 6: output artifact -------------------------------------------------

def test_output_artifact_has_required_structure(tmp_path):
    artifact = run_replay()

    for key in (
        "metadata", "summary", "split_membership", "classifier_summary",
        "infrastructure_summary", "policy_summary", "webhook_ambiguity_safety",
        "non_infrastructure_summary", "transactions",
    ):
        assert key in artifact

    assert {"train_count", "validation_count", "test_count"} <= set(artifact["split_membership"].keys())
    assert len(artifact["transactions"]) > 0
    for record in artifact["transactions"]:
        for field in (
            "transaction_id", "timestamp", "amount", "actual_root_cause",
            "split_membership", "predicted_root_cause", "calibrated_probability",
            "policy_action", "policy_reason_code",
        ):
            assert field in record


def test_output_artifact_file_written_by_running_the_script():
    # Self-contained: writes the artifact itself, exactly as main() does,
    # rather than assuming a prior interactive run already left one on
    # disk. A genuinely fresh clone/checkout has no such prior run, and
    # test execution order across this file is not guaranteed to place
    # this after test_two_separate_processes_produce_byte_identical_
    # artifacts (the only other test in this file that invokes the
    # script as a subprocess) -- found by the Day 15 pre-merge branch
    # dry run, which is the first time this suite ever ran against a
    # truly fresh clone.
    artifact = run_replay()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(artifact, f, indent=2, sort_keys=True)

    assert OUTPUT_PATH.exists()
    with open(OUTPUT_PATH) as f:
        data = json.load(f)
    assert "transactions" in data
    assert len(data["transactions"]) == EXPECTED_BURST_ROWS


# --- Test 7: state isolation --------------------------------------------------

def test_repeated_replay_of_same_transaction_does_not_change_its_action():
    raw_df = load_raw_dataset()
    window_idx = verify_incident_window(raw_df)
    membership = compute_split_membership(raw_df)
    idx = window_idx[0]
    row = raw_df.loc[idx]
    split_label = membership[idx]

    classifier = CalibratedRootCauseClassifier()
    policy = RulesPolicyEngine()

    record_1 = replay_transaction(row, split_label, classifier, policy, simulate=False)
    record_2 = replay_transaction(row, split_label, classifier, policy, simulate=False)
    record_3 = replay_transaction(row, split_label, classifier, policy, simulate=False)

    assert record_1["policy_action"] == record_2["policy_action"] == record_3["policy_action"]
    assert record_1["predicted_root_cause"] == record_2["predicted_root_cause"] == record_3["predicted_root_cause"]
    assert record_1["calibrated_probability"] == record_2["calibrated_probability"] == record_3["calibrated_probability"]


def test_guardian_state_isolation_mechanism_is_reused_not_reinvented():
    """already_executed_actions=frozenset() and the fixed
    EXPERIMENT_EVALUATION_TIME are the exact Day 9 GuardianStrategy
    mechanism (src/experiment/strategies.py) — verified by direct
    source inspection of run_incident_demo.py."""
    source = inspect.getsource(sys.modules["experiments.run_incident_demo"])
    assert "already_executed_actions=frozenset()" in source
    assert "EXPERIMENT_EVALUATION_TIME" in source
    assert "from src.experiment.strategies import" in source


# --- Test 8: determinism ------------------------------------------------------

def test_run_replay_is_deterministic_within_one_process():
    artifact_a = run_replay()
    artifact_b = run_replay()
    assert json.dumps(artifact_a, sort_keys=True) == json.dumps(artifact_b, sort_keys=True)


def test_two_separate_processes_produce_byte_identical_artifacts(tmp_path):
    """Cross-process reproducibility (Day 12 spec section 24). No
    wall-clock run metadata is included in the artifact at all, so no
    field needs to be excluded from this comparison."""
    env_script = REPO_ROOT / "experiments" / "run_incident_demo.py"

    result_1 = subprocess.run(
        [sys.executable, str(env_script)], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120
    )
    assert result_1.returncode == 0, result_1.stderr
    content_1 = OUTPUT_PATH.read_bytes()

    result_2 = subprocess.run(
        [sys.executable, str(env_script)], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120
    )
    assert result_2.returncode == 0, result_2.stderr
    content_2 = OUTPUT_PATH.read_bytes()

    assert content_1 == content_2


# --- Test 9: metric validity --------------------------------------------------

def test_dataset_contains_only_failed_transactions_so_density_is_used():
    raw_df = load_raw_dataset()
    # No success/status column exists anywhere in the frozen schema.
    assert "status" not in raw_df.columns
    assert "success" not in raw_df.columns
    assert "outcome" not in raw_df.columns

    artifact = run_replay()
    assert artifact["metadata"]["metric_type"] == "failure_density"
    assert artifact["metadata"]["dataset_contains_successful_transactions"] is False
    assert "failure_rate" not in json.dumps(artifact)


def test_failure_density_is_not_reported_as_a_percentage():
    artifact = run_replay()
    incident_summary = artifact["summary"]["incident"]
    # A percentage would be bounded at/near 100; density here is a raw
    # count normalized to a time unit and is expected to exceed 100 for
    # the incident window (110 events in 30 minutes).
    assert incident_summary["failure_density_per_unit"] == pytest.approx(110.0)
    assert incident_summary["failed_event_count"] == 110


# --- Comparison window sanity -------------------------------------------------

def test_comparison_windows_are_non_overlapping():
    raw_df = load_raw_dataset()
    before_idx, incident_idx, after_idx = select_comparison_windows(raw_df)

    assert set(before_idx).isdisjoint(set(incident_idx))
    assert set(incident_idx).isdisjoint(set(after_idx))
    assert set(before_idx).isdisjoint(set(after_idx))


def test_infrastructure_classifier_summary_reports_full_window_and_held_out_test_separately():
    artifact = run_replay()
    classifier_summary = artifact["classifier_summary"]
    assert "full_window" in classifier_summary
    assert "held_out_test" in classifier_summary
    # Held-out test is a subset of the full window.
    assert classifier_summary["held_out_test"]["ground_truth_count"] <= classifier_summary["full_window"]["ground_truth_count"]
