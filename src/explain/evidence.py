"""
Recovery Guardian — Day 13 Explanation Evidence

`ExplanationEvidence` is a small, pure-data projection of the ALREADY
FROZEN decision path:

    PaymentEvent -> RootCausePrediction -> PolicyDecision (+ optional
    RecoveryOutcome)

into the facts an explanation is allowed to talk about. It is built
exclusively via `ExplanationEvidence.from_decision()`, which reads every
field from the real domain objects the pipeline already produced — it
never recomputes a prediction or a policy decision, and it has no
mechanism to accept a root cause or action from anywhere else.

Mirrors the precedent set by `src.recovery.evidence.RecoveryEvidence`
(Day 8): a small, frozen dataclass that exists only to narrow what a
downstream component is allowed to see, never to duplicate an existing
domain model.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from src.domain.models import PaymentEvent, PolicyDecision, RecoveryOutcome, RootCausePrediction
from src.policy.engine import PolicyConfig, load_policy_config

# The three, and only three, outcome-provenance states an explanation may
# ever describe (Day 13 spec section 14). Deliberately a plain string
# Enum defined here, not on RecoveryOutcome: provenance is a fact about
# WHERE an outcome came from (Day 8 simulation vs. a real Razorpay
# response that does not exist in this project yet), which the domain
# model itself has no way to know — only the caller assembling evidence
# does.
OBSERVED = "OBSERVED"
SIMULATED = "SIMULATED"
UNAVAILABLE = "UNAVAILABLE"
VALID_OUTCOME_STATUSES = frozenset({OBSERVED, SIMULATED, UNAVAILABLE})

# WEBHOOK_AMBIGUITY has no confidence threshold in src/policy/rules.yaml
# by design (src/policy/engine.py: it is a hard safety override, not a
# confidence-gated business rule) — this is the exact set of root causes
# `from_decision` will look up a threshold for.
_THRESHOLDED_ROOT_CAUSES = frozenset(
    {"INFRASTRUCTURE", "CARD_DECLINE", "INSUFFICIENT_FUNDS", "OTP_TIMEOUT", "USER_ABANDONMENT"}
)


@dataclass(frozen=True)
class ExplanationEvidence:
    """Everything an explanation is permitted to reference. Every field
    here is a fact taken directly from the frozen ML/policy path or from
    Day 8's simulator/a real outcome — nothing on this object is ever
    computed by an LLM."""

    transaction_id: str
    amount: float
    payment_method: str
    failure_code: str
    retry_count: int
    webhook_delay_seconds: float
    incident_active: bool

    predicted_root_cause: str
    predicted_probability: float

    policy_action: str
    policy_reason: str
    policy_version: str
    relevant_threshold: Optional[float]

    safety_flags: List[str] = field(default_factory=list)

    outcome_status: str = UNAVAILABLE
    outcome_recovered: Optional[bool] = None
    outcome_amount: Optional[float] = None
    outcome_reason: str = ""

    def __post_init__(self):
        if self.outcome_status not in VALID_OUTCOME_STATUSES:
            raise ValueError(
                f"outcome_status must be one of {sorted(VALID_OUTCOME_STATUSES)}, "
                f"got {self.outcome_status!r}"
            )
        if self.outcome_status == UNAVAILABLE and (
            self.outcome_recovered is not None or self.outcome_amount is not None
        ):
            raise ValueError(
                "outcome_status is UNAVAILABLE but an outcome value was supplied — "
                "never fabricate outcome facts."
            )

    @classmethod
    def from_decision(
        cls,
        payment_event: PaymentEvent,
        prediction: RootCausePrediction,
        policy_decision: PolicyDecision,
        *,
        outcome: Optional[RecoveryOutcome] = None,
        outcome_status: str = UNAVAILABLE,
        policy_config: Optional[PolicyConfig] = None,
    ) -> "ExplanationEvidence":
        """The ONLY constructor. Reads every fact straight off the real
        `PaymentEvent`/`RootCausePrediction`/`PolicyDecision` the frozen
        pipeline already produced.

        Args:
            outcome: an already-computed `RecoveryOutcome` (e.g. from
                `src.recovery.simulator.estimate_outcome`), if one
                exists. Never computed here.
            outcome_status: caller-declared provenance for `outcome` —
                required whenever `outcome` is supplied, because
                `RecoveryOutcome` itself carries no provenance field.
                Must be OBSERVED or SIMULATED when `outcome` is given.
            policy_config: the real, loaded Day 7 policy configuration
                (for the confidence threshold). Defaults to loading the
                real `src/policy/rules.yaml` — never a hardcoded number.
        """
        if outcome is not None and outcome_status == UNAVAILABLE:
            raise ValueError("outcome was supplied but outcome_status is UNAVAILABLE")
        if outcome is None and outcome_status != UNAVAILABLE:
            raise ValueError("outcome_status is not UNAVAILABLE but no outcome was supplied")

        cfg = policy_config or load_policy_config()
        root_cause_value = prediction.root_cause.value
        threshold = (
            cfg.confidence_thresholds.get(root_cause_value)
            if root_cause_value in _THRESHOLDED_ROOT_CAUSES
            else None
        )

        safety_flags: List[str] = []
        if root_cause_value == "WEBHOOK_AMBIGUITY":
            safety_flags.append("WEBHOOK_AMBIGUITY_HARD_SAFETY_OVERRIDE")

        return cls(
            transaction_id=prediction.transaction_id,
            amount=payment_event.amount,
            payment_method=payment_event.payment_method,
            failure_code=payment_event.failure_code,
            retry_count=payment_event.retry_count,
            webhook_delay_seconds=payment_event.webhook_delay_seconds,
            incident_active=payment_event.incident_active,
            predicted_root_cause=root_cause_value,
            predicted_probability=prediction.probability,
            policy_action=policy_decision.action.value,
            policy_reason=(
                policy_decision.reason_codes[0].value if policy_decision.reason_codes else ""
            ),
            policy_version=policy_decision.policy_version,
            relevant_threshold=threshold,
            safety_flags=safety_flags,
            outcome_status=outcome_status,
            outcome_recovered=outcome.recovered if outcome is not None else None,
            outcome_amount=outcome.amount_recovered if outcome is not None else None,
            outcome_reason=outcome.outcome_reason if outcome is not None else "",
        )
