"""
Recovery Guardian — Policy Scope Guard (Day 4 audit)

The repository is confirmed to still be in STATE A: the policy engine
(src/policy/placeholder_engine.py) is the Day 3 structural placeholder. It
ignores `prediction.root_cause` entirely and always returns
HUMAN_REVIEW — there is no differentiated root-cause -> action mapping of
any kind, safe or unsafe.

These tests are deliberately NOT Day 7 policy tests. They do not exercise,
require, or approximate a differentiated policy engine. They exist only to:

  1. Lock in that today's placeholder cannot, even by accident, emit the
     unsafe WEBHOOK_AMBIGUITY -> DEFER_RETRY mapping (or any other
     automatic action) for ANY predicted root cause — true today only
     because the placeholder is action-blind, not because a real safety
     rule enforces it.
  2. Document, without implementing, the safety invariant Day 7 must
     establish once a differentiated policy engine exists:

         INFRASTRUCTURE      -> DEFER_RETRY
         WEBHOOK_AMBIGUITY   -> BLOCK_RECONCILE
         (never WEBHOOK_AMBIGUITY -> DEFER_RETRY)

If a future change to the placeholder (or an early, partial Day 7
implementation) introduces differentiated behavior without deliberately
updating these tests, this file should fail loudly rather than silently
pass.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.models import (
    PaymentEvent,
    RecoveryAction,
    RootCause,
    RootCausePrediction,
)
from src.policy.placeholder_engine import PolicyEngine


def make_event(**overrides) -> PaymentEvent:
    base = dict(
        event_id="evt_policy_guard_0001",
        transaction_id="txn_policy_guard_0001",
        merchant_id="merchant_001",
        amount=1000.0,
        timestamp=datetime(2026, 8, 1),
        payment_method="card",
        failure_code="gateway_timeout",
        retry_count=0,
        webhook_delay_seconds=12.0,
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


def test_recovery_action_enum_declares_the_future_policy_actions():
    """Documents (does not implement) the Day 7 safety invariant. Only
    confirms these action values already exist on RecoveryAction so a
    future differentiated policy engine has them available — no
    executable differentiated logic exists yet, and this test must not be
    read as evidence that any does."""
    assert RecoveryAction.DEFER_RETRY.value == "DEFER_RETRY"
    assert RecoveryAction.BLOCK_RECONCILE.value == "BLOCK_RECONCILE"


@pytest.mark.parametrize("cause", list(RootCause))
def test_todays_placeholder_never_authorizes_an_automatic_action_for_any_root_cause(cause):
    """Forward guard, not a Day 7 test: regardless of predicted root cause
    -- INCLUDING WEBHOOK_AMBIGUITY -- today's placeholder policy engine
    always escalates to HUMAN_REVIEW and never returns DEFER_RETRY (or any
    other automatic action). This is currently true because the
    placeholder is root-cause-blind, not because a differentiated safety
    rule enforces it -- that real enforcement is Day 7 scope. This test
    only pins down today's actual, already-safe-by-default behavior."""
    prediction = RootCausePrediction(
        transaction_id="txn_policy_guard_0001",
        root_cause=cause,
        probability=0.99,
        model_version="test-fixture",
    )
    event = make_event()
    engine = PolicyEngine()

    decision = engine.decide(prediction, event)

    assert decision.action == RecoveryAction.HUMAN_REVIEW
    assert decision.action != RecoveryAction.DEFER_RETRY
    assert decision.requires_human_review is True
