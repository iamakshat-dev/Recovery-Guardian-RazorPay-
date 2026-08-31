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

## Day 12 — Incident Scenario Replay

Day 12 is a demo/application layer over the already-frozen intelligence
stack (Days 4-11). It is **replay, not injection**: every transaction
evaluated is a real, pre-existing row of the frozen
`data/synthetic_events.csv`. Nothing was regenerated, retrained, or
re-tuned. `data/generate_data.py` was not modified.

    existing Day 1 incident window
        -> real frozen feature builder
        -> frozen calibrated classifier
        -> root-cause prediction + calibrated probability
        -> frozen Day 7 policy engine
        -> recovery action

Entry point: `experiments/run_incident_demo.py`. Tests:
`tests/test_incident_demo.py`. Output artifact:
`experiments/results/day12_incident_demo.json`.

### 1. Why replay, not injection

The incident burst already exists — `data/generate_data.py`'s
`generate_dataset()` deliberately injects 110 transactions into a fixed
30-minute window (`2026-08-15 22:10` – `22:40`) with an
INFRASTRUCTURE-heavy (but deliberately impure) class mix, specifically so
a reproducible incident scenario exists for this kind of demo. Day 12
reads that existing window rather than generating a new one, so the
scenario is exactly reproducible from the same frozen CSV every time.

### 2. Exact verified incident window

Verified directly against the frozen dataset (not assumed):

- Start: `2026-08-15T22:10:00`, end: `2026-08-15T22:40:00` (inclusive
  both ends — matches `data/generate_data.py`'s own `summarize()`
  convention).
- Transaction count: **110** (matches `generate_dataset()`'s
  `burst_rows=110` default exactly).
- Class distribution: INFRASTRUCTURE 73, INSUFFICIENT_FUNDS 15,
  CARD_DECLINE 9, OTP_TIMEOUT 9, USER_ABANDONMENT 3, WEBHOOK_AMBIGUITY 1.

`experiments/run_incident_demo.py`'s `verify_incident_window()` raises
(stops) if the actual count in the frozen CSV ever differs from 110 —
the window is verified at run time, never hardcoded blindly.

### 3. Before/during/after window definitions

Documented, consistent convention (Day 12 spec section 7):

- **INCIDENT**: `[start, end]` — inclusive-inclusive.
- **BEFORE**: `[start-60min, start)` — half-open, excludes `start` so it
  never overlaps the incident window's own inclusive start.
- **AFTER**: `(end, end+60min]` — half-open, excludes `end` so it never
  overlaps the incident window's own inclusive end.

The three windows are non-overlapping by construction (verified by
`test_comparison_windows_are_non_overlapping`).

### 4. Whether a true failure rate exists

**No.** `data/generate_data.py` generates only failed-payment events —
every row carries an `actual_root_cause` failure label; there is no
successful-transaction row anywhere in the schema (`raw_df.columns` has
no `status`/`success`/`outcome` field). A percentage of
`failed rows / total rows` would be 100% by construction and would not
measure anything about the incident.

### 5. Failure density instead of failure rate

Day 12 reports **failure density** — failed transactions per fixed unit
of time (normalized to "per 30 minutes" so the 30-minute incident window
and the two 60-minute before/after windows are directly comparable).
Never described as a percentage or as "failure rate."

### 6. Actual measured density values

From the frozen dataset, this specific run:

| Window   | Duration | Failed events | Density (per 30 min) |
|----------|----------|----------------|------------------------|
| Before   | 60 min   | 0              | 0.0                    |
| Incident | 30 min   | 110            | 110.0                  |
| After    | 60 min   | 3              | 1.5                    |

The `before` window's zero count is an honest artifact of the sparse
background rate (≈1500 background rows spread across 21 days, ≈3
rows/hour expected on average) landing on zero in this specific hour by
chance — not a data or measurement error. It is reported as measured,
not smoothed or explained away.

### 7. Ground-truth vs prediction separation

`actual_root_cause` is read from the raw CSV row **only** for the
returned per-transaction record. `PaymentEvent` has no field for it at
all (`src/domain/models.py`) — `src/ingestion/synthetic_adapter.py`'s
`synthetic_to_payment_event()` never reads it — so `build_features()`,
the calibrated classifier, and the Day 7 policy engine structurally
cannot see it. Verified directly by
`tests/test_incident_demo.py::test_actual_root_cause_does_not_affect_prediction_or_policy`
(constructs otherwise-identical evidence differing only in the
evaluation-only label; prediction/probability/policy action are
unchanged) and
`test_synthetic_to_payment_event_never_reads_actual_root_cause`.

### 8. Train/validation/test membership of incident rows

Reproduces the **exact** Day 4 split
(`src.model.splitting.train_val_test_split`, `random_state=42`) — not a
new split. Incident-window membership:

- TRAIN: 79 (71.8%)
- VALIDATION: 13 (11.8%)
- TEST: 18 (16.4%)

**A majority of incident-window rows are TRAIN-split transactions.**
Per the Day 12 spec, this is explicitly disclosed: the full-window
classifier result below is a **replay behavior demonstration**, not an
out-of-sample generalization claim. The held-out TEST subset (18
transactions) is the defensible out-of-sample view.

