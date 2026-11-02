# Provisional syllabus evidence report

Date: 2026-11-03. **The official syllabus has not been supplied. Every topic is
UNVERIFIED.** This maps actual code to provisional topics, not official permission,
complete coverage, assessment readiness or a statement that each topic was taught.
The existing [checklist](SYLLABUS_CHECKLIST.md) remains authoritative for verification.

| Provisional topic | Official status | Actual implementation / evidence | Explicit gap or caveat |
| --- | --- | --- | --- |
| Linear regression | UNVERIFIED | `training/train_regression.py`: sklearn LinearRegression candidate | The implemented baseline is multivariate; no separate single-feature regression experiment |
| Multiple regression | UNVERIFIED | Same linear candidate uses current numeric/phase features; saved validation MAE 7.017311 s | Not a second independent model or separate coverage claim |
| Polynomial regression | UNVERIFIED | Numeric degree-2 PolynomialFeatures + LinearRegression inside pipeline; validation MAE 6.139516 s | No higher degree, Ridge, Lasso or extra regressor silently added; negative outputs persist |
| Logistic regression | UNVERIFIED | Six-candidate classifier script; validation macro-F1 0.489339 | Fixed C=1, no hyperparameter search or calibrated probability assessment |
| KNN | UNVERIFIED | k=15, distance weighting, scaled inputs; validation macro-F1 0.537601 | Selected model; weak saved final MEDIUM recall 0.055363 |
| Naive Bayes | UNVERIFIED | GaussianNB; validation macro-F1 0.472884 | Gaussian/conditional independence approximation includes one-hot fields; not Multinomial/Bernoulli NB |
| SVM | UNVERIFIED | RBF SVC; validation macro-F1 0.510306 | Classification only; no SVR, kernel comparison or calibration experiment |
| Decision tree | UNVERIFIED | DecisionTreeClassifier depth<=8, min leaf 20; macro-F1 0.509029 | No tree-regression or pruning-search study |
| Random forest | UNVERIFIED | 200-tree classifier, depth<=12, min leaf 5; macro-F1 0.526603 | Classification only; no RandomForestRegressor or forest tuning |
| K-Means | UNVERIFIED | `training/unsupervised.py`, training-only standardized numeric data, seed 57; profiles/plots | Exploratory clusters, not truth labels or control commands |
| Hierarchical clustering | UNVERIFIED | Ward AgglomerativeClustering on disclosed 2,000-row training sample; notebook 04 | Not fitted on all 8,712 rows; sample can omit rare structure |
| DBSCAN | UNVERIFIED | Training-only fit, explicit noise/profile handling | Saved result has one non-noise cluster; silhouette is undefined, not invented |
| PCA | UNVERIFIED | Training-only full-SVD PCA; first-two variance fraction 0.563375 | Exploratory visualization, not an implemented supervised prediction feature or controller |
| Outlier detection | UNVERIFIED | IQR/z-score evidence-gated branches and edge-case tests exist | Saved analysis is SKIPPED_UNVERIFIED; no approved thresholds fitted or raw records filtered |
| Preprocessing | UNVERIFIED | ColumnTransformer, median/constant imputation, unknown-safe one-hot encoding, model-appropriate scaling; fit-isolation tests | No feature selection, target encoding or learned outlier removal; test transforms do not fit |
| EDA | UNVERIFIED | `notebooks/01_eda.ipynb`, saved charts and `EDA_FINDINGS.md` | Historical 20/5/5 map differs from later training split; two later validation groups were exposed |
| Evaluation | UNVERIFIED | Group split audit, baseline comparisons, per-class metrics/confusion/latency, MAE/RMSE/R2, train-only clustering validity, frozen final test, paired controller benchmark | No implemented grouped CV tuning; no live-data external validation or complete course mapping |

Paths above are relative to `ml-service/` unless a docs filename is shown. Supervised
metrics are from saved **validation** comparisons, not reruns or final-test selection.
Both training factories and experiment manifests mark provisional status. The two
named regressors and six named classifiers implement user-requested exploration;
their existence does not verify official syllabus permission.

## Evidence and interpretation

- Code: `ml-service/training/{prepare_data,preprocessing,train_regression,train_classification,unsupervised,final_evaluation}.py`.
- Saved experiments: `artifacts/regression/regression_comparison.csv`,
  `artifacts/classification/model_comparison.csv`, `artifacts/unsupervised/analysis_manifest.json`.
- Notebooks: `ml-service/notebooks/01_eda.ipynb` and `04_unsupervised.ipynb`.
- Leakage: `docs/LEAKAGE_AUDIT.md`; current features are defined by code, not by
  selecting every non-target CSV column. Whole run groups stay together.
- QA: [FINAL_QA_REPORT.md](FINAL_QA_REPORT.md). Passing tests support implemented
  behavior; they do not establish syllabus coverage or empirical validity.

The dataset congestion label is a synthetic rule based on speed/count/queue/wait.
Classification conservatively excludes its direct inputs, but indirect dependence
remains. Future-wait regression uses exact t+60 labels and current simulator truth.
All split/scaler/feature/target semantics must be retained when discussing results.

## Not implemented or outside scope

Grouped CV/hyperparameter search, standalone univariate regression, SVR, tree/forest
regression, supervised PCA features, calibrated confidence scores, cluster-based
signals, automated outlier filtering, real GPS ingestion, live traffic validation,
multi-junction network control, routing optimization and automatic OSM-network import
are not implemented. The optional SUMO smoke adapter is standalone fixed-time and
its runtime remains unverified/unavailable at last check.

Authentication, database storage, multi-user isolated sessions, durable simulation
state, hosted CI/deployment automation and container configuration are not provided.
Real physical signals/hardware, private GPS, paid APIs, RL and deep learning are
outside the permitted scope and must not be described as planned deployment steps.

## How verification can change

The user must provide the official syllabus title, date/version and source. Map each
topic to an exact section/page and any algorithm/depth limits. Then update
`SYLLABUS_CHECKLIST.md` with that evidence and this report with a separate verified
mapping. A generic title such as “outlier detection” is not method-specific approval
for IQR/z-score. Missing topics or evidence remain UNVERIFIED; never infer complete
coverage from this provisional list.
