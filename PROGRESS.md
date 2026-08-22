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

## Known limitations (accurate as of this pass)

- Calibration is **not** implemented (Day 6).
- The policy engine is **still** the Day 3 placeholder — no
  differentiated `root_cause → action` mapping exists (Day 7).
- No counterfactual simulator or three-way experiment exists (Day 8–10).
- No Razorpay integration exists (Day 11).
- No frontend/dashboard exists (Day 13).
- The pinned `requirements.txt` vs. Python 3.14 install mismatch (flagged
  during the earlier security audit) remains unresolved.
- `RootCauseLogRegClassifier` reloads and revalidates the artifact from
  disk on every `run_pipeline()` call — fine at this scale, unaddressed
  because it isn't a correctness issue.
