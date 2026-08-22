"""
Recovery Guardian — Day 10 Frozen Experiment Analysis

    python experiments/run_day10_analysis.py

Reads ONLY the frozen Day 9 result artifacts
(experiments/results/day9_seed_{42,43,44}_per_transaction.json) — never
reruns the Day 9 experiment, never touches Day 9 code, ML, calibration, or
policy. Produces:

    experiments/results/day10_analysis.json   (all computed tables)
    experiments/results/day10_*.png           (plots)
"""

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.analysis.integrity import verify_integrity
from src.analysis.loader import (
    ROOT_CAUSE_NAMES,
    STRATEGY_NAMES,
    load_per_transaction_results,
    pivot_by_transaction,
)
from src.analysis.segments import combined_segment_metrics, root_cause_table, strategy_summary_table
from src.analysis.statistics import mcnemar_exact, wilcoxon_signed_rank

RESULTS_DIR = Path(__file__).parent / "results"
PRIMARY_SEED = 42
SENSITIVITY_SEEDS = [43, 44]


def main() -> None:
    # --- Load frozen results (read-only) ---------------------------------
    results_by_seed = {
        seed: load_per_transaction_results(seed) for seed in [PRIMARY_SEED] + SENSITIVITY_SEEDS
    }
    primary_results = results_by_seed[PRIMARY_SEED]

    # --- Data integrity (Day 10 spec section 6) ---------------------------
    integrity_report = {seed: verify_integrity(rows) for seed, rows in results_by_seed.items()}

    # --- Primary comparison + segments -------------------------------------
    strategy_table = strategy_summary_table(primary_results)
    rc_table = root_cause_table(primary_results)
    combined_99 = combined_segment_metrics(primary_results, ["CARD_DECLINE", "INSUFFICIENT_FUNDS"])

    # --- Seed sensitivity ---------------------------------------------------
    seed_sensitivity = {
        seed: strategy_summary_table(rows) for seed, rows in results_by_seed.items()
    }

    # --- CRN validation signals ---------------------------------------------
    crn_signal_1 = {
        "description": "CARD_DECLINE and INSUFFICIENT_FUNDS: Rules-only and "
        "Guardian select the same effective action (CUSTOMER_RECOVERY) and "
        "produce identical simulated recovery under the shared CRN seed.",
        "CARD_DECLINE": {
            "RULES_ONLY": rc_table["CARD_DECLINE"]["RULES_ONLY"]["simulated_amount_recovered"],
            "GUARDIAN": rc_table["CARD_DECLINE"]["GUARDIAN"]["simulated_amount_recovered"],
        },
        "INSUFFICIENT_FUNDS": {
            "RULES_ONLY": rc_table["INSUFFICIENT_FUNDS"]["RULES_ONLY"]["simulated_amount_recovered"],
            "GUARDIAN": rc_table["INSUFFICIENT_FUNDS"]["GUARDIAN"]["simulated_amount_recovered"],
        },
    }
    crn_signal_2 = {
        "description": "INFRASTRUCTURE: Naive and Rules-only both select "
        "DEFER_RETRY for every transaction in this segment and produce "
        "identical simulated recovery under the shared CRN seed.",
        "INFRASTRUCTURE": {
            "NAIVE_RETRY": rc_table["INFRASTRUCTURE"]["NAIVE_RETRY"]["simulated_amount_recovered"],
            "RULES_ONLY": rc_table["INFRASTRUCTURE"]["RULES_ONLY"]["simulated_amount_recovered"],
        },
    }

    # --- Paired statistical analysis (primary seed only, n=242 paired) -----
    pivoted = pivot_by_transaction(primary_results)
    mcnemar_results = {}
    wilcoxon_results = {}
    for pair in [("GUARDIAN", "NAIVE_RETRY"), ("GUARDIAN", "RULES_ONLY"), ("GUARDIAN", "NO_ACTION")]:
        mc = mcnemar_exact(pivoted, *pair)
        wx = wilcoxon_signed_rank(pivoted, *pair)
        key = f"{pair[0]}_vs_{pair[1]}"
        mcnemar_results[key] = mc.__dict__
        wilcoxon_results[key] = wx.__dict__

    # --- Assemble and save --------------------------------------------------
    report = {
        "primary_seed": PRIMARY_SEED,
        "sensitivity_seeds": SENSITIVITY_SEEDS,
        "integrity_report": integrity_report,
        "strategy_table_primary_seed": strategy_table,
        "root_cause_table_primary_seed": rc_table,
        "combined_card_decline_insufficient_funds_primary_seed": combined_99,
        "seed_sensitivity": seed_sensitivity,
        "crn_validation_signal_1": crn_signal_1,
        "crn_validation_signal_2": crn_signal_2,
        "mcnemar_primary_seed": mcnemar_results,
        "wilcoxon_primary_seed": wilcoxon_results,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "day10_analysis.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(f"Wrote {out_path}")

    # --- Plots (Day 10 spec section 29) --------------------------------------
    _plot_recovery_by_strategy(strategy_table)
    _plot_duplicate_risk_by_strategy(strategy_table)
    _plot_webhook_ambiguity(rc_table["WEBHOOK_AMBIGUITY"])
    _plot_card_decline_insufficient_funds(combined_99)
    _plot_guardian_root_cause_recovery(rc_table)
    _plot_guardian_action_distribution(strategy_table["GUARDIAN"]["action_distribution"])
    _plot_seed_sensitivity(seed_sensitivity)

    print("Wrote day10_*.png plots to", RESULTS_DIR)


def _plot_recovery_by_strategy(strategy_table) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    names = list(STRATEGY_NAMES)
    values = [strategy_table[n]["simulated_amount_recovered"] for n in names]
    ax.bar(names, values, color=["#d62728", "#2ca02c", "#1f77b4", "#7f7f7f"])
    ax.set_ylabel("Simulated amount recovered (₹)")
    ax.set_title("Day 10 — Simulated Recovery by Strategy (seed 42)")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "day10_recovery_by_strategy.png", dpi=150)
    plt.close(fig)


