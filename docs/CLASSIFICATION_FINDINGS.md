# Provisional classifier findings

Official syllabus evidence is absent. All six user-named candidates are
**PROVISIONAL / UNVERIFIED**; **no official coverage is asserted**. No additional
classifiers, model families, grid search, or validation-driven parameter changes are added.

## Split, target and leakage boundary

Use the existing seed-57 18/6/6 run split. Fit 8,712 training rows from 18 whole runs and
evaluate 2,904 validation rows from six disjoint runs. Only train.csv, validation.csv and
the split manifest are opened. test.csv is not opened, transformed, scored or used in
selection. Test IDs from the manifest are used solely for disjointness checks.

Stored low/medium/high classes are mapped to LOW/MEDIUM/HIGH, not regenerated. X is only
incoming_vehicles, outgoing_vehicles, current_phase, seconds_in_phase, time_of_day. All
identifiers, both targets, direct congestion-rule inputs and GPS sample count are excluded.
The label is still a synthetic rule-derived index. Flow/phase/time can indirectly track
its defining inputs and generator schedule, so these scores are not independent empirical
congestion discovery or evidence of real-world/GPS-only accuracy.

Imputers/encoders and optional numeric scaling are inside each fitted pipeline, trained
only on train. LogisticRegression/KNN/SVC use standard-scaled numeric features; the trees
and GaussianNB do not. Phase one-hot columns are unscaled and unknown categories are
ignored. GaussianNB applies a Gaussian/conditional-independence approximation to data
including one-hot phase fields; this assumption is imperfect and no calibration is claimed.

## Fixed candidate settings and selection

LogisticRegression: C=1, max_iter=2000, lbfgs. KNN: k=15, distance weighting, Euclidean.
GaussianNB: var_smoothing=1e-9. SVC: RBF, C=1, gamma=scale, class prediction only (no calibration).
Decision tree: depth<=8, leaf>=20. Random forest: 200 trees, depth<=12, leaf>=5,
max_features=sqrt. Random-state-capable fits use 57; KNN/forest use n_jobs=1.
These are predeclared single-fit settings, not a claim that parameters are optimal.

Selection rule fixed before training: among candidates within **0.02 absolute global
macro-F1** of the best, minimize per-run macro-F1 standard deviation; tie-break by higher
worst-run F1, then higher global F1, then name. No latency or test score selects a winner.
The selected artifact is the already train-fitted pipeline, not a train+validation refit.

Global macro-F1 always averages LOW/MEDIUM/HIGH, zero_division=0. Per-run stability uses
the union of actual/predicted classes present in that run so a perfectly predicted
single-class run does not score only 1/3. Hallucinated absent classes are included and
penalized. Fixed-three-class per-run F1 is also saved. Different class mixes affect this
stability statistic; six runs are few, and this is not random-seed robustness or a CI.

## Validation comparison

| Candidate | Accuracy | Macro-F1 | Per-run F1 std | Worst-run F1 | Fit s | Batch median ms | Amortized us/row | Single-row median ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LogisticRegression | 0.7001 | 0.4893 | 0.0659 | 0.2973 | 0.0662 | 5.289 | 1.821 | 3.412 |
| KNN | 0.7049 | 0.5376 | 0.0679 | 0.3141 | 0.0287 | 27.332 | 9.412 | 3.215 |
| GaussianNB | 0.6622 | 0.4729 | 0.0894 | 0.2693 | 0.0177 | 5.991 | 2.063 | 3.093 |
| SVC | 0.7304 | 0.5103 | 0.0744 | 0.3104 | 1.3976 | 627.937 | 216.232 | 3.268 |
| DecisionTreeClassifier | 0.7245 | 0.5090 | 0.0667 | 0.3226 | 0.0373 | 4.594 | 1.582 | 2.865 |
| RandomForestClassifier | 0.7297 | 0.5266 | 0.0725 | 0.3267 | 0.6509 | 43.993 | 15.149 | 8.385 |

Selected for further review: **KNN**, still PROVISIONAL_UNVERIFIED. Eligible near-best candidates: KNN, RandomForestClassifier. This is a validation-based development choice, not a test-validated deployment recommendation.

Reference only (not another fitted candidate): always predicting training-majority LOW gives validation accuracy 0.4094 and macro-F1 0.1937.

### Class counts

| Split | LOW | MEDIUM | HIGH |
| --- | ---: | ---: | ---: |
| train | 4148 | 935 | 3629 |
| validation | 1189 | 267 | 1448 |

