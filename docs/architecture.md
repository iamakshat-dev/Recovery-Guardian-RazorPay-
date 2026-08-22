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
