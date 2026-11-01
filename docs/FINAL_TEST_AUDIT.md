# Final test usage audit

Date: 2026-11-02 (Asia/Calcutta). This is one locked final assessment on synthetic data;
both models remain **PROVISIONAL / syllabus UNVERIFIED**, with no coverage claim.

## Frozen selection, before test access

The saved validation CSVs were read without opening test.csv. Classification ranking:
higher macro-F1; exact ties use higher minimum per-class recall, higher mean recall,
lower saved single-row latency, then name. This supersedes the earlier near-best
stability-band development rule. No tie occurred: KNN had the highest saved macro-F1.
Regression ranks the two fitted candidates by lower MAE, then RMSE; persistence is a
reference rather than a fitted pipeline candidate. No test score was available to rank.

- Classifier: **KNN**, original validation macro-F1 0.537601, accuracy 70.49%.
- Regressor: **polynomial_degree2**, original validation MAE 6.139516s, RMSE 8.390615s.
- Authoritative selection file: `C:\Users\Hrishit Vats\OneDrive\Desktop\raah\artifacts\final\selection_manifest.json`. SHA-256: `e3605e36e02326835d0e762e6a0ddb5cba435968523c74988bd4f6516155f85c`. It is exclusively created, fsynced and hashed in the event ledger before test access; it was not subsequently edited.

The manifest freezes parameters, feature lists, source/validation-comparison hashes,
library versions, split membership and refit/test policy. Factories are checked against
the saved validation settings. Evaluator code is hashed too. No model/parameter choice
changed after the test result. Only the selected KNN and degree-2 polynomial linear
pipeline were fitted/evaluated; no additional candidate was scored on test.

## Refit policy and artifacts

As documented in the frozen manifest **before test opening**, both entire pipelines were
refitted from scratch on **train+validation: 24 run groups / 11,616 rows**. That includes
imputers, scalers, one-hot encoding, and numeric degree-2 expansion for regression.
The six test run groups are disjoint and contribute no fitted state. Both saved scalers
report n_samples_seen_=11,616. Original validation scores belong to the earlier train-only
fits and are not presented as performance estimates of the refitted models.

Saved before opening test: classification_pipeline.joblib, regression_pipeline.joblib
and feature_schema.json. The schema retains canonical raw/expanded feature order,
missing/unseen-category behavior, target definitions and pipeline hashes. Serialized
pipelines were reloaded and checked using development rows **before test access**.
No test prediction was repeated for serialization or latency checks.

## Ordered event ledger

The real evaluation's events (UTC plus Asia/Calcutta display) are:

| Event | UTC | Asia/Calcutta |
| --- | --- | --- |
| SELECTION_FROZEN | 2026-11-01T21:30:22.697640+00:00 | 2026-11-02T03:00:22.697640+05:30 |
| REFIT_COMPLETE_BEFORE_TEST | 2026-11-01T21:30:35.781987+00:00 | 2026-11-02T03:00:35.781987+05:30 |
| TEST_OPEN_AUTHORIZED_AFTER_FROZEN_SELECTION | 2026-11-01T21:30:35.784985+00:00 | 2026-11-02T03:00:35.784985+05:30 |
| FINAL_TEST_COMPLETE | 2026-11-01T21:30:36.773396+00:00 | 2026-11-02T03:00:36.773396+05:30 |

`test_access_claim.json` is COMPLETE and records:

- **1 original test.csv read**, then parsing from those in-memory bytes.
- **1 classification batch prediction** and **1 regression batch prediction** over all
  2,904 rows in six test runs. No test fitting, hyperparameter search or reselection.
- Prediction arrays and test_predictions.csv cache the outcome. Confusion/per-run
  summaries and all three plots use these cached results, not additional model calls.
- A copied test_snapshot.csv preserves the one-read evidence/recovery input. Its hash
  matches the frozen test input hash. This audit does not reopen the original test file.
- Complete repeat calls return hash-verified saved metrics only. Concurrent reservations
  are exclusive. An incomplete/failed claimed run is blocked, never silently retried.

