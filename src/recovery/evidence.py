"""
Recovery Guardian — Day 8 Counterfactual Evidence

`RecoveryEvidence` is the single "evidence" argument the shared outcome
estimator (src/recovery/simulator.py) takes, alongside a hypothetical
`RecoveryAction`. It is a small, pure-data projection of information
available BEFORE any recovery action is taken — never the outcome of one.

Why a new, small class rather than reusing PaymentEvent/RootCausePrediction
directly: the estimator must be callable for purely hypothetical Day 9/10
baseline scenarios without requiring a full, validated PaymentEvent +
RootCausePrediction pair (e.g. a naive-baseline experiment may want to
construct evidence directly from a dataset row). RecoveryEvidence is NOT a
duplicate of RecoveryOutcome or PolicyDecision — it carries no action, no
outcome, and no policy information; it exists only to make the shared
estimator's dependency surface minimal and Day-9/10-friendly.
"""

from dataclasses import dataclass

from src.domain.models import PaymentEvent, RootCause, RootCausePrediction


@dataclass(frozen=True)
class RecoveryEvidence:
    """Pre-action evidence only. Never include anything that occurs AFTER
    a recovery action is taken (actual recovered amount, actual retry
    result, future reconciliation state, etc.) — see
    src/recovery/simulator.py's module docstring and
    tests/test_recovery_simulator.py's leakage test."""

    transaction_id: str
    amount: float
    root_cause: RootCause
    probability: float  # the calibrated classifier's confidence in root_cause
    retry_count: int = 0
    incident_active: bool = False
    # Added Day 9: the rules-only baseline strategy (src/experiment/
    # strategies.py) needs failure_code, and the Day 9 spec explicitly
    # says it "may be available to all strategies." Additive, defaulted,
    # backward compatible — does not change estimate_outcome()'s logic at
    # all (Day 8's outcome model never reads failure_code).
    failure_code: str = ""

    @classmethod
    def from_payment_event_and_prediction(
        cls, payment_event: PaymentEvent, prediction: RootCausePrediction
    ) -> "RecoveryEvidence":
        """Build evidence from the two domain objects the real pipeline
        already has at decision time — both are pre-action by construction
        (the payment event and the classifier's prediction), so this is a
        pure projection, not a new source of information."""
        return cls(
            transaction_id=prediction.transaction_id,
            amount=payment_event.amount,
            root_cause=prediction.root_cause,
            probability=prediction.probability,
            retry_count=payment_event.retry_count,
            incident_active=payment_event.incident_active,
            failure_code=payment_event.failure_code,
        )
