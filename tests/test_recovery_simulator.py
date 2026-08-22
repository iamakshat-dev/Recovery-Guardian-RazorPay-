"""
Recovery Guardian — Day 8 Shared Counterfactual Estimator Tests

Exercises the actual estimate_outcome() (src/recovery/simulator.py), not a
bypassed/faked assertion.
"""

import inspect
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.models import RecoveryAction, RecoveryOutcome, RootCause
from src.recovery.evidence import RecoveryEvidence
from src.recovery.simulator import estimate_outcome, probability_of_recovery, unrecovered_amount

ALL_ACTIONS = list(RecoveryAction)


def make_evidence(**overrides) -> RecoveryEvidence:
    base = dict(
        transaction_id="txn_sim_0001",
        amount=1000.0,
        root_cause=RootCause.CARD_DECLINE,
        probability=0.9,
        retry_count=0,
        incident_active=False,
    )
    base.update(overrides)
    return RecoveryEvidence(**base)


# --- 1/3: accepts every action, produces a valid RecoveryOutcome ------------

@pytest.mark.parametrize("action", ALL_ACTIONS)
def test_estimator_accepts_every_recovery_action_and_returns_valid_outcome(action):
    evidence = make_evidence()
    outcome = estimate_outcome(evidence, action, seed=42)

    assert isinstance(outcome, RecoveryOutcome)
    assert outcome.action_taken == action
    assert outcome.transaction_id == evidence.transaction_id
    assert 0.0 <= outcome.amount_recovered <= evidence.amount
    assert isinstance(outcome.duplicate_charge_risk, bool)


# --- 2: estimator does not require / import PolicyDecision -------------------

def test_estimator_signature_does_not_require_policy_decision():
    import ast

    import src.recovery.simulator as simulator_module

    params = inspect.signature(estimate_outcome).parameters
    assert "policy_decision" not in params
    assert "policy" not in params

    # Check actual imports (AST), not prose -- the module's own docstring
    # legitimately mentions "PolicyDecision" and "src.policy.engine" to
    # explain why it does NOT depend on them; a raw substring search over
    # the whole source (including that docstring) would be a false
    # positive, exactly the documentation-vs-operational-coupling
    # distinction already learned from the Day 7 forbidden-mapping search.
    tree = ast.parse(inspect.getsource(simulator_module))
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.add(node.module or "")
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)

    assert "PolicyDecision" not in imported_names
    assert not any(name.startswith("src.policy") for name in imported_names)


# --- 4: deterministic under fixed seed ----------------------------------------

def test_same_evidence_same_action_same_seed_is_deterministic():
    evidence = make_evidence()
    outcome_a = estimate_outcome(evidence, RecoveryAction.DEFER_RETRY, seed=123)
    outcome_b = estimate_outcome(evidence, RecoveryAction.DEFER_RETRY, seed=123)

    assert outcome_a.recovered == outcome_b.recovered
    assert outcome_a.amount_recovered == outcome_b.amount_recovered
    assert outcome_a.duplicate_charge_risk == outcome_b.duplicate_charge_risk


def test_deterministic_by_default_with_no_explicit_seed():
    """Same evidence + same action, no seed argument at all, must still be
    reproducible -- not accidentally random."""
    evidence = make_evidence(root_cause=RootCause.INFRASTRUCTURE)
    outcome_a = estimate_outcome(evidence, RecoveryAction.DEFER_RETRY)
    outcome_b = estimate_outcome(evidence, RecoveryAction.DEFER_RETRY)

    assert outcome_a.recovered == outcome_b.recovered
    assert outcome_a.amount_recovered == outcome_b.amount_recovered


# --- 5: different hypothetical actions for the SAME evidence ------------------

