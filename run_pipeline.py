"""
Recovery Guardian — Day 3 CLI Entry Point

    python run_pipeline.py --single-transaction

Loads one real row from the synthetic dataset, converts it through the
synthetic adapter into a PaymentEvent, runs it through the core pipeline,
and prints the resulting decision. This is the Day 3 milestone: proof that
one transaction can travel end to end — event -> features -> classifier
-> policy -> audit record -> SQLite — without any CSV- or
Razorpay-specific logic leaking into the pipeline itself.

Day 4 update: the pipeline's classifier stage became the real, trained
Logistic Regression model (src/model/classifier.py) rather than the Day 3
placeholder. Run `python -m src.model.training` first if no trained
artifact exists yet.

Day 5 update: the pipeline now uses the CALIBRATED classifier
(src/model/calibrated_classifier.py) — this CLI's output will show
`Model Version: root-cause-logreg-calibrated-v1` accordingly. Run
`python -m src.model.calibrate` first if no calibrated artifact exists
yet (it requires the Day 4 raw artifact to already exist). The policy
engine is still the Day 3 placeholder (`Policy Version: placeholder-v1`).

Day 3 rerun semantics: this CLI does NOT implement idempotency. Each
invocation reads the same dataset row but the synthetic adapter mints a
fresh event_id and the pipeline mints a fresh decision_id, so running this
command twice is expected to produce two separate persisted observations
of the same underlying transaction_id. The Day 7 policy/idempotency system
is what will decide, later, whether repeat observations should be
deduplicated, capped, or blocked — that logic does not exist yet.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).parent))

from src.ingestion.synthetic_adapter import synthetic_to_payment_event
from src.pipeline.pipeline import run_pipeline

DATA_PATH = Path(__file__).parent / "data" / "synthetic_events.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Recovery Guardian Day 3 pipeline CLI")
    parser.add_argument(
        "--single-transaction",
        action="store_true",
        help="Process exactly one row from the synthetic dataset end to end.",
    )
    parser.add_argument(
        "--row-index",
        type=int,
        default=0,
        help="Which row of the synthetic dataset to use (default: the first row).",
    )
    args = parser.parse_args()

    if not args.single_transaction:
        parser.error("Day 3 only supports --single-transaction.")

    if not DATA_PATH.exists():
        print(f"Synthetic dataset not found at {DATA_PATH}.")
        print("Generate it first: make data")
        sys.exit(1)

    df = pd.read_csv(DATA_PATH)
    if not (0 <= args.row_index < len(df)):
        print(f"--row-index {args.row_index} is out of range (dataset has {len(df)} rows).")
        sys.exit(1)

    row = df.iloc[args.row_index]
    event = synthetic_to_payment_event(row)
    record = run_pipeline(event)

    print("Recovery Guardian — Single Transaction\n")
    print(f"Transaction: {record.event.transaction_id}")
    print(f"Amount: {record.event.amount}")
    print(f"Root Cause: {record.prediction.root_cause.value}")
    print(f"Confidence: {record.prediction.probability}")
    print(f"Action: {record.policy.action.value}")
    print(f"Reason: {', '.join(rc.value for rc in record.policy.reason_codes)}")
    print(f"Model Version: {record.prediction.model_version}")
    print(f"Policy Version: {record.policy.policy_version}")
    print("\nAudit record persisted successfully.")


if __name__ == "__main__":
    main()
