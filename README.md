# Raah

A semester ML project for estimating traffic congestion from **synthetic GPS-like aggregate
speed, vehicle counts and queue lengths**, comparing permitted models, and adjusting
**VIRTUAL signals** through a constrained rule-based controller.

## Phase 1 status

FastAPI health API, React/Vite JavaScript client, dependency manifests and API tests are
implemented. The client includes a Leaflet abstract network with no external map tiles,
Recharts empty results view, and axios API status. A seeded synthetic dataset and fixed-time virtual junction baseline are now implemented;
provisional regression and classification experiments are implemented; no adaptive virtual controller is implemented yet. Validation-only regression metrics are documented below; there are no real-world traffic measurements.

Every provisional syllabus topic remains **UNVERIFIED** until the official syllabus is
provided. No complete coverage is claimed. See [the checklist](docs/SYLLABUS_CHECKLIST.md),
[implementation guidance](AGENTS.md), and [Phase 1 report](docs/PHASE_1_REPORT.md).

## Boundaries

- Synthetic data only; no real private GPS, paid traffic APIs or physical signal control.
- No reinforcement learning, deep learning, MongoDB, Stripe or authentication services.
- Seed **57**, group-separated splits, training-only preprocessing and transparent metrics.
- Future virtual control must enforce safe phases, clearance intervals and timing constraints.

## Setup (PowerShell, repository root)

Use Python 3.12 and Node meeting `client/package.json` requirements. The local setup was
tested with Python 3.12.14 and Node 24.22.1. Generated environments are excluded from Git.

```powershell
python -m venv ml-service/.venv
.\ml-service\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
npm --prefix client ci
```

If npm is not on PATH but the earlier workspace-local tools exist, substitute `.\npm.cmd`
for `npm`. Those downloaded tools under `work/` are not distributed in Git. For initial
resolution instead of the tested exact Python versions, use `requirements.txt`.

## Run locally (two terminals)

```powershell
.\ml-service\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir ml-service --host 127.0.0.1 --port 8000
npm --prefix client run dev
```

Open http://127.0.0.1:5173. The Vite dev proxy rewrites `/api/health` to the API's
`/health` on port 8000. GET `/health` is liveness only and explicitly marks the controller
as not implemented. Stop each server with Ctrl+C.

Root `.env.example` documents shell variables; it is not automatically loaded. Vite can
load a copied `client/.env.example` as `client/.env.local`. Never put secrets in VITE_
variables. A separately hosted production frontend requires its public API base URL at
build time and corresponding API CORS configuration; the dev proxy is not bundled.

## Checks

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/smoke_imports.py
.\ml-service\.venv\Scripts\python.exe -m pytest
npm --prefix client run build
.\ml-service\.venv\Scripts\python.exe tests/check_runtime.py
```

`docs/PHASE_1_REPORT.md` records actual command output, versions, installation fixes,
and live health verification. The current tests cover API behavior and local CORS;
future data leakage and controller invariant tests must accompany those implementations.

## Layout

- `ml-service/`: FastAPI API and import smoke check.
- `client/`: React/Vite JS frontend, Leaflet, Recharts and axios.
- `simulation/`: seed-57 four-approach generator and fixed-time virtual signal baseline.
- `tests/`: API behavior tests.
- `docs/`: setup, provisional syllabus and verification reports.

Next: confirm the syllabus, define independent synthetic scenario groups and target
semantics, then implement seed-57 generation, train-only pipelines and virtual safety tests.

## Synthetic dataset

```powershell
.\ml-service\.venv\Scripts\python.exe simulation/generate_data.py
```

Generates 30 independent synthetic runs, complete 60-second targets, run metadata,
a tiny sample, source snapshots and phase events under `ml-service/data/`. No live GPS
is used. See [simulation guide](simulation/README.md) and
[generation report](docs/SYNTHETIC_DATA_REPORT.md). Split by run before preprocessing.

## Leakage-aware raw splits

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/training/prepare_data.py
```

