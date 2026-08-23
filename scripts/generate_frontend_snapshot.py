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

Both are produced by running the existing, frozen, unmodified scripts
(`experiments/run_day9_experiment.py --seed 42`,
`experiments/run_incident_demo.py`) — never by this script. If either
artifact is missing, this script fails loudly with instructions to
generate it, rather than fabricating placeholder data.

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


def build_snapshot() -> Dict[str, Any]:
    day9 = _require_file(DAY9_PATH, "python experiments/run_day9_experiment.py --seed 42")
    day12 = _require_file(DAY12_PATH, "python experiments/run_incident_demo.py")

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
            "webhookAmbiguitySafety": {
                "caseCount": _validate_int(safety["case_count"], "webhook_ambiguity_safety.case_count"),
                "blockReconcileCount": _validate_int(safety["block_reconcile_count"], "webhook_ambiguity_safety.block_reconcile_count"),
                "deferRetryCount": _validate_int(safety["defer_retry_count"], "webhook_ambiguity_safety.defer_retry_count"),
                "safetyPass": bool(safety["safety_pass"]),
            },
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
    print(f"Source: {DAY9_PATH.relative_to(REPO_ROOT)}, {DAY12_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
