"""
Recovery Guardian — Day 9 Strategy Isolation + Fairness Tests
"""

import ast
import inspect
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.models import PaymentEvent, RecoveryAction, RootCause
from src.experiment.strategies import (
    GuardianStrategy,
    NaiveRetryStrategy,
    NoActionStrategy,
    RulesOnlyStrategy,
)


def make_event(**overrides) -> PaymentEvent:
    base = dict(
        event_id="evt_x",
        transaction_id="txn_x",
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
        customer_previous_successes=3,
        customer_previous_failures=1,
        incident_active=True,
        source="synthetic",
    )
    base.update(overrides)
    return PaymentEvent(**base)


# --- Strategy 1: Naive always DEFER_RETRY ------------------------------------

@pytest.mark.parametrize("failure_code", ["gateway_timeout", "insufficient_funds", "unknown", "user_cancelled"])
def test_naive_always_defer_retry(failure_code):
    strategy = NaiveRetryStrategy()
    action = strategy.select_action(make_event(failure_code=failure_code))
    assert action == RecoveryAction.DEFER_RETRY


def test_naive_does_not_import_ml_or_policy():
    import src.experiment.strategies as strategies_module

    source = inspect.getsource(NaiveRetryStrategy)
    tree = ast.parse(source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "CalibratedRootCauseClassifier" not in names
    assert "RulesPolicyEngine" not in names


# --- Strategy 2: Rules-only ----------------------------------------------------

@pytest.mark.parametrize(
    "failure_code,expected",
    [
        ("gateway_timeout", RecoveryAction.DEFER_RETRY),
        ("internal_error", RecoveryAction.DEFER_RETRY),
        ("service_unavailable", RecoveryAction.DEFER_RETRY),
        ("issuer_declined", RecoveryAction.CUSTOMER_RECOVERY),
        ("card_expired", RecoveryAction.CUSTOMER_RECOVERY),
        ("invalid_card", RecoveryAction.CUSTOMER_RECOVERY),
        ("insufficient_funds", RecoveryAction.CUSTOMER_RECOVERY),
        ("otp_timeout", RecoveryAction.HUMAN_REVIEW),
        ("3ds_auth_failed", RecoveryAction.HUMAN_REVIEW),
        ("user_cancelled", RecoveryAction.HUMAN_REVIEW),
        ("session_expired", RecoveryAction.HUMAN_REVIEW),
        ("unknown", RecoveryAction.HUMAN_REVIEW),
    ],
)
def test_rules_only_frozen_mapping(failure_code, expected):
    strategy = RulesOnlyStrategy()
    action = strategy.select_action(make_event(failure_code=failure_code))
    assert action == expected


def test_rules_only_unrecognized_code_falls_back_safely():
    strategy = RulesOnlyStrategy()
    action = strategy.select_action(make_event(failure_code="some_new_code_never_seen"))
    assert action == RecoveryAction.HUMAN_REVIEW


def test_rules_only_does_not_import_ml_or_policy():
    source = inspect.getsource(RulesOnlyStrategy)
    tree = ast.parse(source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "CalibratedRootCauseClassifier" not in names
    assert "RulesPolicyEngine" not in names


def test_rules_only_ambiguous_codes_documented_and_frozen():
    """Section 9's mandatory disclosure: gateway_timeout and unknown are
    the two deliberately non-unique codes, and each has exactly one
    frozen action."""
    from src.experiment.strategies import RULES_ONLY_FAILURE_CODE_MAPPING

    assert RULES_ONLY_FAILURE_CODE_MAPPING["gateway_timeout"] == RecoveryAction.DEFER_RETRY
    assert RULES_ONLY_FAILURE_CODE_MAPPING["unknown"] == RecoveryAction.HUMAN_REVIEW


# --- Strategy 3: No Action -------------------------------------------------------

@pytest.mark.parametrize("root_cause", list(RootCause))
def test_no_action_always_selects_no_action(root_cause):
    strategy = NoActionStrategy()
    action = strategy.select_action(make_event())
    assert action == RecoveryAction.NO_ACTION


def test_no_action_does_not_import_ml_or_policy():
    source = inspect.getsource(NoActionStrategy)
    tree = ast.parse(source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "CalibratedRootCauseClassifier" not in names
    assert "RulesPolicyEngine" not in names


# --- Strategy 4: Guardian uses the real pipeline -------------------------------

def test_guardian_uses_real_classifier_and_policy_engine():
    strategy = GuardianStrategy()
    assert isinstance(strategy._classifier.__class__.__name__, str)
    from src.model.calibrated_classifier import CalibratedRootCauseClassifier
    from src.policy.engine import RulesPolicyEngine

    assert isinstance(strategy._classifier, CalibratedRootCauseClassifier)
    assert isinstance(strategy._policy_engine, RulesPolicyEngine)


def test_guardian_called_twice_sequentially_returns_same_action():
    """Mandatory Day 9 test (section 10A): no persistent state leaks
    between calls."""
    strategy = GuardianStrategy()
    event = make_event(transaction_id="txn_repeat_check", failure_code="gateway_timeout")

    action_1 = strategy.select_action(event)
    action_2 = strategy.select_action(event)

    assert action_1 == action_2


def test_guardian_state_does_not_pollute_across_instances():
    event = make_event(transaction_id="txn_isolation_check", failure_code="insufficient_funds")

    action_from_instance_1 = GuardianStrategy().select_action(event)
    action_from_instance_2 = GuardianStrategy().select_action(event)

    assert action_from_instance_1 == action_from_instance_2


def test_guardian_never_writes_to_the_real_database():
    """GuardianStrategy must not import get_connection or persist_*
    anywhere -- Option A (bypass persistence only) must hold structurally,
    not just by convention."""
    source = inspect.getsource(sys.modules["src.experiment.strategies"])
    assert "get_connection" not in source
    assert "persist_decision_record" not in source
    assert "persist_recovery_outcome" not in source
    assert "record_action" not in source
