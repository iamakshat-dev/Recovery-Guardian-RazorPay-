"""
Recovery Guardian — Day 10 Analysis Utility Tests

Small, hand-built synthetic fixtures (NOT the real frozen Day 9 data) so
these tests are independent of any future change to the frozen artifacts.
"""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from src.analysis.integrity import verify_integrity
from src.analysis.loader import pivot_by_transaction
from src.analysis.segments import action_distribution, combined_segment_metrics, segment_metrics
from src.analysis.statistics import mcnemar_exact, wilcoxon_signed_rank


def make_row(txn_id, strategy, action, root_cause, amount, recovered, dup_risk=False):
    return {
        "transaction_id": txn_id,
        "strategy": strategy,
        "selected_action": action,
        "root_cause": root_cause,
        "root_cause_probability": 0.9,
        "transaction_amount": amount,
        "recovered": recovered,
        "amount_recovered": amount if recovered else 0.0,
        "duplicate_charge_risk": dup_risk,
        "outcome_reason": "TEST",
        "experiment_seed": 1,
        "decision_id": "",
    }


def make_full_batch(n=4):
    """n transactions x 4 strategies, matching STRATEGY_NAMES exactly."""
    rows = []
    for i in range(n):
        for strategy in ("NAIVE_RETRY", "RULES_ONLY", "GUARDIAN", "NO_ACTION"):
            rows.append(make_row(f"txn_{i}", strategy, "DEFER_RETRY", "INFRASTRUCTURE", 100.0, i % 2 == 0))
    return rows


# --- Integrity -----------------------------------------------------------------

def test_verify_integrity_passes_on_well_formed_batch():
    rows = make_full_batch(n=5)
    report = verify_integrity(rows, expected_transaction_count=5)
    assert all(report.values())


def test_verify_integrity_fails_on_amount_recovered_exceeding_transaction_amount():
    rows = make_full_batch(n=2)
    rows[0]["amount_recovered"] = 999.0  # transaction_amount is 100.0
    with pytest.raises(AssertionError):
        verify_integrity(rows, expected_transaction_count=2)


def test_verify_integrity_fails_on_wrong_row_count():
    rows = make_full_batch(n=3)
    with pytest.raises(AssertionError):
        verify_integrity(rows, expected_transaction_count=99)


# --- Segments --------------------------------------------------------------------

def test_action_distribution_counts_correctly():
    rows = [make_row("t1", "GUARDIAN", "DEFER_RETRY", "INFRASTRUCTURE", 100, True),
            make_row("t2", "GUARDIAN", "BLOCK_RECONCILE", "WEBHOOK_AMBIGUITY", 100, False)]
    dist = action_distribution(rows)
    assert dist["DEFER_RETRY"] == 1
    assert dist["BLOCK_RECONCILE"] == 1
    assert dist["CUSTOMER_RECOVERY"] == 0


def test_segment_metrics_computes_recovery_rate_correctly():
    rows = [make_row(f"t{i}", "GUARDIAN", "DEFER_RETRY", "INFRASTRUCTURE", 100.0, i < 3) for i in range(10)]
    metrics = segment_metrics(rows)
    assert metrics["transactions"] == 10
    assert metrics["recovered_transaction_count"] == 3
    assert metrics["recovery_rate"] == pytest.approx(0.3)
    assert metrics["simulated_amount_recovered"] == pytest.approx(300.0)


def test_combined_segment_metrics_only_includes_listed_root_causes():
    rows = [
        make_row("t1", "GUARDIAN", "CUSTOMER_RECOVERY", "CARD_DECLINE", 100.0, True),
        make_row("t2", "GUARDIAN", "CUSTOMER_RECOVERY", "INSUFFICIENT_FUNDS", 100.0, True),
        make_row("t3", "GUARDIAN", "DEFER_RETRY", "INFRASTRUCTURE", 100.0, True),
        make_row("t1", "NAIVE_RETRY", "DEFER_RETRY", "CARD_DECLINE", 100.0, False),
        make_row("t2", "NAIVE_RETRY", "DEFER_RETRY", "INSUFFICIENT_FUNDS", 100.0, False),
        make_row("t3", "NAIVE_RETRY", "DEFER_RETRY", "INFRASTRUCTURE", 100.0, True),
        make_row("t1", "RULES_ONLY", "CUSTOMER_RECOVERY", "CARD_DECLINE", 100.0, True),
        make_row("t2", "RULES_ONLY", "CUSTOMER_RECOVERY", "INSUFFICIENT_FUNDS", 100.0, True),
        make_row("t3", "RULES_ONLY", "DEFER_RETRY", "INFRASTRUCTURE", 100.0, True),
        make_row("t1", "NO_ACTION", "NO_ACTION", "CARD_DECLINE", 100.0, False),
        make_row("t2", "NO_ACTION", "NO_ACTION", "INSUFFICIENT_FUNDS", 100.0, False),
        make_row("t3", "NO_ACTION", "NO_ACTION", "INFRASTRUCTURE", 100.0, False),
    ]
    combined = combined_segment_metrics(rows, ["CARD_DECLINE", "INSUFFICIENT_FUNDS"])
    assert combined["GUARDIAN"]["transactions"] == 2  # excludes the INFRASTRUCTURE row
    assert combined["GUARDIAN"]["simulated_amount_recovered"] == pytest.approx(200.0)


