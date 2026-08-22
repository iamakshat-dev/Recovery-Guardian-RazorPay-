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
