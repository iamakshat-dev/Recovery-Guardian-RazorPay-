"""
Recovery Guardian — Day 8 Batch Simulation (minimal, strategy-agnostic)

    simulate_batch(evidence_batch, action_selector) -> list[RecoveryOutcome]

This is ONLY the batch mechanism Day 9/10 will need — it does NOT embed
any particular strategy. `action_selector` is any callable
`(RecoveryEvidence) -> RecoveryAction`; a naive "always retry" selector, a
rules-only selector, and Guardian's real policy-driven selector are all
equally valid callers, and all of them route through the exact same
estimate_outcome() underneath. This module intentionally does NOT
implement any of those three selectors — that's Day 9/10 work.
"""

from typing import Callable, List, Optional

from src.domain.models import RecoveryAction, RecoveryOutcome
from src.recovery.evidence import RecoveryEvidence
from src.recovery.simulator import estimate_outcome

ActionSelector = Callable[[RecoveryEvidence], RecoveryAction]


def simulate_batch(
    evidence_batch: List[RecoveryEvidence],
    action_selector: ActionSelector,
    *,
    seed: Optional[int] = None,
) -> List[RecoveryOutcome]:
    """Run `action_selector` over every evidence item, then score each
    chosen action through the one shared estimate_outcome(). Returns one
    RecoveryOutcome per input item, in the same order.

    `seed`, if given, is combined with each item's index so every call in
    the batch gets a distinct-but-deterministic seed (rather than every
    item reusing the exact same seed, which would correlate their random
    draws in a way a real batch of independent transactions wouldn't)."""
    outcomes = []
    for i, evidence in enumerate(evidence_batch):
        action = action_selector(evidence)
        item_seed = None if seed is None else seed + i
        outcomes.append(estimate_outcome(evidence, action, seed=item_seed))
    return outcomes


def total_recovered(outcomes: List[RecoveryOutcome]) -> float:
    return sum(o.amount_recovered for o in outcomes)


def total_amount_at_risk(evidence_batch: List[RecoveryEvidence]) -> float:
    return sum(e.amount for e in evidence_batch)