### 9. Full-window classifier behavior (INFRASTRUCTURE)

All 110 incident-window transactions, ground-truth INFRASTRUCTURE cases
(73 of them): **73/73 correctly predicted INFRASTRUCTURE** — precision
1.0, recall 1.0, calibrated-probability range [0.5245, 0.9932].

### 10. Held-out-test classifier behavior (INFRASTRUCTURE)

Restricted to the 18 incident-window transactions in the original Day 4
TEST split; 15 of those are ground-truth INFRASTRUCTURE: **15/15
correctly predicted INFRASTRUCTURE** — precision 1.0, recall 1.0,
probability range [0.5245, 0.9901]. This is the out-of-sample-relevant
result; the full-window figure above is not.

### 11. Actual Day 7 confidence threshold

`src/policy/rules.yaml`'s `confidence_thresholds.INFRASTRUCTURE` = **0.75**
(loaded via `src.policy.engine.load_policy_config()`, never assumed or
hardcoded in the Day 12 script).

### 12. Infrastructure policy behavior

Across the 73 ground-truth INFRASTRUCTURE transactions: `DEFER_RETRY`
61, `HUMAN_REVIEW` 12. Every `DEFER_RETRY` corresponds to a calibrated
probability ≥ 0.75; every `HUMAN_REVIEW` corresponds to a probability
below 0.75 (`LOW_MODEL_CONFIDENCE`, per `src/policy/engine.py`'s
`_decide_by_root_cause`). The policy threshold was not changed to make
this result look better.

### 13. WEBHOOK_AMBIGUITY safety result

Exactly 1 WEBHOOK_AMBIGUITY case in the incident window.
`policy_action == BLOCK_RECONCILE` for that case; `DEFER_RETRY` count =
0. `safety_pass = True`. The incident window did not relax the hard
safety invariant. `experiments/run_incident_demo.py`'s
`build_webhook_ambiguity_safety_summary()` raises immediately if this
invariant is ever violated — no test, filter, or config was adjusted to
force this result.

### 14. Non-infrastructure diagnostic behavior

All 37 non-INFRASTRUCTURE incident-window transactions (CARD_DECLINE 9,
INSUFFICIENT_FUNDS 15, OTP_TIMEOUT 9, USER_ABANDONMENT 3,
WEBHOOK_AMBIGUITY 1) were correctly predicted as their own class — **zero
transactions were misclassified as INFRASTRUCTURE** merely because they
occurred during the incident. `incident_active`, timestamp membership,
and `actual_root_cause` are never used to override the classifier
anywhere in the replay path.

### 15. State-isolation mechanism reused from Day 9

`experiments/run_incident_demo.py`'s `replay_transaction()` calls
`RulesPolicyEngine.decide(..., already_executed_actions=frozenset(),
now=EXPERIMENT_EVALUATION_TIME)` — the exact same isolation pattern as
Day 9's `GuardianStrategy` (`src/experiment/strategies.py`), including
importing the same `EXPERIMENT_EVALUATION_TIME` constant rather than
declaring a new one. No second idempotency/state mechanism was invented.
Verified by `test_repeated_replay_of_same_transaction_does_not_change_its_action`
(same transaction replayed three times in-process, identical result
every time) and `test_guardian_state_isolation_mechanism_is_reused_not_reinvented`.

### 16. Deterministic replay methodology

The script performs no database writes and reads no wall clock in its
substantive computation. The only per-run randomness anywhere
(`src.recovery.simulator.estimate_outcome`'s internal draw, used only by
the optional simulation below) is seeded deterministically via
`src.experiment.random_state.derive_transaction_seed()` — the exact Day 9
CRN mechanism, unmodified. Verified by running the script as two
genuinely separate OS processes and diffing the output JSON
byte-for-byte: **identical** (see Reproducibility below). No wall-clock
run metadata (`generated_at` or similar) is included in the artifact at
all, so there was nothing to exclude from that comparison.

### 17. Optional simulation results

