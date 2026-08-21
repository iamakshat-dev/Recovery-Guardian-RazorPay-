"""
Recovery Guardian — Deterministic Train/Validation/Test Split (Day 4)

A single, reusable 70/15/15 stratified split, used by training today and
by any future re-evaluation (e.g. Day 10's threshold reruns) so every
consumer of the dataset partitions it identically.

Deterministic given the same DataFrame and random_state: this is what lets
`docs`/graders reproduce the exact same split, and what lets
test_split_is_deterministic assert repeatability directly.
"""

from typing import Tuple

import pandas as pd
from sklearn.model_selection import train_test_split

DEFAULT_RANDOM_STATE = 42  # the project's fixed reproducibility seed,
# matching data/generate_data.py's --seed default.


def train_val_test_split(
    df: pd.DataFrame,
    label_col: str,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split `df` into 70% train / 15% validation / 15% test, stratified by
    `label_col` wherever every class has enough members to support it.

    Args:
        df: the full features_df (or raw dataset) to split. Not mutated.
        label_col: the column to stratify by (the supervised target).
        random_state: fixed seed for reproducibility. Must be passed
            explicitly by callers, not silently defaulted away, to keep the
            seed visible at the call site.

    Returns:
        (train_df, val_df, test_df) — three disjoint, index-preserving
        DataFrame views covering every row of `df` exactly once.
    """
    labels = df[label_col]

    # First split off 70% train vs. 30% (val+test) combined.
    train_df, remaining_df = train_test_split(
        df,
        test_size=0.30,
        random_state=random_state,
        stratify=labels,
    )

    # Then split the remaining 30% evenly into two 15% halves.
    val_df, test_df = train_test_split(
        remaining_df,
        test_size=0.50,
        random_state=random_state,
        stratify=remaining_df[label_col],
    )

    return train_df, val_df, test_df
