# Recovery Guardian

**AI-assisted payment recovery with deterministic safety controls.**

A 14-day build for the Razorpay AI Builder Intern Challenge (Track 3: AI
Revenue Recovery). This README is the judge-facing entry point — for full
day-by-day implementation detail see `docs/architecture.md` and
`PROGRESS.md`.

## Problem

When a payment fails, the failure can mean very different things:

- the card was declined or funds were insufficient (customer-side),
- the gateway/infrastructure was degraded (retryable),
- the customer abandoned the flow or an OTP timed out, or
- **the payment's final state is genuinely unknown** — the webhook never
  arrived, or arrived too late to trust.

Blindly retrying every failure recovers some revenue but is unsafe: a
retry against a payment whose outcome is unknown can create a **duplicate
charge**. Root-cause classification exists specifically so a system can
tell "safe to retry" apart from "state is ambiguous, do not retry" before
it acts — not merely to label the failure for a dashboard.

## Solution

    payment event
        -> canonical PaymentEvent
        -> calibrated ML root-cause prediction
        -> deterministic policy engine
        -> bounded recovery action
        -> counterfactual outcome evaluation
        -> grounded explanation

A frozen, calibrated Logistic Regression classifies the likely root cause
and reports a calibrated probability. A deterministic, config-driven
policy engine — never the model, never an LLM — decides what action is
*permitted*, applying a fixed safety-first evaluation order (input
validation → opt-out → amount threshold → the `WEBHOOK_AMBIGUITY` hard
override → retry cap → cooldown → idempotency → root-cause + confidence).
A shared counterfactual simulator estimates the consequence of the
authorized action. An explanation layer, backed by Claude with a
deterministic no-network fallback, describes the decision in prose — it
has no authority to change it.

## Safety invariant

    WEBHOOK_AMBIGUITY  ->  BLOCK_RECONCILE

always, regardless of model confidence. This is a hard override in
`src/policy/engine.py`, evaluated before the retry cap, cooldown, and
idempotency guards specifically so nothing downstream can turn it into a
retry. There is no code path anywhere in the policy engine that maps
`WEBHOOK_AMBIGUITY` to `DEFER_RETRY`.

The explanation layer (Day 13) cannot change this either:
`src.explain.service.explain_decision()` reads exactly two free-text
fields (`summary`, `safety_note`) from whatever provider generated them —
every decision field (`root_cause`, `confidence`, `action`, `reason`,
`outcome_status`) is assigned directly from the already-computed
evidence, never from provider output, even from a provider that
deliberately tries to forge a different action
(`tests/test_explain.py::test_provider_cannot_override_the_decision`).

## Evidence (Day 9/10, simulated)

Four strategies scored through one shared counterfactual environment
(`src/recovery/simulator.py`) using Common Random Numbers, so every
strategy is compared on identical draws — only the chosen action differs.
Primary seed 42, n=242 (the frozen Day 4 held-out test split):

| Strategy | Simulated recovery rate | Simulated amount recovered | Duplicate-charge risk |
|---|---|---|---|
| Naive Retry | 29.75% | ₹205,427.28 | 12 |
| Rules-only | 33.88% | ₹238,230.16 | 3 |
| **Guardian** | 28.93% | ₹193,316.24 | **0** |
| No Action | 0.00% | ₹0.00 | 0 |

Recovery rate = recovered transactions / transactions evaluated (count-based, not amount-weighted). All figures are **simulated/counterfactual** (Day 8), never observed production revenue.

**Guardian does not recover the most simulated revenue.** Rules-only
does. Guardian's value proposition is **recovery bounded by explicit
safety constraints**, not unconditional maximum recovery. The clearest
illustration is the `WEBHOOK_AMBIGUITY` population (25 transactions,
seed 42):

| Strategy | Simulated recovery | Duplicate-charge-risk outcomes |
|---|---|---|
| Naive Retry | 68% | 12 |
| Rules-only | 20% | 3 |
| **Guardian** | **0%** | **0** |

Guardian recovers nothing here because it never authorizes an automated
retry when payment state is ambiguous — that is the trade-off being
demonstrated, not a shortcoming. Full methodology, McNemar/Wilcoxon
statistical tests, and per-root-cause breakdowns: `docs/architecture.md`
(Day 9/10 sections).

