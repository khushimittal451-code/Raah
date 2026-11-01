# Train-only preprocessing report

Date: 2026-11-02 (Asia/Calcutta). Existing scikit-learn 1.9.1; no dependencies added.
All syllabus topics remain UNVERIFIED. This step fits transforms, not predictive models.

## Implementation and feature order

`ml-service/training/preprocessing.py` exports:

- `build_preprocessor(task, numeric_scaling=...)`: an **unfitted** sklearn Pipeline of
  canonical feature selection and a ColumnTransformer. `classification` uses the five
  approved non-rule-defining inputs; `future_wait_regression` uses eleven current-time
  features. IDs, targets and unknown extra columns cannot enter transformation branches.
- `fit_training_only(train, validation, test, ...)`: checks nonempty, disjoint run groups,
  fits once on train, and transforms held-out frames without fitting. It hashes full
  fitted state before/after held-out transforms and checks stable finite matrix widths.
- `run_preprocessing(...)`: additionally verifies CSV hashes, run membership/counts and
  feature policy against the authoritative split manifest. This is the preferred fitting
  entry point. A low-level factory can still be misused by a caller; only fit on the
  designated training groups, or training folds within grouped cross-validation.

Canonical named DataFrames are required; positional arrays, missing/duplicate feature
columns, nonnumeric/infinite measurements and nonstring categories fail clearly. Numeric
CSV coercion and missing-value normalization are stateless. Input frames are copied.
Output order is canonical numeric fields followed by one-hot phase columns, with exact
names available from `pipeline.get_feature_names_out()`. Input-column order and extra
excluded targets/metadata do not affect the output.

## Imputation, encoding and scaling

- Numeric: median imputer fitted on **training only**, with keep_empty_features=True.
  An entirely missing training column is retained with a documented zero fallback;
  the report lists any such columns. No validation/test median is consulted.
- Categorical current_phase: constant `__MISSING_PHASE__` imputation and a train-fitted
  OneHotEncoder(handle_unknown='ignore', sparse_output=False). Unseen categories never
  extend the learned vocabulary or matrix width: they map to an all-zero categorical
  block. If the missing token was absent in training, a later missing phase uses that
  same zero-block fallback. This layer does not replace traffic-schema validation.
- `numeric_scaling='standard'`: StandardScaler fitted only after training imputation,
  for scale-sensitive linear/distance/SVM-style workflows. Only the numeric branch is
  scaled; one-hot indicators remain 0/1.
- `numeric_scaling='none'`: no scaler exists in the numeric branch, suitable for tree-style
  workflows. The API requires the scaling choice explicitly; no model is selected here.

## Executed commands

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/training/preprocessing.py
$env:TEMP = (Resolve-Path work/tmp).Path
$env:TMP = $env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_preprocessing.py -q
.\ml-service\.venv\Scripts\python.exe -m pytest -q -o faulthandler_timeout=15
```

The CLI verifies both tasks with both scaling policies; each pipeline fits only the
8,712 rows in the manifest's 18 training runs. Held-out sets have 2,904 rows/six runs each.

| Task | Numeric scaling | Train matrix | Validation matrix | Test matrix | Scaler fit rows |
| --- | --- | --- | --- | --- | ---: |
| classification | none | 8,712 x 10 | 2,904 x 10 | 2,904 x 10 | no scaler |
| classification | standard | 8,712 x 10 | 2,904 x 10 | 2,904 x 10 | 8712 |
| future_wait_regression | none | 8,712 x 16 | 2,904 x 16 | 2,904 x 16 | no scaler |
| future_wait_regression | standard | 8,712 x 16 | 2,904 x 16 | 2,904 x 16 | 8712 |

Fitted pipelines and detailed JSON reports are saved under ignored `artifacts/preprocessing/`.
The reports include learned numeric statistics, categories, feature order, fit group IDs,
shape checks and state hashes. Artifacts are importable as `training.preprocessing` and
were reloaded successfully in a fresh Python process. No raw matrix files are rewritten.

### Focused results

```text
......................                                                   [100%]
22 passed in 17.18s
```

### Full suite

```text
........................................................................ [ 26%]
........................................................................ [ 52%]
........................................................................ [ 78%]
...........................................................              [100%]
275 passed in 13.36s
```

All final commands exited 0; no test warnings or failures. The 22 new cases cover missing
cells, all-missing numeric/category training columns, unseen categories, median/scaler
statistics under extreme held-out values, call spies proving every learned fit sees only
training rows, unchanged fitted state, scaling policy, order/target-injection invariance,
cloneability, bad input/group rejection, manifest corruption, real-split fitting and
cross-process artifact reload. The complete 275-test suite passes.

A scratch import from the repository root initially lacked the ml-service import path;
adding it succeeded. This is an import-path setup issue, not a pipeline or test failure.
CLI scripts and pytest already configure this path; library callers must do the same.

## Reuse and boundaries

From the repository root, library usage can start with:

```python
import sys
sys.path.insert(0, 'ml-service')
from training.preprocessing import build_preprocessor
preprocessor = build_preprocessor('classification', numeric_scaling='none')
# Unfitted: combine with a permitted estimator in an sklearn Pipeline later.
```

For a specific persisted policy:

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/training/preprocessing.py --task future_wait_regression --numeric-scaling standard
```

Inside grouped cross-validation, clone/build the **unfitted** selector + ColumnTransformer
inside the estimator pipeline so each training fold fits its own transforms. Do not fit
once on all training groups and reuse those transformed values for internal validation
folds. The whole-train artifacts here support the fixed external validation/test split;
no hyperparameter tuning or predictive scores are produced.

All original source CSV and split CSV hashes remain equal to the manifest after this step.
No imputation is written back into raw data. The prior leakage audit still applies:
classification labels are synthetic rule-derived; regression uses simulator-truth queue/
count/wait covariates; two validation runs were previously explored in EDA, while final
test groups were not. No physical signals, private GPS or paid services are involved.

Changes remain local and uncommitted; artifacts remain ignored. No assistant contribution
or co-author attribution was added.
