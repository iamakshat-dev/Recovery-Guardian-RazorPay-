# Recovery Guardian — ML Architecture (frozen as of Day 6)

This document records the **verified, frozen** state of the root-cause
classification pipeline after Day 4 (raw classifier), Day 5 (calibration +
evaluation), and Day 6 (freeze + reproducibility verification). Every
number below was regenerated and independently re-verified during the Day
6 clean-checkout reproduction on 2026-08-22 — none of it is copied from
earlier console output or memory.

## Model

| | |
|---|---|
| Algorithm | `sklearn.linear_model.LogisticRegression` (solver `lbfgs`, genuinely multinomial/softmax for 6 classes — `multi_class` no longer exists as a parameter in scikit-learn ≥1.7; `lbfgs` always uses the multinomial formulation for >2 classes) |
| Feature count | 26 (`src.features.build_features.FEATURE_COLUMNS`) |
| Class count | 6 |
| Class ordering | `CARD_DECLINE, INFRASTRUCTURE, INSUFFICIENT_FUNDS, OTP_TIMEOUT, USER_ABANDONMENT, WEBHOOK_AMBIGUITY` (alphabetical — scikit-learn's own convention, taken from `model.classes_`) |
| Model configuration | `max_iter=1000, random_state=42` |
| Raw model version | `root-cause-logreg-v1` |
| Calibrated model version | `root-cause-logreg-calibrated-v1` |

## Dataset

| | |
|---|---|
| Total rows | 1610 |
| Train rows | 1127 |
| Validation rows | 241 |
| Test rows | 242 |
| Generation seed | 42 (`data/generate_data.py --seed 42`) |
| Generator command | `make data` → `python3 generate_data.py --rows 1500 --burst-rows 110 --seed 42 --out synthetic_events.csv` |

## Training

| | |
|---|---|
| Training command | `python -m src.model.training` (or `make train`) |
| Split methodology | Deterministic 70/15/15, stratified by `actual_root_cause` (`src.model.splitting.train_val_test_split`) |
| Random seed | 42, used identically for the split and the `LogisticRegression` fit |
| Training sample count | 1127 |

## Calibration

| | |
|---|---|
| Calibration command | `python -m src.model.calibrate` (or `make calibrate`) |
| Method | Sigmoid (Platt) scaling, via `sklearn.frozen.FrozenEstimator` + `CalibratedClassifierCV(method="sigmoid")` |
| Validation sample count | 241 |
| Test data excluded from calibration fitting? | Yes — `fit_calibration(model, X_val, y_val)` receives only the validation split; verified both by code inspection and by `tests/test_calibration.py::test_calibration_receives_only_validation_data_not_test_data`, which spies on the real call and asserts its input row-index set equals the validation split and is disjoint from the test split. |
| Underlying model retrained by calibration? | No — `FrozenEstimator.fit()` is a no-op by construction; verified by comparing `coef_`/`intercept_`/`classes_` before and after calibration fitting (byte-identical, both in-memory and re-loaded from disk). |

## Final Metrics (test split, n=242)

### Day 4 — raw (uncalibrated) model

| Metric | Value |
|---|---|
| Accuracy | 0.9834710743801653 |
| Macro F1 | 0.9810066476733144 |

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| CARD_DECLINE | 1.0000 | 1.0000 | 1.0000 | 52 |
| INSUFFICIENT_FUNDS | 1.0000 | 1.0000 | 1.0000 | 47 |
| OTP_TIMEOUT | 1.0000 | 1.0000 | 1.0000 | 31 |
| USER_ABANDONMENT | 1.0000 | 1.0000 | 1.0000 | 32 |
| **INFRASTRUCTURE** | 0.9630 | 0.9630 | 0.9630 | 54 |
| **WEBHOOK_AMBIGUITY** | 0.9231 | 0.9231 | 0.9231 | 26 |

### Day 5 — calibrated model

| Metric | Value |
|---|---|
| Accuracy | 0.9793388429752066 |
| Macro Precision | 0.9775757575757575 |
| Macro Recall | 0.9745963912630579 |
| Macro F1 | 0.9760148707801163 |

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| CARD_DECLINE | 1.0000 | 1.0000 | 1.0000 | 52 |
| INSUFFICIENT_FUNDS | 1.0000 | 1.0000 | 1.0000 | 47 |
| OTP_TIMEOUT | 1.0000 | 1.0000 | 1.0000 | 31 |
| USER_ABANDONMENT | 1.0000 | 1.0000 | 1.0000 | 32 |
| **INFRASTRUCTURE** | 0.9455 | 0.9630 | 0.9541 | 54 |
| **WEBHOOK_AMBIGUITY** | 0.9200 | 0.8846 | 0.9020 | 26 |

Every off-diagonal confusion-matrix entry (5 test rows total) occurs
exclusively between `INFRASTRUCTURE` and `WEBHOOK_AMBIGUITY` — the pair
the dataset was deliberately designed to make hard to separate
(`gateway_timeout` is shared between them). All other classes are
perfectly separated because their `failure_code` values are unique to
that class by construction (documented in
`src/features/build_features.py`).

### Calibration quality

| Metric | Raw | Calibrated |
|---|---|---|
| Multiclass Brier score | 0.030333406658799883 | 0.034099774237378415 |
| ECE (top-label, 10 bins) | 0.044046587492415856 | 0.042769588482043784 |

Calibration had **negligible practical effect** on this dataset: Brier
score was marginally *worse* after calibration; ECE improved only
marginally. The raw model was already well-calibrated, and the 241-row
validation set gives sigmoid calibration little room to improve on that —
reported honestly, not retuned.

## Artifacts

| Artifact | Path |
|---|---|
| Raw model | `artifacts/root_cause_classifier.joblib` (gitignored — regenerate with `python -m src.model.training`) |
| Calibrated model | `artifacts/root_cause_classifier_calibrated.joblib` (gitignored — regenerate with `python -m src.model.calibrate`) |
| Day 4 metrics | `artifacts/root_cause_classifier_metrics.json` |
| Day 5 metrics | `experiments/results/evaluation_metrics.json` |
| Day 5 plots | `experiments/results/confusion_matrix.png`, `experiments/results/calibration_plot.png` |

No separate preprocessing artifact exists — feature construction is a
pure function (`src.features.build_features.build_features`) applied
identically at training and inference time; the ordered `FEATURE_COLUMNS`
list is persisted inside both model artifacts and validated against the
live feature builder at load time (`FeatureSchemaMismatchError` on drift).

## Reproducibility (verified 2026-08-22, Day 6)

**Method:** `git clone` of the local repository at commit `6f72b220f0dff08aa449a7e1f14317c4cfab6cb4` into a fresh, isolated directory (containing only committed state — no gitignored files present), with a fresh Python virtual environment.

**Environment note:** the pinned `requirements.txt` (`numpy==2.1.1` etc.) fails to build on this machine's only available Python (3.14.2) — a pre-existing, previously-documented limitation, not a Day 6 finding. The clean-checkout reproduction used the same unpinned dependency versions (`numpy 2.5.2`, `pandas 3.0.5`, `scikit-learn 1.9.0`, `joblib 1.5.3`) as the ones that produced the authoritative frozen results being compared against, for a valid apples-to-apples comparison. `requirements.txt` itself was **not** modified.

**Commands used**, in order:
```
make data
python -m src.model.training
python -m src.model.calibrate
```

**Results:**

| Check | Result |
|---|---|
| Dataset reproduction | Every column except `transaction_id` byte-identical. `transaction_id`'s trailing 6-hex-char suffix differs because `data/generate_data.py` generates it via unseeded `uuid.uuid4()`, not the seeded RNG — a pre-existing generator property, not a defect. `transaction_id` is excluded from `FEATURE_COLUMNS`, so this has no effect on splits, features, or the model. |
| Day 4 model parameters | **Exact match.** `coef_` and `intercept_` byte-identical (max abs diff 0.0), `classes_` identical, `n_iter_` identical. |
| Day 4 predictions | **Exact match** over the complete 242-row test set: 100% prediction agreement, max probability absolute difference 0.0. |
| Day 4 metrics | `artifacts/root_cause_classifier_metrics.json` byte-identical to the frozen file. |
| Day 5 calibration | Sigmoid calibrator parameters (`a_`, `b_` per class) byte-identical (max abs diff 0.0). |
| Day 5 metrics | `experiments/results/evaluation_metrics.json` byte-identical to the frozen file. |

**Verdict: EXACT MATCH** (with the fully-explained, feature-irrelevant `transaction_id` exception above).

---

## Day 8 — Shared Counterfactual Outcome Environment

Day 7's policy engine answers "what are we permitted to do?" This section
covers Day 8: "if we took action X, what would probably happen?" — the
shared environment Day 9/10's three-way experiment (naive retry-everything
vs. rules-only vs. Guardian) will use to score every strategy fairly.