Persists raw `train.csv`, `validation.csv`, `test.csv` and `split_manifest.json` under
`ml-service/data/splits/`: 18/6/6 independent runs (60/20/20), seed 57. No preprocessing
is fitted. Select the task feature allowlist in `training/prepare_data.py`; raw split
CSVs retain identifiers and targets for storage/audit and must not be used wholesale as X.

This manifest supersedes the older exploratory EDA split. Final test groups were not
previously explored; two validation runs were seen in historical EDA, so validation is
a development set rather than a pristine holdout. See [leakage audit](docs/LEAKAGE_AUDIT.md).

## Train-only preprocessing

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/training/preprocessing.py
```

Verifies manifest-backed train-only fitting for both task allowlists and explicit
standard/no-scaling policies. Numeric medians and phase encoders are fitted on train;
validation/test are transform-only. Fitted pipelines and reports live in ignored
`artifacts/preprocessing/`. For cross-validation, build an unfitted preprocessing pipeline
inside each estimator pipeline and fit on training folds only.
See [preprocessing report](docs/PREPROCESSING_REPORT.md) for API usage, missing/unseen
category policies and the 275-test verification results.

## Provisional future-wait regression

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/training/train_regression.py
```

Runs only the two explicitly named provisional methods (LinearRegression and numeric
degree-2 PolynomialFeatures + LinearRegression) and the current-wait persistence reference.
Official syllabus permission remains UNVERIFIED. Fits on train and reports validation
MAE/RMSE/R2/timings with diagnostics; it does not open or evaluate test.csv.
Artifacts and comparison CSV: `artifacts/regression/`. See
[regression findings](docs/REGRESSION_FINDINGS.md) for negative predictions, prior EDA
validation exposure, tests and synthetic-data limitations. No other regressors are added.

## Provisional congestion classifiers

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/training/train_classification.py
```

Compares exactly LogisticRegression, KNN, GaussianNB, SVC, DecisionTreeClassifier and
RandomForestClassifier on the same manifest-backed train/validation groups, using
train-only preprocessing and the conservative classification feature allowlist. All are
provisional UNVERIFIED syllabus candidates; no coverage is asserted. Test data is not opened.
Metrics, per-class counts/recall, confusion matrices, latency and the predeclared
macro-F1/stability candidate selection are saved in `artifacts/classification/`.
See [classifier findings](docs/CLASSIFICATION_FINDINGS.md); the selected KNN has weak
MEDIUM recall and is not control-ready. Derived labels and prior EDA exposure limit claims.

## Training-only unsupervised exploration

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/training/unsupervised.py
.\ml-service\.venv\Scripts\python.exe ml-service/notebooks/execute_unsupervised.py
```

Provisional K-Means, sampled Ward hierarchy, DBSCAN and PCA fit training groups only.
Profiles, meaningful silhouettes, variance, PCA views and per-row flag rationale are
saved in `artifacts/unsupervised/`; the executed notebook is
`ml-service/notebooks/04_unsupervised.ipynb`. Cluster IDs are not ground-truth labels.
IQR/z-score flags remain not evaluated until explicit official method verification.
See [unsupervised findings](docs/UNSUPERVISED_FINDINGS.md) for sample limits, density
noise interpretation, 22 passing tests and the transparent non-Jupyter fallback check.

## Frozen final assessment

The validation-selected KNN and degree-2 polynomial regressor have been refitted on
train+validation and assessed once on the six final test runs. Selection was persisted
before test access. `artifacts/final/` contains selection_manifest.json, full joblib
pipelines, feature_schema.json, metrics.json, cached predictions, plots and the usage
ledger. See [final test audit](docs/FINAL_TEST_AUDIT.md) for exact results and prior exposure.

The test is consumed. Preserve the one-use claim and frozen selection. Completed
evaluator calls replay saved metrics; do not reset the guard or reuse this holdout for
tuning. The classifier's poor MEDIUM recall and the regressor's negative predictions
remain limitations; no model is control-ready or officially syllabus-verified.