## Razorpay integration boundary

- A production-shaped adapter exists (`src/ingestion/razorpay_adapter.py`,
  Day 11) that normalizes a Razorpay-style webhook payload into the same
  canonical `PaymentEvent` the synthetic pipeline uses — proven to
  converge on identical predictions/actions with synthetic twins of the
  same underlying transaction.
- **No live Razorpay integration exists.** No API calls, no credentials,
  no webhook-signature verification. `.env.example` documents the
  expected variable names as empty placeholders only.
- Real platform-level monitoring (gateway error rate, cross-merchant
  failure rate, active-incident signal) is **not implemented** — the
  adapter accepts these as an optional companion `PlatformHealthContext`
  input (Option A) rather than fabricating them from a single payment
  payload, which no real payload can supply on its own.

## Incident replay (Day 12)

`experiments/run_incident_demo.py` replays the existing, deliberately
injected synthetic incident burst (110 transactions, `2026-08-15 22:10`
– `22:40`, `data/generate_data.py`) through the real feature builder,
classifier, and policy engine — not a new incident, not a live detector.

- Full incident window: **73/73** ground-truth `INFRASTRUCTURE`
  transactions correctly predicted.
- Held-out TEST-split subset of that window: **15/15** correctly
  predicted.
- **Disclosed limitation, not smoothed over**: 71.8% of the incident
  window's transactions are in the classifier's TRAIN split, so the
  full-window figure is a replay-behavior demonstration, not a
  generalization claim. The 15-row held-out subset is small, and — this
  is stated plainly rather than implied away — **that perfect 15/15
  result was never run through this project's own established
  suspicious-performance investigation** (the same ">98%" leakage check
  applied at Day 4 to four classes that hit 100% on the full 242-row test
  set). It remains an open methodological gap, recorded honestly in
  `docs/architecture.md`'s Day 13 section, not resolved by asserting it
  away.
- The single `WEBHOOK_AMBIGUITY` case in the incident window still
  produces `BLOCK_RECONCILE` — the safety invariant held during the
  incident too.

## LLM explanation layer (Day 13)

`src/explain/` — `ClaudeExplanationProvider` (Anthropic Messages API,
lazily imported, no package or credentials required unless
`LLM_ENABLED=true`) plus a `DeterministicFallbackProvider` used by
default and automatically on any provider failure (timeout, malformed
response, missing credentials). The LLM only ever contributes prose
(`summary`, `safety_note`); it cannot select a root cause, cannot select
a `RecoveryAction`, and cannot alter the policy reason or confidence —
enforced structurally in `explain_decision()`, not by prompt convention
alone (the system prompt is defense in depth on top of that structural
guarantee).

## Limitations

- The dataset is synthetic (`data/generate_data.py`) — no real payment
  traffic anywhere in this project.
- Recovery probabilities and outcomes are simulated/counterfactual (Day
  8) — never observed production recovery.
- No real production recovery-outcome labels exist to validate the
  simulation assumptions against.
- The Day 12 held-out `INFRASTRUCTURE` sample is small (15 transactions),
  and its 15/15 result remains an open methodological limitation (see
  above) — not independently investigated for leakage or generalization
  plausibility.
- No live Razorpay traffic, credentials, or network calls exist anywhere
  in this repository.
- No real production infrastructure/platform monitoring is implemented.
- No compliance, security certification, or production security review
  has been performed.
- No statistical claim of real-world production effectiveness is made —
  Day 9/10's evidence is a controlled comparison under stated simulation
  assumptions, not a production A/B result.

## Reproduction

