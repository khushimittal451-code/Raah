# Provisional regression findings

Official syllabus evidence has not been supplied. LinearRegression and degree-2
PolynomialFeatures + LinearRegression are **PROVISIONAL / UNVERIFIED**, explicitly named
by the user. No other regressors or complete-coverage/compliance claims are added.
The last-observed-wait reference is not a trained model.

## Objective and fit boundary

Predict the same virtual approach's mean queue-membership wait at exactly t+60 seconds
from the eleven approved current-time fields. Audited labels come from later simulation
states; they are not generated from current wait at training time. The persistence
reference predicts current mean_wait_seconds without a fitted parameter. Counts/queues/
waits are simulator truth, not GPS-only measurements. No real private GPS is used.

Fit on 8,712 rows from 18 runs; evaluate on 2,904 validation rows from six disjoint runs.
Only train.csv, validation.csv and the split manifest are opened for this experiment.
The manifest's future-label audit and unchanged input hashes are checked. test.csv is
never opened, hashed, transformed, predicted or scored. Test group IDs from the manifest
are read only to guard group overlap. No estimator or hyperparameter is selected/tuned
after seeing validation results. All current feature selection precedes preprocessing.

Numeric imputation, polynomial expansion, scaling and phase encoding are inside each
estimator pipeline and fit on train only. Polynomial expansion is limited to the ten
numeric inputs (65 outputs); phase one-hot columns are not multiplied. Total transformed
widths are 16 for linear and 71 for polynomial. StandardScaler follows imputation/expansion
on numeric fields only. Unknown phases do not change feature width. For later grouped
cross-validation, clone the entire unfitted model pipeline within each training fold.

## Validation comparison (raw predictions, seconds)

| Method | Status | MAE (s) | RMSE (s) | R2 | Fit seconds | Negative predictions |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| last_observed_wait | REFERENCE_BASELINE | 10.1030 | 13.3157 | 0.971812 | 0.000000 | 0 |
| linear_regression | PROVISIONAL_UNVERIFIED | 7.0173 | 9.5500 | 0.985501 | 0.049944 | 350 |
| polynomial_degree2 | PROVISIONAL_UNVERIFIED | 6.1395 | 8.3906 | 0.988808 | 0.074391 | 289 |

- linear_regression: validation MAE is 3.0857s lower than persistence; no superiority on test or real traffic is established.
- polynomial_degree2: validation MAE is 3.9635s lower than persistence; no superiority on test or real traffic is established.

Fit time is one measured wall-clock fit including preprocessing, excluding loading,
prediction, plotting and serialization. Baseline fit time is zero (no training). Timing
varies by machine/load and is not a repeated performance benchmark. R2 is dimensionless;
negative R2 is possible and undefined constant-target per-run R2 is left blank. Metrics
are row-weighted over validation observations, not a confidence interval over independent
vehicles. Per-run results are saved separately.

## Diagnostics and limitations

- The two named models are unregularized least squares. Collinear simulator features and
  phase dummy columns can produce rank-deficient designs; rank/feature counts and any fit
  warnings are retained in the comparison CSV. No unrequested regularizer is introduced.
- Residuals are actual minus predicted: positive means underprediction. Both residual
  scatter/histogram and predicted-versus-actual plots are saved for all three methods.
  Raw predictions are not clipped or silently repaired; negative predictions are reported
  as nonphysical limitations, not fed to any controller.
- Current waiting is highly persistent by construction of this short-horizon point-queue
  simulator. High R2 can reflect that persistence and shared simulator assumptions, not
  robust real-world generalization or a causal signal-control benefit.
- Congestion classification labels elsewhere are feature-derived; these runs instead use
  future-state wait labels. No current congestion score or future outcome is a predictor.
- Validation is a development set: two of its runs were previously explored in EDA, as
  disclosed in LEAKAGE_AUDIT.md. The untouched final test remains reserved. No test
  performance, deployment readiness or official syllabus permission is claimed.

### Per-run validation RMSE range

- last_observed_wait: 9.115Ã¢â‚¬â€œ15.895s across six validation runs.
- linear_regression: 7.803Ã¢â‚¬â€œ12.784s across six validation runs.
- polynomial_degree2: 6.417Ã¢â‚¬â€œ11.273s across six validation runs.

Artifacts: `C:\Users\Hrishit Vats\OneDrive\Desktop\raah\artifacts\regression` contains regression_comparison.csv, validation_predictions.csv, validation_per_run_metrics.csv, two full fitted pipelines, experiment_manifest.json and six diagnostic PNGs. Saved pipelines are reloaded and their validation predictions checked against the CSV. Raw input hashes remain unchanged.

Reproduce: `./ml-service/.venv/Scripts/python.exe ml-service/training/train_regression.py`. Seed 57 is retained; the two least-squares estimators themselves use no random fit.

## Artifact inspection and execution tests

All six diagnostic PNGs were checked for valid signatures and visually inspected.
The persistence plots show systematic positive residuals for growing queues; degree 2
reduces that spread but still has skewed/tail errors and nonphysical negative outputs.
Rank and range diagnostics from the final comparison:

- last_observed_wait: minimum prediction 0.000s, maximum 294.214s; 0 negative predictions (0.00%).
- linear_regression: minimum prediction -5.134s, maximum 329.212s; 350 negative predictions (12.05%).
- polynomial_degree2: minimum prediction -20.580s, maximum 317.556s; 289 negative predictions (9.95%).

The fitted linear design rank is 15/16 transformed columns for linear regression and
70/71 for polynomial degree 2; full phase dummies plus an intercept create a redundant
direction. No fit warning was emitted. Serialized pipelines reproduce the saved validation
predictions; comparison and per-run CSV metrics were independently recomputed in tests.
The manifest's training-script hash matches the final source.

```powershell
$env:TEMP = (Resolve-Path work/tmp).Path
$env:TMP = $env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_train_regression.py -q
```

```text
.......................                                                  [100%]
23 passed in 5.59s
```

All **23 regression tests pass**. Tests cover exactly the named provisional algorithms,
degree-2 numeric scope, train-only transform/estimator fitting, correct future target y,
missing/unseen inputs, target-injection isolation, persistence definition, metric units
and residual sign, undefined/negative R2 handling, group overlap, corrupt manifest/hash
rejection, serialized prediction equality, six PNG exports and no-test-file access.
The experiment also runs successfully in a directory containing only train.csv,
validation.csv and the manifest, with no test.csv present. Test-file reads are guarded
by a test that would raise immediately. No broader suite that reads test features was
run for this experiment.

The first test pass had two fixture failures from omitted snapshot audit keys. Fixtures
were corrected and an early required-metadata check was added to reject such inputs
before training. No algorithm or hyperparameter was changed after inspecting validation
scores. Final metric values equal the initial run; measured fit times vary normally.

Changes are saved locally, uncommitted and not pushed. No assistant contributor or
co-author attribution is added.