These are local workflow safeguards, not protection against a person manually deleting
records or using other code. Preserve the claim/ledger; do not reset them or use another
output directory to repeat this assessment. This test is now consumed. Future tuning
requires a genuinely new independent holdout for a fresh final claim.

## Actual final test results

Classifier KNN: accuracy **68.42%**, macro-F1 **0.503522**.

| Class | Precision | Recall | F1 | Actual support |
| --- | ---: | ---: | ---: | ---: |
| LOW | 0.817471 | 0.760922 | 0.788184 | 1648 |
| MEDIUM | 0.186047 | 0.055363 | 0.085333 | 289 |
| HIGH | 0.558411 | 0.741468 | 0.637050 | 967 |

Regressor polynomial_degree2: MAE **5.973365s**, RMSE **8.190121s**, R2 **0.985745**. Negative predictions: **441 / 2904** (15.19%), left unclipped under the frozen policy.

The confusion plot shows only 16/289 MEDIUM examples recognized (5.54% recall);
206 are predicted HIGH and 67 LOW. The classifier is not a reliable three-class control
input. High regression R2 reflects a short-horizon synthetic queue-wait task and temporal
persistence, not real-road accuracy or control benefit. Negative waiting-time predictions
are nonphysical. No adjustment, clipping or retraining was done to improve these test scores.

All three final-test plots were visually inspected. Residuals are actual minus predicted;
remaining tails and low-wait errors are visible. Per-class and per-run metrics, confusion
counts and cached predictions are saved. Scores are descriptive across only six independent
runs, with correlated within-run windows; no confidence/stability/real-world claim is made.

## Prior exposure disclosed

The underlying public synthetic dataset was previously generated and globally checked
for schema, duplicates, nulls and provenance. Earlier splitting/preprocessing code loaded
and transform-checked test features, with preprocessing fitted only on train and **no
supervised test score or test-based model selection**. Thus this is not a claim that
nobody had ever opened these bytes. Earlier classifier/regressor validation experiments
explicitly excluded test, and the protected final test groups were outside prior training
feature EDA. Two validation groups had prior EDA exposure; they are now intentionally
part of the refit development set. Selection/audit history is retained, not rewritten.

Cluster IDs and feature-derived congestion labels are not independent empirical truth.
Classification excludes direct congestion-rule inputs but can exploit correlated flow/
phase/clock proxies. Regression uses current simulator-truth counts/queues/waits and a
future simulation-state target at exactly +60 seconds; it is not GPS-only prediction.
All data is synthetic; no private/live GPS or physical traffic control is involved.

## Executed commands and protocol tests

Tests used only separate temporary, generated unit fixtures, not Raah's real held-out CSV.
They ran before the real freeze/evaluate commands:

```powershell
$env:TEMP = (Resolve-Path work/tmp).Path
$env:TMP = $env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_final_evaluation.py -q
.\ml-service\.venv\Scripts\python.exe ml-service/training/final_evaluation.py --freeze-only
.\ml-service\.venv\Scripts\python.exe ml-service/training/final_evaluation.py --evaluate
```

```text
.........                                                                [100%]
9 passed in 4.78s
```

All **9 protocol tests pass**: selection ranking/ties, freeze without test access,
immutable selection, exactly one read and prediction batches, cached replay without
rereading, concurrent reservation protection, changed-file detection, before-test retry
and after-claim fail-closed behavior, train+validation fitted row counts, feature schema,
serialized pipelines and final-test plots. One test initially rewrote an already-perfect
toy score to the same value; it was corrected to make an actual mutation. No real-test
retry was required. No broad suite that could reopen the original held-out CSV was run.

Final audit inspection loaded only saved metadata, trained artifacts and caches. Both
pipeline hashes, selection/metrics hashes, frozen evaluator-code hash and PNG signatures
match. No test prediction/model call was made for this audit, and original test.csv was
not reopened. Source/selection manifests are preserved.

Changes are saved locally, uncommitted and not pushed. No assistant contributor or
co-author attribution is added. All final artifacts are under artifacts/final/; raw
sources are not modified.
