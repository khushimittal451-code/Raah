# Unsupervised findings

All named clustering/PCA methods are **PROVISIONAL / UNVERIFIED**. No official
syllabus coverage is asserted. **Cluster IDs are arbitrary, not LOW/MEDIUM/HIGH
ground-truth labels**. No label accuracy, ARI or other supervised cluster score is used.

Only the manifest's 8,712 rows from 18 training runs are loaded. Neither validation.csv
nor test.csv is opened, transformed or fitted. Numeric median imputation and standard
scaling fit exclusively on training. The ten current-time numeric fields exclude IDs,
phase categories, congestion_level and future_wait_seconds. Original inputs are unchanged.

## Fixed methods and scope

- K-Means: requested k=3, n_init=20, seed 57, Lloyd. k is reduced explicitly only when
  rows/distinct training vectors are fewer than three; effective k is recorded.
- Hierarchical: Ward/Euclidean on a seed-57 uniform training sample capped at 2,000 rows,
  bounding quadratic memory. Unselected rows have blank hierarchical assignments; no
  nearest-centroid or other out-of-sample labeling method is silently introduced.
- DBSCAN: eps=1.2, min_samples=20 on training-standardized inputs. -1 is unassigned
  density noise, **not a ground-truth anomaly**. Parameters are not tuned using labels
  or held-out sets. Distance-based methods are sensitive to scale and correlated fields.
- PCA: full SVD fitted on all training rows, with per-component/cumulative variance saved.
  Clustering fits the ten-dimensional standardized data, not the 2D plot coordinates.
  Two-dimensional visual separation can distort the full-space structure.

Silhouette excludes DBSCAN noise, uses at most 1,500 seeded training rows, and is left
blank with a rationale for one/all-noise/all-singleton clusters or unsuitable samples.
It is descriptive geometry, not congestion-label correctness or an objective for tuning.

| Method | Fit rows | Non-noise clusters | Noise rows | Silhouette | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| KMeans | 8712 | 3 | 0 | 0.1848 | TRAIN_ONLY_SAMPLED |
| hierarchical | 2000 | 3 | 0 | 0.1534 | TRAIN_ONLY_SAMPLED |
| DBSCAN | 8712 | 1 | 1404 | not meaningful | NOT_MEANINGFUL: need >=2 non-noise clusters and fewer clusters than rows |

PCA first-two-component explained variance: 56.34%. Cluster profiles report counts and original-unit mean/median values; speed summaries use available observations, so sampling coverage can bias them. Empty expected clusters retain explicit EMPTY rows and blank statistics.

## Anomaly gating and rationale

IQR and z-score are **SKIPPED_UNVERIFIED** in the current project: no official
method-specific approval file is present. Their flag cells are blank, not False/normal.
No IQR/z-score statistics are fitted. anomaly_flags.csv includes per-row skip rationale
and a separate DBSCAN density-noise flag; no observations are deleted. A generic
UNVERIFIED outlier-detection topic does not authorize either method.

The optional approval loader requires a retained official title/version/source and
explicit VERIFIED IQR or z_score topic plus exact section. This records user-provided
verification evidence; it does not autonomously authenticate a syllabus document.
If explicitly verified later, IQR uses training-imputed original-unit quartiles and 1.5
IQR fences; z-score uses training mean/population std and |z|>3. Constant-feature cases
are documented rather than divided by zero, and no held-out thresholds are learned.

## Interpretation and limits

The data is synthetic, not live GPS. Counts, queues and waits are simulator truth.
Correlated counts/queues/waits/sample coverage may dominate Euclidean geometry; clusters
can reflect demand magnitude, generator configuration, clock and fixed virtual timing.
Labels elsewhere are feature-derived, so comparing clusters to those labels would be
circular evidence, not independent traffic discovery. Different seeds/parameters can
change arbitrary cluster numbers; no cluster stability or real-road validity is claimed.
The hierarchy sample and silhouette sample are disclosed and may omit rare behavior.
No controller, model selection or raw-data filtering uses these cluster/noise IDs.

Artifacts: `C:\Users\Hrishit Vats\OneDrive\Desktop\raah\artifacts\unsupervised` contains profiles, metrics, assignments, PCA variance/coordinates, anomaly flags with rationale, five PNGs, fitted training objects and analysis_manifest.json. Reproduce with `./ml-service/.venv/Scripts/python.exe ml-service/training/unsupervised.py`.

## Execution checks

Command: `.\ml-service\.venv\Scripts\python.exe ml-service/notebooks/execute_unsupervised.py`.

Jupyter tooling is unavailable in this environment; conventional kernel execution and official nbformat validation were skipped. Plain-Python fallback executes cells in order and captures real outputs; it does not test kernel behavior.

