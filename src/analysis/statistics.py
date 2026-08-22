"""
Recovery Guardian — Day 10 Paired Statistical Analysis

Transaction-level paired methods only (n=242 identical transactions
evaluated under every strategy — a paired/counterfactual design, not four
independent samples). Seed-level (n=3) analysis is deliberately NOT
subjected to a formal significance test — see docs/architecture.md's Day
10 section for why.
"""

from dataclasses import dataclass
from typing import Any, Dict, List

from scipy.stats import binomtest, wilcoxon


@dataclass(frozen=True)
class McNemarResult:
    comparison: str
    both_recovered: int
    both_not_recovered: int
    a_only_recovered: int
    b_only_recovered: int
    concordant_n: int
    discordant_n: int
    statistic: float  # the smaller discordant count (exact binomial test)
    p_value: float


def mcnemar_exact(
    pivoted: Dict[str, Dict[str, Any]],
    strategy_a: str,
    strategy_b: str,
) -> McNemarResult:
    """Exact McNemar's test (binomial on discordant pairs, p=0.5) —
    appropriate here because discordant counts are frequently small
    (Day 10 spec section 24B/24C: verify assumptions before use; the
    exact binomial form has no minimum-count requirement the way the
    chi-square approximation does, so it is used unconditionally for
    every comparison rather than switching tests case by case)."""
    both_recovered = both_not_recovered = a_only = b_only = 0

    for txn_id, by_strategy in pivoted.items():
        a_recovered = by_strategy[strategy_a]["recovered"]
        b_recovered = by_strategy[strategy_b]["recovered"]
        if a_recovered and b_recovered:
            both_recovered += 1
        elif not a_recovered and not b_recovered:
            both_not_recovered += 1
        elif a_recovered and not b_recovered:
            a_only += 1
        else:
            b_only += 1

    discordant_n = a_only + b_only
    concordant_n = both_recovered + both_not_recovered

    if discordant_n == 0:
        # No disagreement at all -- the test is degenerate; p=1.0 by
        # convention (no evidence of any directional difference possible).
        statistic = 0
        p_value = 1.0
    else:
        statistic = min(a_only, b_only)
        p_value = binomtest(statistic, discordant_n, p=0.5).pvalue

    return McNemarResult(
        comparison=f"{strategy_a} vs {strategy_b}",
        both_recovered=both_recovered,
        both_not_recovered=both_not_recovered,
        a_only_recovered=a_only,
        b_only_recovered=b_only,
        concordant_n=concordant_n,
        discordant_n=discordant_n,
        statistic=float(statistic),
        p_value=float(p_value),
    )


@dataclass(frozen=True)
class WilcoxonResult:
    comparison: str
    n_nonzero_differences: int
    statistic: float
    p_value: float
    median_difference: float


def wilcoxon_signed_rank(
    pivoted: Dict[str, Dict[str, Any]],
    strategy_a: str,
    strategy_b: str,
) -> WilcoxonResult:
    """Paired Wilcoxon signed-rank test on per-transaction monetary
    recovery differences (amount_recovered_A - amount_recovered_B).
    Requires at least one non-zero difference (scipy's own assumption);
    if all differences are zero, this is reported explicitly rather than
    silently invoking the test."""
    diffs = []
    for txn_id, by_strategy in pivoted.items():
        a_amt = by_strategy[strategy_a]["amount_recovered"]
        b_amt = by_strategy[strategy_b]["amount_recovered"]
        diffs.append(a_amt - b_amt)

    nonzero = [d for d in diffs if d != 0]
    comparison = f"{strategy_a} vs {strategy_b}"

    if len(nonzero) == 0:
        return WilcoxonResult(comparison, 0, float("nan"), 1.0, 0.0)

    diffs_sorted = sorted(diffs)
    n = len(diffs_sorted)
    median_difference = (
        diffs_sorted[n // 2]
        if n % 2 == 1
        else (diffs_sorted[n // 2 - 1] + diffs_sorted[n // 2]) / 2
    )

    result = wilcoxon(diffs)
    return WilcoxonResult(
        comparison=comparison,
        n_nonzero_differences=len(nonzero),
        statistic=float(result.statistic),
        p_value=float(result.pvalue),
        median_difference=float(median_difference),
    )
