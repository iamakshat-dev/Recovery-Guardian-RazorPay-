"""
Recovery Guardian — Day 9 Money Invariants, Root-Cause Segments, Guardian
Regression, and Dataset Freeze Tests
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.models import PaymentEvent, RecoveryAction, RootCause
from src.experiment.dataset import load_frozen_test_split_payment_events
from src.experiment.results import (
    ROOT_CAUSE_NAMES,
    STRATEGY_NAMES,
    aggregate_metrics_by_root_cause,
    aggregate_metrics_by_strategy,
)
from src.experiment.runner import run_experiment
from src.experiment.strategies import GuardianStrategy

CURRENCY_TOLERANCE = 1e-2  # see docs/architecture.md's Day 9 section: no
# existing repository currency/rounding convention was found (audited
# src/domain/, src/db.py, existing money-related tests, docs/,
# configuration files); this tolerance is Day 9's own explicit choice.


def make_event(**overrides) -> PaymentEvent:
    base = dict(
        event_id="evt_metrics",
        transaction_id="txn_metrics_0001",
        merchant_id="merchant_001",
        amount=1000.0,
        timestamp=datetime(2026, 8, 1),
        payment_method="card",
        failure_code="gateway_timeout",
        retry_count=0,
        webhook_delay_seconds=1.0,
        gateway_error_rate_delta=0.3,
        merchant_failure_rate_delta=0.2,
        cross_merchant_failure_rate=0.15,
        customer_previous_successes=1,
        customer_previous_failures=1,
        incident_active=False,
        source="synthetic",
    )
    base.update(overrides)
    return PaymentEvent(**base)


# --- Money invariants ------------------------------------------------------------

def test_recovery_cannot_exceed_amount_at_risk():
    events = [make_event(transaction_id=f"txn_money_{i}", amount=100.0 * (i + 1)) for i in range(10)]
    results = run_experiment(events, experiment_seed=42)

    agg = aggregate_metrics_by_strategy(results)
    for name, row in agg.items():
        assert row["simulated_amount_recovered"] >= 0.0
        assert row["simulated_amount_recovered"] <= row["total_amount_at_risk"] + CURRENCY_TOLERANCE


def test_per_transaction_amount_recovered_never_exceeds_transaction_amount():
    events = [make_event(transaction_id=f"txn_bound_{i}", amount=50.0 * (i + 1)) for i in range(8)]
    results = run_experiment(events, experiment_seed=42)

    for r in results:
        assert r.amount_recovered >= 0.0
        assert r.amount_recovered <= r.transaction_amount + CURRENCY_TOLERANCE


def test_batch_totals_equal_sum_of_per_transaction_totals():
    events = [make_event(transaction_id=f"txn_sum_{i}", amount=250.0 * (i + 1)) for i in range(6)]
    results = run_experiment(events, experiment_seed=42)

    agg = aggregate_metrics_by_strategy(results)
    for name in STRATEGY_NAMES:
        manual_sum = sum(r.amount_recovered for r in results if r.strategy == name)
        assert abs(manual_sum - agg[name]["simulated_amount_recovered"]) < CURRENCY_TOLERANCE


# --- Root-cause segments ----------------------------------------------------------

def test_all_six_root_cause_segments_always_represented():
    events = [make_event(transaction_id="txn_single", failure_code="insufficient_funds")]
    results = run_experiment(events, experiment_seed=42)

    by_root_cause = aggregate_metrics_by_root_cause(results)
    assert set(by_root_cause.keys()) == set(ROOT_CAUSE_NAMES)
    for rc in ROOT_CAUSE_NAMES:
        assert set(by_root_cause[rc].keys()) == set(STRATEGY_NAMES)


def test_absent_root_causes_report_zero_not_fabricated():
    events = [make_event(transaction_id="txn_single", failure_code="insufficient_funds")]
    results = run_experiment(events, experiment_seed=42)
    by_root_cause = aggregate_metrics_by_root_cause(results)

    # Only INSUFFICIENT_FUNDS should have nonzero transaction counts.
    for rc in ROOT_CAUSE_NAMES:
        if rc != "INSUFFICIENT_FUNDS":
            for strategy_row in by_root_cause[rc].values():
                assert strategy_row["transactions_evaluated"] == 0


# --- Guardian regression (must match frozen Day 7 policy exactly) ---------------

def test_guardian_webhook_ambiguity_regression():
    strategy = GuardianStrategy()
    events = [make_event(failure_code="unknown", transaction_id=f"txn_wa_{i}") for i in range(20)]
    # Find at least one real dataset-shaped case Guardian predicts as
    # WEBHOOK_AMBIGUITY with sufficient confidence, then confirm the
    # frozen policy mapping.
    found = False
    for event in events:
        prediction = strategy.predict(event)
        if prediction.root_cause == RootCause.WEBHOOK_AMBIGUITY and prediction.probability >= 0.75:
            action = strategy.select_action(event)
            assert action == RecoveryAction.BLOCK_RECONCILE
            found = True
    # Not asserting `found` strictly here (webhook_ambiguity's model
    # confidence on a hand-built fixture is not guaranteed) -- the real
    # dataset-driven regression is in test_experiment_dataset_and_pipeline.py.


def test_guardian_infrastructure_and_customer_recovery_regression_via_real_dataset():
    events = load_frozen_test_split_payment_events()
    strategy = GuardianStrategy()

    seen_infra_defer = False
    seen_card_customer_recovery = False
    seen_insufficient_funds_customer_recovery = False
    seen_webhook_block = False

    for event in events:
        prediction = strategy.predict(event)
        action = strategy.select_action(event)
        if prediction.root_cause == RootCause.WEBHOOK_AMBIGUITY:
            assert action != RecoveryAction.DEFER_RETRY
            if action == RecoveryAction.BLOCK_RECONCILE:
                seen_webhook_block = True
        if prediction.root_cause == RootCause.INFRASTRUCTURE and prediction.probability >= 0.75 and action == RecoveryAction.DEFER_RETRY:
            seen_infra_defer = True
        if prediction.root_cause == RootCause.CARD_DECLINE and action == RecoveryAction.CUSTOMER_RECOVERY:
            seen_card_customer_recovery = True
        if prediction.root_cause == RootCause.INSUFFICIENT_FUNDS and action == RecoveryAction.CUSTOMER_RECOVERY:
            seen_insufficient_funds_customer_recovery = True

    assert seen_webhook_block
    assert seen_infra_defer
    assert seen_card_customer_recovery
    assert seen_insufficient_funds_customer_recovery


# --- Dataset freeze ----------------------------------------------------------------

def test_frozen_test_split_is_deterministic_and_matches_day4_size():
    events_a = load_frozen_test_split_payment_events()
    events_b = load_frozen_test_split_payment_events()

    assert len(events_a) == 242  # the same frozen 15% test split size as Day 4/5
    assert [e.transaction_id for e in events_a] == [e.transaction_id for e in events_b]


def test_same_dataset_subset_used_by_all_strategies():
    events = load_frozen_test_split_payment_events()[:20]
    results = run_experiment(events, experiment_seed=42)

    txn_ids_by_strategy = {
        name: {r.transaction_id for r in results if r.strategy == name} for name in STRATEGY_NAMES
    }
    reference = txn_ids_by_strategy["NAIVE_RETRY"]
    for name, ids in txn_ids_by_strategy.items():
        assert ids == reference, f"{name} evaluated a different transaction set"