def _plot_duplicate_risk_by_strategy(strategy_table) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    names = list(STRATEGY_NAMES)
    values = [strategy_table[n]["duplicate_charge_risk_count"] for n in names]
    ax.bar(names, values, color=["#d62728", "#2ca02c", "#1f77b4", "#7f7f7f"])
    ax.set_ylabel("Duplicate-charge risk count")
    ax.set_title("Day 10 — Duplicate-Charge Risk by Strategy (seed 42)")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "day10_duplicate_risk_by_strategy.png", dpi=150)
    plt.close(fig)


def _plot_webhook_ambiguity(webhook_table) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    names = list(STRATEGY_NAMES)
    recovered = [webhook_table[n]["simulated_amount_recovered"] for n in names]
    dup = [webhook_table[n]["duplicate_charge_risk_count"] for n in names]
    x = range(len(names))
    ax.bar([i - 0.2 for i in x], recovered, width=0.4, label="Simulated recovered (₹)", color="#2ca02c")
    ax2 = ax.twinx()
    ax2.bar([i + 0.2 for i in x], dup, width=0.4, label="Duplicate-charge risk count", color="#d62728")
    ax.set_xticks(list(x))
    ax.set_xticklabels(names)
    ax.set_ylabel("Simulated recovered (₹)")
    ax2.set_ylabel("Duplicate-charge risk count")
    ax.set_title("Day 10 — WEBHOOK_AMBIGUITY: Recovery vs. Duplicate Risk (seed 42)")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "day10_webhook_ambiguity_recovery_vs_risk.png", dpi=150)
    plt.close(fig)


def _plot_card_decline_insufficient_funds(combined_99) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    names = list(STRATEGY_NAMES)
    values = [combined_99[n]["simulated_amount_recovered"] for n in names]
    ax.bar(names, values, color=["#d62728", "#2ca02c", "#1f77b4", "#7f7f7f"])
    ax.set_ylabel("Simulated amount recovered (₹)")
    ax.set_title("Day 10 — CARD_DECLINE + INSUFFICIENT_FUNDS Recovery (seed 42)")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "day10_card_decline_insufficient_funds.png", dpi=150)
    plt.close(fig)


def _plot_guardian_root_cause_recovery(rc_table) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    names = list(ROOT_CAUSE_NAMES)
    values = [rc_table[rc]["GUARDIAN"]["simulated_amount_recovered"] for rc in names]
    ax.bar(names, values, color="#1f77b4")
    ax.set_ylabel("Simulated amount recovered (₹)")
    ax.set_title("Day 10 — Guardian Recovery by Root Cause (seed 42)")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "day10_guardian_recovery_by_root_cause.png", dpi=150)
    plt.close(fig)


def _plot_guardian_action_distribution(action_dist) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    names = list(action_dist.keys())
    values = list(action_dist.values())
    ax.bar(names, values, color="#1f77b4")
    ax.set_ylabel("Transaction count")
    ax.set_title("Day 10 — Guardian Action Distribution (seed 42, n=242)")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "day10_guardian_action_distribution.png", dpi=150)
    plt.close(fig)


def _plot_seed_sensitivity(seed_sensitivity) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    seeds = [PRIMARY_SEED] + SENSITIVITY_SEEDS
    for strategy, color in zip(STRATEGY_NAMES, ["#d62728", "#2ca02c", "#1f77b4", "#7f7f7f"]):
        values = [seed_sensitivity[seed][strategy]["duplicate_charge_risk_count"] for seed in seeds]
        ax.plot(seeds, values, marker="o", label=strategy, color=color)
    ax.set_xlabel("Experiment seed")
    ax.set_ylabel("Duplicate-charge risk count")
    ax.set_title("Day 10 — Seed Sensitivity: Duplicate-Charge Risk")
    ax.set_xticks(seeds)
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "day10_seed_sensitivity.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
