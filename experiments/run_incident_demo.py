"""
Recovery Guardian — Day 12 Incident Scenario Replay

    existing Day 1 incident window
        -> real frozen feature builder
        -> frozen calibrated classifier
        -> root-cause prediction + calibrated probability
        -> frozen Day 7 policy engine
        -> recovery action

This is REPLAY, not a new intelligence subsystem: every payment-failure
event evaluated here is a real, pre-existing row of the frozen
data/synthetic_events.csv (see data/generate_data.py's deliberate
110-transaction incident burst around 2026-08-15 22:10-22:40). Nothing is
regenerated, retrained, or re-tuned. The ML model, the calibration, the
feature builder, and the Day 7 policy engine are used exactly as Day
6/7/9 froze them.

GROUND-TRUTH ISOLATION (Day 12 spec section 3 — the critical invariant):

    dataset transaction
        -> canonical PaymentEvent          (via src.ingestion.synthetic_adapter,
                                             which never reads actual_root_cause)
        -> frozen feature builder          (build_features(..., keep_label=False))
        -> frozen calibrated classifier
        -> frozen Day 7 policy
        -> prediction + action

    dataset actual_root_cause  ------------------------------>  evaluation only

`actual_root_cause` is read directly from the raw CSV row for reporting,
kept in a completely separate variable, and is NEVER passed into
PaymentEvent, build_features(), the classifier, or the policy engine.
PaymentEvent itself has no field for it (see src/domain/models.py) — so
this separation is structural, not merely a coding discipline. See
tests/test_incident_demo.py's leakage tests for a direct empirical proof.

STATE ISOLATION: reuses the exact Day 9 GuardianStrategy pattern (see
src/experiment/strategies.py) — `already_executed_actions=frozenset()`
and a fixed evaluation `now` (imported directly from
src.experiment.strategies.EXPERIMENT_EVALUATION_TIME, not a new
constant) — so replaying the same transaction any number of times, in any
order, in any process, never changes its action because of persistence or
idempotency pollution. There is no database write anywhere in this
script.

Run:
    python experiments/run_incident_demo.py
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.models import RecoveryAction
from src.experiment.random_state import derive_transaction_seed
from src.experiment.strategies import EXPERIMENT_EVALUATION_TIME
from src.features.build_features import LABEL_COL, build_features
from src.ingestion.synthetic_adapter import synthetic_to_payment_event
from src.model.calibrated_classifier import CalibratedRootCauseClassifier
from src.model.splitting import train_val_test_split
from src.model.training import DATA_PATH, RANDOM_STATE
from src.policy.engine import RulesPolicyEngine, load_policy_config
from src.recovery.evidence import RecoveryEvidence
from src.recovery.simulator import estimate_outcome

REPO_ROOT = Path(__file__).parent.parent
OUTPUT_PATH = REPO_ROOT / "experiments" / "results" / "day12_incident_demo.json"

# --- Verified incident window (data/generate_data.py's literal injection
# window — see that module's `generate_dataset()`/`summarize()`). This is
# the historically-described window, VERIFIED against the frozen dataset
# below (see verify_incident_window()) rather than trusted blindly.
INCIDENT_START = pd.Timestamp("2026-08-15T22:10:00")
INCIDENT_END = pd.Timestamp("2026-08-15T22:40:00")
EXPECTED_BURST_ROWS = 110  # data/generate_data.py's generate_dataset() default

# Comparison-window convention (Day 12 spec section 7), documented and used
# consistently:
#   INCIDENT window: [start, end]      inclusive-inclusive
#       (matches data/generate_data.py's own summarize() convention:
#        `(df["timestamp"] >= start) & (df["timestamp"] <= end)`)
#   BEFORE window:   [start-60min, start)   half-open, excludes `start` so
#       it never overlaps the incident window's own inclusive start.
#   AFTER window:    (end, end+60min]       half-open, excludes `end` so it
#       never overlaps the incident window's own inclusive end.
BEFORE_START = INCIDENT_START - pd.Timedelta(minutes=60)
AFTER_END = INCIDENT_END + pd.Timedelta(minutes=60)
DENSITY_UNIT_MINUTES = 30  # normalize all densities to "per 30 minutes"

# Reuses the exact Day 9 CRN mechanism (src.experiment.random_state) for
# the OPTIONAL recovery simulation (Day 12 spec section 20). A distinct
# seed value from Day 9's primary experiment seed (42) so this is legible
# as its own, independent run — it reads only the frozen simulator and
# frozen dataset, and neither reads nor writes any Day 9/10 result file.
DAY12_SIMULATION_SEED = 1200


def load_raw_dataset(data_path: Path = DATA_PATH) -> pd.DataFrame:
    """The frozen dataset, unmodified. Not regenerated, not filtered."""
    return pd.read_csv(data_path)


def verify_incident_window(raw_df: pd.DataFrame) -> pd.Index:
    """Verifies (does not assume) the historically-described incident
    window against the actual frozen dataset. STOPS (raises) if the
    dataset does not match the description — see Day 12 spec section 4."""
    ts = pd.to_datetime(raw_df["timestamp"])
    in_window = (ts >= INCIDENT_START) & (ts <= INCIDENT_END)
    window_idx = raw_df.index[in_window]

    if len(window_idx) != EXPECTED_BURST_ROWS:
        raise RuntimeError(
            f"Incident window verification FAILED: expected "
            f"{EXPECTED_BURST_ROWS} transactions in "
            f"[{INCIDENT_START}, {INCIDENT_END}], found {len(window_idx)}. "
            f"Refusing to proceed — the dataset must not be modified to "
            f"force a match."
        )
    return window_idx


def select_comparison_windows(raw_df: pd.DataFrame) -> Tuple[pd.Index, pd.Index, pd.Index]:
    ts = pd.to_datetime(raw_df["timestamp"])
    before_idx = raw_df.index[(ts >= BEFORE_START) & (ts < INCIDENT_START)]
    incident_idx = raw_df.index[(ts >= INCIDENT_START) & (ts <= INCIDENT_END)]
    after_idx = raw_df.index[(ts > INCIDENT_END) & (ts <= AFTER_END)]
    return before_idx, incident_idx, after_idx


def compute_split_membership(raw_df: pd.DataFrame) -> Dict[int, str]:
    """Reproduces the EXACT Day 4 train/validation/test split — same
    split function, same random_state, same label column — never a new
    split. See src/model/splitting.py and src/model/training.py."""
    features_df = build_features(raw_df, keep_label=True)
    train_df, val_df, test_df = train_val_test_split(
        features_df, label_col=LABEL_COL, random_state=RANDOM_STATE
    )
    membership: Dict[int, str] = {}
    for idx in train_df.index:
        membership[idx] = "TRAIN"
    for idx in val_df.index:
        membership[idx] = "VALIDATION"
    for idx in test_df.index:
        membership[idx] = "TEST"
    return membership


def replay_transaction(
    row: pd.Series,
    split_label: str,
    classifier: CalibratedRootCauseClassifier,
    policy: RulesPolicyEngine,
    *,
    simulate: bool = True,
) -> Dict[str, Any]:
    """Runs ONE dataset row through the real, frozen production decision
    path. `actual_root_cause` is read from `row` here ONLY for the return
    record — it is never passed to PaymentEvent (which has no such field),
    build_features(), the classifier, or the policy engine."""
    actual_root_cause = str(row["actual_root_cause"])

    # `synthetic_to_payment_event` never reads `actual_root_cause` (see
    # src/ingestion/synthetic_adapter.py) — PaymentEvent structurally
    # cannot carry it.
    event = synthetic_to_payment_event(row)

    features_df = build_features(pd.DataFrame([event.model_dump()]), keep_label=False)
    prediction = classifier.predict(features_df.iloc[0])

    decision = policy.decide(
        prediction,
        event,
        already_executed_actions=frozenset(),
        now=EXPERIMENT_EVALUATION_TIME,
    )

    record: Dict[str, Any] = {
        "transaction_id": event.transaction_id,
        "timestamp": event.timestamp.isoformat(),
        "amount": round(event.amount, 2),
        "actual_root_cause": actual_root_cause,  # evaluation-only
        "split_membership": split_label,
        "predicted_root_cause": prediction.root_cause.value,
        "calibrated_probability": round(prediction.probability, 6),
        "policy_action": decision.action.value,
        "policy_reason_code": decision.reason_codes[0].value if decision.reason_codes else "",
        "failure_code": event.failure_code,
        "payment_method": event.payment_method,
        "incident_active": event.incident_active,
        "webhook_delay_seconds": round(event.webhook_delay_seconds, 2),
    }

    if simulate:
        evidence = RecoveryEvidence.from_payment_event_and_prediction(event, prediction)
        seed = derive_transaction_seed(event.transaction_id, DAY12_SIMULATION_SEED)
        outcome = estimate_outcome(
            evidence,
            decision.action,
            seed=seed,
            decision_id=f"day12_{event.transaction_id}",
            timestamp=EXPERIMENT_EVALUATION_TIME,
        )
        record["simulated_recovered"] = outcome.recovered
        record["simulated_amount_recovered"] = round(outcome.amount_recovered, 2)
        record["simulated_duplicate_charge_risk"] = outcome.duplicate_charge_risk

    return record


def _density_per_unit(count: int, window_minutes: float) -> float:
    return round(count * (DENSITY_UNIT_MINUTES / window_minutes), 4)


def build_incident_shape_summary(
    raw_df: pd.DataFrame, before_idx: pd.Index, incident_idx: pd.Index, after_idx: pd.Index
) -> Dict[str, Any]:
    before_minutes = (INCIDENT_START - BEFORE_START).total_seconds() / 60.0
    incident_minutes = (INCIDENT_END - INCIDENT_START).total_seconds() / 60.0
    after_minutes = (AFTER_END - INCIDENT_END).total_seconds() / 60.0

    return {
        "metric_type": "failure_density",
        "density_unit_minutes": DENSITY_UNIT_MINUTES,
        "before": {
            "window_start": BEFORE_START.isoformat(),
            "window_end": INCIDENT_START.isoformat(),
            "window_minutes": before_minutes,
            "failed_event_count": int(len(before_idx)),
            "failure_density_per_unit": _density_per_unit(len(before_idx), before_minutes),
        },
        "incident": {
            "window_start": INCIDENT_START.isoformat(),
            "window_end": INCIDENT_END.isoformat(),
            "window_minutes": incident_minutes,
            "failed_event_count": int(len(incident_idx)),
            "failure_density_per_unit": _density_per_unit(len(incident_idx), incident_minutes),
        },
        "after": {
            "window_start": INCIDENT_END.isoformat(),
            "window_end": AFTER_END.isoformat(),
            "window_minutes": after_minutes,
            "failed_event_count": int(len(after_idx)),
            "failure_density_per_unit": _density_per_unit(len(after_idx), after_minutes),
        },
    }


def build_infrastructure_probability_statistics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Section 21's `infrastructure_summary.probability_statistics` — full
    incident-window ground-truth INFRASTRUCTURE cases only."""
    infra_actual = [r for r in records if r["actual_root_cause"] == "INFRASTRUCTURE"]
    if not infra_actual:
        return {
            "ground_truth_count": 0,
            "predicted_class_distribution": {},
            "probability_statistics": None,
        }
    probs = [r["calibrated_probability"] for r in infra_actual]
    predicted_dist = Counter(r["predicted_root_cause"] for r in infra_actual)
    return {
        "ground_truth_count": len(infra_actual),
        "predicted_class_distribution": dict(predicted_dist),
        "probability_statistics": {
            "min": round(min(probs), 6),
            "max": round(max(probs), 6),
            "mean": round(sum(probs) / len(probs), 6),
        },
    }


