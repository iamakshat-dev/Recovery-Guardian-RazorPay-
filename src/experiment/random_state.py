"""
Recovery Guardian — Day 9 Common Random Numbers (CRN)

Derives a deterministic per-transaction seed from (transaction_id,
experiment_seed) using SHA-256 — NEVER Python's built-in `hash()`, which is
randomized per-process via PYTHONHASHSEED and would silently break
cross-process reproducibility (Day 9 spec sections 17 and 52).

Day 8 API compatibility finding (see docs/architecture.md's Day 9
section): `src.recovery.simulator.estimate_outcome`'s existing `seed`
keyword parameter already provides exactly the CRN property Day 9 needs.
Verified empirically before writing any Day 9 code: holding `seed`
constant while varying only `action` produces the identical underlying
`random.Random(seed)` draw sequence regardless of which action is being
evaluated — only the action-specific probability
(`probability_of_recovery`, and the private duplicate-charge-risk
probability, both unmodified from Day 8) determines the outcome. This is
Situation B (existing injectable-randomness interface sufficient) — NOT
Situation C. No change to src/recovery/simulator.py was made or needed.

This module derives exactly ONE seed per transaction (not one per
stochastic event): Day 8's `estimate_outcome` internally draws from ONE
`random.Random(seed)` stream for both the recovery event and the
duplicate-charge-risk event, in that fixed order — holding the seed
constant reproduces both draws identically across strategies without
Day 9 needing to know or reconstruct that internal ordering itself.
"""

import hashlib


def derive_transaction_seed(transaction_id: str, experiment_seed: int) -> int:
    """Deterministic, cross-process-stable seed for one transaction under
    one experiment configuration. Same transaction_id + same
    experiment_seed always produces the same integer, on any machine, in
    any process, any Python version — unlike `hash()`."""
    digest = hashlib.sha256(f"{transaction_id}:{experiment_seed}".encode()).hexdigest()
    return int(digest[:16], 16)