### The shared function

```
estimate_outcome(evidence: RecoveryEvidence, action: RecoveryAction) -> RecoveryOutcome
```
(`src/recovery/simulator.py`). It is deliberately **not** coupled to
`PolicyDecision` and does not import `src.policy.engine` — it takes a bare
`RecoveryAction` and evaluates it exactly as given, for any of the five
values (`DEFER_RETRY`, `CUSTOMER_RECOVERY`, `BLOCK_RECONCILE`,
`HUMAN_REVIEW`, `NO_ACTION`), regardless of whether Guardian's real policy
would ever authorize that action for the given evidence.

**Why it accepts hypothetical actions:** Guardian's production pipeline
(`src/pipeline/pipeline.py`) calls this function with the actual Day
7-authorized action only — it never asks the estimator to evaluate
anything else. Day 9/10 will call the exact same function with
hypothetical actions a naive or rules-only strategy would have chosen
instead, including ones Guardian's own policy would never authorize (e.g.
`DEFER_RETRY` on `WEBHOOK_AMBIGUITY` evidence). This is required for a
fair three-way comparison: scoring what a strategy *would have done* is
not the same as authorizing it to actually happen, and using a different
outcome model per strategy would invalidate the comparison entirely.
There is exactly one outcome mechanism in the codebase — no
`guardian_outcome_model`, `naive_outcome_model`, or `rules_outcome_model`
exists or should ever be created.

### Observed vs. expected vs. simulated

- **Observed** — an actual recorded payment outcome. **The project has
  none.** Audited before building anything: `data/generate_data.py`'s
  synthetic dataset, the `recovery_outcomes` table, and every other data
  source were inspected, and none contain action-taken/recovery-success
  labels. Building a supervised outcome model on fabricated labels was
  therefore explicitly rejected in favor of a transparent synthetic
  simulator (`src/recovery/simulation_config.yaml`).
- **Expected** — a probability-weighted estimate,
  `amount × probability_of_recovery(evidence, action)`. Exposed as a
  separate function specifically so it's never confused with a realized
  outcome.
- **Simulated** — the single realized `RecoveryOutcome` `estimate_outcome`
  returns for one (evidence, action, seed) — a Bernoulli draw from a
  local `random.Random(seed)` instance (never the global `random` module),
  reproducible by default even with no explicit seed (one is derived
  deterministically from `transaction_id` + `action`).

**No simulated recovery is ever reported as real revenue.** Nothing in
this codebase or its documentation claims "₹X was recovered" — only
simulated/expected/counterfactual recovery.

### Duplicate-charge risk

`RecoveryOutcome.duplicate_charge_risk: bool` (additive field, default
`False`) represents the downside of unsafe actions, independent of
`recovered` — an outcome can be `recovered=True` **and**
`duplicate_charge_risk=True` simultaneously (an unsafe retry can recover
money while also creating a duplicate charge). Only
`DEFER_RETRY` on `WEBHOOK_AMBIGUITY` evidence carries nonzero risk in the
current model: the payment state is genuinely unknown, so retrying might
be re-charging a payment that already silently succeeded. This is
governed by two **explicit, synthetic, documented simulation
assumptions** in `simulation_config.yaml` (not observed statistics):

| Assumption | Value | Meaning |
|---|---|---|
| `original_payment_already_succeeded_probability` | 0.40 | P(the unresolved payment had already succeeded) |
| `genuine_retry_success_probability` | 0.50 | P(a retry succeeds, given the original genuinely failed) |

If the original had already succeeded, the "retry" trivially succeeds
again — recovering nothing new and flagging `duplicate_charge_risk=True`.
`BLOCK_RECONCILE` on the same evidence always produces
`duplicate_charge_risk=False, recovered=False` — no automatic retry, no
invented recovery.

### RecoveryOutcome (existing model, minimally extended)

The original Day 1 fields are **unchanged**: `transaction_id`,
`action_taken`, `recovered`, `amount_recovered`, `decision_id`,
`timestamp` (nothing was ever renamed or replaced). Day 8 added exactly
two additive fields, both defaulted for backward compatibility:
`duplicate_charge_risk: bool = False` and `outcome_reason: str = ""`
(a short audit label, e.g. `"WEBHOOK_AMBIGUITY_RETRY_DUPLICATE_CHARGE"`).

`unrecovered_amount` was deliberately **not** added as a stored field —
storing it would require also redundantly storing the original
transaction amount on `RecoveryOutcome`. Instead it's a small derived
helper, `src.recovery.simulator.unrecovered_amount(transaction_amount,
outcome)`, computed from the amount already available on
`PaymentEvent`/`RecoveryEvidence`.

The existing `recovery_outcomes` table (`src/db.py`) was extended
additively with `duplicate_charge_risk INTEGER NOT NULL DEFAULT 0` and
`outcome_reason TEXT NOT NULL DEFAULT ''` — no new table, no redesign.
`transaction_id` remains that table's existing primary key (a Day 1/2
decision); persisting therefore uses `INSERT OR REPLACE`, so re-simulating
an outcome for a transaction updates it rather than conflicting with the
Day 3 "each run is a new observation" semantics already used elsewhere.

### Production integration

