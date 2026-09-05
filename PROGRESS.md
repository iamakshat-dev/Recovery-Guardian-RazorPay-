# Recovery Guardian — Progress Log

Tracks only work that has actually been completed and verified, day by
day. Nothing here describes intended/future behavior as if it already
existed — see each day's "Limitations" for what explicitly does not exist
yet.

## Day 1–2 — Synthetic data + domain models + feature builder

- `data/generate_data.py`: synthetic payment-failure dataset generator,
  6 root-cause classes, deliberately overlapping/non-trivial feature
  distributions (`INFRASTRUCTURE` vs `WEBHOOK_AMBIGUITY` share failure
  codes by design), plus an injected incident-window burst.
- `src/domain/models.py`: typed domain objects (`PaymentEvent`,
  `RootCausePrediction`, `PolicyDecision`, `RecoveryOutcome`,
  `DecisionRecord`) and enums (`RootCause`, `RecoveryAction`, `ReasonCode`).
- `src/db.py`: SQLite schema (`payment_events`, `decisions`,
  `recovery_outcomes`, `idempotency_log`).
- `src/features/build_features.py`: feature builder, fixed
  `FEATURE_COLUMNS` contract (26 features), fixed category vocabularies.
- 11 feature-builder unit tests.

## Day 3 — End-to-end pipeline

- `src/ingestion/synthetic_adapter.py`: CSV row → `PaymentEvent` adapter.
- `src/model/placeholder_classifier.py`: structural placeholder classifier
  (fixed 0.50, feature-blind) — kept in the repo as a reference fixture,
  no longer used in the production pipeline as of Day 4.
- `src/policy/placeholder_engine.py`: structural placeholder policy
  engine — always returns `HUMAN_REVIEW` / `LOW_MODEL_CONFIDENCE`,
  regardless of predicted root cause.
- `src/pipeline/pipeline.py`: the core reusable pipeline
  (`PaymentEvent → features → classifier → policy → DecisionRecord → SQLite`).
- `src/audit/logger.py`: persists a `DecisionRecord` into the existing
  SQLite schema.
- `run_pipeline.py`: CLI (`python run_pipeline.py --single-transaction`).
- `tests/test_pipeline_e2e.py`: 10 end-to-end tests.

## Day 4 — Real Logistic Regression classifier

- `src/model/splitting.py`: deterministic 70/15/15 stratified
  train/validation/test split, `random_state=42`.
- `src/model/artifacts.py`: model artifact save/load (joblib).
- `src/model/training.py`: trains a multinomial Logistic Regression
  (`sklearn.linear_model.LogisticRegression`, `random_state=42`) on
  `FEATURE_COLUMNS` against the `actual_root_cause` target, evaluates on
  validation + test, persists the artifact + a metrics JSON. Run via
  `python -m src.model.training` (or `make train`).
- `src/model/classifier.py`: production classifier. Loads the persisted
  artifact, validates the live `FEATURE_COLUMNS` against the schema the
  model was trained on (raises `FeatureSchemaMismatchError` on drift,
  `ModelArtifactNotFoundError` if untrained — never a silent fallback to
  the placeholder), and predicts via real `predict_proba()`.
- `src/pipeline/pipeline.py` updated to use the real classifier. The
  policy engine is **unchanged** — still the Day 3 placeholder.
- Model version: `root-cause-logreg-v1`. Policy version: still
  `placeholder-v1`.
- 13 new model tests (`tests/test_model.py`) + a session-scoped fixture
  (`tests/conftest.py`) that trains a real model into an isolated temp
  path for the whole test session, so `pytest -q` is reproducible on a
  fresh clone with no manual training step required first.

### Day 4 evaluation (test split, n=242, `random_state=42`)

- Accuracy: 0.9835, Macro F1: 0.9810
- Per-class precision/recall: `CARD_DECLINE` 1.00/1.00,
  `INSUFFICIENT_FUNDS` 1.00/1.00, `OTP_TIMEOUT` 1.00/1.00,
  `USER_ABANDONMENT` 1.00/1.00, `INFRASTRUCTURE` 0.963/0.963,
  `WEBHOOK_AMBIGUITY` 0.923/0.923.
- Full confusion matrix: `artifacts/root_cause_classifier_metrics.json`
  (gitignored — regenerate with `python -m src.model.training`).
- Investigated the four 100%-scoring classes for leakage (mandatory
  per the >98% trigger): `failure_code` maps deterministically to
  `CARD_DECLINE`/`INSUFFICIENT_FUNDS`/`OTP_TIMEOUT`/`USER_ABANDONMENT`
  with zero cross-contamination (verified via crosstab), while
  `INFRASTRUCTURE`/`WEBHOOK_AMBIGUITY` share `gateway_timeout` by design.
  Every test-set misclassification (4 rows) occurs exclusively between
  that intentionally-hard pair. **Conclusion: no leakage** — the result
  reflects the dataset's documented design, not a bug.
- Probabilities are raw `predict_proba()` output. **Not calibrated** —
  calibration is Day 6 scope and has not been implemented.

## Day 4 correction/audit pass (this pass)

Baseline before this pass: 34 passed, working tree clean at `ef09f4f`.

- **Policy scope determination:** confirmed the repository is in STATE A
  — the Day 3 placeholder policy engine, with no differentiated
  root-cause → action mapping of any kind. **No Day 7 policy engine was
  introduced.** The unsafe `WEBHOOK_AMBIGUITY → DEFER_RETRY` mapping does
  not exist anywhere in executable code (confirmed via repository-wide
  search).
- **ML model audit:** confirmed the classifier is a genuine, trained
  multinomial Logistic Regression (scikit-learn 1.9's `LogisticRegression`
  removed the `multi_class` parameter — solver `lbfgs` now always uses
  the multinomial/softmax formulation for >2 classes). Inspected the
  fitted artifact directly: `coef_` shape `(6, 26)`, 100% non-zero
  weights, `n_iter_=[187]` — genuinely optimized, not hardcoded.
- **Found and fixed a real bug** in `src/features/build_features.py`'s
  `_one_hot()`: `pd.get_dummies()` was called on a bare `pd.Categorical`
  rather than a `pd.Series`, which returns a fresh 0-based index
  decoupled from the input DataFrame's real index. The later
  `pd.concat` inside `build_features` aligns by index, so any input
  whose index wasn't already a contiguous 0-based range (e.g. a
  filtered/sampled sub-batch like `raw_df.iloc[[3, 7, 100]]`) silently
  produced **NaN** in every one-hot column. Verified training and the
  production single-transaction CLI/pipeline path were never affected
  (both always build features on a freshly-indexed DataFrame) — this was
  a latent landmine for any future batch/evaluation caller, not a data
  integrity problem in the already-reported Day 4 metrics or CLI output.
  Fixed by re-wrapping the `Categorical` in a `Series` carrying the
  original index before calling `get_dummies`. Added a permanent
  regression test
  (`test_build_features_is_robust_to_non_contiguous_input_index`).
- Retrained the model under the fixed code; metrics are byte-identical
  to the pre-fix run, confirming the fix has no effect on the training
  path (as expected) and the previously reported Day 4 metrics stand.
- Added two forward-looking policy **guard** tests
  (`tests/test_policy_scope_guard.py`) that lock in today's actual safe
  behavior (the placeholder can't emit an automatic action for any root
  cause) and document — without implementing — the Day 7 safety
  invariant (`INFRASTRUCTURE → DEFER_RETRY`,
  `WEBHOOK_AMBIGUITY → BLOCK_RECONCILE`, never the reverse mapping).
