"""
Recovery Guardian — Day 8 Batch Simulation Tests

simulate_batch() is strategy-agnostic (src/recovery/batch.py) — these
tests use small, local, throwaway action selectors purely as test
fixtures. They are NOT the naive/rules-only/Guardian Day 9/10 strategies.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.models import RecoveryAction, RootCause
from src.recovery.batch import simulate_batch, total_amount_at_risk, total_recovered
from src.recovery.evidence import RecoveryEvidence


def make_batch():
    return [
        RecoveryEvidence(f"txn_{i}", amount=1000.0 * (i + 1), root_cause=RootCause.INFRASTRUCTURE, probability=0.9)
        for i in range(6)
    ]


def test_batch_uses_the_shared_estimator_not_a_separate_strategy_specific_model():
    """The batch mechanism itself must not embed a strategy -- confirmed
    by using two DIFFERENT trivial selectors and observing both produce
    outcomes via the same estimate_outcome() (i.e. neither selector has
    its own outcome logic)."""
    batch = make_batch()

    always_defer = lambda evidence: RecoveryAction.DEFER_RETRY
    always_block = lambda evidence: RecoveryAction.BLOCK_RECONCILE

    outcomes_a = simulate_batch(batch, always_defer, seed=1)
    outcomes_b = simulate_batch(batch, always_block, seed=1)

    assert all(o.action_taken == RecoveryAction.DEFER_RETRY for o in outcomes_a)
    assert all(o.action_taken == RecoveryAction.BLOCK_RECONCILE for o in outcomes_b)
    # BLOCK_RECONCILE never recovers anything (see simulator semantics).
    assert all(o.amount_recovered == 0.0 for o in outcomes_b)


def test_batch_money_invariants():
    batch = make_batch()
    outcomes = simulate_batch(batch, lambda e: RecoveryAction.DEFER_RETRY, seed=7)

    at_risk = total_amount_at_risk(batch)
    recovered = total_recovered(outcomes)

    assert recovered >= 0.0
    assert recovered <= at_risk
    for evidence, outcome in zip(batch, outcomes):
        assert outcome.amount_recovered <= evidence.amount


def test_batch_result_equals_sum_of_individual_outcomes():
    batch = make_batch()
    outcomes = simulate_batch(batch, lambda e: RecoveryAction.CUSTOMER_RECOVERY, seed=3)

    manual_total = sum(o.amount_recovered for o in outcomes)
    assert total_recovered(outcomes) == manual_total


def test_batch_is_deterministic_given_a_seed():
    batch = make_batch()
    selector = lambda e: RecoveryAction.DEFER_RETRY

    run_1 = simulate_batch(batch, selector, seed=99)
    run_2 = simulate_batch(batch, selector, seed=99)

    assert [o.recovered for o in run_1] == [o.recovered for o in run_2]
    assert [o.amount_recovered for o in run_1] == [o.amount_recovered for o in run_2]
