"""
Recovery Guardian — Day 14 Judge-Facing Product Demo

    Input event
        -> canonical PaymentEvent           (src.ingestion.synthetic_adapter)
        -> feature builder                  (src.features.build_features)
        -> calibrated ML classifier         (src.model.calibrated_classifier)
        -> RootCausePrediction
        -> Day 7 policy engine              (src.policy.engine)
        -> PolicyDecision / RecoveryAction
        -> Day 8 counterfactual simulator   (src.recovery.simulator)
        -> RecoveryOutcome (SIMULATED)
        -> Day 13 explanation layer         (src.explain.service)
        -> Explanation

This is a PRODUCTIZATION of the already-frozen system — it introduces no
new ML, no new policy, no new simulation logic, and no new explanation
authority. It calls the real `src.pipeline.pipeline.run_pipeline()`
(Day 3-8, unmodified) against an isolated in-memory SQLite connection —
the exact pattern already established by Day 9's fresh test fixtures and
Day 11/12's integration tests — so running this demo touches neither the
real `recovery_guardian.db` nor the idempotency guard's production state.

Ground-truth firewall: the three scenario transaction IDs below were
identified offline by filtering on the CALIBRATED CLASSIFIER'S OWN
predicted root cause and probability (the same technique already used by
Day 11/13's test fixtures, e.g. `_find_real_row_predicted_as`) — never by
inspecting `actual_root_cause`. At demo runtime, `actual_root_cause` is
read from the row (if present) ONLY after the real decision has already
been produced, purely for an optional reference line, and is never
passed into `PaymentEvent`, the feature builder, the classifier, the
policy engine, or the explanation layer (see
`tests/test_judge_demo.py::test_ground_truth_never_reaches_decision_path`).

Run:
    python experiments/run_judge_demo.py                 # all scenarios
    python experiments/run_judge_demo.py --scenario webhook_ambiguity
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))

from src.db import SCHEMA
from src.explain.evidence import SIMULATED
from src.explain.provider import ClaudeExplanationProvider, DeterministicFallbackProvider
from src.explain.service import explain_decision
from src.ingestion.synthetic_adapter import synthetic_to_payment_event
from src.model.training import DATA_PATH
from src.pipeline.pipeline import run_pipeline
from src.policy.engine import load_policy_config

REPO_ROOT = Path(__file__).parent.parent
OUTPUT_PATH = REPO_ROOT / "experiments" / "results" / "day14_demo.json"

# Fixed, deterministic scenario selections — identified offline by the
# calibrated classifier's OWN predicted root cause / probability, never
# by actual_root_cause. Same real dataset rows already used and verified
# by Day 13's representative-case tests (tests/test_explain.py).
SCENARIOS = {
    "webhook_ambiguity": {
        "transaction_id": "txn_000536_9f0ef7",
        "label": "Primary safety scenario — WEBHOOK_AMBIGUITY",
    },
    "infrastructure_high_confidence": {
        "transaction_id": "txn_001453_f609ab",
        "label": "Secondary scenario — INFRASTRUCTURE, high confidence",
    },
    "infrastructure_low_confidence": {
        "transaction_id": "txn_001247_939b14",
        "label": "Secondary scenario — INFRASTRUCTURE, low confidence",
    },
}


def _fresh_isolated_conn() -> sqlite3.Connection:
    """An in-memory SQLite connection, never the real recovery_guardian.db
    — the exact isolation pattern Day 9/11/12's tests already established
    (see e.g. tests/test_razorpay_integration.py's fresh_conn())."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _load_row(transaction_id: str) -> pd.Series:
    raw_df = pd.read_csv(DATA_PATH)
    matches = raw_df[raw_df["transaction_id"] == transaction_id]
    if matches.empty:
        raise RuntimeError(f"transaction_id {transaction_id} not found in frozen dataset")
    return matches.iloc[0]


def _select_provider():
    """LLM_ENABLED is an explicit kill switch (see .env.example): unless
    it is exactly "true", the demo never attempts a Claude call at all —
    no network access, no credential lookup. When enabled,
    ClaudeExplanationProvider is still safe to construct with a missing
    key: explain_decision() catches any provider failure and falls back
    to the deterministic provider automatically."""
    llm_enabled = os.environ.get("LLM_ENABLED", "false").strip().lower() == "true"
    if not llm_enabled:
        return DeterministicFallbackProvider()
    return ClaudeExplanationProvider(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def run_scenario(scenario_key: str) -> Dict[str, Any]:
    scenario = SCENARIOS[scenario_key]
    row = _load_row(scenario["transaction_id"])

    # Ground truth read here ONLY for an optional, post-hoc reference
    # line -- never passed to anything below this point.
    actual_root_cause_reference = str(row.get("actual_root_cause", ""))

    event = synthetic_to_payment_event(row)

    conn = _fresh_isolated_conn()
    try:
        record = run_pipeline(event, conn=conn)
    finally:
        conn.close()

    provider = _select_provider()
    explanation = explain_decision(
        record.event,
        record.prediction,
        record.policy,
        outcome=record.outcome,
        outcome_status=SIMULATED,
        provider=provider,
    )

    cfg = load_policy_config()
    threshold = cfg.confidence_thresholds.get(record.prediction.root_cause.value)

    action_before_explanation = record.policy.action.value
    action_after_explanation = explanation.action

    return {
        "scenario": scenario_key,
        "scenario_label": scenario["label"],
        "transaction_id": record.event.transaction_id,
        "payment_event_summary": {
            "_provenance": "OBSERVED (synthetic dataset transaction fields)",
            "amount": round(record.event.amount, 2),
            "payment_method": record.event.payment_method,
            "failure_code": record.event.failure_code,
            "retry_count": record.event.retry_count,
            "webhook_delay_seconds": round(record.event.webhook_delay_seconds, 2),
            "incident_active": record.event.incident_active,
        },
        "prediction": {
            "_provenance": "OBSERVED (frozen calibrated classifier output)",
            "predicted_root_cause": record.prediction.root_cause.value,
            "predicted_probability": round(record.prediction.probability, 6),
            "model_version": record.prediction.model_version,
        },
        "policy": {
            "_provenance": "OBSERVED (frozen Day 7 deterministic policy engine output)",
            "policy_action": record.policy.action.value,
            "policy_reason": record.policy.reason_codes[0].value if record.policy.reason_codes else "",
            "policy_version": record.policy.policy_version,
            "threshold_if_applicable": threshold,
        },
        "outcome": {
            "_provenance": "SIMULATED (Day 8 counterfactual estimator — not observed production revenue)",
            "recovered": record.outcome.recovered if record.outcome else None,
            "amount_recovered": round(record.outcome.amount_recovered, 2) if record.outcome else None,
            "duplicate_charge_risk": record.outcome.duplicate_charge_risk if record.outcome else None,
        },
        "explanation": {
            "_provenance": "LLM prose (or deterministic fallback) — decision fields below are re-derived from evidence, never from the provider",
            "summary": explanation.summary,
            "safety_note": explanation.safety_note,
        },
        "safety_invariant_check": {
            "action_before_explanation": action_before_explanation,
            "action_after_explanation": action_after_explanation,
            "unchanged": action_before_explanation == action_after_explanation,
        },
        "ground_truth_reference": {
            "_provenance": "OBSERVED (synthetic label) — diagnostic display only, read AFTER the decision above; never used to select the transaction, the prediction, the action, or the explanation",
            "actual_root_cause": actual_root_cause_reference,
        },
    }


def print_console_narrative(results: Dict[str, Dict[str, Any]]) -> None:
    print("=" * 60)
    print("RECOVERY GUARDIAN")
    print("JUDGE-FACING DEMONSTRATION")
    print("=" * 60)
    print()
    print("A payment event arrives. Guardian normalizes it into a canonical")
    print("PaymentEvent, the calibrated classifier identifies the most likely")
    print("failure cause, and the deterministic policy engine decides what")
    print("action is safe. The explanation layer describes the decision but")
    print("cannot change it.")

    for key, result in results.items():
        print()
        print("-" * 60)
        print(result["scenario_label"])
        print("-" * 60)
        print(f"Transaction:              {result['transaction_id']}")
        pe = result["payment_event_summary"]
        print(f"Amount / method:          {pe['amount']} / {pe['payment_method']}")
        print(f"Failure code:             {pe['failure_code']}")
        pred = result["prediction"]
        print(f"Predicted root cause:     {pred['predicted_root_cause']} "
              f"(probability {pred['predicted_probability']:.4f}) [OBSERVED]")
        pol = result["policy"]
        threshold_str = f" (threshold {pol['threshold_if_applicable']})" if pol["threshold_if_applicable"] is not None else " (no confidence threshold — hard safety override)"
        print(f"Policy action:            {pol['policy_action']}{threshold_str} [OBSERVED]")
        print(f"Policy reason:            {pol['policy_reason']}")
        out = result["outcome"]
        print(f"Simulated outcome:        recovered={out['recovered']}, "
              f"amount={out['amount_recovered']}, "
              f"duplicate_charge_risk={out['duplicate_charge_risk']} [SIMULATED]")
        exp = result["explanation"]
        print(f"Explanation:              {exp['summary']}")
        print(f"Safety note:              {exp['safety_note']}")
        chk = result["safety_invariant_check"]
        print(f"Action before explanation: {chk['action_before_explanation']}")
        print(f"Action after explanation:  {chk['action_after_explanation']}")
        print(f"Unchanged:                 {chk['unchanged']}")
        gt = result["ground_truth_reference"]
        print(f"(Reference only, not used in the decision above — actual_root_cause: "
              f"{gt['actual_root_cause']})")

    print()
    print("-" * 60)
    print("CONTRAST: naive retry-everything on the WEBHOOK_AMBIGUITY population")
    print("(Day 9 simulated result, seed 42, 25 WEBHOOK_AMBIGUITY transactions):")
    print("  Naive Retry:  68% simulated recovery, 12 duplicate-charge-risk outcomes")
    print("  Rules-only:   20% simulated recovery, 3 duplicate-charge-risk outcomes")
    print("  Guardian:      0% simulated recovery, 0 duplicate-charge-risk outcomes")
    print("Guardian recovers less in this population because BLOCK_RECONCILE never")
    print("attempts an automated retry when payment state is ambiguous — that is the")
    print("safety trade-off being demonstrated, not a shortcoming to explain away.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Recovery Guardian — Day 14 judge-facing demo")
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        default=None,
        help="Run a single scenario. Omit to run all scenarios.",
    )
    args = parser.parse_args()

    scenario_keys = [args.scenario] if args.scenario else list(SCENARIOS.keys())
    results = {key: run_scenario(key) for key in scenario_keys}

    print_console_narrative(results)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)
    print(f"Structured artifact written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
