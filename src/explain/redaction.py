"""
Recovery Guardian — Day 13 Provider Redaction Boundary

Everything sent to an external LLM provider passes through
`redact_evidence_for_provider()` first. Today `ExplanationEvidence`
carries no secrets, tokens, or free-text customer PII at all — every
field on it is either a numeric fact, a controlled-vocabulary string
(`failure_code`, `payment_method`, an enum `.value`), or a
transaction/policy identifier — so this function's job is currently an
explicit ALLOWLIST plus a defensive pattern check, not active stripping
of anything actually present. It exists as a permanent, inspectable
boundary precisely so a future evidence field is never sent to a
provider merely because it exists on the dataclass.

Does NOT modify `PaymentEvent` or `ExplanationEvidence` — redaction
happens only at this boundary, immediately before constructing a
provider request.
"""

import re
from typing import Any, Dict

from src.explain.evidence import ExplanationEvidence

# Defense in depth: if a future evidence field's value ever happens to
# look like a credential, refuse to send it rather than trust the
# allowlist alone. Mirrors the project's existing secret-scan patterns
# (see the Day 7-12 master prompts' secret-scan regex).
_SECRET_LIKE_PATTERN = re.compile(
    r"rzp_(live|test)_|sk_(live|test)_|AKIA[0-9A-Z]{16}|BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY",
    re.IGNORECASE,
)

# Explicit allowlist of fields a provider may ever see. Anything on
# ExplanationEvidence not listed here is never sent, by construction.
_ALLOWED_FIELDS = (
    "transaction_id",
    "amount",
    "payment_method",
    "failure_code",
    "retry_count",
    "webhook_delay_seconds",
    "incident_active",
    "predicted_root_cause",
    "predicted_probability",
    "policy_action",
    "policy_reason",
    "policy_version",
    "relevant_threshold",
    "safety_flags",
    "outcome_status",
    "outcome_recovered",
    "outcome_amount",
    "outcome_reason",
)


class UnsafeEvidenceError(ValueError):
    """Raised when a value that looks like a credential is about to be
    sent to a provider. Fails closed rather than silently sending it."""


def redact_evidence_for_provider(evidence: ExplanationEvidence) -> Dict[str, Any]:
    redacted: Dict[str, Any] = {}
    for field_name in _ALLOWED_FIELDS:
        value = getattr(evidence, field_name)
        if isinstance(value, str) and _SECRET_LIKE_PATTERN.search(value):
            raise UnsafeEvidenceError(
                f"Refusing to send field '{field_name}': value matches a "
                f"credential-like pattern."
            )
        redacted[field_name] = value
    return redacted
