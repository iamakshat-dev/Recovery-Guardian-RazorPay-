"""
Recovery Guardian — Day 10 Data Integrity Checks

Verifies the frozen Day 9 per-transaction results are internally
consistent, before any interpretation is built on top of them. Read-only:
never modifies the frozen artifacts.
"""

from typing import Any, Dict, List

from src.analysis.loader import CURRENCY_TOLERANCE, ROOT_CAUSE_NAMES, STRATEGY_NAMES


def verify_integrity(results: List[Dict[str, Any]], expected_transaction_count: int = 242) -> Dict[str, Any]:
    """Returns a dict of {check_name: bool} plus any diagnostic detail.
    Raises AssertionError immediately if any check fails — Day 10 must
    STOP rather than proceed on inconsistent frozen data."""
    report: Dict[str, Any] = {}

    # 1. Action counts per strategy sum to the expected transaction count.
    for strategy in STRATEGY_NAMES:
        rows = [r for r in results if r["strategy"] == strategy]
        assert len(rows) == expected_transaction_count, (
            f"{strategy}: expected {expected_transaction_count} rows, found {len(rows)}"
        )
    report["action_counts_sum_to_expected"] = True

    # 2. Per-transaction amount invariants: 0 <= amount_recovered <= amount.
    for r in results:
        assert r["amount_recovered"] >= -CURRENCY_TOLERANCE, r
        assert r["amount_recovered"] <= r["transaction_amount"] + CURRENCY_TOLERANCE, r
    report["per_transaction_amount_bounds_hold"] = True

    # 3. sum(root-cause recovery) == total strategy recovery, per strategy.
    for strategy in STRATEGY_NAMES:
        rows = [r for r in results if r["strategy"] == strategy]
        total = sum(r["amount_recovered"] for r in rows)
        by_root_cause_total = 0.0
        for rc in ROOT_CAUSE_NAMES:
            by_root_cause_total += sum(r["amount_recovered"] for r in rows if r["root_cause"] == rc)
        assert abs(total - by_root_cause_total) < CURRENCY_TOLERANCE, (strategy, total, by_root_cause_total)
    report["root_cause_sums_match_strategy_totals"] = True

    # 4. total recovered <= total amount at risk, per strategy.
    for strategy in STRATEGY_NAMES:
        rows = [r for r in results if r["strategy"] == strategy]
        total_recovered = sum(r["amount_recovered"] for r in rows)
        total_at_risk = sum(r["transaction_amount"] for r in rows)
        assert total_recovered <= total_at_risk + CURRENCY_TOLERANCE, (strategy, total_recovered, total_at_risk)
    report["recovered_never_exceeds_at_risk"] = True

    # 5. Every root cause present is one of the six known ones.
    seen_root_causes = {r["root_cause"] for r in results}
    assert seen_root_causes.issubset(set(ROOT_CAUSE_NAMES)), seen_root_causes
    report["root_causes_within_known_set"] = True

    return report