```
PaymentEvent -> features -> calibrated classifier -> RootCausePrediction
    -> RulesPolicyEngine -> authorized action
    -> estimate_outcome(evidence, authorized action)   <- exactly this action, never a hypothetical one
    -> RecoveryOutcome -> persisted into recovery_outcomes
```
`src/pipeline/pipeline.py` calls `estimate_outcome` with
`policy_decision.action` — Day 8 never chooses or overrides the action;
that remains entirely Day 7's decision. Verified directly: a real
`WEBHOOK_AMBIGUITY` prediction run through the full pipeline is always
scored with `BLOCK_RECONCILE`, never `DEFER_RETRY`
(`tests/test_recovery_pipeline_integration.py`).

### Limitations

- Every recovery probability and the duplicate-charge-risk assumption are
  **synthetic simulation parameters**, not observed statistics — they
  must be replaced/recalibrated against real labeled recovery outcomes
  once production data exists (see `simulation_config.yaml`'s own
  disclaimer).
- The simulation is binary all-or-nothing recovery (an outcome either
  recovers the full transaction amount or none of it) — a deliberate
  simplification, not a partial-recovery model.
- `simulate_batch()` (`src/recovery/batch.py`) is the only batch mechanism
  built so far; the naive, rules-only, and Guardian action selectors
  themselves are explicitly Day 9/10 work and do not exist yet.

---

## Day 9 — Four-Strategy Counterfactual Experiment

The question Day 9 answers: *given exactly the same transaction evidence,
how do four action-selection strategies compare when evaluated against
the same counterfactual outcome environment and the same controlled
randomness?* This is a measurement exercise, not a tuning exercise — no
ML, calibration, Day 7 policy, or Day 8 simulation assumption was changed
to produce these numbers.

### Day 8 API compatibility (verified before writing any Day 9 code)

`estimate_outcome`'s existing `seed: Optional[int] = None` keyword
parameter was **already sufficient** for Day 9's common-random-number
requirement — **Situation B**, not C. Verified empirically: holding
`seed` constant while varying only `action` produces the identical
underlying `random.Random(seed)` draw sequence regardless of action; only
the action-specific probability (`probability_of_recovery`, unchanged)
determines the result. **No change was made to
`src/recovery/simulator.py`.** Day 8's stochastic structure — two
separate draws per automated action (one for `recovered`, one for
`duplicate_charge_risk`), computed from marginal, not joint, probabilities
— was inspected and preserved exactly as-is; Day 9 does not reinterpret or
"fix" it.

`RecoveryEvidence` was extended additively with `failure_code: str = ""`
(the rules-only strategy needs it, and the Day 9 spec explicitly permits
it being available to every strategy) — the same additive-field pattern
used on every previous day; nothing existing was renamed or altered.

### Common random numbers

One deterministic seed per transaction, derived via SHA-256 (never
Python's `hash()`, which is randomized per-process by `PYTHONHASHSEED`
and would break cross-process reproducibility):

```
seed = int(sha256(f"{transaction_id}:{experiment_seed}").hexdigest()[:16], 16)
```
(`src/experiment/random_state.py`). The same seed is passed into
`estimate_outcome` for all four strategies evaluating a given
transaction — so differences in outcome arise from *which action was
selected*, never from independent simulation luck.

### The four strategies

Common interface: `select_action(payment_event: PaymentEvent) ->
RecoveryAction` (`src/experiment/strategies.py`). Strategies only select
an action — none of them simulate outcomes or touch `estimate_outcome`
directly.

| Strategy | Logic | Uses ML/policy? |
|---|---|---|
| `NaiveRetryStrategy` | Always `DEFER_RETRY`, unconditionally | No |
| `RulesOnlyStrategy` | Frozen `failure_code -> action` table (below) | No |
| `GuardianStrategy` | Real feature builder -> real calibrated classifier -> real Day 7 `RulesPolicyEngine` | Yes — the actual production path |
| `NoActionStrategy` | Always `NO_ACTION`, unconditionally | No |

**Rules-only's frozen mapping** (decided before running the experiment):

| failure_code | Action |
|---|---|
| `gateway_timeout` | `DEFER_RETRY` |
| `internal_error`, `service_unavailable` | `DEFER_RETRY` |
| `issuer_declined`, `card_expired`, `invalid_card`, `insufficient_funds` | `CUSTOMER_RECOVERY` |
| `otp_timeout`, `3ds_auth_failed`, `user_cancelled`, `session_expired` | `HUMAN_REVIEW` |
| `unknown` | `HUMAN_REVIEW` |
| anything else | `HUMAN_REVIEW` (safe fallback) |