- Test count: 34 → 42 passed (35 after the build_features fix/regression
  test, +7 from the new policy guard file). No regressions.

## Day 5 — Probability calibration + rigorous evaluation

Baseline before this pass: 42 passed, working tree clean at `a5131e6`.
Correction to the note above: calibration is the project's Day 5 item (not
Day 6, as this file previously and incorrectly said).

- **Day 4 remained frozen.** No change to the dataset, `FEATURE_COLUMNS`,
  `train_val_test_split`, or the trained `LogisticRegression`'s parameters.
  `src/model/classifier.py` (the raw Day 4 classifier) and
  `src/model/training.py` were not modified. Verified in code and by test:
  `coef_`/`intercept_`/`classes_` compared before vs. after calibration
  fitting, byte-identical, both in-memory and re-loaded from disk.
- `src/model/calibrate.py`: loads the frozen Day 4 artifact (read-only),
  fits a **sigmoid (Platt)** calibration layer using
  `sklearn.frozen.FrozenEstimator` + `CalibratedClassifierCV` on the
  **validation split only** (241 rows), evaluates on the untouched **test
  split** (242 rows), and persists a separate calibrated artifact +
  `experiments/results/{evaluation_metrics.json, confusion_matrix.png,
  calibration_plot.png}`. Sigmoid was chosen over isotonic specifically
  because the validation set is small (~40 rows/class on average) —
  isotonic risks overfitting into a jagged step function at this size.
  `FrozenEstimator.fit()` is a no-op by construction, so calibration
  fitting is structurally incapable of retraining the underlying model —
  verified empirically (object identity + parameter equality) before
  writing the module, and re-verified by
  `tests/test_calibration.py::test_calibration_does_not_change_the_frozen_day4_model`.
- `src/model/calibrated_classifier.py`: new, separate
  `CalibratedRootCauseClassifier` (same `.predict(features) ->
  RootCausePrediction` contract) — `src/model/classifier.py`'s raw Day 4
  `RootCauseLogRegClassifier` was NOT modified and remains independently
  loadable.
- Model version: `root-cause-logreg-calibrated-v1` (base:
  `root-cause-logreg-v1`). Artifact:
  `artifacts/root_cause_classifier_calibrated.joblib` — separate file,
  raw artifact untouched (confirmed unchanged on-disk mtime).
- `src/pipeline/pipeline.py` updated to serve the calibrated classifier
  (the one intentional, explicitly-authorized Day 5 integration point —
  analogous to the Day 3→4 swap). Policy engine unchanged.
- 10 new tests in `tests/test_calibration.py`, covering: valid 6-class
  probabilities, validation-only calibration data flow (via a spy on the
  actual `fit_calibration` call, not a comment), frozen-model integrity,
  distinct/independently-loadable artifacts, all-six-class metrics,
  artifact existence/non-empty, valid multiclass Brier/ECE, and real
  end-to-end calibrated inference through `run_pipeline()`.
- Updated `tests/conftest.py`'s session fixture to also fit and register a
  real calibrated artifact (in addition to the Day 4 raw one), so
  `pytest -q` remains reproducible on a fresh clone with no manual
  training/calibration step required first.
- Updated the two production-pipeline `model_version` assertions in
  `tests/test_pipeline_e2e.py` and one in `tests/test_model.py` from
  `root-cause-logreg-v1` to `root-cause-logreg-calibrated-v1` — the one
  intentional Day 4 → Day 5 contract change (analogous to the Day 3 → Day
  4 update). The raw classifier's own direct-instantiation tests were left
  asserting `root-cause-logreg-v1`, unchanged, since that classifier
  itself did not change.
- Test count: 42 → 52 passed. No regressions.

### Day 5 evaluation (test split, n=242, calibrated model, `random_state=42`)

- Accuracy: 0.9793, Macro F1: 0.9760 (raw Day 4: accuracy 0.9835, macro F1
  0.9810 — a very small, honestly-reported decrease: one additional
  `WEBHOOK_AMBIGUITY`→`INFRASTRUCTURE` misclassification post-calibration).
- Per-class (calibrated): `CARD_DECLINE` 1.00/1.00,
  `INSUFFICIENT_FUNDS` 1.00/1.00, `OTP_TIMEOUT` 1.00/1.00,
  `USER_ABANDONMENT` 1.00/1.00, `INFRASTRUCTURE` 0.945/0.963,
  `WEBHOOK_AMBIGUITY` 0.920/0.885.
- Multiclass Brier score: calibrated 0.0341 vs. raw 0.0303 — calibration
  made the Brier score **slightly worse**, not better, on this dataset.
- Top-label ECE (10 bins): calibrated 0.0428 vs. raw 0.0440 — a marginal
  improvement, well within noise for a 242-row test set.
- **Honest conclusion: calibration had essentially no practical effect
  here.** The raw Day 4 model was already well-calibrated on this
  synthetic dataset (very low Brier/ECE to begin with), and a 241-row
  validation set gives sigmoid calibration little room to improve on
  that. This is reported as-is — no retuning was done to make the result
  look better, per the project's no-fabrication rule.
- Full confusion matrix, per-class support, and both plots:
  `experiments/results/{evaluation_metrics.json, confusion_matrix.png,
  calibration_plot.png}` (gitignored — regenerate with
  `python -m src.model.calibrate`, after `python -m src.model.training`).

## Day 6 — Freeze + clean-checkout reproducibility verification

Baseline before this pass: 52 passed, working tree clean at `6f72b22`.
This was a freeze/verification checkpoint — no new functionality, no
model/feature/calibration changes.

- **Artifact verification (PASS):** raw artifact
  (`artifacts/root_cause_classifier.joblib`, `root-cause-logreg-v1`) and
  calibrated artifact (`artifacts/root_cause_classifier_calibrated.joblib`,
  `root-cause-logreg-calibrated-v1`) both load independently, remain
  separate files, and the production pipeline (`src/pipeline/pipeline.py`)
  confirmed to import `CalibratedRootCauseClassifier` (calibrated), not
  the raw classifier. `FEATURE_COLUMNS` and class ordering confirmed
  identical in both artifacts. The calibrated model's internal frozen
  estimator confirmed to reference the exact same `coef_`/`intercept_`/
  `classes_` as the standalone raw artifact — not a retrained copy.
- **Clean-checkout reproduction (PASS):** cloned the local repo at commit
  `6f72b220f0dff08aa449a7e1f14317c4cfab6cb4` into a fresh, isolated
  directory (only committed state — no gitignored files present), fresh
  venv, and ran `make data` → `python -m src.model.training` →
  `python -m src.model.calibrate` from scratch.
  - Dataset: every column except `transaction_id` byte-identical to the
    frozen dataset. `transaction_id`'s trailing 6-hex-char suffix comes
    from unseeded `uuid.uuid4()` in `data/generate_data.py` (not the
    seeded RNG) — a pre-existing generator property, documented, not
    fixed (out of scope; has zero effect since `transaction_id` isn't a
    feature).
  - Day 4 model: `coef_`/`intercept_` byte-identical (max abs diff 0.0),
    `classes_` and `n_iter_` identical.
  - Day 4 predictions: 100% agreement over the complete 242-row test set,
    max probability absolute difference 0.0.
  - Day 4 metrics JSON: byte-identical to the frozen file.
  - Day 5 calibration: fitted sigmoid calibrator parameters byte-identical
    (max abs diff 0.0).
  - Day 5 metrics JSON: byte-identical to the frozen file.
  - **Reproducibility verdict: EXACT MATCH** (with the fully-explained,
    feature-irrelevant `transaction_id` exception above).
