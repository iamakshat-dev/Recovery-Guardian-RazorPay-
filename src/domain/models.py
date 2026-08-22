"""
Recovery Guardian — Domain Models

Four separate typed objects, matching the four-stage pipeline:

    PaymentEvent -> RootCausePrediction -> PolicyDecision -> RecoveryOutcome

Kept deliberately small (this is a 15-day hackathon build, not a production
service) — the value here is the SEPARATION of these four concepts, not an
elaborate class hierarchy. A payment event is not a model prediction; a
prediction is not a policy decision; a decision is not an outcome. Keeping
them as distinct typed objects (rather than one big mutable dict getting
fields bolted onto it as it flows through the pipeline) is what makes the
audit trail and the reproducibility story credible.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RootCause(str, Enum):
    INFRASTRUCTURE = "INFRASTRUCTURE"
    CARD_DECLINE = "CARD_DECLINE"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    OTP_TIMEOUT = "OTP_TIMEOUT"
    USER_ABANDONMENT = "USER_ABANDONMENT"
    WEBHOOK_AMBIGUITY = "WEBHOOK_AMBIGUITY"


class RecoveryAction(str, Enum):
    DEFER_RETRY = "DEFER_RETRY"
    CUSTOMER_RECOVERY = "CUSTOMER_RECOVERY"
    BLOCK_RECONCILE = "BLOCK_RECONCILE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    NO_ACTION = "NO_ACTION"


class ReasonCode(str, Enum):
    """Machine-readable reason codes for every policy decision. The LLM
    explanation layer (Day 13) may translate these into a sentence for a
    human reader, but the audit log itself never depends on free-text
    reasoning — every decision must be explainable by a fixed code alone."""
    INFRA_CLUSTER_HIGH = "INFRA_CLUSTER_HIGH"
    WEBHOOK_STATE_UNKNOWN = "WEBHOOK_STATE_UNKNOWN"
    RETRY_LIMIT_REACHED = "RETRY_LIMIT_REACHED"
    CUSTOMER_OPTED_OUT = "CUSTOMER_OPTED_OUT"
    LOW_MODEL_CONFIDENCE = "LOW_MODEL_CONFIDENCE"
    HIGH_VALUE_ESCALATION = "HIGH_VALUE_ESCALATION"
    IDEMPOTENCY_BLOCK = "IDEMPOTENCY_BLOCK"
    CUSTOMER_SIDE_FAILURE = "CUSTOMER_SIDE_FAILURE"
    # Added Day 7 (src/policy/engine.py) — the eight codes above already
    # covered nearly every case the real policy engine needed; these three
    # fill the only genuine gaps rather than duplicating an existing code:
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    INVALID_POLICY_INPUT = "INVALID_POLICY_INPUT"
    NO_AUTOMATED_ACTION_DEFINED = "NO_AUTOMATED_ACTION_DEFINED"


class PaymentEvent(BaseModel):
    """What came from the payment system (Razorpay test-mode or synthetic).
    Both adapters must normalize into exactly this shape — that equivalence
    is what the Day 11 adapter pattern depends on."""
    event_id: str
    transaction_id: str
    merchant_id: str
    amount: float
    timestamp: datetime
    payment_method: str
    failure_code: str
    retry_count: int
    webhook_delay_seconds: float
    gateway_error_rate_delta: float = Field(ge=0.0, le=1.0)
    merchant_failure_rate_delta: float = Field(ge=0.0, le=1.0)
    cross_merchant_failure_rate: float = Field(ge=0.0, le=1.0)
    customer_previous_successes: int
    customer_previous_failures: int
    incident_active: bool
    source: str = Field(description="'razorpay' or 'synthetic'")
    # Added Day 7 for the policy engine (src/policy/engine.py). Both are
    # optional and default to "no restriction" precisely so every existing
    # Day 3-6 PaymentEvent construction (none of which sets these) keeps
    # working unchanged — this is additive, not a breaking change to the
    # frozen contract. Neither field is read by the feature builder or the
    # ML model; build_features() only ever selects FEATURE_COLUMNS by name.
    customer_opted_out: bool = Field(
        default=False,
        description="True if the customer has opted out of automated recovery.",
    )
    last_recovery_action_at: Optional[datetime] = Field(
        default=None,
        description="When an automated recovery action was last authorized "
        "for this transaction, if ever — used for the policy cooldown guard.",
    )


class RootCausePrediction(BaseModel):
    """What the model believes. Probability MUST come from a calibrated
    classifier (see Day 4-6), never from an LLM asserting a number."""
    transaction_id: str
    root_cause: RootCause
    probability: float = Field(ge=0.0, le=1.0)
    model_version: str


class PolicyDecision(BaseModel):
    """What is allowed. Produced by the deterministic policy engine
    (Day 7-8) — never by the model or the LLM directly."""
    transaction_id: str
    action: RecoveryAction
    reason_codes: list[ReasonCode]
    policy_version: str
    requires_human_review: bool = False


class RecoveryOutcome(BaseModel):
    """What actually happened, from the recovery simulator (Day 8-10) or,
    for real Razorpay test-mode events, from the actual API response."""
    transaction_id: str
    action_taken: RecoveryAction
    recovered: bool
    amount_recovered: float
    decision_id: str
    timestamp: datetime
    # Added Day 8 (src/recovery/simulator.py). Both are additive with safe
    # defaults, so nothing that already constructs a RecoveryOutcome (there
    # is no such caller yet — this model was declared in Day 1 but never
    # populated until Day 8) breaks.
    duplicate_charge_risk: bool = Field(
        default=False,
        description="True if this simulated outcome carries duplicate-charge "
        "risk — e.g. a hypothetical retry of an unresolved WEBHOOK_AMBIGUITY "
        "payment that may have already succeeded. Independent of `recovered`: "
        "an outcome can be recovered=True and duplicate_charge_risk=True at "
        "the same time.",
    )
    outcome_reason: str = Field(
        default="",
        description="Short machine-readable label for why the simulator "
        "produced this outcome (e.g. 'WEBHOOK_AMBIGUITY_RETRY_DUPLICATE'), "
        "for audit/debugging — not a substitute for the policy ReasonCode.",
    )


class DecisionRecord(BaseModel):
    """The full audit record for one transaction — the single artifact a
    judge should be able to inspect end to end: evidence in, decision out."""
    decision_id: str
    event: PaymentEvent
    prediction: RootCausePrediction
    policy: PolicyDecision
    outcome: Optional[RecoveryOutcome] = None