`gateway_timeout` and `unknown` are **deliberately non-unique** by Day 1
dataset design — both occur under `INFRASTRUCTURE` and under
`WEBHOOK_AMBIGUITY`. Rules-only cannot distinguish those two root causes
from failure_code alone. `gateway_timeout -> DEFER_RETRY` is the natural
judgment call a naive, ML-free rule-writer would make ("this reads like a
network hiccup") — and it is exactly what makes this baseline unsafe on
the `WEBHOOK_AMBIGUITY` share of that code. That risk is intentional, not
a bug in the baseline's design.

### Guardian state isolation (Day 9 spec section 10A)

Guardian's real production path (`src/pipeline/pipeline.py`) writes to
`idempotency_log`, `payment_events`, `decisions`, and `recovery_outcomes`.
Day 9 evaluates the same transactions repeatedly (primary run,
sensitivity seeds, cross-process reruns) — if any of those writes
persisted, a later evaluation could see a stale "already executed" record
and be forced into `HUMAN_REVIEW` for reasons having nothing to do with
evidence, model, policy, or seed.

**Option A was used**: `GuardianStrategy` calls the real feature
builder, the real `CalibratedRootCauseClassifier`, and the real
`RulesPolicyEngine.decide()` directly — with `already_executed_actions=
frozenset()` and a fixed `now` (`EXPERIMENT_EVALUATION_TIME`, a constant,
never wall-clock) — bypassing **only** the persistence/audit/idempotency-
write layer. Feature construction, calibrated prediction, confidence
thresholds, and every Day 7 safety guard are byte-for-byte identical to
production. Production's real idempotency/cooldown behavior was **not**
modified, weakened, or disabled — `src/pipeline/pipeline.py` and
`src/policy/engine.py` are untouched by Day 9 (verified via `git diff`).
Verified directly: calling `GuardianStrategy.select_action` twice
sequentially for the same transaction returns the same action, and a
fresh `GuardianStrategy` instance produces the same action as a previous
one for the same transaction.

### Dataset

The existing frozen **15% test split** (242 rows) —
`src.model.splitting.train_val_test_split(random_state=42)`, the exact
same split Day 4/5 already evaluated the classifier against. Frozen
*before* the experiment ran (`experiments/day9_experiment_config.yaml`).
Rationale: Day 9 measures policy/outcome behavior downstream of the
already-frozen classifier, not classifier generalization — reusing the
established held-out split avoids introducing a new, undocumented subset
choice.

### Money definitions and precision

- **Simulated amount recovered** — the sum of realized, common-random
  `estimate_outcome()` draws. This is the primary recovery metric.
- **Expected amount recovered** — `amount × probability_of_recovery(...)`,
  a probability-weighted estimate exposed separately by Day 8. Reported as
  supplementary only, never merged with simulated recovery.
- No repository-wide currency/rounding convention was found (audited
  `src/domain/`, `src/db.py`, existing money tests, `docs/`, config
  files). Day 9 explicitly defines its own comparison tolerance:
  **`1e-2`** (documented in `experiments/day9_experiment_config.yaml` and
  `tests/test_experiment_metrics.py` — not claimed as a pre-existing
  repository convention).

### Fairness verification

Machine-checked (`tests/test_experiment_crn.py`,
`tests/test_experiment_metrics.py`): same evidence object across all four
strategies (root_cause, probability, amount identical), same transaction
set per strategy, same `estimate_outcome`, same derived seed, same
simulation configuration — only action-selection logic differs.

### Synthetic assumption disclosure

Every recovery/duplicate-charge probability driving these results is a
**Day 8 synthetic simulation assumption**, not an observed Razorpay
production statistic (there are none anywhere in this repository). The
Day 9 results demonstrate **comparative behavior under the configured
counterfactual environment** — they are not, and must never be reported
as, real recovered revenue. Real production outcome data would require
recalibrating the Day 8 simulation assumptions before these comparisons
would carry production meaning.

### Reproducibility

Verified twice: (1) the identical experiment, run as two **separate shell
processes** with `--seed 42`, produced byte-identical output files
(confirmed via `diff` and matching MD5 checksums); (2) three predeclared
seeds (42 primary, 43/44 sensitivity) each individually reproduce
identically across repeated runs. See `experiments/run_day9_experiment.py`
and `experiments/day9_experiment_config.yaml`.

### Limitations

- All outcome probabilities remain Day 8's synthetic assumptions —
  unchanged, unrecalibrated, and explicitly disclosed as such everywhere
  results are reported.
- Guardian's lower raw recovery rate on `INFRASTRUCTURE` and its zero
  recovery on `OTP_TIMEOUT`/`USER_ABANDONMENT` (both intentional
  consequences of its confidence threshold and its Day 7 `NO_ACTION`
  mapping for those two classes) are genuine, measured trade-offs against
  the naive/rules-only baselines' higher raw recovery on those same
  segments — not concealed.
- Statistical significance testing is explicitly **out of scope** for Day
  9 (Day 10 work) — only absolute/relative differences are reported here.
- No frontend, dashboard, Razorpay adapter, or LLM component was touched
  or built.

---

## Day 10 — Frozen Experiment Analysis

Day 10 is analysis-only: it reads the frozen Day 9 result artifacts
(`experiments/results/day9_seed_{42,43,44}_per_transaction.json`) and
never reruns the experiment or touches Day 9/8/7/ML code
(`src/analysis/`, read-only by construction — verified via `git diff`).

### Methodology and metric definitions

**`recovery_rate`** is explicitly **count-based**:
`recovered_transaction_count / transactions_evaluated` — *not*
`amount_recovered / amount_at_risk`. This was the Day 9 definition
already in use; Day 10 only makes it explicit in writing.

**Taxonomy preserved throughout**: OBSERVED (an actual recorded payment
outcome — the project has none), EXPECTED
(`amount × probability_of_recovery`, a Day 8 probability-weighted
estimate), SIMULATED (one realized `estimate_outcome()` draw — what every
number below actually is). *"Guardian recovered ₹193,316.24" means
simulated/counterfactual recovery under the configured environment — it
does not mean Razorpay recovered that amount.*

### Data integrity (verified, `src/analysis/integrity.py`)

For all three seeds: action counts sum to 242 per strategy; every
`0 ≤ amount_recovered ≤ transaction_amount`; per-strategy root-cause
recovery sums equal the strategy total; total recovered never exceeds
total at risk. All checks passed — no discrepancy required investigation.

### Table A — Primary comparison (seed 42, n=242)

| Metric | Naive Retry | Rules-only | Guardian | No Action |
|---|---:|---:|---:|---:|
| Transactions | 242 | 242 | 242 | 242 |
| Amount at risk | ₹677,213.78 | ₹677,213.78 | ₹677,213.78 | ₹677,213.78 |
| Simulated amount recovered | ₹205,427.28 | ₹238,230.16 | ₹193,316.24 | ₹0.00 |
| Recovery rate (count-based) | 29.75% | 33.88% | 28.93% | 0.00% |
| Duplicate-charge risk | 12 | 3 | **0** | 0 |
| Unsafe outcomes | 12 | 3 | **0** | 0 |

**Guardian did NOT achieve the highest raw simulated recovery.**
Rules-only did (₹238,230.16). This is stated plainly, not minimized: the
claim *"Guardian maximizes recovery"* is false on this frozen result and
must never be made. The defensible claim is: **Guardian is a
safety-constrained recovery strategy** — its distinguishing, reproduced
property is **zero duplicate-charge-risk outcomes across all three
seeds**, while both higher-recovery active strategies incurred measurable
risk.

### Recovery and safety differences (Guardian vs. each baseline, seed 42)

| Comparison | Recovery Δ (₹) | Recovery-rate Δ (pp) | Duplicate-risk Δ |
|---|---:|---:|---:|
| Guardian − Naive | −12,111.04 | −0.82 | −12 |
| Guardian − Rules-only | −44,913.92 | −4.95 | −3 |
| Guardian − No Action | +193,316.24 | +28.93 | 0 |

Guardian recovers less than both active baselines in raw ₹ terms, and
strictly more than doing nothing, while carrying zero of either
baseline's duplicate-charge exposure.

### Safety-constrained interpretation

If the objective were *raw simulated recovery without safety
constraints*, **Rules-only performed best** in this experiment — this is
not a euphemism, it is the measured result. Rules-only is not "bad": it
achieves strong recovery on several classes but still incurs risk because
`failure_code` alone cannot resolve ambiguous payment-state cases.
Guardian is not "best overall" in an unqualified sense: it is best under
the objective *maximum recoverable revenue subject to explicit safety
constraints* — a different, narrower, and explicitly stated objective.

### WEBHOOK_AMBIGUITY deep dive (Table G)

25 transactions, ₹63,716.20 at risk.

| Strategy | Action | Txns | At Risk | Recovered | Recovery Rate | Duplicate Risk |
|---|---|---:|---:|---:|---:|---:|
| Naive Retry | DEFER_RETRY | 25 | ₹63,716.20 | ₹45,875.80 | 68.00% | 12 |
| Rules-only | DEFER_RETRY (9) / HUMAN_REVIEW (16) | 25 | ₹63,716.20 | ₹17,645.09 | 20.00% | 3 |
| **Guardian** | **BLOCK_RECONCILE (25/25 — measured, not asserted)** | 25 | ₹63,716.20 | ₹0.00 | 0.00% | **0** |
| No Action | NO_ACTION | 25 | ₹63,716.20 | ₹0.00 | 0.00% | 0 |

Guardian's action distribution within these 25 transactions was measured
directly from the frozen per-transaction results: **25/25 BLOCK_RECONCILE,
0/25 anything else.** WEBHOOK_AMBIGUITY represents unresolved payment
state; retrying can create duplicate-charge exposure if the original
payment actually succeeded. Guardian's zero recovery here is an
**intentional policy consequence** (the Day 7 hard safety invariant), not
a model failure — it is buying zero-risk at the cost of all recovery on
this segment.

### INFRASTRUCTURE deep dive (Table C, one segment)

55 transactions, ₹143,862.56 at risk.

| Strategy | Recovered | Recovery Rate | Duplicate Risk |
|---|---:|---:|---:|
| Naive Retry | 34/55 (₹89,184.69) | 61.82% | 0 |
| Rules-only | 34/55 (₹89,184.69) | 61.82% | 0 |
| Guardian | 27/55 (₹61,915.86) | 49.09% | 0 |

**Proved from the action distribution, not merely asserted.** Guardian's
measured actions on these 55 transactions: **DEFER_RETRY = 43,
HUMAN_REVIEW = 12** (43 + 12 = 55). Naive and Rules-only both select
`DEFER_RETRY` unconditionally for every one of the 55 — no confidence
gate. Guardian's Day 7 policy only authorizes `DEFER_RETRY` when
calibrated confidence ≥ 0.75; the 12 lower-confidence `INFRASTRUCTURE`
predictions instead receive `HUMAN_REVIEW`, which credits **zero**
recovery in this simulation. That gap — 12 transactions receiving no
recovery credit instead of a `DEFER_RETRY` attempt — is the entire
arithmetic explanation for Guardian's 27 vs. 34 recovered count
(34 − 27 = 7 fewer *recoveries*, consistent with 12 fewer *attempts* at
Day 8's ~0.70 configured DEFER_RETRY-on-INFRASTRUCTURE recovery
probability: 12 × 0.70 ≈ 8.4, in the same range as the observed 7-recovery
gap, allowing for CRN sampling variation over 55 draws).

### CARD_DECLINE + INSUFFICIENT_FUNDS combined analysis (Table F)

99 of 242 transactions (**40.9%** of the evaluation set) — a major
portion of the experiment, analyzed together as instructed.

| Strategy | Txns | At Risk | Recovered | Recovery Rate | Action Pattern |
|---|---:|---:|---:|---:|---|
| Naive Retry | 99 | ₹292,408.37 | ₹12,678.86 | 9.09% | 99× `DEFER_RETRY` |
| Rules-only | 99 | ₹292,408.37 | ₹131,400.38 | 43.43% | 99× `CUSTOMER_RECOVERY` |
| Guardian | 99 | ₹292,408.37 | ₹131,400.38 | 43.43% | 98× `CUSTOMER_RECOVERY`, 1× `HUMAN_REVIEW` |
| No Action | 99 | ₹292,408.37 | ₹0.00 | 0.00% | 99× `NO_ACTION` |

**Naive's action-mismatch finding (mandatory, distinct from the safety
story):** on this 99-transaction segment, Naive recovers roughly **1/10th**
of what Guardian/Rules-only recover — not because of any safety exposure
(0 duplicate risk here for all four strategies), but because `DEFER_RETRY`
is the wrong action for these two root causes.