- **Environment note:** the pinned `requirements.txt` still fails to
  install on this machine's only available Python (3.14.2) —
  pre-existing, previously documented, not modified today. The clean
  checkout used the same unpinned dependency versions that produced the
  authoritative frozen results, for a valid comparison.
- `docs/architecture.md` created — the frozen ML state, freshly
  re-verified numbers only (no copied console output).
- No defects found. No source code changes were required or made.
- Test count: 52 → 52 (unchanged — Day 6 is verification, not new
  functionality; no new tests were added).

## Known limitations (accurate as of this pass)

- Calibration provided negligible benefit on this dataset/validation-set
  size — reported honestly above, not treated as a problem to fix by
  retuning against the test set.
- No Razorpay integration exists (Day 11).
- No frontend/dashboard exists (Day 13).
- The pinned `requirements.txt` vs. Python 3.14 install mismatch remains
  unresolved (confirmed again during Day 6's clean-checkout attempt).
- `RootCauseLogRegClassifier` / `CalibratedRootCauseClassifier` reload and
  revalidate their artifacts from disk on every `run_pipeline()` call —
  fine at this scale, unaddressed because it isn't a correctness issue.
- The reliability diagram's mid-confidence bins are noisy (few samples per
  bin) because the test set is only 242 rows and the model is already
  highly accurate — a real property of the evaluation, not a plotting bug.
- `transaction_id`'s random suffix (unseeded `uuid.uuid4()` in
  `data/generate_data.py`) means the synthetic dataset CSV is not
  byte-for-byte reproducible in that one column, though every substantive
  column (features + label) is. Not fixed — out of Day 6 scope (dataset
  generator is frozen), and has no effect on model/metrics reproducibility.

## Day 7 — Deterministic policy engine

Implemented and verified (99 tests passing, aggregate adversarial safety
test with 48 cases, forbidden-mapping search clean, ML foundation
confirmed frozen — see commit `cc65f13`). All six root causes have
intentional behavior: `INFRASTRUCTURE → DEFER_RETRY`,
`CARD_DECLINE`/`INSUFFICIENT_FUNDS → CUSTOMER_RECOVERY`,
`WEBHOOK_AMBIGUITY → BLOCK_RECONCILE` (unconditional hard safety
invariant), `OTP_TIMEOUT`/`USER_ABANDONMENT → NO_ACTION` (documented
assumption, no explicit spec exists for these two). Safety guards: opt-out,
amount threshold, retry cap, cooldown, idempotency (via the existing
`idempotency_log` table). A detailed prose write-up in this file and in
`docs/architecture.md` was explicitly deferred at the time (skipped by
request) — the implementation itself is fully tested and documented in
code comments/docstrings in `src/policy/engine.py`.

## Day 8 — Shared counterfactual outcome environment

Baseline before this pass: 99 passed, working tree clean at `cc65f13`.

- **Data availability audit (mandatory, performed first):** inspected
  `data/generate_data.py`, the `recovery_outcomes` table, and every other
  data source. **No observed recovery-outcome labels exist anywhere in
  the repository** — confirmed, not assumed. Built a transparent
  synthetic counterfactual simulator instead of fabricating a supervised
  training problem.
- `src/recovery/evidence.py`: `RecoveryEvidence` — small, pre-action-only
  evidence object (not a duplicate of `RecoveryOutcome`/`PolicyDecision`).
- `src/recovery/simulation_config.yaml`: explicit, documented synthetic
  simulation assumptions (recovery probabilities per action/root-cause,
  the `WEBHOOK_AMBIGUITY` duplicate-charge-risk parameters) — not
  production statistics, clearly labeled as such.
- `src/recovery/simulator.py`: the one shared
  `estimate_outcome(evidence, action) -> RecoveryOutcome`. Independent of
  `PolicyDecision` (verified by AST inspection of its actual imports, not
  a prose claim); accepts all five `RecoveryAction` values including ones
  Guardian's Day 7 policy would never authorize (required for Day 9/10's
  fair three-way comparison); deterministic by default (seed derived from
  transaction_id + action when none is given), using a local
  `random.Random` instance, never the global `random` module.
- `src/recovery/batch.py`: `simulate_batch(evidence_batch,
  action_selector)` — strategy-agnostic; does not implement the naive/
  rules-only/Guardian selectors themselves (explicitly Day 9/10 work).
- `src/domain/models.py`: `RecoveryOutcome` extended additively with
  `duplicate_charge_risk: bool = False` and `outcome_reason: str = ""` —
  all six original fields (`transaction_id`, `action_taken`, `recovered`,
  `amount_recovered`, `decision_id`, `timestamp`) unchanged. Nothing
  previously constructed a `RecoveryOutcome` anywhere in the codebase, so
  this was a purely additive change.
- `src/db.py`: `recovery_outcomes` table extended additively with
  `duplicate_charge_risk` and `outcome_reason` columns — same table, same
  primary key, no second outcome table.
- `src/audit/logger.py`: `persist_recovery_outcome()` added, reusing the
  existing connection/schema exactly as `persist_decision_record()` does.
- `src/pipeline/pipeline.py`: now calls `estimate_outcome` with the real
  Day-7-authorized `policy_decision.action` (never a hypothetical one) and
  persists the result — verified directly: a real `WEBHOOK_AMBIGUITY`
  prediction run through the full pipeline is always scored with
  `BLOCK_RECONCILE`, never `DEFER_RETRY`.
- Test count: 99 → 132 passed (33 new: `test_recovery_simulator.py` [26],
  `test_recovery_batch.py` [4], `test_recovery_pipeline_integration.py`
  [3]). One pre-existing Day 3 test's assertion (`record.outcome is None`)
  was updated to reflect the intentional Day 3 → Day 8 contract change
  (outcome is no longer `None`) — the same pattern as every previous
  day's classifier/policy version-transition updates. No other tests
  weakened or deleted. Day 7's full safety suite (47 tests, including the
  48-case aggregate adversarial test) re-run and still green.
- ML foundation confirmed frozen: `git diff` against both the Day 6
  (`0a85d8a`) and Day 7 (`cc65f13`) commits for `src/model`, `src/features`,
  and `data` all empty.

### Known limitations (Day 8)

- Every recovery probability and the `WEBHOOK_AMBIGUITY` duplicate-charge
  assumption are **synthetic simulation parameters**, not observed
  statistics — the project has zero real recovery-outcome labels. These
  must be recalibrated against real labeled data before any number this
  simulator produces could be treated as a real recovery-rate estimate.
- The simulation is binary all-or-nothing (an outcome recovers the full
  transaction amount or none of it) — a deliberate simplification.
- The naive, rules-only, and Guardian action selectors for the Day 9/10
  three-way experiment do not exist yet — only the shared scoring
  environment they will all use.
