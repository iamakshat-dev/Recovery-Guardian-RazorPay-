"""
Recovery Guardian — Day 9 Experiment Entry Point

    python experiments/run_day9_experiment.py [--seed 42] [--out PATH]

Loads the frozen dataset subset (experiments/day9_experiment_config.yaml),
runs all four strategies through the one shared counterfactual outcome
environment, and writes per-transaction + aggregate results as JSON.

Designed to be run as a completely independent process each time (Section
52's cross-process reproducibility requirement): nothing here depends on
in-process state from a previous run, wall-clock time, or any
non-deterministic source — two separate invocations with the same --seed
must produce byte-identical output files.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.experiment.dataset import load_frozen_test_split_payment_events
from src.experiment.results import (
    aggregate_metrics_by_root_cause,
    aggregate_metrics_by_strategy,
    results_to_dicts,
)
from src.experiment.runner import run_experiment

RESULTS_DIR = Path(__file__).parent / "results"


def main() -> None:
    parser = argparse.ArgumentParser(description="Recovery Guardian Day 9 four-strategy experiment")
    parser.add_argument("--seed", type=int, default=42, help="experiment seed (default: 42, the primary seed)")
    parser.add_argument(
        "--out-prefix",
        type=str,
        default=None,
        help="output filename prefix (default: day9_seed_<seed>)",
    )
    args = parser.parse_args()

    prefix = args.out_prefix or f"day9_seed_{args.seed}"

    events = load_frozen_test_split_payment_events()
    results = run_experiment(events, experiment_seed=args.seed)

    per_transaction_path = RESULTS_DIR / f"{prefix}_per_transaction.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(per_transaction_path, "w") as f:
        json.dump(results_to_dicts(results), f, indent=2, sort_keys=True)

    aggregate = {
        "experiment_seed": args.seed,
        "transaction_count": len(events),
        "by_strategy": aggregate_metrics_by_strategy(results),
        "by_root_cause": aggregate_metrics_by_root_cause(results),
    }
    aggregate_path = RESULTS_DIR / f"{prefix}_aggregate.json"
    with open(aggregate_path, "w") as f:
        json.dump(aggregate, f, indent=2, sort_keys=True)

    print(f"Wrote {per_transaction_path}")
    print(f"Wrote {aggregate_path}")
    print(f"Transactions evaluated: {len(events)}")
    for name, row in aggregate["by_strategy"].items():
        print(
            f"  {name}: recovered={row['simulated_amount_recovered']:.2f} "
            f"recovery_rate={row['recovery_rate']:.4f} "
            f"duplicate_charge_risk={row['duplicate_charge_risk_count']}"
        )


if __name__ == "__main__":
    main()