Day 8's frozen `simulation_config.yaml` (unmodified, cited directly, not
invented): `recovery_probability.DEFER_RETRY.default = 0.15` (the rate
applied to `CARD_DECLINE`/`INSUFFICIENT_FUNDS` under `DEFER_RETRY`, since
neither is listed under that action's table) vs.
`recovery_probability.CUSTOMER_RECOVERY.CARD_DECLINE = 0.55` and
`.INSUFFICIENT_FUNDS = 0.45`. The observed rates track these configured
assumptions closely, within the sampling variation expected at n=52/47:
`CARD_DECLINE` — Naive 5/52 = 9.6% (config: 15%), Guardian/Rules 25/52 =
48.1% (config: 55%); `INSUFFICIENT_FUNDS` — Naive 4/47 = 8.5% (config:
15%), Guardian/Rules 18/47 = 38.3% (config: 45%).

**Conclusion: Naive Retry is not merely riskier than Rules-only — it is
also less effective on 40.9% of the dataset because blanket `DEFER_RETRY`
is a poor action for `CARD_DECLINE`/`INSUFFICIENT_FUNDS`, where
`CUSTOMER_RECOVERY` is markedly more effective under the configured
simulation. Aggression is not the same as effectiveness.**

### CRN validation signals (architecture-validation, not findings about strategy quality)

**Signal 1** — `CARD_DECLINE`: Rules-only = Guardian = ₹86,924.28 exactly.
`INSUFFICIENT_FUNDS`: Rules-only = Guardian = ₹44,476.10 exactly. Both
strategies select the same effective action (`CUSTOMER_RECOVERY`, for the
51/52 and 47/47 rows where Guardian doesn't fall back to `HUMAN_REVIEW`)
on these transactions, and produce byte-identical simulated recovery —
proof that the same evidence + same action + same common random draw
yields the same outcome, exactly as the shared environment requires.

**Signal 2** — `INFRASTRUCTURE`: Naive = Rules-only = ₹89,184.69 exactly.
Both select `DEFER_RETRY` unconditionally for all 55 transactions in this
segment and produce identical simulated recovery under the shared seed.

These identical results are validation evidence for the experiment's
architecture, not bugs or coincidences.

### Guardian action distribution (Table E, n=242)

| Action | Count | Percentage |
|---|---:|---:|
| CUSTOMER_RECOVERY | 98 | 40.5% |
| NO_ACTION | 63 | 26.0% |
| DEFER_RETRY | 43 | 17.8% |
| BLOCK_RECONCILE | 25 | 10.3% |
| HUMAN_REVIEW | 13 | 5.4% |
| **Total** | **242** | **100%** |

By root cause (fully reconciles against the table above): `INFRASTRUCTURE`
→ 43 `DEFER_RETRY` + 12 `HUMAN_REVIEW` (55); `WEBHOOK_AMBIGUITY` → 25
`BLOCK_RECONCILE` (25); `CARD_DECLINE` → 51 `CUSTOMER_RECOVERY` + 1
`HUMAN_REVIEW` (52); `INSUFFICIENT_FUNDS` → 47 `CUSTOMER_RECOVERY` (47);
`OTP_TIMEOUT` → 31 `NO_ACTION` (31); `USER_ABANDONMENT` → 32 `NO_ACTION`
(32).

### Table C — Full root-cause comparison (seed 42)

| Root Cause | Strategy | Txns | At Risk | Recovered | Recovery Rate | Duplicate Risk |
|---|---|---:|---:|---:|---:|---:|
| CARD_DECLINE | Naive / Rules / Guardian / NoAction | 52 | ₹196,131.84 | 3,683 / 86,924 / 86,924 / 0 | 9.6% / 48.1% / 48.1% / 0% | 0/0/0/0 |
| INSUFFICIENT_FUNDS | same order | 47 | ₹96,276.53 | 8,995 / 44,476 / 44,476 / 0 | 8.5% / 38.3% / 38.3% / 0% | 0/0/0/0 |
| OTP_TIMEOUT | same order | 31 | ₹76,940.59 | 20,740 / 0 / 0 / 0 | 16.1% / 0% / 0% / 0% | 0/0/0/0 |
| USER_ABANDONMENT | same order | 32 | ₹100,286.06 | 36,948 / 0 / 0 / 0 | 21.9% / 0% / 0% / 0% | 0/0/0/0 |
| INFRASTRUCTURE | same order | 55 | ₹143,862.56 | 89,185 / 89,185 / 61,916 / 0 | 61.8% / 61.8% / 49.1% / 0% | 0/0/0/0 |
| WEBHOOK_AMBIGUITY | same order | 25 | ₹63,716.20 | 45,876 / 17,645 / 0 / 0 | 68% / 20% / 0% / 0% | 12/3/**0**/0 |

`OTP_TIMEOUT`/`USER_ABANDONMENT` are not hidden: Guardian and Rules-only
both forfeit all recovery there (Guardian's documented Day 7 `NO_ACTION`
assumption for these two classes; Rules-only routes them to
`HUMAN_REVIEW`), while Naive picks up modest recovery blindly — a genuine
trade-off, reported honestly.

### Seed sensitivity (Table D, predeclared seeds only — no cherry-picking)

| Seed | Strategy | Recovery | Recovery Rate | Duplicate Risk |
|---:|---|---:|---:|---:|
| 42 | Naive | ₹205,427.28 | 29.75% | 12 |
| 42 | Rules-only | ₹238,230.16 | 33.88% | 3 |
| 42 | Guardian | ₹193,316.24 | 28.93% | **0** |
| 43 | Naive | ₹168,554.05 | 31.82% | 5 |
| 43 | Rules-only | ₹175,672.81 | 33.06% | 1 |
| 43 | Guardian | ₹151,387.84 | 27.69% | **0** |
| 44 | Naive | ₹173,330.03 | 30.17% | 10 |
| 44 | Rules-only | ₹239,307.76 | 36.36% | 2 |
| 44 | Guardian | ₹186,728.41 | 29.34% | **0** |

**Guardian's duplicate-charge-risk count is 0 across all three predeclared
seeds** — the one property that does not vary. Recovery varies
(₹151k–₹193k for Guardian, reflecting ordinary CRN sampling variation,
not a change in policy or strategy).

### Statistical analysis

**Seed-level (n=3): no formal significance test performed.** Three
observations cannot support one — reporting only qualitative range
(above) as instructed.

**Transaction-level paired analysis (seed 42, n=242 identical
transactions under every strategy — a paired design, McNemar/Wilcoxon
appropriate):**

#### Table H — McNemar (binary recovery) and Wilcoxon (monetary) paired comparisons

| Comparison | Both Recovered | Both Not Recovered | A-only (Guardian) | B-only | Concordant N | Discordant N | McNemar stat | McNemar p | Wilcoxon p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Guardian vs Naive | 36 | 136 | 34 | 36 | 172 | **70** | 34 | 0.9050 | 0.9370 |
| Guardian vs Rules-only | 70 | 160 | 0 | 12 | 230 | **12** | 0 | 0.00049 | 0.00222 |
| Guardian vs No Action | 0 | 172 | 70 | 0 | 172 | **70** | 0 | 1.69e-21 | 3.56e-13 |

**Interpretation, exactly as measured — no overclaiming:**

- **Guardian vs. Naive: NOT statistically significant** (p=0.905 McNemar,
  p=0.937 Wilcoxon). Despite Naive's unsafe behavior, the paired
  transaction-level recovery difference between Guardian and Naive is not
  distinguishable from chance at this sample size (70 discordant pairs,
  nearly evenly split 34 vs. 36).
- **Guardian vs. Rules-only: statistically significant** (p=0.00049
  McNemar, p=0.00222 Wilcoxon) — and the direction is unambiguous: of the
  12 discordant pairs, Guardian recovered **zero** transactions Rules-only
  didn't, while Rules-only recovered **12** transactions Guardian didn't
  (`a_only_recovered=0`). Every discordant pair favors Rules-only.
- **Guardian vs. No Action: statistically significant** (p=1.69e-21
  McNemar, p=3.56e-13 Wilcoxon) — Guardian recovers meaningfully more than
  doing nothing.

**Why the effective discordant sample is smaller than 242, and what that
does and does not mean (mandatory disclosure):** Guardian vs. Rules-only
has only 12 discordant pairs out of 242 because **230 transactions are
concordant** — largely explained by CRN Validation Signal 1
(`CARD_DECLINE`/`INSUFFICIENT_FUNDS`: identical action, identical outcome
for both strategies on 98 of those 99 rows). McNemar's test is driven
entirely by discordant pairs; concordant pairs do not count as evidence
for either direction, but they are not wasted or ignored — they
positively confirm the two strategies behaved identically there, which is
itself the CRN validation signal. **A small discordant N with a
significant p-value is not evidence that the ₹44,913.92 aggregate
monetary difference (Table A) doesn't exist — the two analyses answer
different questions** (paired binary recovery disagreement vs. aggregate
₹ comparison), and here they agree: the discordant pairs are concentrated
almost entirely in `WEBHOOK_AMBIGUITY` (where Guardian blocks and
Rules-only sometimes doesn't), consistent with the WEBHOOK_AMBIGUITY deep
dive above.

No test result here was omitted, rerun, or suppressed regardless of
significance.

### Business interpretation

The business problem is **recovering revenue without causing unsafe
payment actions** — not maximizing recovery at any cost.

- **Naive Retry**: attempts recovery on every transaction regardless of
  action appropriateness. Produces *both* the highest safety exposure
  *and* lower aggregate recovery than Rules-only — aggression is not
  effectiveness.
- **Rules-only**: produced the **highest raw simulated recovery** in this
  experiment. It still incurs duplicate-charge risk because `failure_code`
  alone cannot resolve `WEBHOOK_AMBIGUITY`/`INFRASTRUCTURE` overlap.
- **Guardian**: produced **lower raw simulated recovery** than both active
  baselines. It enforces explicit safety boundaries and produced **zero**
  simulated duplicate-charge risk across all three tested seeds.
- **No Action**: the safest possible lower-bound baseline; recovers
  nothing.

**Central principle: maximum recoverable revenue *subject to* safety
constraints** — not "maximum recovery," full stop.

### Judge-facing questions

**Q: Why trust Guardian if it recovered less?**
A: Guardian is not optimized for unconstrained recovery. It separates
diagnosis from action and deliberately blocks ambiguous payment-state
cases where retrying can create duplicate-charge exposure — measured at
zero duplicate-risk outcomes across three seeds, at a measured cost in
raw recovery.

**Q: Why did Rules-only recover more?**
A: In this synthetic experiment, Rules-only selected effective recovery
actions (`CUSTOMER_RECOVERY`) for `CARD_DECLINE`/`INSUFFICIENT_FUNDS` —
identically to Guardian on those classes (CRN Signal 1) — but it still
lacks the ML-based root-cause distinction needed to safely resolve
`gateway_timeout`'s overlap between `INFRASTRUCTURE` and
`WEBHOOK_AMBIGUITY`, so it retries some `WEBHOOK_AMBIGUITY` cases Guardian
blocks.

**Q: Why did Naive recover less despite retrying everything?**
A: Blanket `DEFER_RETRY` is not an effective action for every failure
type. `CARD_DECLINE`/`INSUFFICIENT_FUNDS` are 99 of 242 transactions
(40.9%), and `CUSTOMER_RECOVERY` recovers roughly 4-5× more of that
segment than `DEFER_RETRY` under the frozen simulation assumptions.

**Q: Why does Guardian recover zero on WEBHOOK_AMBIGUITY?**
A: The payment state is unresolved. Guardian maps it to `BLOCK_RECONCILE`
rather than risking a duplicate charge through retry — measured at 25/25
transactions, not merely asserted.

**Q: If Guardian and Rules-only have identical results on many rows, what
does McNemar's test actually tell you?**
A: McNemar's test uses only the 12 discordant paired outcomes here. The
230 concordant rows still validate that both strategies behaved
identically on those transactions (a CRN architecture check), but they
don't add statistical weight to either direction — so the effective
discordant sample (12) is reported explicitly alongside the p-value,
never just "n=242."

**Q: Is this real Razorpay recovery?**
A: No. The recovery environment is synthetic/counterfactual (Day 8). The
experiment demonstrates comparative architecture and policy behavior.
Real production deployment would require real labeled outcome data and
recalibration of the simulation assumptions.

### Limitations

- All recovery/duplicate-charge probabilities remain Day 8's
  unrecalibrated synthetic assumptions — no real Razorpay recovery labels
  exist anywhere in this project.
- Results are counterfactual/simulated throughout, never observed
  production revenue.
- Only three sensitivity seeds were run (predeclared); no formal
  seed-level significance testing was performed or is claimed (n=3 is
  insufficient).
- Transaction-level paired tests (McNemar, Wilcoxon) were used only where
  their assumptions held (paired binary/continuous outcomes on the same
  242 transactions); the McNemar effective discordant sample is
  frequently much smaller than 242 due to concordant ties, reported
  explicitly for every comparison.
- `recovery_rate` is count-based (`recovered_transaction_count /
  transactions_evaluated`), not amount-weighted — stated explicitly to
  avoid ambiguity.
- Guardian's lower raw recovery on `INFRASTRUCTURE`/`OTP_TIMEOUT`/
  `USER_ABANDONMENT` and Rules-only's higher raw recovery overall are
  reported as genuine, measured findings — not smoothed over.
- Statistical significance (where found) is not equivalent to production
  validity — no deployment claim is made from this analysis.
- No new model, policy, threshold, or business logic was introduced; Day
  10 is read-only analysis over frozen Day 9 artifacts.

---

## Day 11 — Production-Shaped Razorpay Adapter

Day 11 proves that a Razorpay-shaped payment event can enter Recovery
Guardian, normalize into the existing canonical `PaymentEvent` contract,
and flow through the already-frozen feature → calibrated ML → policy
architecture **without creating a parallel intelligence pipeline**. It is
not a live Razorpay integration — no API calls, no credentials, no
webhook-signature verification exist or are required.

```
Razorpay-shaped payload           Synthetic CSV row
        │                                │
        ▼                                ▼
  RazorpayAdapter               synthetic_adapter
  (src/ingestion/                (src/ingestion/
   razorpay_adapter.py)           synthetic_adapter.py)
        │                                │
        └───────────┬────────────────────┘
                     ▼
            canonical PaymentEvent
                     │
                     ▼
       existing feature builder (unmodified, 26 FEATURE_COLUMNS)
                     │
                     ▼
       frozen calibrated classifier (unmodified)
                     │
                     ▼
       frozen Day 7 RulesPolicyEngine (unmodified)
                     │
                     ▼
       existing recovery/audit layer (unmodified)
```

**The recovery intelligence is data-source agnostic at the canonical
`PaymentEvent` boundary.** Synthetic and production-shaped inputs
normalize into the same internal event contract and reuse the same
frozen feature, prediction, calibration, and policy layers — proven
directly (not merely asserted) by the convergence tests below. This does
**not** mean production deployment is ready: it would still require
validated production event schemas, real operational monitoring inputs,
labeled recovery outcomes, retraining/recalibration, security review, and
compliance review (see "Production Readiness Boundary" below).

### The adapter

`src/ingestion/razorpay_adapter.py::razorpay_webhook_to_payment_event(webhook_payload, *, platform_health=None) -> PaymentEvent`
— mirrors the existing `synthetic_to_payment_event(row) -> PaymentEvent`
convention exactly (same file layout pattern, same "one pure function"
shape). It is a boundary layer only: no ML, no policy, no feature
engineering, no persistence, no network calls anywhere in the module
(verified by source inspection in `tests/test_razorpay_adapter.py`).
Malformed input raises `AdapterValidationError` rather than silently
producing a corrupt event.

The payload shape is **representative/production-shaped**, built from
Razorpay's well-documented public conventions (amounts as integers in the
smallest currency subunit; a payment `error_code`/`error_reason` pair; a
webhook envelope with its own `created_at` wrapping
`payload.payment.entity`) — **not captured from live Razorpay production
traffic**, and no official schema guarantee is claimed.

### Field mapping (implemented, not aspirational)

| External/Representative Field | Canonical Field | Source Type | Transformation | Required? |
|---|---|---|---|---|
| `payload.payment.entity.id` | `transaction_id` | payload-derived | direct | Yes |
| `payload.payment.entity.amount` | `amount` | payload-derived | ÷100 (paise → rupees; Razorpay's documented smallest-subunit convention) | Yes |
| `payload.payment.entity.created_at` | `timestamp` | payload-derived | Unix epoch seconds → `datetime` (UTC, naive) | Yes |
| `payload.payment.entity.method` | `payment_method` | payload-derived | lowercased, passed through (no second taxonomy) | No (defaults via existing OOV handling) |
| `payload.payment.entity.error_reason` | `failure_code` | payload-derived | mapped via a small frozen table to the existing `FAILURE_CODE_CATEGORIES`; unrecognized/absent → existing canonical `"unknown"` bucket | No |
| `payload.payment.entity.attempts` | `retry_count` | payload-derived | direct; defaults to 0 if absent | No |
| `webhook_payload.created_at` + `entity.created_at` | `webhook_delay_seconds` | **derived from two payload timestamps** | `webhook_created_at − payment_created_at`, seconds | Yes (both timestamps) |
| `entity.notes.merchant_id` | `merchant_id` | payload-derived (via a representative `notes` convention) | direct; defaults to `"unknown_merchant"` if absent | No |
| `entity.notes.customer_previous_successes/failures` | `customer_previous_successes/failures` | **customer-history lookup input** (a third category — see below) | direct; defaults to 0/0 | No |
| `platform_health.gateway_error_rate_delta` | `gateway_error_rate_delta` | **companion monitoring input** (Option A) | direct; defaults to 0.0 if no context supplied | No |
| `platform_health.merchant_failure_rate_delta` | `merchant_failure_rate_delta` | companion monitoring input | direct; defaults to 0.0 | No |
| `platform_health.cross_merchant_failure_rate` | `cross_merchant_failure_rate` | companion monitoring input | direct; defaults to 0.0 | No |
| `platform_health.incident_active` | `incident_active` | companion monitoring input | direct; defaults to `False` | No |
| — | `source` | synthetic test-only (adapter-set constant) | always `"razorpay"` | — |

**No separate `status` field exists on `PaymentEvent`, and none was
invented.** Payment state is represented entirely through `failure_code`
(inspected directly from `src/domain/models.py`) — Razorpay's
`status`/`error_reason` terminology maps into that single existing
mechanism, never a second one.

### Critical aggregate-field decision — Option A selected

Every `PaymentEvent` field was classified by where its information can
realistically originate:

**Transaction/payload-derivable** (§6A): `transaction_id`, `amount`,
`timestamp`, `payment_method`, `failure_code`, `retry_count` — all
plausibly present on a single Razorpay payment/webhook payload.
`webhook_delay_seconds` is derived from two payload timestamps, never
defaulted.

**Platform-wide aggregate fields** (§6B): `gateway_error_rate_delta`,
`merchant_failure_rate_delta`, `cross_merchant_failure_rate`,
`incident_active`. A single payment payload cannot legitimately carry
real-time cross-merchant failure statistics — that requires a separate
monitoring/observability service this project does not build.

**Selected: Option A** — `PlatformHealthContext`
(`src/ingestion/razorpay_adapter.py`) is an explicit, optional companion
input representing exactly what such a service would supply. **This
assumes an external monitoring/observability input that this project
does not currently build.** The adapter clearly separates payment payload
data from this companion context — it is never disguised as part of the
Razorpay payload itself. If omitted, the resulting event carries neutral
(non-incident) values — verified directly by
`test_no_platform_health_context_defaults_to_documented_neutral_values`.

**Production limitation, stated plainly: without a real
platform-monitoring integration, a production-shaped Razorpay event
cannot currently provide all aggregate infrastructure signals required by
the frozen classifier.** A production deployment lacking that monitoring
service would see `INFRASTRUCTURE` classification degrade toward whatever
signal `failure_code` alone provides — the same limitation
`RulesOnlyStrategy` already demonstrated in Day 9/10's experiment.

**A third category** exists that Section 6 didn't separately name:
`customer_previous_successes`/`customer_previous_failures` require a
per-customer history lookup (e.g. a merchant's CRM), which a single
webhook payload doesn't inherently carry either. Unlike the platform
aggregates, defaulting these to 0/0 is the **correct**,
already-designed-for representation for "no history available" —
`src/features/build_features.py`'s Laplace-smoothed
`customer_success_rate` and `is_new_customer` indicator exist
specifically for this case (see that module's own Day 2 docstring) — so
this default does not suppress a systemic signal the way defaulting
`incident_active` would.

### Webhook delay — the WEBHOOK_AMBIGUITY-critical field

`webhook_delay_seconds` is **calculated**, never defaulted to zero:
`webhook_created_at (webhook envelope) − payment_created_at (payment
entity)`, both required Unix-epoch-second fields. A webhook claiming to
have arrived before the payment was even created is rejected as malformed
input (`AdapterValidationError`), not silently clamped. If a real
integration cannot supply the webhook envelope's own timestamp, this
adapter cannot safely compute the delay and will reject the payload —
this is an explicit, documented limitation, not a silent zero.

Razorpay's real timestamps are integer-second precision (no
sub-second component), so exact fractional-second reproduction of a
synthetic dataset row's `webhook_delay_seconds` is not possible through
this representative format — the convergence tests round to the nearest
second on both sides for a fair, honest comparison (documented directly
in `tests/test_razorpay_integration.py`), rather than silently truncating
without acknowledgment.

### Synthetic/canonical convergence — proven, not merely asserted

`tests/test_razorpay_integration.py` takes a **real** frozen-dataset
`WEBHOOK_AMBIGUITY` row and a real `INFRASTRUCTURE` row, expresses each
as both a synthetic CSV row and an equivalent Razorpay-shaped payload
(companion `PlatformHealthContext` supplying that row's real aggregate
values — Option A, explicitly, not hidden), and proves:

- Identical `RootCausePrediction` (`root_cause` equal, `probability`
  equal within `1e-9`) from the real frozen calibrated classifier.
- Identical `PolicyDecision.action` from the real frozen
  `RulesPolicyEngine`.
- The `WEBHOOK_AMBIGUITY` twin's action is `BLOCK_RECONCILE` — **never**
  `DEFER_RETRY` — for the Razorpay-sourced event, exactly as the
  synthetic path already guaranteed.

This proves **same canonical boundary, same feature builder, same model,
same policy** for the fields both sources can legitimately supply. It
does **not** prove real production infrastructure monitoring exists —
that limitation is stated explicitly above, not concealed by the
convergence result.

### Production Monitoring Boundary

Transaction-level `PaymentEvent` fields can be normalized from real
payment/webhook data. `gateway_error_rate_delta`,
`merchant_failure_rate_delta`, `cross_merchant_failure_rate`, and
`incident_active` require platform-level operational monitoring rather
than a single payment payload. Day 11's fixture and convergence tests
assume a companion monitoring input (Option A) supplying these — this
project does not build that monitoring service, and no claim is made that
it exists.

### Production Readiness Boundary

**What is now demonstrated:** a Razorpay-shaped payment/webhook event can
be normalized into the canonical `PaymentEvent`, pass unmodified through
the existing feature builder, the existing frozen calibrated classifier,
and the existing frozen Day 7 policy engine, and produce a valid
`PolicyDecision` — with the `WEBHOOK_AMBIGUITY → BLOCK_RECONCILE` safety
invariant intact for a Razorpay-sourced event specifically.

**What is NOT yet implemented:** live Razorpay API integration;
production authentication; production webhook-signature verification;
real platform monitoring (Option A's companion input); real labeled
recovery outcomes (Day 8's simulation remains synthetic); ML
retraining/recalibration against real data; security review; compliance
review. None of these were built, attempted, or claimed on Day 11.

### Limitations

- The adapter is representative/production-shaped, not verified against
  live Razorpay production traffic or official schema documentation
  beyond well-known public API conventions (amount subunits, webhook
  envelope shape).
- `INFRASTRUCTURE` classification for a real Razorpay-sourced event
  without a genuine monitoring integration is honestly incomplete — see
  the aggregate-field decision above.
- Webhook delay cannot be computed without both a payment-level and a
  webhook-envelope-level timestamp; payloads lacking either are rejected,
  not defaulted.
- Convergence with synthetic data is exact for feature-relevant fields
  but necessarily rounds webhook delay to whole seconds (Razorpay's real
  timestamp precision) — documented, not hidden.
- No live Razorpay integration, credentials, or network calls exist
  anywhere in this module or its tests.