```bash
pip install -r requirements.txt

# Generate the frozen synthetic dataset (deterministic, seed 42)
make data

# Train + calibrate the classifier (or skip — a committed artifact may
# already exist locally; both commands are idempotent and safe to rerun)
make train
make calibrate

# Run the full backend test suite (309 tests as of Day 14; the
# frontend's own test suite — 66 tests as of Day 15 — is separate, see below)
pytest -q

# Day 14 — judge-facing demo (WEBHOOK_AMBIGUITY + two INFRASTRUCTURE
# scenarios, real ML -> policy -> outcome -> explanation, deterministic,
# no credentials required)
python experiments/run_judge_demo.py
python experiments/run_judge_demo.py --scenario webhook_ambiguity

# Day 12 — incident scenario replay (110-transaction synthetic incident
# burst, real pipeline, full safety verification)
python experiments/run_incident_demo.py

# Day 9 — four-strategy counterfactual experiment (writes
# experiments/results/day9_seed_<N>_*.json)
python experiments/run_day9_experiment.py --seed 42

# Day 10 — statistical analysis over the frozen Day 9 results
python experiments/run_day10_analysis.py

# Day 15 — regenerate the frontend's artifact-backed data snapshot
# (reads the three JSON artifacts above; fails loudly if any is missing)
python scripts/generate_frontend_snapshot.py

# Day 15 — frontend (Overview, Safety, Decision Pipeline, Explainability,
# Incident Replay)
cd frontend
npm install
npm run dev     # local dev server
npm test        # 66 frontend tests
npm run build   # production build
```

All of the above are deterministic given the same inputs (verified via
two-separate-process byte-identical output for the Day 12/14 demos, and
cross-process reproducibility checks for Day 9's experiment output — see
`docs/architecture.md`). `experiments/results/*.json` and `*.png` are
gitignored and regenerated by running the commands above.

## Frontend (Day 15)

A React/TypeScript/Vite/Tailwind product shell (`frontend/`) visualizing
the already-computed evidence above — it never runs the model, the
policy engine, or the simulator itself.

- **Overview** — the judge-facing landing page: hero, the primary safety
  KPI, strategy comparison, and the `WEBHOOK_AMBIGUITY` signature case.
- **Safety** — a dedicated expansion of the recovery-vs-safety trade-off.
- **Decision Pipeline** — an interactive, scenario-switchable replay of
  the real pipeline (`Payment Event → Feature Builder → ML Classifier →
  Policy Engine → Recovery Action`) for the three Day 14 judge-demo
  scenarios.
- **Explainability** — answers "why did Guardian make this decision?"
  strictly downstream of the decision: root cause, policy action/reason,
  the Day 13 explanation prose, and an explicit
  `action before explanation == action after explanation` check proving
  the explanation layer cannot alter the outcome.
- **Incident Replay** — the Day 12 synthetic incident window (before →
  incident → after failure density, root-cause distribution, classifier/
  policy result, train/validation/test disclosure, the `WEBHOOK_AMBIGUITY`
  safety result), explicitly labeled a **historical synthetic replay**,
  never live monitoring.

**Data plumbing**: `scripts/generate_frontend_snapshot.py` is the single,
read-only boundary between the frozen backend artifacts
(`experiments/results/day{9,12,14}_*.json`) and the frontend
(`frontend/src/data/snapshot.ts`, committed and typed). It only reads,
validates, and selects already-computed values — it never recomputes a
metric, reruns the model or policy, or invents a missing value; missing/
malformed source data fails the generation loudly rather than silently
defaulting.

The Day 9 `WEBHOOK_AMBIGUITY` population (25 held-out test transactions,
shown on Safety) and the Day 12 `WEBHOOK_AMBIGUITY` population (1
incident-window transaction, shown on Incident Replay) are two distinct
populations, always labeled separately and never combined.

## Architecture

```
Razorpay-shaped Event                Synthetic dataset row
        |                                    |
Razorpay Adapter                   Synthetic Adapter
 (src/ingestion/                  (src/ingestion/
  razorpay_adapter.py)             synthetic_adapter.py)
        \                                    /
         \                                  /
          v                                v
              PaymentEvent (canonical, shared)
                        |
                Feature Builder
              (src/features/build_features.py)
                        |
              Calibrated ML Classifier
          (src/model/calibrated_classifier.py, frozen)
                        |
                RootCausePrediction
                        |
              Day 7 Policy Engine
              (src/policy/engine.py, frozen)
                        |
                  RecoveryAction
                  /            \
                 /              \
    Recovery Outcome        Explanation Layer
    Simulator (Day 8,        (src/explain/, Day 13)
    frozen, SIMULATED)              |
                              Claude, or
                          Deterministic Fallback
                       (no decision authority either way)
```

