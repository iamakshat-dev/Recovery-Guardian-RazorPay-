"""
Recovery Guardian — Day 13 Explanation Output

`Explanation` is the final, structured result handed back to a caller
(judge-facing console, a future API endpoint, etc.). Its structured
fields (`root_cause`, `confidence`, `action`, `reason`, `outcome_status`)
are ALWAYS populated by `src.explain.service.explain_decision()` directly
from `ExplanationEvidence` — never from provider output. Only `summary`
and `safety_note` are provider-generated prose. See
`src/explain/service.py`'s module docstring for the exact mechanism that
guarantees this.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Explanation:
    summary: str
    root_cause: str
    confidence: float
    action: str
    reason: str
    safety_note: str
    outcome_status: str

    def to_dict(self) -> dict:
        return asdict(self)