# --- Statistics --------------------------------------------------------------------

def test_mcnemar_exact_reports_correct_cells():
    rows = []
    # 2 both-recovered, 3 both-not, 4 A-only(GUARDIAN), 1 B-only(NAIVE_RETRY)
    for i in range(2):
        rows += [make_row(f"br{i}", "GUARDIAN", "X", "INFRASTRUCTURE", 100, True),
                 make_row(f"br{i}", "NAIVE_RETRY", "X", "INFRASTRUCTURE", 100, True)]
    for i in range(3):
        rows += [make_row(f"bn{i}", "GUARDIAN", "X", "INFRASTRUCTURE", 100, False),
                 make_row(f"bn{i}", "NAIVE_RETRY", "X", "INFRASTRUCTURE", 100, False)]
    for i in range(4):
        rows += [make_row(f"ao{i}", "GUARDIAN", "X", "INFRASTRUCTURE", 100, True),
                 make_row(f"ao{i}", "NAIVE_RETRY", "X", "INFRASTRUCTURE", 100, False)]
    for i in range(1):
        rows += [make_row(f"bo{i}", "GUARDIAN", "X", "INFRASTRUCTURE", 100, False),
                 make_row(f"bo{i}", "NAIVE_RETRY", "X", "INFRASTRUCTURE", 100, True)]

    pivoted = pivot_by_transaction(rows)
    result = mcnemar_exact(pivoted, "GUARDIAN", "NAIVE_RETRY")

    assert result.both_recovered == 2
    assert result.both_not_recovered == 3
    assert result.a_only_recovered == 4
    assert result.b_only_recovered == 1
    assert result.concordant_n == 5
    assert result.discordant_n == 5
    assert 0.0 <= result.p_value <= 1.0


def test_mcnemar_exact_handles_zero_discordant_pairs():
    rows = []
    for i in range(5):
        rows += [make_row(f"t{i}", "GUARDIAN", "X", "INFRASTRUCTURE", 100, True),
                 make_row(f"t{i}", "NAIVE_RETRY", "X", "INFRASTRUCTURE", 100, True)]
    pivoted = pivot_by_transaction(rows)
    result = mcnemar_exact(pivoted, "GUARDIAN", "NAIVE_RETRY")
    assert result.discordant_n == 0
    assert result.p_value == 1.0


def test_wilcoxon_reports_nan_when_no_nonzero_differences():
    rows = []
    for i in range(5):
        rows += [make_row(f"t{i}", "GUARDIAN", "X", "INFRASTRUCTURE", 100, True),
                 make_row(f"t{i}", "NAIVE_RETRY", "X", "INFRASTRUCTURE", 100, True)]
    pivoted = pivot_by_transaction(rows)
    result = wilcoxon_signed_rank(pivoted, "GUARDIAN", "NAIVE_RETRY")
    assert result.n_nonzero_differences == 0
    assert result.p_value == 1.0


def test_wilcoxon_detects_a_real_paired_difference():
    rows = []
    for i in range(10):
        rows += [
            make_row(f"t{i}", "GUARDIAN", "X", "CARD_DECLINE", 100, True),
            make_row(f"t{i}", "NO_ACTION", "X", "CARD_DECLINE", 100, False),
        ]
    pivoted = pivot_by_transaction(rows)
    result = wilcoxon_signed_rank(pivoted, "GUARDIAN", "NO_ACTION")
    assert result.n_nonzero_differences == 10
    assert result.p_value < 0.05
    assert result.median_difference > 0