Per-class precision, recall, F1, support and predicted counts are in per_class_metrics.csv.
Confusion CSVs/PNGs are counts with **rows actual, columns predicted**, in LOW/MEDIUM/HIGH
order. Zero prediction/actual denominators use zero with support/counts disclosed.
Accuracy alone can hide the minority MEDIUM class; inspect its recall and per-run scores.

Latency includes the full preprocessing+predict path, not file loading. It uses an
excluded warmup, five full validation batches and twenty single-row calls by default.
Batch p95 is an empirical quantile of only five calls, not a service-level guarantee.
Amortized batch time per row is not single-request latency. Machine load and native
threading affect timings; n_jobs=1 does not universally fix BLAS thread count.

## Limits and reproducibility

All data is synthetic; no private/live GPS or physical signals are involved. Shared
point-queue assumptions, aligned run clocks and correlated windows limit generalization.
All approaches/windows stay in their run group. Two validation runs were explored in
prior EDA, as disclosed by the leakage audit. Test remains reserved. No claims of
controller benefits, calibrated probabilities, real-road performance or syllabus coverage
are made. Candidate selection itself uses validation, so its score is not an unbiased
final estimate. Future tuning must use grouped training folds with fresh full pipelines.

Artifacts: `C:\Users\Hrishit Vats\OneDrive\Desktop\raah\artifacts\classification` includes model_comparison.csv, per_class_metrics.csv, per_run_metrics.csv, class_counts.csv, validation_predictions.csv, six confusion CSVs/PNGs, fitted pipelines, selected_classifier.joblib, selected_candidate.json and experiment_manifest.json. Model reloads reproduce validation predictions and input hashes are unchanged.

Reproduce: `./ml-service/.venv/Scripts/python.exe ml-service/training/train_classification.py`.

## Selection limitations and artifact inspection

Selected KNN: pooled macro-F1 0.537601, accuracy 70.49%, per-run F1 mean 0.427738, population std 0.067914, worst-run F1 0.314065. The eligible forest has std 0.072466; this small descriptive difference across six runs is not evidence of statistical superiority. Pooled F1 is not the average of per-run F1 because class mixes differ.

**Major weakness: MEDIUM recall is 8.61% (23/267 rows), precision 19.33%.** The confusion matrix shows 80 MEDIUM rows sent to LOW and 164 to HIGH. This candidate is not a reliable three-way congestion classifier yet and must not be treated as control-ready. LogisticRegression and SVC predict no MEDIUM rows at these fixed settings. No class weighting, resampling or parameter change was introduced after seeing validation scores.

Selected end-to-end single-row median latency: 3.215 ms; validation-batch median 27.332 ms. Timing is environment-specific, not a network/API or production SLA.

All six confusion PNGs have valid signatures; candidate/forest/logistic plots were
visually inspected, with actual/predicted axes and all counts checked against CSVs.
An initial UTF-8 title issue was repaired with ASCII titles and readable count boxes.
All six saved pipelines reload to the same validation predictions. All fit-warning
fields are empty. Source-code hash matches the final script; train/validation input
hashes remain unchanged. Only the exact six named candidates were trained; none has
official coverage asserted.

The first fitted-state assertion detected KNN's mutable distance-query counter rather
than learned data. Diagnostic comparison confirmed tree data/indices/nodes/bounds and
all preprocessing were unchanged. The guard now normalizes only query bookkeeping;
regression tests prove it detects actual KNN training-array and forest-tree mutations.
Explicit SVC probability=False caused a library deprecation warning; omitting that
argument retains default class prediction without adding calibration or another method.

## Executed tests

```powershell
$env:TEMP = (Resolve-Path work/tmp).Path
$env:TMP = $env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_train_classification.py tests/test_train_regression.py -q
```

```text
..............................................                           [100%]
46 passed in 12.76s
```

All **46 targeted tests pass**: 23 classifier tests plus 23 regression tests. They verify
exact candidate types/scaling/seed, uppercase label mapping, all-class and present-label
F1, zero denominators/confusion orientation, predeclared stable selection, train-only
transform/estimator fits, future-target exclusion, unseen/missing inputs, state guards,
latency consistency, artifact reload, input contract rejection and no-test-file access.
The integration experiments run in directories containing only train.csv, validation.csv
and the manifest, with no test.csv. Additional read guards would fail on a test-file open.
A test-only missing joblib import was corrected; final tests have no errors or warnings.
No broader suite that opens the held-out data was executed for this experiment.

Changes remain local, uncommitted and not pushed. No assistant contributor or co-author
attribution was added. Fitted artifacts remain excluded by the existing ignore rules.