Implemented (Day 12 spec section 20, optional). Reuses
`src.recovery.simulator.estimate_outcome()` (Day 8, unmodified) with a
per-transaction seed from `src.experiment.random_state.derive_transaction_seed()`
(Day 9's CRN mechanism, unmodified), evaluated against each
transaction's actual frozen-policy-chosen action. Every resulting figure
is labeled **SIMULATED / COUNTERFACTUAL** in both the JSON artifact
(`simulated_recovery_summary`) and the per-transaction records
(`simulated_recovered`, `simulated_amount_recovered`,
`simulated_duplicate_charge_risk`) — never described as observed,
actual, or real Razorpay revenue. Does not read from or write to any Day
9/10 result file.

### 18. Limitations

- **Training-membership limitation**: a majority (71.8%) of
  incident-window transactions are in the classifier's TRAIN split. The
  full-window classifier/policy results above are a replay-behavior
  demonstration, not an out-of-sample generalization claim — the 18-row
  held-out TEST subset is the defensible generalization-oriented view,
  and even that is a small sample.
- **Synthetic-data limitation**: every transaction is synthetic
  (`data/generate_data.py`); no real Razorpay production traffic was
  used anywhere in Day 12.
- **Failure-density-not-rate limitation**: the dataset contains no
  successful-transaction rows, so no genuine failure-rate percentage can
  be computed; density (events per unit time) is reported instead.
- **Monitoring limitation**: this is a historical replay of an existing
  dataset window, not a live incident detector — no real-time monitoring
  or production-detection capability exists or is implied.
- **Representative-data limitation**: the incident scenario is a
  designed synthetic burst, not evidence of how a real Razorpay
  infrastructure incident would present.
- **Sample-size limitation**: several per-class counts in the incident
  window are small (e.g. exactly 1 WEBHOOK_AMBIGUITY case, 3
  USER_ABANDONMENT cases) — single-digit counts are reported as such,
  not smoothed into a percentage that would overstate precision.
- **Simulation limitation**: the optional recovery simulation is a
  counterfactual estimate from the frozen Day 8 simulator, not a
  measurement of real recovered revenue.

## Day 13 — Grounded LLM Explanation Layer

Day 13 adds an explanation layer downstream of the already-frozen
decision path. It is a pure `str`-in-facts, `str`-out-prose transform —
it has no authority over, and cannot influence, the root cause, the
confidence, the policy action, or the policy reason.

    PaymentEvent -> feature builder -> calibrated classifier
        -> RootCausePrediction -> Day 7 policy engine -> PolicyDecision
        -> ExplanationEvidence.from_decision()
        -> provider.generate(evidence)   [LLM, or the deterministic
                                           fallback on ANY failure]
        -> Explanation

New package: `src/explain/` (`evidence.py`, `models.py`, `provider.py`,
`redaction.py`, `service.py`). Tests: `tests/test_explain.py` (41 tests).

### 1. Purpose of the explanation layer

Converts an already-computed Recovery Guardian decision into a concise,
evidence-backed, human-readable explanation, for a judge/operator reading
a single decision. It is the FIRST layer in the project with any LLM
involvement, and is explicitly scoped as explanation-only, per the Day 13
master prompt's "the LLM is an explanation component, not a
decision-maker."

### 2. Architecture position

Strictly downstream. `src/explain/service.py`'s `explain_decision()`
takes an already-produced `PaymentEvent`, `RootCausePrediction`, and
`PolicyDecision` (and optionally a `RecoveryOutcome`) as arguments — it
never calls the feature builder, the classifier, or the policy engine
itself, and has no code path that feeds anything back into any of them.

### 3. Evidence contract

`src.explain.evidence.ExplanationEvidence` — a frozen dataclass built
ONLY via `.from_decision()`, which reads every field directly off the
real domain objects: `transaction_id`, `amount`, `payment_method`,
`failure_code`, `retry_count`, `webhook_delay_seconds`,
`incident_active`, `predicted_root_cause`, `predicted_probability`,
`policy_action`, `policy_reason`, `policy_version`,
`relevant_threshold` (loaded from `src/policy/rules.yaml` via
`load_policy_config()` — `None` for `WEBHOOK_AMBIGUITY`, which has no
threshold by design), `safety_flags`, and `outcome_status` /
`outcome_recovered` / `outcome_amount` / `outcome_reason`. Mirrors the
precedent set by Day 8's `RecoveryEvidence` — a small, purpose-narrowing
projection, not a duplicate domain model.

### 4. LLM provider boundary

`src.explain.provider.ExplanationProvider` is a narrow `Protocol` with
exactly one method, `generate(evidence) -> dict`. Two implementations:

- `ClaudeExplanationProvider` — thin wrapper over the Anthropic Messages
  API (`anthropic` package, imported lazily so it is never required at
  module-import time). No API key or network access is required by the
  automated test suite: tests inject a duck-typed fake `client` object
  implementing `.messages.create(...)`.
- `DeterministicFallbackProvider` — no LLM, no network, always succeeds.

The provider's return value is read for exactly two keys — `summary` and
`safety_note`, both free text. `explain_decision()` never copies
`root_cause`/`action`/`reason`/`confidence`/`outcome_status` out of a
provider's response, no matter what it contains — proven directly by
`tests/test_explain.py::test_provider_cannot_override_the_decision`,
which uses a provider that deliberately tries to forge those fields.

### 5. Deterministic fallback

Used directly when no provider is configured, and automatically on ANY
provider failure — missing credentials, network/timeout error, malformed
response shape, unparseable JSON, or an empty summary
(`src/explain/service.py`'s `explain_decision()` catches every exception
from `provider.generate()` and falls back). LLM failure degrades prose
quality only; the decision fields are computed from `evidence` either
way and are therefore unaffected regardless of which path produced the
prose.

### 6. Grounding controls

The values that MUST come from the deterministic system — root cause,
probability, action, reason, threshold — are assigned directly from
`ExplanationEvidence` in `explain_decision()`, never read back from
provider output. There is no `if root_cause == ...: action = ...`
anywhere in `src/explain/` (verified directly, via AST inspection of
every file in the package, by
`test_no_conditional_root_cause_dispatch_anywhere_in_explain_package`) —
this package contains no second policy engine and no second ML model.

### 7. Safety controls

`action_before_explanation == action_after_explanation` is verified for
every representative case (CARD_DECLINE → CUSTOMER_RECOVERY,
INSUFFICIENT_FUNDS → CUSTOMER_RECOVERY, INFRASTRUCTURE high-confidence →
DEFER_RETRY, INFRASTRUCTURE low-confidence → HUMAN_REVIEW,
WEBHOOK_AMBIGUITY → BLOCK_RECONCILE, OTP_TIMEOUT → NO_ACTION), each
built through the REAL feature builder, REAL calibrated classifier, and
REAL Day 7 policy engine on a real dataset row — no fake `PolicyDecision`
is constructed for any of these tests.

### 8. WEBHOOK_AMBIGUITY behavior

The primary safety integration test
(`test_real_pipeline_webhook_ambiguity_explanation_preserves_block_reconcile`)
runs a real WEBHOOK_AMBIGUITY dataset row through the full real pipeline
and asserts the resulting `Explanation.action == "BLOCK_RECONCILE"`.
`test_webhook_ambiguity_stays_block_reconcile_even_with_forging_provider`
additionally re-runs the same case against a provider that forges
`DEFER_RETRY`, a provider that raises, and a provider that returns a
malformed response — `BLOCK_RECONCILE` is unchanged in every case.

### 9. Observed/Simulated/Unavailable outcome semantics

`ExplanationEvidence.outcome_status` is one of exactly three values —
`OBSERVED`, `SIMULATED`, `UNAVAILABLE` — enforced by `__post_init__`
(raises if `outcome_status` is invalid, or if it's `UNAVAILABLE` while an
outcome value was supplied, or non-`UNAVAILABLE` with no outcome
supplied — there is no way to fabricate outcome facts through this
constructor). `RecoveryOutcome` carries no provenance field itself, so
the caller declares it explicitly — currently only `SIMULATED` (from Day
8's `estimate_outcome()`) is ever produced anywhere in this project;
`OBSERVED` exists in the contract for a real Razorpay outcome that does
not exist yet, and is never fabricated. The deterministic fallback's
summary text says "Simulation estimates..." for `SIMULATED` and never
"recovered ₹X" — verified by
`test_simulated_outcome_is_labeled_simulated_not_observed`.

### 10. Prompt-injection defense

`PaymentEvent` has no free-text customer/merchant-description field —
`merchant_id` is the closest thing to an attacker-influenceable string,
so `test_malicious_merchant_id_cannot_change_the_decision` constructs one
containing instruction-like text ("IGNORE ALL PREVIOUS INSTRUCTIONS...")
and confirms it cannot reach or alter `root_cause`/`action`. The Claude
system prompt (`src.explain.provider.SYSTEM_PROMPT`) additionally
instructs the model explicitly that all evidence content, including
identifiers, is DATA and never an instruction — defense in depth on top
of the structural guarantee in section 6 above, which holds regardless
of whether the LLM actually obeys that instruction.

### 11. Secret / PII boundary

`src.explain.redaction.redact_evidence_for_provider()` is an explicit
allowlist of exactly the `ExplanationEvidence` fields a provider may see
(no `event_id`, no raw `PaymentEvent`), plus a defensive regex check
(the same credential-pattern family used by this project's existing
secret scans) that refuses to send any string value that looks like a
live credential. `PaymentEvent`/`ExplanationEvidence` were not modified
to support this — redaction happens only at this one boundary function.

### 12. Testing

41 new tests in `tests/test_explain.py`: real-pipeline integration (1),
representative-case coverage across all 6 required cases (parametrized),
grounding/anti-hallucination (root cause/probability/action/reason
preserved, simulated-vs-observed labeling, missing-outcome
non-fabrication), WEBHOOK_AMBIGUITY/HUMAN_REVIEW/NO_ACTION invariance
across multiple providers including a deliberately malicious one,
prompt-injection defense, secret/PII redaction, provider-failure
fallback behavior (timeout, malformed response, empty summary, missing
credentials), a fake-Anthropic-client plumbing test (no real package or
API key required), no-second-policy-engine / no-second-ML-model AST
checks, reproducibility of structured evidence and fallback output, and
a side-effect firewall (no DB write, no idempotency-module import).

### 13. Known limitations

- LLM-backed (`ClaudeExplanationProvider`) prose is not claimed to be
  byte-identical across calls — only the deterministic fallback and the
  structured decision fields are tested for exact reproducibility.
- The Claude system prompt is a strong instruction, not a cryptographic
  guarantee against a sufficiently adversarial model; the actual safety
  guarantee is structural (section 6/8 above), not prompt-based — the
  prompt is defense in depth, not the primary control.
- `merchant_id` is the only realistic injection-vector field currently
  on `PaymentEvent`; there is no free-text customer-facing field in this
  project to test injection through, since none exists.
- No live Razorpay integration, credentials, or network calls exist
  anywhere in this layer or its tests.
- The explanation layer has not been evaluated for prose quality by a
  human judge beyond spot-checking; only its grounding/safety properties
  are tested.

### 14. Day 12 perfect-score disclosure status

Day 12's held-out-test INFRASTRUCTURE result (15/15, 100%) was
**reported** in the Day 12 section above but was **not** run through the
project's own established leakage-investigation methodology (the ">98%
trigger" applied at Day 4 to four classes that scored 100% on the full
242-row test set — see PROGRESS.md's Day 4 section) or cross-referenced
against Day 4's known full-test-set INFRASTRUCTURE recall (0.963) for
plausibility. Day 13 did not re-open, re-investigate, or modify the Day
12 result — it is preserved as frozen historical evidence. This gap is
recorded here and in PROGRESS.md rather than silently treated as a
validated invariant; no Day 13 test asserts that the 15/15 result is
intrinsically correct.

## Day 14 — Final Productization + Judge-Facing Evidence

Day 14 makes no changes to the intelligence or safety behavior measured
by Days 4-13. It productizes what already exists: a judge-facing demo
runner, a complete README, and a documentation-consistency audit. If any
proposed change during Day 14 touched a frozen subsystem, the instruction
was to stop and report it out of scope — no such change was needed or
made.

### 1. Product surface audit (before building anything)

Inspected before writing any new code:

- `README.md` — existed, but was still the Day 1 stub, explicitly
  stating "Full README ... lands on Day 14." Rewritten today (not merely
  appended) as originally planned.
- `Makefile` — existing `data`/`initdb`/`train`/`calibrate`/`run`/`test`/
  `clean` targets, reused as-is in the README's reproduction section, not
  duplicated.
- `run_pipeline.py` (repo root, Day 3) — an existing single-transaction
  CLI. Persists to the real `recovery_guardian.db` by default and has no
  Day 13 explanation integration, so it was left untouched rather than
  modified into something it was never designed to be — the Day 14 demo
  is a new, narrowly-scoped script instead (see below).
- `src/api/app.py` — the Day 1 FastAPI skeleton, unchanged, not expanded.
- `dashboard/` — an empty placeholder directory only; no frontend
  implementation exists. Left empty, per the Day 14 frontend boundary.
- No `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, or Kubernetes
  manifests exist anywhere in the repository. None were added.
- `.env.example` — already contained only empty placeholder values and
  an explicit `LLM_ENABLED=false` kill switch; no real credentials
  present, none added.

### 2. Judge-facing demo: `experiments/run_judge_demo.py`

New, per the established `experiments/run_*.py` convention (Day 9-12).
Calls the real, unmodified `src.pipeline.pipeline.run_pipeline()` against
an isolated in-memory SQLite connection (the exact pattern already used
by Day 9/11/12's test fixtures) for three fixed, deterministic scenarios:

- `webhook_ambiguity` (primary safety scenario)
- `infrastructure_high_confidence` (→ `DEFER_RETRY`)
- `infrastructure_low_confidence` (→ `HUMAN_REVIEW`)

Each scenario's transaction ID was identified offline by filtering on the
calibrated classifier's own predicted root cause and probability — the
same technique Day 11/13's test fixtures already used — never by
inspecting `actual_root_cause`. The dataset's `actual_root_cause` column
is read once per scenario, strictly after the real decision has already
been produced, only for an optional judge-facing reference line, and is
never passed into `PaymentEvent`, the feature builder, the classifier,
the policy engine, or the explanation layer — verified both functionally
(swapping the label changes nothing) and by AST inspection (the variable
holding it is never passed into any decision-path call) in
`tests/test_judge_demo.py`.

Each scenario's `run_pipeline()` result feeds directly into
`src.explain.service.explain_decision()` with `outcome_status=SIMULATED`
(Day 8's simulator is the only outcome source that exists in this
project). `action_before_explanation`/`action_after_explanation` are
both reported explicitly in the output and asserted equal for every
scenario.

Provider selection respects the existing `.env.example` kill switch:
unless `LLM_ENABLED=true`, the demo never attempts a Claude call at all
(no network access, no credential lookup) and uses
`DeterministicFallbackProvider` directly — this is also why the demo's
default output is byte-identical across processes (see Reproducibility
below).

### 3. Reproducibility (verified, not assumed)

Ran `python experiments/run_judge_demo.py` as two genuinely separate OS
processes and diffed both the console output and the written
`experiments/results/day14_demo.json` — **byte-identical** in both. No
wall-clock or random-identifier field (`event_id`, `decision_id`) is
included in the output at all, so there was nothing to exclude from the
comparison — the same discipline Day 12 established. Day 8's simulator
seed is derived deterministically from `(transaction_id, action)`, so the
simulated outcome is identical across runs without any explicit seed
needing to be threaded through the demo.

`experiments/run_incident_demo.py` (Day 12) was re-run directly today and
confirmed unchanged: 110 incident-window transactions, the same
71.82%/11.82%/16.36% TRAIN/VALIDATION/TEST split, and
`webhook_ambiguity_safety.safety_pass = true`.

### 4. Documentation-consistency audit

Searched the repository for the forbidden claim patterns ("highest
recovery", "100% infrastructure accuracy", "real Razorpay data",
"production recovery", "live Razorpay", "guaranteed recovery", etc.).
Every existing match in `docs/architecture.md`/`PROGRESS.md` was already
a negated, honest statement ("Not a live Razorpay integration...", "No
observed recovery-outcome labels exist...") — **no correction was
required**; the existing documentation was already consistent with the
verified evidence. The new README was written to the same standard.

### 5. Day 9/10 evidence — reported, not re-measured

The README cites the exact Day 9 primary-seed-42 numbers, re-verified
today by re-running `python experiments/run_day9_experiment.py --seed
42` (a frozen, unmodified script) and confirming the console output
matches exactly: Naive Retry ₹205,427.28 (29.75%, 12 duplicate-risk),
Rules-only ₹238,230.16 (33.88%, 3 duplicate-risk), Guardian ₹193,316.24
(28.93%, 0 duplicate-risk), No Action ₹0.00 (0.00%, 0). Guardian is
never described as recovering the most revenue — the README states
explicitly that Rules-only recovers more, and frames Guardian's value as
safety-constrained recovery.

### 6. Frozen firewall

Verified via `git diff d778097` against `src/model`, `src/features`,
`src/policy`, `src/recovery`, `data`, `experiments/run_day9_experiment.py`,
`experiments/day9_experiment_config.yaml`, `src/experiment`,
`src/ingestion/razorpay_adapter.py`, `src/explain` (the confirmed actual
Day 13 explanation-layer path), `experiments/run_incident_demo.py`, and
`tests/test_incident_demo.py` — all empty.

### 7. Limitations

- The Day 14 demo covers three fixed, hand-selected representative
  scenarios, not an exhaustive sweep of the dataset.
- LLM-backed (`ClaudeExplanationProvider`) demo output is not claimed
  byte-identical — only the default deterministic-fallback path is
  tested and documented as reproducible.
- The README's "no frontend" position is a deliberate Day 14 scope
  decision, not a claim that a frontend would be undesirable at a later
  stage.
- All Day 12/13 limitations already documented in their own sections
  above remain unchanged and are carried forward, not re-litigated.

## Day 15 — Frontend (Milestones 1-4)

A React/TypeScript/Vite/Tailwind product shell (`frontend/`), built on
`frontend/day15-productization` off the `submission-v1` (`7db4b02`)
checkpoint. Five pages: Overview, Safety, Decision Pipeline,
Explainability, Incident Replay. The frontend is a visualization layer —
it never runs the ML model, the policy engine, or the simulator; it
reads only already-computed evidence.

### Data plumbing (Option A: build-time static snapshot)

`scripts/generate_frontend_snapshot.py` is the single, read-only
boundary between three frozen backend artifacts and the frontend:

    experiments/results/day9_seed_42_aggregate.json    (+ seeds 43/44
                                                          for cross-seed
                                                          sensitivity)
    experiments/results/day12_incident_demo.json
    experiments/results/day14_demo.json
        -> scripts/generate_frontend_snapshot.py (read-only)
        -> frontend/src/data/snapshot.ts (typed, committed)
        -> React UI

The script only reads, validates (type/range checks per field), selects,
and rounds-for-display — it never recomputes a metric, reruns the model
or policy, or invents a missing value; a missing or malformed source
field fails generation loudly (non-zero exit) rather than silently
defaulting. Verified deterministic: two consecutive runs produce
byte-identical output except the documented `generatedAt`/
`SNAPSHOT_GENERATED_AT` wall-clock field (the same discipline Day 12
established for its own run metadata).

Milestone 3 extended this one script and this one output file — it did
not create a second generator or a second scenario/incident data model.
Both extensions merge new fields onto the exact same records Milestone 2
already produced:
- `_day14_scenario()`'s `explanation` field is read from the SAME
  per-scenario dict (`day14[scenario_key]`) every other scenario field
  already comes from — there is no second artifact to identity-cross-
  check against, since it is structurally the same record.
- `day12`'s new `before`/`incident`/`after` density windows and
  `simulatedRecoverySummary` are read from the SAME already-loaded
  `day12` dict Milestone 2's split-membership/classifier fields come
  from.

### Milestone 1 — product shell, Overview

Design system: `#080A0D`/`#101318`/`#151A20`/`#252B33` surfaces,
`#22C55E` safety green (used sparingly, via a restrained "Safety Glow"
radial motif), system sans-serif for prose and system monospace for
technical data (transaction IDs, probabilities, amounts, actions,
versions) — no external font dependency. Application shell: a left
navigation rail (collapsing to a mobile top bar), with disabled,
clearly-marked "Soon" placeholders for unimplemented sections rather
than fake pages. Overview: hero → primary safety KPI (0 duplicate-charge
risk, seeds 42/43/44) → strategy comparison → `WEBHOOK_AMBIGUITY`
signature case → static decision-pipeline preview → provenance/
limitations footer. An axe-core audit found one real, fixed issue: the
`text-muted` token (`#68717D`) failed WCAG AA contrast (3.88:1) against
the darkest surface; lightened to `#7B8794` (5.10:1) — the only Milestone
1 palette value ever changed, and only for accessibility.

### Milestone 2 — Safety Hero, interactive Decision Pipeline

`src/explain/`-style "one component, many contexts" discipline applied
to the frontend: `components/pipeline/PipelineDiagram.tsx` is the single
shared implementation of the pipeline visual (node design, connector
lines, the ceremonial lock+glow, the quiet settle transition) — the
Overview's static preview and the new interactive Decision Pipeline page
both render through it; `PipelinePreview.tsx` was refactored into a thin
wrapper rather than duplicated. Three real scenarios (verified against
the raw Day 14 artifact before any UI was written — see the Day 15
Milestone 2/3 final reports for the verbatim extraction):
`WEBHOOK_AMBIGUITY → BLOCK_RECONCILE` (ceremonial), `INFRASTRUCTURE`
high-confidence `→ DEFER_RETRY` (quiet, info accent), `INFRASTRUCTURE`
low-confidence `→ HUMAN_REVIEW` (quiet, warning accent) — the action-to-
accent mapping is presentational only (the same "look up how to display
an already-known value" pattern `ProvenanceBadge` uses), never a
computation of the action itself. Node click reveals an inline detail
panel (not a modal), fully keyboard-accessible. A real interaction bug
was found and fixed: clicking a node reset and replayed the entire
reveal animation, because the node array was rebuilt (new reference) on
every render — fixed with `useMemo`. A real responsive bug was found and
fixed: the pipeline row overflowed horizontally at the 768px tablet
breakpoint because flex children couldn't shrink below their text's
intrinsic width — fixed with `min-w-0` + `break-words`.

### Milestone 3 — Explainability, Incident Replay

**Explainability**: decision summary → evidence chain (reusing
`PipelineDiagram`) → explanation prose → a prominent
`action before explanation == action after explanation` safety-invariant
display → provenance legend. The explanation prose is rendered as
text only — nothing on this page parses it to determine anything; every
structured field (root cause, probability, action, reason) comes from
the same `prediction`/`policy` records the Decision Pipeline page uses.

A genuine finding during raw-source verification: `run_judge_demo.py`
writes the identical fixed disclaimer string into
`explanation._provenance` regardless of whether
`DeterministicFallbackProvider` or `ClaudeExplanationProvider` actually
produced the prose for a given scenario — the artifact does not record
which provider ran. Rather than guessing/bucketing this into "LLM-
generated" vs. "Deterministic" (which would have invented a fact the
source doesn't contain), the frontend passes the raw disclaimer through
verbatim and says so explicitly on the page.

**Incident Replay**: explicitly labeled "Historical synthetic replay" in
the header (never live monitoring or real-time telemetry) — before →
incident → after failure-density timeline (labeled "Failure density,"
not "failure rate," with the "why" stated inline, not in a tooltip) →
root-cause distribution → full-window/held-out-test classifier result
with the 15/15 limitation disclosed inline → train/validation/test
membership with the training-majority disclosure → `WEBHOOK_AMBIGUITY`
safety (Day 12's 1-transaction incident-window population) → simulated
recovery (labeled SIMULATED, explicitly "never observed production
revenue").

**Day 9 vs. Day 12 `WEBHOOK_AMBIGUITY` population firewall**: the Safety
page's Day 9 population (25 held-out test transactions) and the Incident
Replay page's Day 12 population (1 incident-window transaction) are
never combined into one number anywhere in the frontend. Incident Replay
explicitly names both populations and states "the two are never
combined"; a dedicated test
(`IncidentReplay.test.tsx`'s "Day 9 vs Day 12 WEBHOOK_AMBIGUITY
population firewall" describe block) asserts the rendered Day 12 count
is exactly 1, not 25 or 26.

### Testing and QA (Milestones 1-3 combined)

66 frontend tests (Vitest + React Testing Library) across 10 files,
covering: rendering, scenario switching, structured-field accuracy
against the live snapshot, the action-before/after safety invariant,
provenance labeling, unavailable-data states, keyboard interaction,
no-second-decision-logic source scans, and data-continuity (M2 fields
unchanged after M3's extension, M3 fields merged onto — not duplicating
— M2's scenario objects). axe-core: 0 violations (of any severity) across
all five pages, including interactive states (a node expanded, a
non-default scenario selected) — one moderate heading-order violation
introduced by Milestone 2's own `NodeDetailPanel` (`h3`→`h2`) was found
and fixed during Milestone 2. Reduced motion and keyboard navigation
verified via automated checks with a real Chrome browser (a temporary,
non-committed `playwright-core`/`@axe-core/playwright` install, removed
after each milestone's QA pass). Responsive QA at 1440×900/768×1024/
390×844 for every page.

### Milestone 4 — Recovery Analysis

**Data-granularity audit (performed before any visualization was
designed)**: confirmed, by direct inspection of the actual artifacts —
not assumed —

- **Per-strategy aggregate**: AVAILABLE (`day9_seed_42_aggregate.json`
  `by_strategy`; equivalently `day10_analysis.json`
  `strategy_table_primary_seed`, which additionally carries each
  strategy's full `action_distribution`).
- **Per-strategy × root-cause**: AVAILABLE (`day10_analysis.json`
  `root_cause_table_primary_seed`, one full strategy row — including
  `action_distribution` — per of the 6 root causes).
- **Per-seed × strategy**: AVAILABLE, and *fully* available (not merely
  duplicate-risk counts) — verified directly by reading all three
  `day9_seed_{42,43,44}_aggregate.json` files independently and
  confirming an identical schema before relying on
  `day10_analysis.json`'s already-consolidated `seed_sensitivity`
  object, which contains the complete 3×4 recovery/rate/risk/action
  matrix in one schema-consistent artifact.

A fourth artifact, `experiments/results/day10_analysis.json` (frozen,
produced by the existing `experiments/run_day10_analysis.py`), was wired
into `scripts/generate_frontend_snapshot.py` for the first time —
preferred over re-deriving root-cause/seed breakdowns from the raw Day 9
per-transaction records, because Day 10 already normalizes exactly this
comparison. New snapshot section: `day10` (`strategyTable`,
`rootCauseTable`, `combinedCardDeclineInsufficientFunds`,
`seedSensitivity`, `mcnemarGuardianVsRulesOnly`). No second generator, no
recomputation — pure selection of already-computed Day 10 output.

**Page**: hero ("Recovery, constrained by safety.") → the same
`SafetyKpi` component (Guardian's zero duplicate-charge risk, seeds
42/43/44) as the primary headline, never a recovery-amount headline →
a hand-built SVG Recovery-vs-Safety chart (one aggregate point per
strategy — X = simulated recovery, Y = duplicate-charge risk, axis
range derived from the data with zero always included, no truncation,
no chart library added for four points) with a full accessible data
table alongside it → the reused `StrategyComparison` component in
**experiment order** (Naive Retry, Rules-only, Guardian, No Action —
never Guardian-first) → evidence-backed interpretation (including a
Day 10 McNemar reference, reported as measured, not as a significance
claim) → the reused `WebhookAmbiguityCase` component, explicitly labeled
"Day 9 test-set safety analysis — 25 transactions" → a root-cause ×
strategy matrix → the full 3-seed × 4-strategy sensitivity table
(genuinely available, so shown in full — not scoped down) →
provenance/limitations.

**Real bugs found and fixed during Milestone 4 QA**:
- A landmark/ID duplication: an early draft wrapped the reused
  `StrategyComparison` component (which already renders its own
  `<section aria-labelledby="strategy-comparison-heading">`) in a second,
  identically-ID'd section — axe flagged `landmark-unique`. Fixed by
  rendering the reused component directly, matching the pattern already
  established on the Safety page.
- A genuine mobile-viewport horizontal-overflow bug, present since
  Milestone 1: `SafetyKpi`'s decorative "Safety Glow" radial div (420px,
  absolutely positioned and centered) was 30px wider than a 390px
  mobile viewport and had no clipping ancestor, inflating
  `document.documentElement.scrollWidth` by 15px on every page that
  renders `SafetyKpi` (Overview, Safety, and now Recovery). Fixed with
  one `overflow-hidden` on the component's own section — the same fix
  `WebhookAmbiguityCase`'s equivalent glow already had.
- A transient axe false-positive: a full-page re-audit briefly flagged a
  `color-contrast` violation on the Explainability page's pipeline
  final node — investigated, not dismissed: the flagged colors
  (`#24282d`, `#404245`, `#0e3720`) were mid-CSS-transition
  interpolated values, caught by axe running at the exact tail of the
  500ms ceremonial reveal. Re-confirmed 0 violations with a longer
  settle wait; not a persistent defect.

### Limitations

- The frontend covers exactly the three Day 14 judge-demo scenarios —
  no arbitrary transaction search or live inference exists or is
  planned for this product surface.
- LLM-backed (`ClaudeExplanationProvider`) prose is not claimed
  byte-identical; only the deterministic-fallback path and the
  structured decision fields are tested for exact reproducibility.
- The source artifact does not distinguish which explanation provider
  produced a given scenario's prose — disclosed explicitly on the
  Explainability page rather than guessed at.
- Headless QA (axe, screenshots, keyboard/reduced-motion checks) used a
  temporary, non-committed browser-automation install against the local
  system Chrome — not part of a CI pipeline.
- The Recovery Analysis seed-sensitivity table shows n=3 seeds
  qualitatively only — no confidence interval or significance test is
  computed or implied anywhere on that page.
- The Day 10 McNemar comparison shown on Recovery Analysis describes
  transaction-level paired outcomes under simulation; it is not a claim
  of production effectiveness.
- All Day 9-14 limitations already documented in their own sections
  above remain unchanged and are carried forward, not re-litigated —
  including Day 12's un-investigated 15/15 held-out INFRASTRUCTURE
  result, disclosed on the Incident Replay page.