```json
{
  "mode": "python-sequential-fallback",
  "jupyter_tooling": {
    "nbformat": false,
    "nbclient": false,
    "jupyter_client": false,
    "ipykernel": false
  },
  "code_cells": 7,
  "executed_code_cells": 7,
  "cell_errors": 0,
  "embedded_charts": 5,
  "checks": {
    "all_code_cells_executed": true,
    "no_cell_errors": true,
    "five_embedded_charts": true,
    "five_saved_charts": true,
    "valid_png_signatures": true,
    "all_input_csv_hashes_unchanged": true
  },
  "elapsed_seconds": 3.572,
  "error": null,
  "official_nbformat_validation": false
}
```

No packages installed and no raw input files changed. Named unsupervised methods fit training only. Charts are derived artifacts; no supervised model is evaluated.

## Plot/profile inspection

All five PNGs were visually inspected. K-Means and Ward groups overlap in the PCA view;
the modest silhouettes do not establish sharply separated traffic regimes. The queue
color gradient follows the leading PCA direction, consistent with correlated count/
queue/wait inputs dominating part of the geometry. Dense overlapping plot points are
not evidence of independent observations. The PCA plot discards substantial variation.

PC1 explains 44.03%, PC2 12.30%; 7 components are needed to exceed 95% training variance. This is not predictive model accuracy.

K-Means profiles have 4,805 / 2,612 / 1,295 rows in IDs 0/1/2, with mean queues
8.23 / 3.47 / 138.90 vehicles. These descriptions do not rename clusters as true
congestion classes. Ward profiles cover only its 2,000 sampled observations.
DBSCAN density noise contains 1,404 rows with a mean queue around 114.38, versus
9.29 for its 7,308 assigned rows. Such tail behavior can be valid high-demand simulation
output; it is not evidence of invalid data or permission to delete rows.

IQR/z-score flags are blank for every row and have SKIPPED_UNVERIFIED rationale.
Only DBSCAN's separately named density_noise_flag is populated; no anomaly ground
truth or normality claim is made.

## Executed script and tests

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/training/unsupervised.py
.\ml-service\.venv\Scripts\python.exe ml-service/notebooks/execute_unsupervised.py
$env:TEMP = (Resolve-Path work/tmp).Path
$env:TMP = $env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_unsupervised.py -q
```

Script output:

```text
method                 status        fit_status  requested_clusters  effective_nonnoise_clusters  fit_rows  noise_rows  silhouette  silhouette_rows                                                        silhouette_status
      KMeans PROVISIONAL_UNVERIFIED FITTED_TRAIN_ONLY                 3.0                            3      8712           0    0.184828             1500                                                       TRAIN_ONLY_SAMPLED
hierarchical PROVISIONAL_UNVERIFIED FITTED_TRAIN_ONLY                 3.0                            3      2000           0    0.153415             1500                                                       TRAIN_ONLY_SAMPLED
      DBSCAN PROVISIONAL_UNVERIFIED FITTED_TRAIN_ONLY                 NaN                            1      8712        1404         NaN                0 NOT_MEANINGFUL: need >=2 non-noise clusters and fewer clusters than rows
PCA two-component variance: 0.5633753244225892
Anomaly methods: {'IQR': 'SKIPPED_UNVERIFIED', 'z_score': 'SKIPPED_UNVERIFIED'}
Validation/test opened: False False
```

Test output:

```text
......................                                                   [100%]
22 passed in 3.02s
```

The **22 tests pass without warnings**. They cover train-only fit calls and isolated
training-file loading, missing/all-missing fields, finite feature handling, target
injection invariance, seeded hierarchy sampling, no invented all-row hierarchy labels,
one-row/constant PCA/hierarchy edge cases, one/all-noise/all-singleton silhouette cases,
noise exclusion, empty profiles, explicit method-specific evidence gates and anomaly
threshold rationale using fake unit fixtures only. No project IQR/z-score threshold
analysis was run under the currently unverified syllabus.

The one-row hierarchy is explicitly skipped with no assignment; multirow constant
data can form one cluster but PCA/variance and silhouette remain not meaningful.
No failed assertion remains. No validation or test files are needed by the integration
test: it copies only train.csv and its manifest and installs read guards for both
held-out filenames. Broader tests that read held-out data were not run for this task.

Notebook execution: **7/7 code cells passed, zero errors, five embedded charts and
five plain-English takeaways**. Jupyter tooling remains absent, so execution used the
transparent Python-cell fallback; kernel behavior and official nbformat validation were
not tested. Saved JSON/AST, execution order, plot signatures, train/source code hashes,
6,712 blank unsampled hierarchical assignments and skipped anomaly flags were independently
checked. Source train.csv and split_manifest.json hashes remain unchanged.

Changes are local, uncommitted and not pushed. Existing classifier/regression work is
preserved. No assistant contributor or co-author attribution is added.
