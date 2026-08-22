"""
Recovery Guardian — Day 9 Result Records and Aggregate Metrics

`PerTransactionResult` is the audit-chain unit: transaction -> strategy ->
action -> outcome, traceable back to `experiment_seed` (and, for Guardian,
`decision_id` where meaningful — always empty here, since Day 9 never
persists a real DecisionRecord; see GuardianStrategy's docstring).
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

STRATEGY_NAMES = ("NAIVE_RETRY", "RULES_ONLY", "GUARDIAN", "NO_ACTION")
ACTION_NAMES = ("DEFER_RETRY", "CUSTOMER_RECOVERY", "BLOCK_RECONCILE", "HUMAN_REVIEW", "NO_ACTION")
ROOT_CAUSE_NAMES = (
    "CARD_DECLINE",
    "INSUFFICIENT_FUNDS",
    "OTP_TIMEOUT",
    "USER_ABANDONMENT",
    "INFRASTRUCTURE",
    "WEBHOOK_AMBIGUITY",
)


@dataclass(frozen=True)
class PerTransactionResult:
    transaction_id: str
    strategy: str
    selected_action: str
    root_cause: str
    root_cause_probability: float
    transaction_amount: float
    recovered: bool
    amount_recovered: float
    duplicate_charge_risk: bool
    outcome_reason: str
    experiment_seed: int
    decision_id: str = ""


def _empty_action_counts() -> Dict[str, int]:
    return {a: 0 for a in ACTION_NAMES}


def aggregate_metrics_by_strategy(results: List[PerTransactionResult]) -> Dict[str, Dict[str, Any]]:
    """One row per strategy. `unsafe_outcome_count` is defined exactly as
    Day 9 spec section 24 requires (no broader Day 7/8 safety definition
    exists to preserve instead): count(outcome.duplicate_charge_risk ==
    True)."""
    by_strategy: Dict[str, Dict[str, Any]] = {}
    for name in STRATEGY_NAMES:
        by_strategy[name] = {
            "transactions_evaluated": 0,
            "total_amount_at_risk": 0.0,
            "simulated_amount_recovered": 0.0,
            "recovered_transaction_count": 0,
            "duplicate_charge_risk_count": 0,
            "action_counts": _empty_action_counts(),
        }

    for r in results:
        row = by_strategy[r.strategy]
        row["transactions_evaluated"] += 1
        row["total_amount_at_risk"] += r.transaction_amount
        row["simulated_amount_recovered"] += r.amount_recovered
        row["recovered_transaction_count"] += int(r.recovered)
        row["duplicate_charge_risk_count"] += int(r.duplicate_charge_risk)
        row["action_counts"][r.selected_action] += 1

    for row in by_strategy.values():
        n = row["transactions_evaluated"]
        row["recovery_rate"] = (row["recovered_transaction_count"] / n) if n else 0.0
        row["duplicate_charge_risk_rate"] = (row["duplicate_charge_risk_count"] / n) if n else 0.0
        row["unsafe_outcome_count"] = row["duplicate_charge_risk_count"]

    return by_strategy


def aggregate_metrics_by_root_cause(results: List[PerTransactionResult]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """[root_cause][strategy] -> metrics row. Every one of the six root
    causes is always present, even with zero transactions — never a
    fabricated/omitted row (Day 9 spec section 29)."""
    by_root_cause: Dict[str, Dict[str, Dict[str, Any]]] = {
        rc: {
            name: {
                "transactions_evaluated": 0,
                "total_amount_at_risk": 0.0,
                "simulated_amount_recovered": 0.0,
                "recovered_transaction_count": 0,
                "duplicate_charge_risk_count": 0,
            }
            for name in STRATEGY_NAMES
        }
        for rc in ROOT_CAUSE_NAMES
    }

    for r in results:
        if r.root_cause not in by_root_cause:
            continue  # defensive; every root cause in this dataset is one of ROOT_CAUSE_NAMES
        row = by_root_cause[r.root_cause][r.strategy]
        row["transactions_evaluated"] += 1
        row["total_amount_at_risk"] += r.transaction_amount
        row["simulated_amount_recovered"] += r.amount_recovered
        row["recovered_transaction_count"] += int(r.recovered)
        row["duplicate_charge_risk_count"] += int(r.duplicate_charge_risk)

    for strategies in by_root_cause.values():
        for row in strategies.values():
            n = row["transactions_evaluated"]
            row["recovery_rate"] = (row["recovered_transaction_count"] / n) if n else 0.0
            row["duplicate_charge_risk_rate"] = (row["duplicate_charge_risk_count"] / n) if n else 0.0

    return by_root_cause


def results_to_dicts(results: List[PerTransactionResult]) -> List[Dict[str, Any]]:
    return [asdict(r) for r in results]


def save_results_json(results: List[PerTransactionResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(results_to_dicts(results), f, indent=2, sort_keys=True)