- `unrecovered_amount` is a derived helper function, not a persisted
  `RecoveryOutcome` field (documented design choice — see
  `docs/architecture.md`'s Day 8 section).

## Day 9 — Four-strategy counterfactual experiment

Baseline before this pass: 132 passed, working tree clean at `7ce6ba3`.

- **Objective:** measure how four action-selection strategies
  (`NAIVE_RETRY`, `RULES_ONLY`, `GUARDIAN`, `NO_ACTION`) compare against
  the same evidence, the same Day 8 outcome environment, and the same
  common random numbers. Not a tuning exercise — nothing in the ML,
  calibration, Day 7 policy, or Day 8 simulation config was changed.
- **Day 8 compatibility check performed first:** `estimate_outcome`'s
  existing `seed` parameter already satisfies Day 9's CRN requirement
  (verified empirically) — **Situation B**, no compatibility fix needed,
  `src/recovery/simulator.py` untouched.
- `src/experiment/random_state.py`: SHA-256-based deterministic
  per-transaction seed derivation (never Python's `hash()`).
- `src/experiment/strategies.py`: the four strategies, one common
  `select_action(payment_event) -> RecoveryAction` interface.
  `GuardianStrategy` calls the real feature builder + real calibrated
  classifier + real Day 7 `RulesPolicyEngine` directly, bypassing only
  the persistence/idempotency-write layer (Option A) — verified to
  return the same action on repeated/cross-instance calls for the same
  transaction, and to never import any DB/persistence function.
- `src/experiment/dataset.py`: loads the existing frozen 15% test split
  (242 rows, `random_state=42`) — the same split Day 4/5 evaluated.
- `src/experiment/runner.py`, `results.py`: one shared experiment runner
  and aggregation module — no per-strategy runner or simulator exists.
- `src/recovery/evidence.py`: `RecoveryEvidence` extended additively with
  `failure_code: str = ""` (rules-only needs it; explicitly permitted by
  spec) — same additive-field pattern as every previous day.
- `experiments/day9_experiment_config.yaml`: frozen **before** the
  primary run — dataset subset, primary seed (42), sensitivity seeds (43,
  44, predeclared), currency tolerance (`1e-2`, no pre-existing repo
  convention existed).
- `experiments/run_day9_experiment.py`: CLI entry point. Run three times
  (seeds 42, 43, 44) plus a second, fully independent process re-run of
  seed 42 — **byte-identical output confirmed** (`diff` + matching MD5).
- Test count: 132 → 182 passed (50 new, across
  `test_experiment_strategies.py` [31], `test_experiment_crn.py` [10],
  `test_experiment_metrics.py` [9]). Day 7's full safety suite (47 tests)
  re-run and still green. ML foundation confirmed frozen via `git diff`
  against both the Day 6 and Day 8 commits (`src/model`, `src/features`,
  `data` all empty).
- Forbidden-mapping search: only documentation/test/hypothetical-
  capability matches (no operational Guardian mapping); directly verified
  in the actual experiment output that Guardian selected `BLOCK_RECONCILE`
  for all 25 `WEBHOOK_AMBIGUITY` transactions in the test split and
  `DEFER_RETRY` zero times for that root cause.

### Primary result (seed 42, 242 transactions, `experiments/results/day9_seed_42_aggregate.json`)

| Metric | Naive Retry | Rules-only | Guardian | No Action |
|---|---:|---:|---:|---:|
| Amount at risk | ₹677,213.78 | ₹677,213.78 | ₹677,213.78 | ₹677,213.78 |
| Simulated recovered | ₹205,427.28 | ₹238,230.16 | ₹193,316.24 | ₹0.00 |
| Recovery rate | 29.75% | 33.88% | 28.93% | 0.00% |
| Duplicate-charge risk count | 12 | 3 | **0** | 0 |

Sensitivity seeds 43/44 show the same qualitative pattern: Guardian's
duplicate-charge-risk count is **0 across all three seeds**; naive ranges
5–12, rules-only ranges 1–3. Guardian's `WEBHOOK_AMBIGUITY` handling (25
transactions, seed 42): 0 recovered, 0 duplicate risk, 100%
`BLOCK_RECONCILE`, vs. naive's 68% recovery *and* 48% duplicate-charge
risk on the same 25 transactions. Full per-transaction and root-cause
segment data is in `experiments/results/`.

**All recovery figures above are SIMULATED/counterfactual — Day 8
synthetic assumptions, not observed Razorpay revenue.**

### Known limitations (Day 9)

- All outcome probabilities are still Day 8's unrecalibrated synthetic
  assumptions.
- Guardian trades some raw recovery (lower than naive/rules-only on
  `INFRASTRUCTURE`, zero on `OTP_TIMEOUT`/`USER_ABANDONMENT`) for zero
  duplicate-charge risk — a genuine, measured trade-off, not concealed.
- No statistical significance testing performed (explicitly Day 10 work).
- Day 10 will separately analyze and interpret these frozen results —
  not started.

## Day 10 — Frozen experiment analysis

Baseline before this pass: 182 passed, working tree clean at `de0dbb1`.
Analysis-only: reads the frozen Day 9 result artifacts, never reruns the
experiment, never touches ML/calibration/policy/simulator/dataset/Day 9
strategy or configuration code (verified via `git diff`).

- **`recovery_rate` explicitly defined**: count-based
  (`recovered_transaction_count / transactions_evaluated`), not
  amount-weighted — documented in `docs/architecture.md`.
- **Data integrity verified** (`src/analysis/integrity.py`) for all three
  seeds: action counts sum to 242, per-transaction amount bounds hold,
  root-cause sums reconcile to strategy totals, total recovered never
  exceeds total at risk. All checks passed.
- `src/analysis/`: `loader.py` (reads frozen JSON only), `segments.py`
  (root-cause / action-distribution aggregation), `statistics.py`
  (exact McNemar via `scipy.stats.binomtest`, Wilcoxon signed-rank via
  `scipy.stats.wilcoxon`).
- `experiments/run_day10_analysis.py`: orchestrates the above over the
  frozen seed 42/43/44 artifacts, writes `experiments/results/
  day10_analysis.json` and 7 plots (all gitignored, reproducible via the
  script). Added `scipy` to `requirements.txt` (now used directly).
- Test count: 182 → 192 passed (10 new, `tests/test_day10_analysis.py`,
  hand-built synthetic fixtures independent of the real frozen data).

### Major findings (see `docs/architecture.md`'s Day 10 section for full detail)

1. **Guardian did NOT achieve the highest raw simulated recovery.**
   Rules-only did (₹238,230.16 vs. Guardian's ₹193,316.24, seed 42). This
   is stated plainly — the claim "Guardian maximizes recovery" is false
   and is never made. Guardian's reproduced distinguishing property is
   **zero duplicate-charge-risk outcomes across all three seeds** (42,
   43, 44), vs. Naive's 5–12 and Rules-only's 1–3.
2. **Naive action-mismatch finding**: on the 99 `CARD_DECLINE`/
   `INSUFFICIENT_FUNDS` transactions (40.9% of the dataset), Naive
   recovers only ₹12,678.86 (9.09%) vs. Guardian/Rules-only's identical
   ₹131,400.38 (43.43%) — driven by `DEFER_RETRY` being a poor action for
   these classes under Day 8's frozen simulation assumptions
   (`DEFER_RETRY.default=0.15` vs. `CUSTOMER_RECOVERY.CARD_DECLINE=0.55`/
   `.INSUFFICIENT_FUNDS=0.45`), not by any safety exposure (0 duplicate
   risk here for all strategies). **Aggression ≠ effectiveness.**
3. **Two independent CRN validation signals** confirmed the shared
   environment/common-random-number architecture: identical actions on
   identical evidence produced byte-identical simulated recovery
   (`CARD_DECLINE`/`INSUFFICIENT_FUNDS`: Rules-only = Guardian exactly;
   `INFRASTRUCTURE`: Naive = Rules-only exactly).
4. **Paired statistical analysis** (seed 42, n=242, McNemar + Wilcoxon):
   Guardian vs. Naive — **not significant** (p=0.905/0.937); Guardian vs.
   Rules-only — **significant** (p=0.00049/0.00222), all 12 discordant
   pairs favoring Rules-only; Guardian vs. No Action — **significant**
   (p=1.7e-21/3.6e-13). The Guardian-vs-Rules-only discordant sample (12
   of 242) is explicitly reported as smaller than the full n, explained
   by 230 concordant rows (largely the CRN Signal 1 ties) — not treated
   as evidence the aggregate ₹ difference doesn't exist.
- Seed-level (n=3) results reported qualitatively only — no formal
  significance test performed, as instructed (n=3 is insufficient).

### Known limitations (Day 10)

- All findings are counterfactual/simulated (Day 8 synthetic
  assumptions) — never claimed as observed Razorpay revenue.
- Statistical significance (where found) is not equivalent to production
  validity.
- Guardian's lower raw recovery and Rules-only's higher raw recovery are
  reported as genuine findings, not smoothed over.
- No new model, policy, threshold, or strategy was introduced.

## Day 11 — Production-shaped Razorpay adapter

Baseline before this pass: 192 passed, working tree clean at `411bbd2`.
Not a live Razorpay integration — no API calls, no credentials, no
webhook-signature verification anywhere in this project.

- `src/ingestion/razorpay_adapter.py`:
  `razorpay_webhook_to_payment_event(webhook_payload, *,
  platform_health=None) -> PaymentEvent` — mirrors the existing
  `synthetic_to_payment_event` convention exactly. Pure, side-effect-free,
  no ML/policy/persistence/network code (verified by source inspection).
  Malformed input raises `AdapterValidationError`, never silently
  produces a corrupt event.
- **Every `PaymentEvent` field classified by source** before writing any
  code: payload-derivable (`transaction_id`, `amount`, `timestamp`,
  `payment_method`, `failure_code`, `retry_count`), derived from two
  payload timestamps (`webhook_delay_seconds` — calculated, never
  defaulted to zero), platform-wide aggregates requiring monitoring this
  project doesn't build (`gateway_error_rate_delta`,
  `merchant_failure_rate_delta`, `cross_merchant_failure_rate`,
  `incident_active`), and a third category — customer-history lookup
  (`customer_previous_successes/failures`, safely defaultable to 0/0,
  unlike the platform aggregates).
- **Option A selected** for the aggregate-field gap: `PlatformHealthContext`,
  an explicit optional companion-monitoring input, clearly separated from
  the payment payload — documented as assuming a monitoring service this
  project does not build. Omitting it yields documented neutral defaults,
  not a silent fabrication.
- No separate `status` field exists on `PaymentEvent` (verified directly
  from `src/domain/models.py`) — none was invented; Razorpay's
  status/error terminology maps into the existing `failure_code`
  mechanism only, via a small frozen table mapping unrecognized/absent
  reasons to the existing canonical `"unknown"` bucket (already one of
  the 12 frozen `FAILURE_CODE_CATEGORIES`, not a new value).
- `tests/fixtures/razorpay_payloads.py`: representative/production-shaped
  fixtures, explicitly labeled as such — not claimed as captured from
  live Razorpay traffic.
- 30 new tests: `tests/test_razorpay_adapter.py` (22 — valid payload,
  missing/invalid amount, invalid/inverted timestamps, unknown
  status/failure mapping, optional-field defaults, payment-method
  normalization, webhook-delay calculation, Option A threading, no
  persistence side effects) and `tests/test_razorpay_integration.py` (8 —
  full real, unmocked pipeline: adapter → features → calibrated model →
  policy → valid `PolicyDecision`; and the **synthetic/canonical
  convergence proof**: a real `WEBHOOK_AMBIGUITY` dataset row and a real
  `INFRASTRUCTURE` row, expressed as both a synthetic row and an
  equivalent Razorpay-shaped payload, produce identical
  `RootCausePrediction` (probability equal within `1e-9`) and identical
  `PolicyDecision.action` — with the Razorpay-sourced
  `WEBHOOK_AMBIGUITY` case confirmed `BLOCK_RECONCILE`, never
  `DEFER_RETRY`).
- Test count: 192 → 222 passed. Adapter + integration tests re-run as two
  fully separate `python3 -m pytest` processes — identical (`30 passed`
  both times). Day 7 (47), Day 9 (50), and Day 10 (10) regression suites
  all re-run and green.
- ML/feature/policy/simulator/dataset/Day 9/Day 10 all confirmed
  untouched via `git diff` against `411bbd2` (all empty).
  `FEATURE_COLUMNS` count (26) and hash unchanged; calibrated classifier
  still loads.
- No frontend, dashboard, `src/api/`, or Day 12 work started.

### Known limitations (Day 11)

- Representative/production-shaped fixtures only — not verified against
  live Razorpay production traffic.
- `INFRASTRUCTURE` classification for a real Razorpay-sourced event is
  honestly incomplete without a genuine platform-monitoring integration
  (Option A's companion input is assumed, not built).
- Webhook delay requires both a payment and a webhook-envelope timestamp;
  payloads lacking either are rejected, not defaulted.
- Convergence with synthetic data rounds webhook delay to whole seconds
  (Razorpay's real integer-second timestamp precision) — documented, not
  hidden.
- No live Razorpay integration, credentials, authentication, or webhook
  verification exists.

## Day 12 — Incident Scenario Replay

- **Status: COMPLETE.**
- Artifact: `experiments/results/day12_incident_demo.json`. Entry point:
  `experiments/run_incident_demo.py`. Tests: `tests/test_incident_demo.py`.
- Incident window (verified, not assumed): `2026-08-15T22:10:00` –
  `2026-08-15T22:40:00` inclusive, 110 transactions (matches
  `data/generate_data.py`'s existing injected burst exactly).
  `data/generate_data.py` and the dataset itself were NOT modified or
  regenerated.
- Metric type: **failure density** (events per 30 min), not failure
  rate — the dataset contains only failed-payment rows, no
  success/status column exists. Before 0.0, incident 110.0, after 1.5
  (per 30 min).
- Split membership of the 110 incident-window transactions: TRAIN 79
  (71.8%), VALIDATION 13 (11.8%), TEST 18 (16.4%). Majority-TRAIN
  disclosed explicitly — the full-window result is a replay-behavior
  demonstration, not an out-of-sample generalization claim; the 18-row
  held-out TEST subset is reported separately as the defensible view.
- Infrastructure classifier result: full-window 73/73 ground-truth
  INFRASTRUCTURE correctly predicted (precision/recall 1.0); held-out
  test subset 15/15 correctly predicted (precision/recall 1.0).
- Infrastructure policy result: 61 `DEFER_RETRY` / 12 `HUMAN_REVIEW`
  among the 73 ground-truth INFRASTRUCTURE cases, split exactly at the
  real `src/policy/rules.yaml` threshold (0.75) — not modified.
- Non-infrastructure diagnostic: all 37 non-INFRASTRUCTURE incident-window
  transactions correctly predicted as their own class; zero
  misclassified as INFRASTRUCTURE merely for occurring during the
  incident.
- **Safety result**: the single WEBHOOK_AMBIGUITY case in the window
  produced `BLOCK_RECONCILE`; zero `DEFER_RETRY`. Safety invariant held
  during the incident.
- Ground-truth leakage: `actual_root_cause` proven structurally
  incapable of reaching `PaymentEvent`/`build_features`/classifier/policy
  (no such field on `PaymentEvent`); direct leakage regression test
  passes.
- State isolation: reuses Day 9's `GuardianStrategy` mechanism exactly
  (`already_executed_actions=frozenset()`, the same
  `EXPERIMENT_EVALUATION_TIME` constant) — no new mechanism invented.
- Reproducibility: two separate `python3` processes running the script
  produced byte-identical `day12_incident_demo.json` output. No
  wall-clock run metadata is included in the artifact.
- Optional Day 8/9-reused recovery simulation implemented; all figures
  labeled SIMULATED/COUNTERFACTUAL, structurally separate from measured
  classifier/policy metrics, and does not touch any Day 9/10 result file.
- Test count: 222 → 242 passed (20 new Day 12 tests). Day 7 (54), Day 9
  (50), Day 10 (10), Day 11 (30) regression suites all re-run and green.
- Frozen firewall verified via `git diff 32a2e05` against
  `data/generate_data.py`, the dataset, `src/model`, `src/features`,
  `src/policy`, `src/recovery`, `experiments/day9_experiment_config.yaml`,
  `experiments/run_day9_experiment.py`, `experiments/run_day10_analysis.py`,
  all Day 9/10 result JSONs, and `src/ingestion/razorpay_adapter.py` — all
  empty.
- No frontend, dashboard, LLM layer, live Razorpay integration, or Day 13
  work started.

### Known limitations (Day 12)

- A majority of incident-window transactions are TRAIN-split — the
  full-window classifier result is a replay demonstration, not a
  generalization claim; the held-out TEST subset (18 rows) is small.
- All data is synthetic; no real Razorpay production traffic was used.
- No true failure rate is computable from this dataset (no
  successful-transaction rows) — failure density is reported instead.
- This is a historical replay, not a live incident detector or
  production monitoring capability.
- The incident scenario is a designed synthetic burst, not evidence
  about real Razorpay infrastructure incidents.
- Several per-class counts in the window are small (e.g. 1
  WEBHOOK_AMBIGUITY case, 3 USER_ABANDONMENT cases) and are reported as
  raw counts, not smoothed into misleadingly precise percentages.
- The optional recovery simulation is a counterfactual estimate, not
  observed recovered revenue.

## Day 13 — Grounded LLM Explanation Layer

- **Status: COMPLETE.**
- New package: `src/explain/` (`evidence.py`, `models.py`, `provider.py`,
  `redaction.py`, `service.py`). Tests: `tests/test_explain.py`.
- Pre-flight integrity check (mandatory per the Day 13 prompt): Day 12's
  15/15 held-out INFRASTRUCTURE result was reported but was **not**
  previously run through the project's own established >98%
  leakage-investigation trigger (applied at Day 4 to the four classes
  that hit 100% on the full 242-row test set) or cross-checked against
  Day 4's known full-test-set INFRASTRUCTURE recall (0.963). **CASE B**:
  Day 13 did not investigate or modify Day 12; the result is preserved
  as frozen historical evidence, and this gap is recorded honestly
  rather than papered over. No Day 13 test claims the 15/15 result is
  intrinsically valid.
- Architecture: `ExplanationEvidence.from_decision()` (built only from
  the real, already-computed `PaymentEvent`/`RootCausePrediction`/
  `PolicyDecision`) → `provider.generate(evidence)` (LLM or deterministic
  fallback) → `Explanation`. The orchestrator
  (`src.explain.service.explain_decision()`) reads only `summary`/
  `safety_note` from provider output; every decision field
  (`root_cause`, `confidence`, `action`, `reason`, `outcome_status`) is
  assigned directly from evidence, never from the provider — verified
  directly by a test using a provider that deliberately tries to forge
  a different action.
- Provider: `ClaudeExplanationProvider` (Anthropic Messages API, lazily
  imported, no API key required at import/construction time) plus a
  `DeterministicFallbackProvider` used whenever no provider is
  configured or on ANY provider failure. No API keys, network access, or
  credentials are required by the automated test suite — tests inject a
  duck-typed fake Anthropic client.
- Safety result: the real feature builder → real calibrated classifier →
  real Day 7 policy engine → explanation integration test confirms
  `WEBHOOK_AMBIGUITY → BLOCK_RECONCILE` is preserved through the
  explanation layer, including against a provider that deliberately
  tries to forge `DEFER_RETRY`, a raising provider, and a malformed-
  response provider. All 6 representative cases (CARD_DECLINE,
  INSUFFICIENT_FUNDS, INFRASTRUCTURE high/low confidence,
  WEBHOOK_AMBIGUITY, NO_ACTION) run through the real pipeline and
  confirm root cause/action/reason/probability are preserved exactly.
- Outcome provenance: `OBSERVED`/`SIMULATED`/`UNAVAILABLE` enforced by
  the evidence constructor itself (raises on an inconsistent
  status/outcome pairing) — simulated Day 8 outcomes are always
  described as "Simulation estimates...", never as observed recovered
  revenue.
- Prompt-injection defense: `merchant_id` (the only realistic
  free-text-shaped `PaymentEvent` field) constructed with
  instruction-like text; the decision path is unaffected. Secret/PII
  redaction: explicit field allowlist plus a credential-pattern refusal
  check at the provider boundary.
- Test count: 242 → 283 passed (41 new Day 13 tests). Day 7 (54), Day 9
  (50), Day 10 (10), Day 11 (30), Day 12 (20) regression suites all
  re-run and green. Day 12 incident demo re-run directly and confirmed
  unchanged (110 transactions, same split, safety PASS).
- Frozen firewall verified via `git diff f430401` against `src/model`,
  `src/features`, `src/policy`, `src/recovery`, `data`, `experiments`,
  `src/ingestion/razorpay_adapter.py`, `experiments/run_incident_demo.py`,
  and `tests/test_incident_demo.py` — all empty.
- No frontend, dashboard, live Razorpay integration, model tuning, or
  Day 14 work started.

### Known limitations (Day 13)

- LLM-backed prose is not claimed to be byte-identical across calls;
  only the deterministic fallback and structured decision fields are
  tested for exact reproducibility.
- The Claude system prompt is defense in depth, not the primary safety
  guarantee — the actual guarantee is structural (the orchestrator never
  reads decision fields from provider output).
- `merchant_id` is the only realistic prompt-injection vector currently
  available on `PaymentEvent`; no free-text customer-facing field exists
  in this project.
- No live Razorpay integration, credentials, or network calls exist
  anywhere in this layer.
- Explanation prose quality has not been evaluated by a human judge
  beyond spot-checking; only grounding/safety properties are tested.
- Day 12's 15/15 held-out INFRASTRUCTURE result remains un-investigated
  for leakage/generalization plausibility (see pre-flight check above) —
  carried forward as an open gap, not resolved by Day 13.

## Day 14 — Final Productization + Judge-Facing Evidence

- **Status: COMPLETE.**
- No ML/policy/simulator/experiment/adapter/incident-methodology/
  explanation-decision-authority change of any kind — Day 14 is a
  productization day only.
- New: `experiments/run_judge_demo.py` — three fixed, deterministic
  scenarios (`webhook_ambiguity`, `infrastructure_high_confidence`,
  `infrastructure_low_confidence`), each run through the real, unmodified
  `run_pipeline()` against an isolated in-memory SQLite connection (no
  writes to the real `recovery_guardian.db`), then through the real Day
  13 `explain_decision()`. `tests/test_judge_demo.py` (26 tests).
- README.md rewritten from the Day 1 stub into the full judge-facing
  document it always said would land on Day 14: problem/solution,
  the `WEBHOOK_AMBIGUITY -> BLOCK_RECONCILE` safety invariant, exact Day
  9/10 evidence (Guardian correctly NOT described as maximizing
  recovery), the Razorpay integration boundary, Day 12 incident replay
  with its disclosed limitation, the Day 13 explanation layer, an
  architecture diagram matching only components that actually exist, a
  verified reproduction section (every command actually re-run today),
  and 18 judge-facing questions answered from actual repository
  behavior.
- Documentation-consistency audit: searched for overclaiming patterns
  ("highest recovery", "100% infrastructure accuracy", "live Razorpay",
  "guaranteed recovery", etc.) across `docs/architecture.md`/
  `PROGRESS.md`. Every existing match was already a negated, honest
  statement — no correction was required.
- Reproducibility: `experiments/run_judge_demo.py` run as two separate
  processes, byte-identical console and JSON output (no wall-clock or
  random-identifier fields are included at all). `run_incident_demo.py`
  (Day 12) re-run directly and confirmed unchanged. `run_day9_experiment.py
  --seed 42` and `run_day10_analysis.py` (both frozen, unmodified) re-run
  directly to verify the README's cited numbers exactly, rather than
  trusting previously-recorded values.
- No frontend, dashboard, Docker, Kubernetes, or blockchain/Alchemy work
  introduced — none existed before Day 14 and the master prompt
  explicitly places all of them out of scope; a minimal dashboard remains
  only a possible Day 15 stretch item.
- Test count: 283 → 309 passed (26 new Day 14 tests). Day 7 (54), Day 9
  (50), Day 10 (10), Day 11 (30), Day 12 (20), Day 13 (41) regression
  suites all re-run and green.
- Frozen firewall verified via `git diff d778097` against `src/model`,
  `src/features`, `src/policy`, `src/recovery`, `data`,
  `experiments/run_day9_experiment.py`,
  `experiments/day9_experiment_config.yaml`, `src/experiment`,
  `src/ingestion/razorpay_adapter.py`, `src/explain` (the confirmed
  actual Day 13 explanation-layer path), `experiments/run_incident_demo.py`,
  and `tests/test_incident_demo.py` — all empty.
- Secret scan: clean (no real credentials; `.env.example` already
  contained only empty placeholders and an explicit `LLM_ENABLED=false`
  kill switch, unchanged).

### Known limitations (Day 14)

- The judge demo covers three fixed, hand-selected representative
  scenarios, not an exhaustive sweep of the dataset.
- LLM-backed demo output is not claimed byte-identical — only the
  default deterministic-fallback path is tested and documented as
  reproducible.
- "No frontend" is a deliberate Day 14 scope decision, not a claim that
  one would be undesirable later.
- Every Day 9/10/12/13 limitation already on record remains unchanged
  and is carried forward, not re-litigated — including Day 12's
  un-investigated 15/15 held-out INFRASTRUCTURE result.

## Day 15 — Frontend Product Surface (Milestones 1-3)

- **Status: COMPLETE (Milestones 1-3).** Branch:
  `frontend/day15-productization`, off the `submission-v1` (`7db4b02`)
  safety checkpoint. `main` and `submission-v1` both untouched
  throughout.
- Stack: React + TypeScript + Vite + Tailwind CSS + Vitest/React Testing
  Library. No router, no chart library, no animation library, no icon
  library, no state-management library — hand-rolled primitives
  throughout.
- Five pages: Overview (M1), Safety, Decision Pipeline (M2),
  Explainability, Incident Replay (M3). Every other planned nav item
  remains a disabled, clearly-marked "Soon" placeholder.
- Data plumbing: `scripts/generate_frontend_snapshot.py` — the single,
  read-only, always-extended-never-duplicated boundary between the
  frozen `experiments/results/day{9,12,14}_*.json` artifacts and
  `frontend/src/data/snapshot.ts` (typed, committed). Fails loudly on
  missing/malformed/wrong-type source data; verified deterministic
  (byte-identical across two runs except the documented `generatedAt`
  field).
- Shared components: `PipelineDiagram` (the pipeline visual, one
  implementation, used by both the Overview preview and the interactive
  Decision Pipeline/Explainability evidence chain), `ScenarioSelector`,
  `NodeDetailPanel`, `ProvenanceBadge`.
- Safety demonstrated end to end in the frontend: `WEBHOOK_AMBIGUITY →
  BLOCK_RECONCILE` (ceremonial lock+glow), `INFRASTRUCTURE` high-
  confidence `→ DEFER_RETRY` and low-confidence `→ HUMAN_REVIEW` (quiet
  settle, distinct accent colors), all three verified against the raw
  Day 14 artifact before any UI code was written. Explainability's
  action-before/action-after check proves the explanation layer cannot
  alter the decision. Incident Replay explicitly labeled "Historical
  synthetic replay," never live monitoring; failure density (not rate)
  used and explained inline; the Day 12 15/15 held-out INFRASTRUCTURE
  limitation disclosed inline; the Day 9 (25 transactions) vs. Day 12 (1
  transaction) `WEBHOOK_AMBIGUITY` populations kept explicitly separate
  and tested as such.
- Real bugs found and fixed during implementation: a WCAG AA contrast
  failure on the `text-muted` token (M1, found by axe); a heading-order
  violation from `NodeDetailPanel`'s `<h3>` (M2, found by axe); a
  tablet-width horizontal-overflow bug in the shared pipeline component
  (M2, found by manual responsive QA); a node-click animation-reset bug
  caused by an unmemoized node array (M2, found by manual QA); a missing
  literal "failure density" label caught by Incident Replay's own tests
  (M3).
- Test count: frontend 0 → 21 (M1) → 41 (M2) → 66 (M3). Backend
  unchanged at 309 throughout all three milestones.
- Accessibility: axe-core 0 violations (all severities) across every
  page and interactive state, verified after each milestone. Keyboard
  navigation, focus states, and `prefers-reduced-motion` verified via
  automated real-browser checks.
- Frozen firewall (`src/model`, `src/features`, `src/policy`,
  `src/recovery`, `data`, `experiments`, `src/ingestion`, `src/explain`)
  verified empty after every milestone.
- Secret scan clean throughout; no credentials added; no live network
  dependency in the built app.

### Known limitations (Day 15)

- The frontend covers exactly the three Day 14 judge-demo scenarios —
  no arbitrary transaction search or live inference.
- LLM-backed explanation prose is not claimed byte-identical; the source
  artifact doesn't record which provider produced a given scenario's
  prose, and the frontend discloses this rather than guessing.
- Headless QA (axe, screenshots, keyboard/reduced-motion) used a
  temporary, non-committed browser-automation install — not part of a
  CI pipeline.
- Milestones 5+ (Transactions, Architecture pages; any
  Docker/Kubernetes/blockchain/live-Razorpay work) are explicitly out of
  scope and were not started.
- Every Day 9-14 limitation already on record remains unchanged and is
  carried forward, not re-litigated.

## Day 15 Milestone 4 — Recovery Analysis

- **Status: COMPLETE.**
- Data-granularity audit performed before any visualization was
  designed: per-strategy aggregate AVAILABLE, per-strategy×root-cause
  AVAILABLE, per-seed×strategy AVAILABLE (full recovery figures, not
  just duplicate-risk counts — verified across all 3 seed artifacts
  before use). A fourth artifact,
  `experiments/results/day10_analysis.json`, was wired into
  `scripts/generate_frontend_snapshot.py` (extended, not duplicated) for
  the first time.
- New page: Recovery Analysis (nav item "Recovery"). Hero → Guardian's
  zero duplicate-charge-risk KPI (reused `SafetyKpi`, never a
  recovery-amount headline) → hand-built SVG Recovery-vs-Safety chart
  (one aggregate point per strategy, no chart library added) with a full
  accessible data table → strategy comparison in **experiment order**
  (Naive Retry, Rules-only, Guardian, No Action — never
  Guardian-first) → evidence-backed interpretation → Day 9
  `WEBHOOK_AMBIGUITY` deep dive (25 transactions, explicitly labeled
  "Day 9 test-set safety analysis," explicitly distinguished from Day
  12's 1-transaction incident-window population) → root-cause × strategy
  matrix → full 3-seed × 4-strategy sensitivity table (shown in full
  because genuinely, fully available) → provenance/limitations.
- Content integrity: every headline number (₹205,427.28 / ₹238,230.16 /
  ₹193,316.24 / ₹0.00; 29.75% / 33.88% / 28.93% / 0.00%; duplicate risk
  12/3/0/0; Guardian dup-risk 0 across seeds 42/43/44; Day 9
  `WEBHOOK_AMBIGUITY`=25 vs Day 12=1; INFRASTRUCTURE 55 txns, Guardian 43
  DEFER_RETRY/12 HUMAN_REVIEW at the real 0.75 threshold; CARD_DECLINE +
  INSUFFICIENT_FUNDS = 99/242 = 40.9%) re-verified against the live
  snapshot immediately before final QA — zero discrepancies found.
- Real bugs found and fixed: a landmark/ID-duplication axe violation
  (redundant wrapping section around a component that already renders
  its own); a genuine mobile horizontal-overflow bug in the shared
  `SafetyKpi` component (present since Day 15 Milestone 1, affecting
  Overview/Safety/Recovery alike — fixed with one `overflow-hidden`); a
  transient axe color-contrast false-positive during a CSS transition
  (investigated and confirmed non-persistent, not dismissed
  unverified).
- Test count: frontend 66 → 84 (11 test files). Backend unchanged at
  309.
- Accessibility: axe-core 0 violations (all severities) across all six
  pages, re-verified after the SafetyKpi fix.
- Frozen firewall (`src/model`, `src/features`, `src/policy`,
  `src/recovery`, `data`, `experiments`, `src/ingestion`, `src/explain`)
  verified empty against the Milestone 3 baseline (`d78fce0`).
- Secret scan clean; no credentials added.

### Known limitations (Day 15 Milestone 4)

- Seed sensitivity (n=3) is qualitative only — no confidence interval or
  significance test is computed or implied.
- The Day 10 McNemar comparison shown describes transaction-level paired
  outcomes under simulation, not production effectiveness.
- Headless QA used a temporary, non-committed browser-automation
  install — not part of a CI pipeline.
- Every Day 9-14 limitation already on record remains unchanged and is
  carried forward, not re-litigated.

## Day 15 Final Productization — Reproducibility Fix (data/synthetic_events.csv)

- **Finding**: the Day 15 pre-merge branch dry run (a genuinely fresh
  clone, never before performed) ran `make data` per the README's own
  reproduction instructions and broke 60 backend tests. Root cause:
  `data/generate_data.py`'s `transaction_id` suffix uses `uuid.uuid4()`,
  which is **not** determined by `--seed` — every field except that
  suffix reproduces identically given seed 42, but the suffix itself is
  fresh-random on every run. `data/synthetic_events.csv` was gitignored
  the entire project (Day 1-14), so no fresh clone could ever reproduce
  the exact transaction IDs the Day 11-15 test/demo/frontend layer
  hardcodes (e.g. `txn_000536_9f0ef7`, the primary `WEBHOOK_AMBIGUITY`
  scenario).
- **Fix**: `data/synthetic_events.csv` is now a tracked, committed file
  (removed from `.gitignore`) — the exact realization already in use
  throughout Days 1-15, unchanged in content. `data/generate_data.py`
  itself was **not modified** — the frozen generation code is untouched;
  only the already-generated output's git-tracking status changed.
  Verified: full backend suite (309) still passes; the dataset's content
  is byte-identical to what every prior day's artifact/snapshot was
  already built from.
- This does not change any measured result, any frozen model/policy
  behavior, or any previously-reported number — it only makes the
  existing, unchanged dataset actually reproducible from a fresh clone,
  as the README already claimed it was.
- **Second finding, same dry run**: `tests/test_incident_demo.py::
  test_output_artifact_file_written_by_running_the_script` asserted
  `experiments/results/day12_incident_demo.json` already existed,
  implicitly relying on an earlier interactive run having left it on
  disk — invisible throughout local development (the file was always
  already present from many prior manual runs) but failing on a
  genuinely fresh clone/checkout, since that test runs before the one
  other test in the same file that actually invokes the script.
  **Fix**: the test now writes the artifact itself (mirroring
  `main()`'s exact write logic) before asserting on it — self-contained,
  no assertion weakened, no frozen production code touched (`tests/` is
  not part of the frozen firewall). Verified: 309/309 backend tests pass
  from a genuinely fresh clone after this fix.

## Day 15 Final Polish — Architecture, Transaction Explorer, Accessibility

Branch `frontend/final-polish`, off `main` at `3707ce2`. Full details in
`docs/architecture.md`'s "Day 15 Final Polish" section. Summary:

- Data-availability audit found genuine transaction-level records in two
  places: Day 9's per-transaction file (968 = 242 transactions × 4
  strategies, cardinality trap avoided) and Day 12's `transactions`
  array (110, one per transaction, richer fields). Built the Transaction
  Explorer on the Day 12 population — search/filter/sort plus a detail
  panel distinguishing "Predicted root cause (model)" from "Known root
  cause (synthetic label)" (ground-truth firewall).
- Added an Architecture page: the same shared `PipelineDiagram`/node
  labels used elsewhere, the explanation layer rendered as a visually
  separate downstream/optional callout (never a node between Policy
  Engine and Action), an explicit safety-boundary statement, a
  determinism statement, and an honest scope disclosure.
- Full-navigation axe pass (3 viewports × 8 pages) found and fixed one
  real issue — three data-table scrollable containers not keyboard-
  focusable below 768px (`tabIndex`/`role="region"` added to all three);
  re-confirmed the Milestone 4 transient color-contrast finding on
  Decision Pipeline is still transient, not a regression.
- Frontend test suite: 84 → 100 tests (13 files). Backend: unchanged,
  309 passed. Frozen firewall diff against `3707ce2`: empty throughout.
- Bundle size grew ~28.6% raw / ~14.6% gzip on the JS bundle, entirely
  attributable to the two new pages and their components — no new
  runtime dependency.
