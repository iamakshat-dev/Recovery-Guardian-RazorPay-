"""
Recovery Guardian — Day 15 Frontend Data-Plumbing Script (Option A)

    authoritative JSON artifact
            -> THIS SCRIPT (read-only)
            -> frontend/src/data/snapshot.ts (typed, committed)
            -> React UI

This script may ONLY read, validate, select, type-annotate, and format
values already present in the frozen experiment artifacts. It MUST NOT
recompute any metric, recalculate a recovery rate or duplicate-risk
count, change a transaction population, filter transactions, reinterpret
a result, or invent a missing value. Every numeric value written into
`snapshot.ts` is copied verbatim (only rounded for display, never
recalculated) from one of:

    experiments/results/day9_seed_42_aggregate.json   (Day 9, frozen)
    experiments/results/day12_incident_demo.json       (Day 12, frozen)
    experiments/results/day14_demo.json                (Day 14, frozen)

All three are produced by running the existing, frozen, unmodified
scripts (`experiments/run_day9_experiment.py --seed 42`,
`experiments/run_incident_demo.py`, `experiments/run_judge_demo.py`) —
never by this script. If any artifact is missing, this script fails
loudly with instructions to generate it, rather than fabricating
placeholder data.

Milestone 2 addition: the Day 14 artifact supplies the transaction-level
scenario traces (payment event fields, predicted root cause/probability,
policy action/reason/threshold) the interactive Decision Pipeline needs.
`threshold_if_applicable` is copied verbatim from that artifact, which
itself reads `src/policy/rules.yaml` via `load_policy_config()` inside
`run_judge_demo.py` — this script never re-reads the policy YAML
directly and never hardcodes a threshold number.

Milestone 3 addition (Explainability + Incident Replay): extends the
SAME two record types M2 already reads — no second artifact and no
second scenario/incident data model:
  - `_day14_scenario()` now additionally copies each scenario's
    `explanation` object (`summary`, `safety_note`, `_provenance`) from
    the SAME per-scenario dict (`s = day14[scenario_key]`) M2 already
    reads every other scenario field from. There is no separate
    "explanation artifact" to identity-cross-check against — it is the
    same record, so no transaction_id/scenario mismatch is possible.
  - `build_snapshot()`'s `day12` section now additionally copies the
    before/incident/after failure-density windows and the simulated
    recovery summary from the SAME `day12` dict already loaded for the
    class-distribution/split-membership fields.

Run:
    python3 scripts/generate_frontend_snapshot.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).parent.parent
RESULTS_DIR = REPO_ROOT / "experiments" / "results"
DAY9_PATH = RESULTS_DIR / "day9_seed_42_aggregate.json"
DAY9_SENSITIVITY_SEEDS = [43, 44]
DAY9_SENSITIVITY_PATHS = {seed: RESULTS_DIR / f"day9_seed_{seed}_aggregate.json" for seed in DAY9_SENSITIVITY_SEEDS}
DAY12_PATH = RESULTS_DIR / "day12_incident_demo.json"
DAY14_PATH = RESULTS_DIR / "day14_demo.json"
EXPECTED_DAY14_SCENARIOS = ["webhook_ambiguity", "infrastructure_high_confidence", "infrastructure_low_confidence"]
OUTPUT_PATH = REPO_ROOT / "frontend" / "src" / "data" / "snapshot.ts"


class SnapshotSourceError(RuntimeError):
    pass


def _require_file(path: Path, generate_command: str) -> Dict[str, Any]:
    if not path.exists():
        raise SnapshotSourceError(
            f"Required authoritative artifact not found: {path}\n"
            f"Generate it first with the existing, frozen script:\n"
            f"    {generate_command}"
        )
    with open(path) as f:
        return json.load(f)


def _validate_numeric(value: Any, field_path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SnapshotSourceError(f"{field_path} is not numeric: {value!r}")
    return float(value)


def _validate_int(value: Any, field_path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SnapshotSourceError(f"{field_path} is not an integer: {value!r}")
    return value


def _strategy_row(by_strategy: Dict[str, Any], strategy: str) -> Dict[str, Any]:
    if strategy not in by_strategy:
        raise SnapshotSourceError(f"by_strategy missing expected key: {strategy}")
    row = by_strategy[strategy]
    return {
        "simulatedAmountRecovered": round(_validate_numeric(row["simulated_amount_recovered"], f"{strategy}.simulated_amount_recovered"), 2),
        "recoveryRate": _validate_numeric(row["recovery_rate"], f"{strategy}.recovery_rate"),
        "duplicateChargeRiskCount": _validate_int(row["duplicate_charge_risk_count"], f"{strategy}.duplicate_charge_risk_count"),
        "transactionsEvaluated": _validate_int(row["transactions_evaluated"], f"{strategy}.transactions_evaluated"),
        "totalAmountAtRisk": round(_validate_numeric(row["total_amount_at_risk"], f"{strategy}.total_amount_at_risk"), 2),
    }


def _webhook_ambiguity_row(by_root_cause: Dict[str, Any], strategy: str) -> Dict[str, Any]:
    wa = by_root_cause.get("WEBHOOK_AMBIGUITY")
    if wa is None:
        raise SnapshotSourceError("by_root_cause missing WEBHOOK_AMBIGUITY")
    row = wa.get(strategy)
    if row is None:
        raise SnapshotSourceError(f"WEBHOOK_AMBIGUITY missing strategy: {strategy}")
    return {
        "recoveryRate": _validate_numeric(row["recovery_rate"], f"WEBHOOK_AMBIGUITY.{strategy}.recovery_rate"),
        "duplicateChargeRiskCount": _validate_int(row["duplicate_charge_risk_count"], f"WEBHOOK_AMBIGUITY.{strategy}.duplicate_charge_risk_count"),
        "transactionsEvaluated": _validate_int(row["transactions_evaluated"], f"WEBHOOK_AMBIGUITY.{strategy}.transactions_evaluated"),
        "totalAmountAtRisk": round(_validate_numeric(row["total_amount_at_risk"], f"WEBHOOK_AMBIGUITY.{strategy}.total_amount_at_risk"), 2),
    }


def _validate_str(value: Any, field_path: str) -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotSourceError(f"{field_path} is not a non-empty string: {value!r}")
    return value


def _validate_probability(value: Any, field_path: str) -> float:
    v = _validate_numeric(value, field_path)
    if not (0.0 <= v <= 1.0):
        raise SnapshotSourceError(f"{field_path} is not a valid probability (0-1): {v}")
    return v


def _day14_scenario(day14: Dict[str, Any], scenario_key: str) -> Dict[str, Any]:
    if scenario_key not in day14:
        raise SnapshotSourceError(f"day14_demo.json missing required scenario: {scenario_key}")
    s = day14[scenario_key]
    p = f"{scenario_key}"

    threshold = s["policy"]["threshold_if_applicable"]
    if threshold is not None:
        threshold = _validate_numeric(threshold, f"{p}.policy.threshold_if_applicable")

    outcome = s.get("outcome") or {}
    amount_recovered = outcome.get("amount_recovered")
    if amount_recovered is not None:
        amount_recovered = round(_validate_numeric(amount_recovered, f"{p}.outcome.amount_recovered"), 2)

    explanation = s["explanation"]
    # IMPORTANT, discovered during Milestone 3 raw-source verification:
    # experiments/run_judge_demo.py writes the SAME fixed disclaimer
    # string into explanation._provenance regardless of whether
    # DeterministicFallbackProvider or ClaudeExplanationProvider actually
    # produced the prose ("LLM prose (or deterministic fallback) --
    # decision fields ... never from the provider"). The artifact does
    # NOT record which provider actually ran for a given scenario. This
    # script therefore does NOT guess/bucket it into "LLM-generated" vs
    # "Deterministic" -- that would be inventing a fact the source
    # doesn't contain. The raw disclaimer is passed through verbatim
    # instead; see docs/architecture.md's Day 15 Milestone 3 section for
    # the full discussion of this finding.
    explanation_source_note = _validate_str(explanation["_provenance"], f"{p}.explanation._provenance")

    return {
        "scenarioLabel": _validate_str(s["scenario_label"], f"{p}.scenario_label"),
        "transactionId": _validate_str(s["transaction_id"], f"{p}.transaction_id"),
        "paymentEvent": {
            "amount": round(_validate_numeric(s["payment_event_summary"]["amount"], f"{p}.payment_event_summary.amount"), 2),
            "paymentMethod": _validate_str(s["payment_event_summary"]["payment_method"], f"{p}.payment_event_summary.payment_method"),
            "failureCode": _validate_str(s["payment_event_summary"]["failure_code"], f"{p}.payment_event_summary.failure_code"),
            "retryCount": _validate_int(s["payment_event_summary"]["retry_count"], f"{p}.payment_event_summary.retry_count"),
            "webhookDelaySeconds": round(_validate_numeric(s["payment_event_summary"]["webhook_delay_seconds"], f"{p}.payment_event_summary.webhook_delay_seconds"), 2),
            "incidentActive": bool(s["payment_event_summary"]["incident_active"]),
        },
        "prediction": {
            "rootCause": _validate_str(s["prediction"]["predicted_root_cause"], f"{p}.prediction.predicted_root_cause"),
            "probability": _validate_probability(s["prediction"]["predicted_probability"], f"{p}.prediction.predicted_probability"),
            "modelVersion": _validate_str(s["prediction"]["model_version"], f"{p}.prediction.model_version"),
        },
        "policy": {
            "action": _validate_str(s["policy"]["policy_action"], f"{p}.policy.policy_action"),
            "reason": _validate_str(s["policy"]["policy_reason"], f"{p}.policy.policy_reason"),
            "version": _validate_str(s["policy"]["policy_version"], f"{p}.policy.policy_version"),
            "thresholdIfApplicable": threshold,
        },
        "outcome": {
            "recovered": outcome.get("recovered"),
            "amountRecovered": amount_recovered,
            "duplicateChargeRisk": outcome.get("duplicate_charge_risk"),
            "provenance": "SIMULATED",
        },
        "safetyInvariantCheck": {
            "actionBeforeExplanation": _validate_str(
                s["safety_invariant_check"]["action_before_explanation"], f"{p}.safety_invariant_check.action_before_explanation"
            ),
            "actionAfterExplanation": _validate_str(
                s["safety_invariant_check"]["action_after_explanation"], f"{p}.safety_invariant_check.action_after_explanation"
            ),
            "unchanged": bool(s["safety_invariant_check"]["unchanged"]),
        },
        "explanation": {
            "summary": _validate_str(explanation["summary"], f"{p}.explanation.summary"),
            "safetyNote": _validate_str(explanation["safety_note"], f"{p}.explanation.safety_note"),
            "sourceNote": explanation_source_note,
        },
    }


def build_snapshot() -> Dict[str, Any]:
    day9 = _require_file(DAY9_PATH, "python experiments/run_day9_experiment.py --seed 42")
    day12 = _require_file(DAY12_PATH, "python experiments/run_incident_demo.py")
    day14 = _require_file(DAY14_PATH, "python experiments/run_judge_demo.py")

    day14_scenarios = {key: _day14_scenario(day14, key) for key in EXPECTED_DAY14_SCENARIOS}

    by_strategy = day9["by_strategy"]
    by_root_cause = day9["by_root_cause"]
    strategies = ["GUARDIAN", "RULES_ONLY", "NAIVE_RETRY", "NO_ACTION"]

    strategy_comparison = {s: _strategy_row(by_strategy, s) for s in strategies}
    webhook_ambiguity_comparison = {
        s: _webhook_ambiguity_row(by_root_cause, s) for s in ("GUARDIAN", "RULES_ONLY", "NAIVE_RETRY")
    }

    guardian_block_reconcile_count = by_strategy["GUARDIAN"]["action_counts"].get("BLOCK_RECONCILE")
    if guardian_block_reconcile_count is None:
        raise SnapshotSourceError("GUARDIAN.action_counts missing BLOCK_RECONCILE")

    # Cross-seed sensitivity check for the headline "0 duplicate-charge
    # risk across seeds 42/43/44" claim -- read, not recomputed, from
    # each seed's own already-frozen aggregate artifact.
    seed_sensitivity = {"42": _validate_int(by_strategy["GUARDIAN"]["duplicate_charge_risk_count"], "GUARDIAN.duplicate_charge_risk_count (seed 42)")}
    for seed, path in DAY9_SENSITIVITY_PATHS.items():
        seed_data = _require_file(path, f"python experiments/run_day9_experiment.py --seed {seed}")
        seed_sensitivity[str(seed)] = _validate_int(
            seed_data["by_strategy"]["GUARDIAN"]["duplicate_charge_risk_count"],
            f"GUARDIAN.duplicate_charge_risk_count (seed {seed})",
        )

    incident_summary = day12["summary"]
    incident_metadata = day12["metadata"]
    infra_summary = day12["infrastructure_summary"]
    non_infra_by_class = day12["non_infrastructure_summary"]["by_actual_class"]
    split = day12["split_membership"]
    classifier_summary = day12["classifier_summary"]
    safety = day12["webhook_ambiguity_safety"]
    policy_summary = day12["policy_summary"]
    sim_recovery = day12["simulated_recovery_summary"]

    def _density_window(key: str) -> Dict[str, Any]:
        w = incident_summary[key]
        return {
            "windowStart": _validate_str(w["window_start"], f"summary.{key}.window_start"),
            "windowEnd": _validate_str(w["window_end"], f"summary.{key}.window_end"),
            "windowMinutes": _validate_numeric(w["window_minutes"], f"summary.{key}.window_minutes"),
            "failedEventCount": _validate_int(w["failed_event_count"], f"summary.{key}.failed_event_count"),
            "failureDensityPerUnit": _validate_numeric(w["failure_density_per_unit"], f"summary.{key}.failure_density_per_unit"),
        }

    incident_class_distribution = {
        "INFRASTRUCTURE": _validate_int(infra_summary["ground_truth_count"], "infrastructure_summary.ground_truth_count"),
    }
    for cls, row in non_infra_by_class.items():
        incident_class_distribution[cls] = _validate_int(row["count"], f"non_infrastructure_summary.by_actual_class.{cls}.count")

    if not safety.get("safety_pass"):
        raise SnapshotSourceError("Day 12 webhook_ambiguity_safety.safety_pass is not true — refusing to snapshot")

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceArtifacts": {
            "day9": str(DAY9_PATH.relative_to(REPO_ROOT)),
            "day12": str(DAY12_PATH.relative_to(REPO_ROOT)),
            "day14": str(DAY14_PATH.relative_to(REPO_ROOT)),
        },
        "day9": {
            "experimentSeed": _validate_int(day9["experiment_seed"], "experiment_seed"),
            "transactionCount": _validate_int(day9["transaction_count"], "transaction_count"),
            "strategyComparison": strategy_comparison,
            "webhookAmbiguity": {
                "comparison": webhook_ambiguity_comparison,
                "guardianBlockReconcileCount": guardian_block_reconcile_count,
            },
            "guardianDuplicateChargeRiskBySeed": seed_sensitivity,
        },
        "day12": {
            "incidentWindow": {
                "start": incident_metadata["incident_window"]["start"],
                "end": incident_metadata["incident_window"]["end"],
            },
            "beforeWindow": {
                "start": incident_metadata["before_window"]["start"],
                "end": incident_metadata["before_window"]["end"],
            },
            "afterWindow": {
                "start": incident_metadata["after_window"]["start"],
                "end": incident_metadata["after_window"]["end"],
            },
            "metricType": _validate_str(incident_metadata["metric_type"], "metadata.metric_type"),
            "datasetContainsSuccessfulTransactions": bool(incident_metadata["dataset_contains_successful_transactions"]),
            "densityUnitMinutes": _validate_int(incident_summary["density_unit_minutes"], "summary.density_unit_minutes"),
            "before": _density_window("before"),
            "incident": _density_window("incident"),
            "after": _density_window("after"),
            "incidentCount": _validate_int(incident_summary["incident_count"], "summary.incident_count"),
            "classDistribution": incident_class_distribution,
            "splitMembership": {
                "trainCount": _validate_int(split["train_count"], "split_membership.train_count"),
                "validationCount": _validate_int(split["validation_count"], "split_membership.validation_count"),
                "testCount": _validate_int(split["test_count"], "split_membership.test_count"),
            },
            "fullWindowInfrastructure": {
                "correct": _validate_int(classifier_summary["full_window"]["correctly_predicted_count"], "full_window.correctly_predicted_count"),
                "total": _validate_int(classifier_summary["full_window"]["ground_truth_count"], "full_window.ground_truth_count"),
            },
            "heldOutTestInfrastructure": {
                "correct": _validate_int(classifier_summary["held_out_test"]["correctly_predicted_count"], "held_out_test.correctly_predicted_count"),
                "total": _validate_int(classifier_summary["held_out_test"]["ground_truth_count"], "held_out_test.ground_truth_count"),
            },
            "infrastructurePolicyActionDistribution": {
                action: _validate_int(count, f"policy_summary.infrastructure_action_distribution.{action}")
                for action, count in policy_summary["infrastructure_action_distribution"].items()
            },
            "infrastructureConfidenceThreshold": _validate_numeric(
                policy_summary["infrastructure_confidence_threshold"], "policy_summary.infrastructure_confidence_threshold"
            ),
            "webhookAmbiguitySafety": {
                "caseCount": _validate_int(safety["case_count"], "webhook_ambiguity_safety.case_count"),
                "blockReconcileCount": _validate_int(safety["block_reconcile_count"], "webhook_ambiguity_safety.block_reconcile_count"),
                "deferRetryCount": _validate_int(safety["defer_retry_count"], "webhook_ambiguity_safety.defer_retry_count"),
                "safetyPass": bool(safety["safety_pass"]),
            },
            "simulatedRecoverySummary": {
                "transactionsEvaluated": _validate_int(sim_recovery["transactions_evaluated"], "simulated_recovery_summary.transactions_evaluated"),
                "recoveredCount": _validate_int(sim_recovery["simulated_recovered_count"], "simulated_recovery_summary.simulated_recovered_count"),
                "totalAmountRecovered": round(
                    _validate_numeric(sim_recovery["simulated_total_amount_recovered"], "simulated_recovery_summary.simulated_total_amount_recovered"), 2
                ),
                "duplicateChargeRiskCount": _validate_int(
                    sim_recovery["simulated_duplicate_charge_risk_count"], "simulated_recovery_summary.simulated_duplicate_charge_risk_count"
                ),
            },
        },
        "day14": {
            "scenarios": day14_scenarios,
        },
    }


TS_HEADER = """/**
 * Recovery Guardian — Day 15 Frontend Data Snapshot
 *
 * GENERATED FILE. Do not hand-edit.
 *
 * Generated by: scripts/generate_frontend_snapshot.py
 * Source artifacts:
 *   - experiments/results/day9_seed_42_aggregate.json  (Day 9, frozen)
 *   - experiments/results/day12_incident_demo.json      (Day 12, frozen)
 *   - experiments/results/day14_demo.json               (Day 14, frozen)
 *
 * Every numeric value below is copied verbatim (rounded for display
 * only) from the authoritative artifacts above — nothing here is
 * recomputed, re-derived, or invented by this project's frontend. See
 * scripts/generate_frontend_snapshot.py's module docstring for the full
 * data-plumbing contract (Day 15 Milestone 1, section 22A).
 *
 * Regenerate with:
 *   python3 scripts/generate_frontend_snapshot.py
 */
"""


def render_typescript(snapshot: Dict[str, Any]) -> str:
    body = json.dumps(snapshot, indent=2)
    return (
        TS_HEADER
        + "\nexport const SNAPSHOT_GENERATED_AT = "
        + json.dumps(snapshot["generatedAt"])
        + ";\n\n"
        + "export const snapshot = "
        + body
        + " as const;\n\n"
        + "export type Snapshot = typeof snapshot;\n"
    )


def main() -> None:
    try:
        snapshot = build_snapshot()
    except SnapshotSourceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render_typescript(snapshot))
    print(f"Wrote {OUTPUT_PATH}")
    print(
        f"Source: {DAY9_PATH.relative_to(REPO_ROOT)}, "
        f"{DAY12_PATH.relative_to(REPO_ROOT)}, {DAY14_PATH.relative_to(REPO_ROOT)}"
    )


if __name__ == "__main__":
    main()