def build_classifier_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    def _stats(subset: List[Dict[str, Any]]) -> Dict[str, Any]:
        infra_actual = [r for r in subset if r["actual_root_cause"] == "INFRASTRUCTURE"]
        if not infra_actual:
            return {
                "ground_truth_count": 0,
                "predicted_class_distribution": {},
                "correctly_predicted_count": 0,
                "probability_range": None,
                "precision": None,
                "recall": None,
            }
        predicted_dist = Counter(r["predicted_root_cause"] for r in infra_actual)
        correct = sum(1 for r in infra_actual if r["predicted_root_cause"] == "INFRASTRUCTURE")
        probs = [r["calibrated_probability"] for r in infra_actual]

        predicted_infra = [r for r in subset if r["predicted_root_cause"] == "INFRASTRUCTURE"]
        true_positive = sum(1 for r in predicted_infra if r["actual_root_cause"] == "INFRASTRUCTURE")
        precision = (true_positive / len(predicted_infra)) if predicted_infra else None
        recall = (correct / len(infra_actual)) if infra_actual else None

        return {
            "ground_truth_count": len(infra_actual),
            "predicted_class_distribution": dict(predicted_dist),
            "correctly_predicted_count": correct,
            "probability_range": [round(min(probs), 6), round(max(probs), 6)],
            "precision": round(precision, 6) if precision is not None else None,
            "recall": round(recall, 6) if recall is not None else None,
        }

    full_window = _stats(records)
    held_out_test = _stats([r for r in records if r["split_membership"] == "TEST"])
    return {"full_window": full_window, "held_out_test": held_out_test}


