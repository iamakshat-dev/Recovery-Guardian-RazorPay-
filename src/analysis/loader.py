"""
Recovery Guardian — Day 10 Frozen Result Loader

Day 10 is analysis-only: it consumes the frozen Day 9 result artifacts
(experiments/results/day9_seed_*_per_transaction.json) and never reruns
the experiment or touches any Day 9 code. This module only reads.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

RESULTS_DIR = Path(__file__).parent.parent.parent / "experiments" / "results"

STRATEGY_NAMES = ("NAIVE_RETRY", "RULES_ONLY", "GUARDIAN", "NO_ACTION")
ROOT_CAUSE_NAMES = (
    "CARD_DECLINE",
    "INSUFFICIENT_FUNDS",
    "OTP_TIMEOUT",
    "USER_ABANDONMENT",
    "INFRASTRUCTURE",
    "WEBHOOK_AMBIGUITY",
)
CURRENCY_TOLERANCE = 1e-2  # matches Day 9's declared tolerance (no
# pre-existing repository currency convention — see docs/architecture.md).


def load_per_transaction_results(seed: int, results_dir: Path = RESULTS_DIR) -> List[Dict[str, Any]]:
    path = results_dir / f"day9_seed_{seed}_per_transaction.json"
    with open(path) as f:
        return json.load(f)


def load_aggregate_results(seed: int, results_dir: Path = RESULTS_DIR) -> Dict[str, Any]:
    path = results_dir / f"day9_seed_{seed}_aggregate.json"
    with open(path) as f:
        return json.load(f)


def pivot_by_transaction(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """{transaction_id: {strategy: result_row}} — the paired-analysis
    shape: every transaction's outcome under every strategy, side by
    side."""
    pivoted: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in results:
        pivoted.setdefault(row["transaction_id"], {})[row["strategy"]] = row
    return pivoted