def test_same_evidence_can_be_evaluated_under_every_action():
    evidence = make_evidence(root_cause=RootCause.WEBHOOK_AMBIGUITY)
    outcomes = {action: estimate_outcome(evidence, action, seed=1) for action in ALL_ACTIONS}

    assert len(outcomes) == 5
    for action, outcome in outcomes.items():
        assert outcome.action_taken == action


# --- 6: Guardian's real policy does not alter hypothetical-action behavior --

def test_estimator_evaluates_the_requested_action_exactly_as_given():
    """estimate_outcome(webhook_evidence, DEFER_RETRY) must evaluate
    DEFER_RETRY as requested -- it must never silently substitute
    BLOCK_RECONCILE merely because that's what Guardian's policy would
    have chosen for this evidence."""
    evidence = make_evidence(root_cause=RootCause.WEBHOOK_AMBIGUITY, probability=0.99)
    outcome = estimate_outcome(evidence, RecoveryAction.DEFER_RETRY, seed=7)

    assert outcome.action_taken == RecoveryAction.DEFER_RETRY
    assert outcome.action_taken != RecoveryAction.BLOCK_RECONCILE


# --- 7/8: WEBHOOK_AMBIGUITY hypothetical evaluation ---------------------------

def test_webhook_ambiguity_defer_retry_can_be_evaluated_as_hypothetical_unsafe_action():
    evidence = make_evidence(root_cause=RootCause.WEBHOOK_AMBIGUITY)
    # Must not raise, must not refuse -- the estimator has no safety opinion.
    outcome = estimate_outcome(evidence, RecoveryAction.DEFER_RETRY, seed=99)
    assert outcome.action_taken == RecoveryAction.DEFER_RETRY


def test_webhook_ambiguity_block_reconcile_produces_no_automatic_retry():
    evidence = make_evidence(root_cause=RootCause.WEBHOOK_AMBIGUITY)
    outcome = estimate_outcome(evidence, RecoveryAction.BLOCK_RECONCILE, seed=5)

    assert outcome.recovered is False
    assert outcome.amount_recovered == 0.0
    assert outcome.duplicate_charge_risk is False


# --- 9/10: HUMAN_REVIEW / NO_ACTION produce zero automated recovery -----------

@pytest.mark.parametrize("action", [RecoveryAction.HUMAN_REVIEW, RecoveryAction.NO_ACTION])
def test_non_automated_actions_produce_zero_recovery(action):
    evidence = make_evidence()
    outcome = estimate_outcome(evidence, action, seed=3)

    assert outcome.recovered is False
    assert outcome.amount_recovered == 0.0
    assert outcome.duplicate_charge_risk is False


# --- 11: CUSTOMER_RECOVERY is not a same-instrument automatic retry -----------

def test_customer_recovery_reason_reflects_customer_directed_path_not_a_retry():
    evidence = make_evidence(root_cause=RootCause.CARD_DECLINE)
    outcome = estimate_outcome(evidence, RecoveryAction.CUSTOMER_RECOVERY, seed=11)

    assert outcome.action_taken == RecoveryAction.CUSTOMER_RECOVERY
    assert "CUSTOMER_RECOVERY" in outcome.outcome_reason
    assert "RETRY" not in outcome.outcome_reason


# --- Duplicate charge risk tests (spec section 26) ---------------------------

def test_duplicate_charge_risk_test_a_webhook_ambiguity_defer_retry_may_produce_either():
    """Over many seeds, WEBHOOK_AMBIGUITY + DEFER_RETRY must be CAPABLE of
    producing both recovery and duplicate_charge_risk, per the configured
    synthetic assumption -- not hardcoded to one fixed answer."""
    evidence = make_evidence(root_cause=RootCause.WEBHOOK_AMBIGUITY)
    outcomes = [estimate_outcome(evidence, RecoveryAction.DEFER_RETRY, seed=s) for s in range(200)]

    assert any(o.duplicate_charge_risk for o in outcomes)
    assert any(not o.duplicate_charge_risk for o in outcomes)
    assert any(o.recovered for o in outcomes)