def build_policy_summary(records: List[Dict[str, Any]], threshold: float) -> Dict[str, Any]:
    action_dist = Counter(r["policy_action"] for r in records)
    infra_records = [r for r in records if r["actual_root_cause"] == "INFRASTRUCTURE"]
    infra_action_dist = Counter(r["policy_action"] for r in infra_records)
    return {
        "infrastructure_confidence_threshold": threshold,
        "action_distribution": dict(action_dist),
        "infrastructure_action_distribution": dict(infra_action_dist),
    }


def build_webhook_ambiguity_safety_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    wa_records = [r for r in records if r["actual_root_cause"] == "WEBHOOK_AMBIGUITY"]
    action_counts = Counter(r["policy_action"] for r in wa_records)
    block_reconcile_count = action_counts.get(RecoveryAction.BLOCK_RECONCILE.value, 0)
    defer_retry_count = action_counts.get(RecoveryAction.DEFER_RETRY.value, 0)
    other_count = len(wa_records) - block_reconcile_count - defer_retry_count
    safety_pass = (defer_retry_count == 0) and (block_reconcile_count == len(wa_records))

    if not safety_pass:
        raise RuntimeError(
            "SAFETY CHECK FAILED: a WEBHOOK_AMBIGUITY transaction in the "
            "incident window did not route to BLOCK_RECONCILE. Refusing to "
            "continue. Do not weaken the policy, the model, or this check "
            "to work around this. action_counts=" + repr(dict(action_counts))
        )

    return {
        "case_count": len(wa_records),
        "block_reconcile_count": block_reconcile_count,
        "defer_retry_count": defer_retry_count,
        "other_count": other_count,
        "safety_pass": safety_pass,
    }


