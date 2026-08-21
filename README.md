# Recovery Guardian
### The decision layer for safe, measured revenue recovery

> Work in progress — Day 1 of a 15-day build for the Razorpay AI Builder Intern Challenge (Track 3: AI Revenue Recovery). Full README with architecture, methodology, and results lands on Day 14.

## What's here today (Day 1)

- `data/generate_data.py` — synthetic payment-failure dataset generator with deliberately overlapping, non-trivial feature distributions across 6 root-cause classes, plus an explicitly injected failure-rate spike (Aug 15, 22:10–22:40) used for the incident demo later in the build.
- `src/domain/models.py` — typed domain objects: `PaymentEvent`, `RootCausePrediction`, `PolicyDecision`, `RecoveryOutcome`, `DecisionRecord`.
- `src/db.py` — SQLite schema (events, decisions, outcomes, idempotency log).
- `src/api/app.py` — FastAPI skeleton: health check + event ingestion. No classifier or policy logic yet — that's Day 4 onward.

## Quickstart

```bash
pip install -r requirements.txt
make data      # generates data/synthetic_events.csv
make initdb    # creates recovery_guardian.db
make run       # starts the API on localhost:8000
```

Then: `curl http://localhost:8000/health`

## Design notes worth knowing up front

- **SQLite, not Postgres** — a deliberate choice for zero-setup reproducibility, not an oversight.
- **The synthetic dataset is intentionally not trivially separable.** `incident_active` only explains ~18% of `INFRASTRUCTURE` cases by design — the classifier has to combine multiple signals, or its precision/recall numbers wouldn't mean anything.
- **Four separate typed objects, not one dict that grows fields as it flows through the pipeline.** Payment event ≠ model prediction ≠ policy decision ≠ outcome.
