"""
Recovery Guardian — Day 3 Placeholder Policy Engine

STRUCTURAL PLACEHOLDER ONLY. This is not the Day 7 policy system. It does
not implement retry caps, cooldowns, opt-out enforcement, amount
thresholds, a full idempotency guard, or config-driven (rules.yaml) rules —
all of that is later, real work.

What it must do today is produce a single, always-safe, always-valid
PolicyDecision so the rest of the Day 3 pipeline (audit record, SQLite
persistence, CLI) can be exercised end to end.

Decision logic, and why:
    The Day 3 classifier's probability (0.50) is explicitly non-informative
    — it is not a real confidence score. The only honest policy response to
    a meaningless confidence value is to never take an automated recovery
    action on its basis. So this placeholder always escalates to
    HUMAN_REVIEW, using ReasonCode.LOW_MODEL_CONFIDENCE.

    LOW_MODEL_CONFIDENCE is not a perfect semantic fit — the placeholder
    doesn't have a "low" confidence so much as a fabricated, meaningless
    one — but it is the closest existing ReasonCode, and it captures the
    correct downstream behavior (escalate, don't act) without introducing
    a new ad-hoc reason value. This will be reconsidered once Day 4-6
    produce a real calibrated probability worth reasoning about.

Will be REPLACED by the Day 7 config-driven rules engine
(src/policy/rules.yaml + src/policy/engine.py).
"""

from src.domain.models import (
    PaymentEvent,
    PolicyDecision,
    ReasonCode,
    RecoveryAction,
    RootCausePrediction,
)

POLICY_VERSION = "placeholder-v1"


class PolicyEngine:
    """Day 3 structural placeholder. See module docstring."""

    def decide(
        self, prediction: RootCausePrediction, payment_event: PaymentEvent
    ) -> PolicyDecision:
        return PolicyDecision(
            transaction_id=prediction.transaction_id,
            action=RecoveryAction.HUMAN_REVIEW,
            reason_codes=[ReasonCode.LOW_MODEL_CONFIDENCE],
            policy_version=POLICY_VERSION,
            requires_human_review=True,
        )
