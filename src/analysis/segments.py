"""
Recovery Guardian — Day 10 Segment / Action-Distribution Analysis

All functions here are pure, read-only aggregations over the frozen Day 9
per-transaction result rows (loaded by src.analysis.loader).
"""

from typing import Any, Dict, List, Optional

from src.analysis.loader import CURRENCY_TOLERANCE, ROOT_CAUSE_NAMES, STRATEGY_NAMES

ACTION_NAMES = ("DEFER_RETRY", "CUSTOMER_RECOVERY", "BLOCK_RECONCILE", "HUMAN_REVIEW", "NO_ACTION")


def filter_rows(
    results: List[Dict[str, Any]],
    strategy: Optional[str] = None,
    root_cause: Optional[str] = None,
) -> List[Dict[str, Any]]:
    rows = results
    if strategy is not None:
        rows = [r for r in rows if r["strategy"] == strategy]
    if root_cause is not None:
        rows = [r for r in rows if r["root_cause"] == root_cause]
    return rows


def action_distribution(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {a: 0 for a in ACTION_NAMES}
    for r in rows:
        counts[r["selected_action"]] += 1
    return counts


def segment_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    at_risk = sum(r["transaction_amount"] for r in rows)
    recovered_amount = sum(r["amount_recovered"] for r in rows)
    recovered_count = sum(1 for r in rows if r["recovered"])
    dup_risk_count = sum(1 for r in rows if r["duplicate_charge_risk"])
    return {
        "transactions": n,
        "amount_at_risk": at_risk,
        "simulated_amount_recovered": recovered_amount,
        "recovered_transaction_count": recovered_count,
        "recovery_rate": (recovered_count / n) if n else 0.0,
        "duplicate_charge_risk_count": dup_risk_count,
        "duplicate_charge_risk_rate": (dup_risk_count / n) if n else 0.0,
        "action_distribution": action_distribution(rows),
    }


def strategy_summary_table(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {s: segment_metrics(filter_rows(results, strategy=s)) for s in STRATEGY_NAMES}


def root_cause_table(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    table = {}
    for rc in ROOT_CAUSE_NAMES:
        table[rc] = {
            s: segment_metrics(filter_rows(results, strategy=s, root_cause=rc)) for s in STRATEGY_NAMES
        }
    return table


def combined_segment_metrics(results: List[Dict[str, Any]], root_causes: List[str]) -> Dict[str, Dict[str, Any]]:
    """One combined segment across multiple root causes (e.g. CARD_DECLINE
    + INSUFFICIENT_FUNDS), per strategy."""
    out = {}
    for s in STRATEGY_NAMES:
        rows = [r for r in filter_rows(results, strategy=s) if r["root_cause"] in root_causes]
        out[s] = segment_metrics(rows)
    return out
