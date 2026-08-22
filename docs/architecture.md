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
