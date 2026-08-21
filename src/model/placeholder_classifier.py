"""
Recovery Guardian — Day 3 Placeholder Root-Cause Classifier

STRUCTURAL PLACEHOLDER ONLY. This exists purely to give the Day 3 pipeline
something that satisfies the RootCauseClassifier interface end to end, so
the plumbing (feature builder -> classifier -> policy engine -> audit ->
SQLite) can be proven out before there is a real model to plug in.

It is deliberately:
    - non-informative: probability is a fixed 0.50, not a calibrated
      confidence. It must never be read as "the model is 50% sure" —
      there is no model here yet.
    - feature-blind: it does not inspect failure_code, amount, retry_count,
      incident_active, customer history, gateway error rate, or any other
      signal. Reading `features` here beyond identifying the transaction
      would be building hidden rule-based logic disguised as a placeholder,
      which would contaminate the Day 9 "rules-only" baseline that must be
      implemented completely independently for the three-way experiment to
      be a fair comparison.

This will be REPLACED by the trained + calibrated Logistic Regression
classifier during Day 4-6 (see src/model/train_classifier.py,
src/model/calibrate.py once they exist). Nothing here should be extended
incrementally toward that — it should be deleted and swapped out.
"""

from typing import Any, Mapping

from src.domain.models import RootCause, RootCausePrediction

MODEL_VERSION = "placeholder-v1"


class RootCauseClassifier:
    """Day 3 structural placeholder. See module docstring."""

    def predict(self, features: Mapping[str, Any]) -> RootCausePrediction:
        """Args:
            features: one row of the feature-builder output (must contain
                `transaction_id` for record-keeping). Every other value in
                `features` is intentionally ignored — see module docstring.
        """
        return RootCausePrediction(
            transaction_id=str(features["transaction_id"]),
            root_cause=RootCause.CARD_DECLINE,
            probability=0.50,
            model_version=MODEL_VERSION,
        )