Every external source normalizes into the same canonical `PaymentEvent`
before touching the feature builder, the model, or the policy — a future
real Razorpay dataset requires mapping the new source into that contract
and retraining/recalibrating against appropriately labeled production
data. It does not require rebuilding the intelligence pipeline. The
current synthetic-trained model is not claimed to already be
production-accurate.

## Judge questions

**What revenue problem does Recovery Guardian solve?** Recovering
payment-failure revenue without introducing duplicate-charge risk from
blind, undifferentiated retries.

**Why is naive retry unsafe?** It retries `WEBHOOK_AMBIGUITY` cases too —
measured at 12 simulated duplicate-charge-risk outcomes out of 25 such
transactions, seed 42.

**Why is root-cause classification necessary?** `failure_code` alone
cannot distinguish `INFRASTRUCTURE` from `WEBHOOK_AMBIGUITY` — both
legitimately produce `gateway_timeout` by dataset design; the ML
classifier combines multiple signals to make that distinction.

**Why does `WEBHOOK_AMBIGUITY` require `BLOCK_RECONCILE`?** The payment's
final state is unknown; retrying risks charging a payment that may have
already succeeded. Blocking and reconciling by other means is the only
safe automated action.

**What exactly does the ML model do?** Predicts a calibrated probability
distribution over 6 root causes from 26 frozen features (Logistic
Regression + sigmoid calibration, `src/model/`). It never decides an
action.

**What exactly does the policy engine do?** Deterministically maps
(root cause, confidence, safety context) to one of 5 `RecoveryAction`
values via a fixed, config-driven, safety-first evaluation order
(`src/policy/engine.py`, `src/policy/rules.yaml`). It never touches the
model.

**Can the LLM change the recovery decision?** No — structurally, not by
convention (see "LLM explanation layer" above).

**What happens if Claude fails?** `DeterministicFallbackProvider`
produces a template-based explanation directly from the same evidence;
the decision is unaffected either way.

**What happens if Razorpay later provides real production data?** It
gets mapped through an adapter into the same canonical `PaymentEvent` —
no pipeline rebuild required (see "Architecture").

**Can the model be retrained against normalized real data?** Yes — the
feature contract (`FEATURE_COLUMNS`) and training path
(`src/model/training.py`, `src/model/calibrate.py`) are source-agnostic;
retraining requires real, appropriately labeled data, which does not
exist in this project.

**What is simulated rather than observed?** Every recovery outcome and
recovered-amount figure (Day 8's `estimate_outcome()`). Model predictions
and policy decisions are observed (deterministic code behavior), not
simulated.

**Why does Guardian recover less than Rules-only currently?** Rules-only
retries some `WEBHOOK_AMBIGUITY` transactions that share a `gateway_timeout`
failure code with `INFRASTRUCTURE`; Guardian's ML-based distinction
correctly blocks those instead, trading simulated recovery for zero
duplicate-charge risk.

**How does Guardian demonstrate safety?** Zero simulated duplicate-charge
risk across all three tested seeds (42, 43, 44) and every
`WEBHOOK_AMBIGUITY` transaction in both the Day 9 experiment and the Day
12 incident replay routing to `BLOCK_RECONCILE`, never `DEFER_RETRY`.

**What is the limitation of the Day 12 15/15 result?** It is a small,
held-out sample that was never run through the project's own
suspicious-performance investigation methodology — disclosed explicitly
above and in `docs/architecture.md`, not treated as a validated
invariant.

**Is this a live Razorpay integration?** No.

**Why isn't blockchain/Alchemy required?** There is no problem in this
project — payment-failure classification and bounded recovery — that
needs on-chain settlement or a blockchain audit trail.

**Why isn't Kubernetes required?** The project runs as a deterministic
CLI + SQLite + a small FastAPI skeleton; there is no deployed, scaled
service to orchestrate yet.

**Why is the current CLI demo sufficient for this stage?** It exercises
the real, unmodified decision path end to end, produces deterministic
structured JSON evidence, and can be screen-recorded directly — a
frontend would add visual polish without adding engineering evidence, and
was deliberately deferred rather than rushed.
