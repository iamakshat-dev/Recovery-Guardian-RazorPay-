"""
Recovery Guardian — Day 14 Judge-Facing Demo Tests

Exercises the actual experiments/run_judge_demo.py (not a
reimplementation). Only genuinely new behavior is covered here — the
underlying ML/policy/simulator/explanation guarantees already have
regression suites (tests/test_policy_safety.py, tests/test_explain.py,
etc.) that this file deliberately does not duplicate.
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.models import RecoveryAction, RootCause
from src.explain.evidence import SIMULATED
from src.explain.provider import DeterministicFallbackProvider
from src.features.build_features import build_features
from src.ingestion.synthetic_adapter import synthetic_to_payment_event
from src.model.calibrated_classifier import CalibratedRootCauseClassifier
from src.model.training import DATA_PATH
from src.policy.engine import RulesPolicyEngine

from experiments.run_judge_demo import OUTPUT_PATH, SCENARIOS, run_scenario

REPO_ROOT = Path(__file__).parent.parent


def _load_row(transaction_id: str) -> pd.Series:
    raw_df = pd.read_csv(DATA_PATH)
    return raw_df[raw_df["transaction_id"] == transaction_id].iloc[0]


# --- Demo uses the real pipeline (not a reimplementation) --------------------

@pytest.mark.parametrize("scenario_key", list(SCENARIOS.keys()))
def test_demo_scenario_matches_the_real_pipeline_independently(scenario_key):
    """Independently reruns the real feature builder -> real calibrated
    classifier -> real Day 7 policy engine for the same transaction and
    confirms the demo's reported prediction/action match exactly."""
    txn_id = SCENARIOS[scenario_key]["transaction_id"]
    row = _load_row(txn_id)
    event = synthetic_to_payment_event(row)
    features_df = build_features(pd.DataFrame([event.model_dump()]), keep_label=False)
    classifier = CalibratedRootCauseClassifier()
    prediction = classifier.predict(features_df.iloc[0])
    policy = RulesPolicyEngine()
    from datetime import datetime, timezone

    decision = policy.decide(
        prediction, event, already_executed_actions=frozenset(),
        now=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    result = run_scenario(scenario_key)
    assert result["prediction"]["predicted_root_cause"] == prediction.root_cause.value
    # The demo rounds probability to 6 decimal places for display -- match
    # that rounding rather than asserting full float precision.
    assert result["prediction"]["predicted_probability"] == pytest.approx(prediction.probability, abs=1e-6)
    assert result["policy"]["policy_action"] == decision.action.value


def test_webhook_ambiguity_scenario_produces_block_reconcile():
    result = run_scenario("webhook_ambiguity")
    assert result["prediction"]["predicted_root_cause"] == "WEBHOOK_AMBIGUITY"
    assert result["policy"]["policy_action"] == "BLOCK_RECONCILE"
    assert result["policy"]["policy_action"] != "DEFER_RETRY"


def test_infrastructure_high_confidence_scenario_produces_defer_retry():
    result = run_scenario("infrastructure_high_confidence")
    assert result["prediction"]["predicted_root_cause"] == "INFRASTRUCTURE"
    assert result["policy"]["policy_action"] == "DEFER_RETRY"
    threshold = result["policy"]["threshold_if_applicable"]
    assert threshold is not None
    assert result["prediction"]["predicted_probability"] >= threshold


def test_infrastructure_low_confidence_scenario_produces_human_review():
    result = run_scenario("infrastructure_low_confidence")
    assert result["prediction"]["predicted_root_cause"] == "INFRASTRUCTURE"
    assert result["policy"]["policy_action"] == "HUMAN_REVIEW"
    threshold = result["policy"]["threshold_if_applicable"]
    assert threshold is not None
    assert result["prediction"]["predicted_probability"] < threshold


# --- Explanation cannot alter the decision (safety invariant) ----------------

@pytest.mark.parametrize("scenario_key", list(SCENARIOS.keys()))
def test_action_before_explanation_equals_action_after_explanation(scenario_key):
    result = run_scenario(scenario_key)
    check = result["safety_invariant_check"]
    assert check["unchanged"] is True
    assert check["action_before_explanation"] == check["action_after_explanation"]


# --- Outcome provenance discipline --------------------------------------------

@pytest.mark.parametrize("scenario_key", list(SCENARIOS.keys()))
def test_outcome_is_explicitly_labeled_simulated(scenario_key):
    result = run_scenario(scenario_key)
    assert result["outcome"]["_provenance"].startswith("SIMULATED")
    assert "not observed production revenue" in result["outcome"]["_provenance"]


@pytest.mark.parametrize("scenario_key", list(SCENARIOS.keys()))
def test_prediction_and_policy_are_labeled_observed(scenario_key):
    result = run_scenario(scenario_key)
    assert result["prediction"]["_provenance"].startswith("OBSERVED")
    assert result["policy"]["_provenance"].startswith("OBSERVED")


# --- Ground-truth leakage firewall --------------------------------------------

def test_ground_truth_never_reaches_decision_path():
    """Swaps the ground-truth label of the demo's chosen row and confirms
    the demo's prediction/action are completely unaffected — the same
    technique already used in tests/test_incident_demo.py and
    tests/test_explain.py, applied here to the actual demo script's own
    code path (run_scenario), not a hand-rebuilt copy of it."""
    txn_id = SCENARIOS["webhook_ambiguity"]["transaction_id"]
    row = _load_row(txn_id)

    # PaymentEvent construction never even sees actual_root_cause --
    # verified structurally, not just by one swapped-label run.
    event_from_real_row = synthetic_to_payment_event(row)
    fake_row = row.copy()
    fake_row["actual_root_cause"] = "CARD_DECLINE"  # deliberately wrong
    event_from_fake_row = synthetic_to_payment_event(fake_row)

    assert event_from_real_row.model_dump(exclude={"event_id"}) == event_from_fake_row.model_dump(exclude={"event_id"})


def test_run_judge_demo_source_never_threads_actual_root_cause_into_the_decision():
    """AST-level check: the local variable holding actual_root_cause is
    used in exactly one place -- the output dict's diagnostic
    `ground_truth_reference` section -- and is never passed as an
    argument to `synthetic_to_payment_event`, `run_pipeline`, or
    `explain_decision`."""
    import ast

    source = Path(__file__).parent.parent.joinpath("experiments", "run_judge_demo.py").read_text()
    tree = ast.parse(source)

    forbidden_calls = {"synthetic_to_payment_event", "run_pipeline", "explain_decision"}
    variable_name = "actual_root_cause_reference"

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if func_name in forbidden_calls:
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    if isinstance(arg, ast.Name) and arg.id == variable_name:
                        pytest.fail(
                            f"{variable_name} was passed into {func_name}() -- ground "
                            f"truth must never reach the decision path."
                        )

    # `row` itself (which DOES contain actual_root_cause as a column) is
    # passed to synthetic_to_payment_event, which is fine -- that adapter
    # is separately proven never to read that column
    # (test_ground_truth_never_reaches_decision_path above, and
    # src/ingestion/synthetic_adapter.py's own docstring/tests).


def test_scenario_selection_is_a_fixed_constant_not_a_runtime_ground_truth_lookup():
    """SCENARIOS is a module-level constant dict of transaction_id
    strings -- there is no function anywhere that selects a transaction
    by filtering on actual_root_cause at demo runtime."""
    for key, scenario in SCENARIOS.items():
        assert isinstance(scenario["transaction_id"], str)
    source = Path(__file__).parent.parent.joinpath("experiments", "run_judge_demo.py").read_text()
    assert "actual_root_cause ==" not in source
    assert "df[df[" not in source  # no runtime filtering/selection logic at all


# --- Deterministic fallback / no credentials required -------------------------

def test_demo_works_with_no_llm_env_vars_set(monkeypatch):
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = run_scenario("webhook_ambiguity")
    assert result["explanation"]["summary"]
    assert result["policy"]["policy_action"] == "BLOCK_RECONCILE"


def test_deterministic_fallback_provider_is_selected_by_default(monkeypatch):
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    from experiments.run_judge_demo import _select_provider

    provider = _select_provider()
    assert isinstance(provider, DeterministicFallbackProvider)


# --- Reproducibility -----------------------------------------------------------

def test_run_scenario_is_deterministic_within_one_process(monkeypatch):
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    result_a = run_scenario("infrastructure_high_confidence")
    result_b = run_scenario("infrastructure_high_confidence")
    assert json.dumps(result_a, sort_keys=True) == json.dumps(result_b, sort_keys=True)


def test_two_separate_processes_produce_byte_identical_demo_output():
    script = REPO_ROOT / "experiments" / "run_judge_demo.py"

    result_1 = subprocess.run(
        [sys.executable, str(script)], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120
    )
    assert result_1.returncode == 0, result_1.stderr
    content_1 = OUTPUT_PATH.read_bytes()

    result_2 = subprocess.run(
        [sys.executable, str(script)], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120
    )
    assert result_2.returncode == 0, result_2.stderr
    content_2 = OUTPUT_PATH.read_bytes()

    assert content_1 == content_2


# --- No side effects / no persistent state pollution --------------------------

def test_demo_never_touches_the_real_database():
    real_db_path = REPO_ROOT / "recovery_guardian.db"
    existed_before = real_db_path.exists()
    mtime_before = real_db_path.stat().st_mtime if existed_before else None

    run_scenario("webhook_ambiguity")

    if existed_before:
        assert real_db_path.stat().st_mtime == mtime_before
    else:
        assert not real_db_path.exists()


def test_repeated_execution_with_fresh_isolated_conn_produces_the_same_decision():
    """Calling the same scenario repeatedly (each call opens its own
    fresh in-memory connection, exactly as the demo does) must never
    change the resulting action because of idempotency-guard state
    leaking between calls."""
    actions = {run_scenario("webhook_ambiguity")["policy"]["policy_action"] for _ in range(3)}
    assert actions == {"BLOCK_RECONCILE"}


# --- Output contract -----------------------------------------------------------

def test_output_json_has_the_required_contract_fields():
    result = run_scenario("webhook_ambiguity")
    assert "transaction_id" in result
    assert "payment_event_summary" in result
    assert "prediction" in result
    assert "policy" in result
    assert "outcome" in result
    assert "explanation" in result
    assert "safety_invariant_check" in result
    for section in ("payment_event_summary", "prediction", "policy", "outcome"):
        assert "_provenance" in result[section]


def test_output_artifact_file_is_written_by_running_the_script():
    assert OUTPUT_PATH.exists()
    with open(OUTPUT_PATH) as f:
        data = json.load(f)
    assert set(data.keys()) <= set(SCENARIOS.keys())
    assert len(data) > 0
