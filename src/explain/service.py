"""
Recovery Guardian — Day 13 Explanation Orchestration

    PaymentEvent + RootCausePrediction + PolicyDecision (+ optional
    RecoveryOutcome)
        -> ExplanationEvidence.from_decision()
        -> provider.generate(evidence)   [LLM, or the deterministic
                                           fallback on ANY failure]
        -> Explanation

THE STRUCTURAL GUARANTEE (Day 13 spec sections 25/40): `explain_decision`
is the only place a provider's output is ever read, and it reads exactly
two keys from it — `summary` and `safety_note`, both free text. Every
other field on the returned `Explanation` (`root_cause`, `confidence`,
`action`, `reason`, `outcome_status`) is assigned directly from
`evidence`, which was itself built only from the real, already-computed
`RootCausePrediction`/`PolicyDecision` — never recomputed here, never
read from provider output. There is no `if root_cause == ...: action =
...` anywhere in this module or anywhere else in `src/explain/` — this
package contains no second policy engine. A provider cannot change the
recovery action no matter what it returns, including a provider that
deliberately tries to (see
`tests/test_explain.py::test_provider_cannot_override_the_decision`).

No side effects: this module makes no database write, no idempotency
write, no recovery-action execution, and no mutation of any Day 3-12
object. It only reads already-computed objects and returns a new,
independent `Explanation`.
"""

from typing import Optional

from src.domain.models import PaymentEvent, PolicyDecision, RecoveryOutcome, RootCausePrediction
from src.explain.evidence import UNAVAILABLE, ExplanationEvidence
from src.explain.models import Explanation
from src.explain.provider import (
    DeterministicFallbackProvider,
    ExplanationProvider,
    ExplanationProviderError,
    default_safety_note,
)
from src.policy.engine import PolicyConfig


def explain_decision(
    payment_event: PaymentEvent,
    prediction: RootCausePrediction,
    policy_decision: PolicyDecision,
    *,
    outcome: Optional[RecoveryOutcome] = None,
    outcome_status: str = UNAVAILABLE,
    provider: Optional[ExplanationProvider] = None,
    policy_config: Optional[PolicyConfig] = None,
) -> Explanation:
    """The single public entry point for Day 13. `provider` defaults to
    the deterministic fallback; passing a `ClaudeExplanationProvider` (or
    any other `ExplanationProvider`) only changes the prose quality of
    `summary`/`safety_note` — it can never change `root_cause`,
    `confidence`, `action`, `reason`, or `outcome_status`."""
    evidence = ExplanationEvidence.from_decision(
        payment_event,
        prediction,
        policy_decision,
        outcome=outcome,
        outcome_status=outcome_status,
        policy_config=policy_config,
    )

    fallback = DeterministicFallbackProvider()
    active_provider = provider or fallback

    try:
        raw = active_provider.generate(evidence)
        if not isinstance(raw, dict):
            raise ExplanationProviderError(f"provider returned {type(raw)!r}, expected dict")
        summary = str(raw.get("summary") or "").strip()
        safety_note = str(raw.get("safety_note") or "").strip()
        if not summary:
            raise ExplanationProviderError("provider returned an empty summary")
    except Exception:
        # ANY provider failure — missing credentials, network error,
        # timeout, malformed response, empty summary, or an unexpected
        # exception from a badly-behaved provider — degrades explanation
        # QUALITY only. The decision fields below are unaffected either
        # way, because they never came from the provider in the first
        # place.
        fallback_raw = fallback.generate(evidence)
        summary = fallback_raw["summary"]
        safety_note = fallback_raw["safety_note"]

    if not safety_note:
        safety_note = default_safety_note(evidence)

    # Decision fields: ALWAYS from evidence, NEVER from `raw`/provider
    # output. This is the enforcement point for the Day 13 safety
    # invariant `action_before_explanation == action_after_explanation`.
    return Explanation(
        summary=summary,
        root_cause=evidence.predicted_root_cause,
        confidence=evidence.predicted_probability,
        action=evidence.policy_action,
        reason=evidence.policy_reason,
        safety_note=safety_note,
        outcome_status=evidence.outcome_status,
    )