def build_non_infrastructure_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    non_infra = [r for r in records if r["actual_root_cause"] != "INFRASTRUCTURE"]
    by_actual_class: Dict[str, Any] = {}
    misclassified_as_infrastructure = []
    for actual_class in sorted({r["actual_root_cause"] for r in non_infra}):
        subset = [r for r in non_infra if r["actual_root_cause"] == actual_class]
        predicted_dist = Counter(r["predicted_root_cause"] for r in subset)
        correct = sum(1 for r in subset if r["predicted_root_cause"] == actual_class)
        by_actual_class[actual_class] = {
            "count": len(subset),
            "predicted_class_distribution": dict(predicted_dist),
            "correctly_predicted_count": correct,
        }
        for r in subset:
            if r["predicted_root_cause"] == "INFRASTRUCTURE":
                misclassified_as_infrastructure.append(r["transaction_id"])

    return {
        "cases_analyzed": len(non_infra),
        "by_actual_class": by_actual_class,
        "misclassified_as_infrastructure_count": len(misclassified_as_infrastructure),
        "misclassified_as_infrastructure_transaction_ids": misclassified_as_infrastructure,
    }


def build_simulated_recovery_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Reuses the exact Day 8 estimate_outcome() / Day 9 CRN mechanism.
    Every figure here is SIMULATED / COUNTERFACTUAL — never labeled as
    observed or actual recovered revenue (Day 12 spec section 20)."""
    total_simulated_amount_recovered = round(
        sum(r["simulated_amount_recovered"] for r in records if r.get("simulated_recovered")), 2
    )
    recovered_count = sum(1 for r in records if r.get("simulated_recovered"))
    duplicate_risk_count = sum(1 for r in records if r.get("simulated_duplicate_charge_risk"))
    return {
        "label": "SIMULATED / COUNTERFACTUAL — not observed production revenue",
        "method": "src.recovery.simulator.estimate_outcome(), Day 8, unmodified",
        "crn_methodology": "src.experiment.random_state.derive_transaction_seed(), Day 9, unmodified",
        "simulation_seed": DAY12_SIMULATION_SEED,
        "transactions_evaluated": len(records),
        "simulated_recovered_count": recovered_count,
        "simulated_total_amount_recovered": total_simulated_amount_recovered,
        "simulated_duplicate_charge_risk_count": duplicate_risk_count,
    }


def run_replay(data_path: Path = DATA_PATH, commit: str = "32a2e05") -> Dict[str, Any]:
    raw_df = load_raw_dataset(data_path)
    window_idx = verify_incident_window(raw_df)
    before_idx, incident_idx, after_idx = select_comparison_windows(raw_df)
    assert list(incident_idx) == list(window_idx)

    split_membership = compute_split_membership(raw_df)
    cfg = load_policy_config()
    infra_threshold = cfg.confidence_thresholds["INFRASTRUCTURE"]

    classifier = CalibratedRootCauseClassifier()
    policy = RulesPolicyEngine(config=cfg)

    # Chronological order for the narrative and for deterministic output.
    ordered_idx = sorted(incident_idx, key=lambda i: (raw_df.loc[i, "timestamp"], raw_df.loc[i, "transaction_id"]))

    records: List[Dict[str, Any]] = []
    for idx in ordered_idx:
        row = raw_df.loc[idx]
        split_label = split_membership.get(idx, "UNKNOWN")
        records.append(replay_transaction(row, split_label, classifier, policy))

    split_counts = Counter(r["split_membership"] for r in records)
    total = len(records)

    artifact = {
        "metadata": {
            "commit": commit,
            "dataset_path": str(Path("data") / "synthetic_events.csv"),
            "incident_window": {"start": INCIDENT_START.isoformat(), "end": INCIDENT_END.isoformat()},
            "before_window": {"start": BEFORE_START.isoformat(), "end": INCIDENT_START.isoformat()},
            "after_window": {"start": INCIDENT_END.isoformat(), "end": AFTER_END.isoformat()},
            "window_convention": "incident=[start,end] inclusive; before=[start-60m,start) half-open; after=(end,end+60m] half-open",
            "metric_type": "failure_density",
            "dataset_contains_successful_transactions": False,
            "policy_version": cfg.policy_version,
            "infrastructure_confidence_threshold": infra_threshold,
            "split_random_state": RANDOM_STATE,
        },
        "summary": {
            "before_count": int(len(before_idx)),
            "incident_count": int(len(incident_idx)),
            "after_count": int(len(after_idx)),
            **build_incident_shape_summary(raw_df, before_idx, incident_idx, after_idx),
        },
        "split_membership": {
            "train_count": split_counts.get("TRAIN", 0),
            "validation_count": split_counts.get("VALIDATION", 0),
            "test_count": split_counts.get("TEST", 0),
            "total": total,
            "train_pct": round(100.0 * split_counts.get("TRAIN", 0) / total, 2) if total else None,
            "validation_pct": round(100.0 * split_counts.get("VALIDATION", 0) / total, 2) if total else None,
            "test_pct": round(100.0 * split_counts.get("TEST", 0) / total, 2) if total else None,
            "training_membership_limitation": (
                "The full incident replay contains a substantial proportion of "
                "transactions that were present in the classifier training data. "
                "Therefore the full-window classifier result is a replay "
                "behavior demonstration, not an out-of-sample generalization "
                "claim. The held-out test subset below is the defensible "
                "out-of-sample view."
                if split_counts.get("TRAIN", 0) > total / 2
                else "Training-set transactions do not form a majority of the incident window."
            ),
        },
        "classifier_summary": build_classifier_summary(records),
        "infrastructure_summary": build_infrastructure_probability_statistics(records),
        "policy_summary": build_policy_summary(records, infra_threshold),
        "webhook_ambiguity_safety": build_webhook_ambiguity_safety_summary(records),
        "non_infrastructure_summary": build_non_infrastructure_summary(records),
        "simulated_recovery_summary": build_simulated_recovery_summary(records),
        "transactions": records,
    }
    return artifact


def print_console_narrative(artifact: Dict[str, Any]) -> None:
    meta = artifact["metadata"]
    summary = artifact["summary"]
    split = artifact["split_membership"]
    classifier_summary = artifact["classifier_summary"]
    policy_summary = artifact["policy_summary"]
    safety = artifact["webhook_ambiguity_safety"]
    non_infra = artifact["non_infrastructure_summary"]

    print("=" * 60)
    print("RECOVERY GUARDIAN")
    print("INCIDENT SCENARIO REPLAY")
    print("=" * 60)

    print("\nINCIDENT WINDOW")
    print(f"    verified start: {meta['incident_window']['start']}")
    print(f"    verified end:   {meta['incident_window']['end']}")
    print(f"    transaction count: {summary['incident_count']}")

    print("\nBASELINE VS INCIDENT")
    print(f"    metric type: {meta['metric_type']} (dataset contains only failed-payment "
          f"events, so no success denominator exists — see LIMITATIONS)")
    b, i, a = summary["before"], summary["incident"], summary["after"]
    unit = summary["density_unit_minutes"]
    print(f"    before:  {b['failed_event_count']} events over {b['window_minutes']:.0f} min "
          f"(density {b['failure_density_per_unit']} per {unit} min)")
    print(f"    during:  {i['failed_event_count']} events over {i['window_minutes']:.0f} min "
          f"(density {i['failure_density_per_unit']} per {unit} min)")
    print(f"    after:   {a['failed_event_count']} events over {a['window_minutes']:.0f} min "
          f"(density {a['failure_density_per_unit']} per {unit} min)")

    print("\nDATASET SPLIT DISCLOSURE")
    print(f"    train:      {split['train_count']} ({split['train_pct']}%)")
    print(f"    validation: {split['validation_count']} ({split['validation_pct']}%)")
    print(f"    test:       {split['test_count']} ({split['test_pct']}%)")
    print(f"    {split['training_membership_limitation']}")

    print("\nINFRASTRUCTURE DETECTION")
    fw = classifier_summary["full_window"]
    ho = classifier_summary["held_out_test"]
    print(f"    full-window result: {fw['correctly_predicted_count']}/{fw['ground_truth_count']} "
          f"correctly predicted INFRASTRUCTURE (precision={fw['precision']}, recall={fw['recall']}, "
          f"probability range={fw['probability_range']})")
    print(f"    held-out-test result: {ho['correctly_predicted_count']}/{ho['ground_truth_count']} "
          f"correctly predicted INFRASTRUCTURE (precision={ho['precision']}, recall={ho['recall']}, "
          f"probability range={ho['probability_range']})")

    print("\nPOLICY RESPONSE")
    print(f"    actual threshold (src/policy/rules.yaml, INFRASTRUCTURE): "
          f"{policy_summary['infrastructure_confidence_threshold']}")
    print(f"    action distribution (all {summary['incident_count']} window transactions): "
          f"{policy_summary['action_distribution']}")
    print(f"    INFRASTRUCTURE-ground-truth action distribution: "
          f"{policy_summary['infrastructure_action_distribution']}")

    print("\nSAFETY CHECK")
    print(f"    WEBHOOK_AMBIGUITY cases: {safety['case_count']}")
    print(f"    BLOCK_RECONCILE: {safety['block_reconcile_count']}")
    print(f"    DEFER_RETRY: {safety['defer_retry_count']}")
    print(f"    RESULT: {'PASS' if safety['safety_pass'] else 'FAIL'}")

    print("\nNON-INFRASTRUCTURE DURING INCIDENT")
    print(f"    cases analyzed: {non_infra['cases_analyzed']}")
    print(f"    misclassified as INFRASTRUCTURE: "
          f"{non_infra['misclassified_as_infrastructure_count']}")
    for cls, stats in non_infra["by_actual_class"].items():
        print(f"      {cls}: {stats['correctly_predicted_count']}/{stats['count']} correctly predicted")

    print("\nLIMITATIONS")
    print("    training-membership limitation: full-window results include "
          "TRAIN-split transactions; see DATASET SPLIT DISCLOSURE above — "
          "the held-out-test result is the defensible generalization view.")
    print("    synthetic-data limitation: all events are synthetic "
          "(data/generate_data.py); no real Razorpay production traffic "
          "was used anywhere in this replay.")
    print("    monitoring limitation: this is a historical replay of an "
          "existing dataset window, not a live incident detector — no "
          "real-time monitoring capability exists.")
    print()


def main() -> None:
    artifact = run_replay()
    print_console_narrative(artifact)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(artifact, f, indent=2, sort_keys=True)
    print(f"Structured artifact written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
