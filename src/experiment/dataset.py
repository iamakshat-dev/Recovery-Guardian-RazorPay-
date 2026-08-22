"""
Recovery Guardian — Day 9 Dataset Subset (frozen before results)

Dataset subset choice, frozen BEFORE the Day 9 experiment was run:

    The existing frozen 15% TEST split (242 rows), produced by
    src.model.splitting.train_val_test_split(random_state=42) — the exact
    same split already used for Day 4/5 evaluation.

Rationale: Day 9 evaluates POLICY/OUTCOME behavior downstream of the
already-frozen classifier — it is NOT re-evaluating classifier
generalization, so there is no methodological reason to touch the split.
Reusing the already-established held-out test split avoids introducing a
new, undocumented subset choice, and matches the roadmap's own framing of
the three-way comparison running "on the identical held-out dataset."
"""

from pathlib import Path
from typing import List

import pandas as pd

from src.domain.models import PaymentEvent
from src.features.build_features import LABEL_COL, build_features
from src.model.splitting import train_val_test_split
from src.model.training import DATA_PATH, RANDOM_STATE


def load_frozen_test_split_payment_events(data_path: Path = DATA_PATH) -> List[PaymentEvent]:
    """Loads the same frozen test split Day 4/5 evaluated, converted into
    PaymentEvent objects (one per row), deterministically ordered by
    row index so repeated calls always produce the identical sequence."""
    raw_df = pd.read_csv(data_path)
    features_df = build_features(raw_df, keep_label=True)
    _, _, test_df = train_val_test_split(features_df, label_col=LABEL_COL, random_state=RANDOM_STATE)

    # test_df carries the engineered feature columns, not the raw ones
    # PaymentEvent needs -- re-select the corresponding raw rows by index,
    # sorted for a stable, deterministic iteration order.
    raw_test_df = raw_df.loc[sorted(test_df.index)]

    events = []
    for _, row in raw_test_df.iterrows():
        events.append(
            PaymentEvent(
                # Deterministic, not uuid4(): event_id never affects
                # feature building, classification, policy, or any Day 9
                # result field, but derived-from-transaction_id keeps it
                # fully reproducible anyway, with no exception.
                event_id=f"evt_experiment_{row['transaction_id']}",
                transaction_id=str(row["transaction_id"]),
                merchant_id=str(row["merchant_id"]),
                amount=float(row["amount"]),
                timestamp=row["timestamp"],
                payment_method=str(row["payment_method"]),
                failure_code=str(row["failure_code"]),
                retry_count=int(row["retry_count"]),
                webhook_delay_seconds=float(row["webhook_delay_seconds"]),
                gateway_error_rate_delta=float(row["gateway_error_rate_delta"]),
                merchant_failure_rate_delta=float(row["merchant_failure_rate_delta"]),
                cross_merchant_failure_rate=float(row["cross_merchant_failure_rate"]),
                customer_previous_successes=int(row["customer_previous_successes"]),
                customer_previous_failures=int(row["customer_previous_failures"]),
                incident_active=bool(int(row["incident_active"])),
                source="synthetic",
            )
        )
    return events