def test_duplicate_charge_risk_test_b_webhook_ambiguity_block_reconcile_always_safe():
    evidence = make_evidence(root_cause=RootCause.WEBHOOK_AMBIGUITY)
    for s in range(20):
        outcome = estimate_outcome(evidence, RecoveryAction.BLOCK_RECONCILE, seed=s)
        assert outcome.duplicate_charge_risk is False
        assert outcome.recovered is False


def test_duplicate_charge_risk_test_c_non_ambiguous_retry_has_no_duplicate_risk():
    """A genuine (non-ambiguous) INFRASTRUCTURE retry follows the
    configured simulation assumptions -- which currently assign it zero
    duplicate-charge risk, since the original payment is known to have
    failed (not ambiguous)."""
    evidence = make_evidence(root_cause=RootCause.INFRASTRUCTURE)
    for s in range(20):
        outcome = estimate_outcome(evidence, RecoveryAction.DEFER_RETRY, seed=s)
        assert outcome.duplicate_charge_risk is False


# --- Money tests (spec section 27) -------------------------------------------

@pytest.mark.parametrize("amount", [0.0, 1.0, 250.5, 999999.99])
def test_recovered_amount_stays_within_transaction_amount_bounds(amount):
    evidence = make_evidence(amount=amount, root_cause=RootCause.INFRASTRUCTURE)
    for s in range(10):
        outcome = estimate_outcome(evidence, RecoveryAction.DEFER_RETRY, seed=s)
        assert outcome.amount_recovered >= 0.0
        assert outcome.amount_recovered <= amount


def test_unrecovered_amount_helper_satisfies_the_invariant():
    evidence = make_evidence(amount=5000.0, root_cause=RootCause.CARD_DECLINE)
    outcome = estimate_outcome(evidence, RecoveryAction.CUSTOMER_RECOVERY, seed=1)

    unrecovered = unrecovered_amount(evidence.amount, outcome)
    assert 0.0 <= unrecovered <= evidence.amount
    assert outcome.amount_recovered + unrecovered == evidence.amount


# --- Leakage test (spec section 28) ------------------------------------------

def test_evidence_feature_contract_excludes_post_action_information():
    """RecoveryEvidence must never be constructible from post-action
    information -- inspect its actual declared fields directly."""
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(RecoveryEvidence)}
    forbidden = {
        "recovered", "amount_recovered", "duplicate_charge_risk",
        "action_taken", "outcome_reason", "reconciliation_result",
    }
    assert field_names.isdisjoint(forbidden)


# --- Expected vs simulated distinction ----------------------------------------

def test_probability_of_recovery_is_expected_not_simulated():
    """probability_of_recovery() returns the EXPECTED probability (a
    float in [0, 1]) -- distinct from estimate_outcome()'s single
    SIMULATED realized draw."""
    evidence = make_evidence(root_cause=RootCause.INFRASTRUCTURE)
    p = probability_of_recovery(evidence, RecoveryAction.DEFER_RETRY)
    assert 0.0 <= p <= 1.0
    assert isinstance(p, float)


def test_reproducibility_across_all_five_actions_for_the_same_evidence():
    """Direct Day 9 compatibility proof (spec section 33): the same
    evidence object, evaluated under every action, twice, is identical
    both times -- no separate models required."""
    evidence = make_evidence(root_cause=RootCause.WEBHOOK_AMBIGUITY)

    run_1 = {a: estimate_outcome(evidence, a, seed=42) for a in ALL_ACTIONS}
    run_2 = {a: estimate_outcome(evidence, a, seed=42) for a in ALL_ACTIONS}

    for action in ALL_ACTIONS:
        assert run_1[action].recovered == run_2[action].recovered
        assert run_1[action].amount_recovered == run_2[action].amount_recovered
        assert run_1[action].duplicate_charge_risk == run_2[action].duplicate_charge_risk
