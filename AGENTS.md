# Raah implementation guidance

## Scope and boundaries

Raah is a reproducible semester ML project that estimates traffic congestion from synthetic GPS-like aggregate speed, vehicle counts, and queue lengths. It compares syllabus-permitted models and adjusts VIRTUAL traffic signals with a constrained rule-based controller.

- Use only synthetic data. Never collect or use real private GPS data, paid traffic APIs, or physical traffic signal control. Do not implement hardware integrations or deployment to real signals.
- No reinforcement learning or deep learning.
- Use seed **57** for data generation, splits, stochastic models, and experiments. Record library versions, configurations, and any remaining nondeterminism.
- Every proposed syllabus topic is **UNVERIFIED** until the user provides the official syllabus. Treat the list as provisional, not permission to claim syllabus compliance or complete coverage. Update `docs/SYLLABUS_CHECKLIST.md` with official evidence before changing verification status.

## Data and evaluation

- Define aggregate units, sampling windows, feature availability, congestion labels/targets, and synthetic generation assumptions explicitly. Avoid identifiers or future measurements as predictors. Explain if labels are constructed from the same inputs used by the model.
- Separate train, validation, and test data by independent synthetic scenario/run groups before fitting anything. Keep correlated windows and duplicate/derived records from a group in a single split; document group keys and verify no overlap. Use grouped cross-validation for tuning. Consider temporal ordering where forecasting requires it.
- Fit imputation, scaling, encoding, polynomial expansion, PCA, feature selection, and learned outlier rules on training data only, inside each cross-validation fold. Apply fitted transformations unchanged to validation/test data. Never tune using test results.
- Compare only models permitted by the official syllabus once supplied. Until then label any exploration provisional. Use common splits and appropriate simple baselines. Keep regression, classification, clustering, and dimensionality reduction objectives distinct.
- Report transparent metrics, units, sample/group counts, class balance, hyperparameters, and limitations. For regression consider MAE/RMSE/R-squared; for classification precision/recall/F1/confusion matrix and justified averaging; for clustering state noise handling and validity assumptions. Do not fabricate results or present clustering as supervised accuracy.
- Keep final test evaluation separate from model selection. Report scenario-level variation and failure cases, including low speed with low count, long queues, missing data, and outliers.

## Virtual controller safety

- Keep the controller rule-based, deterministic, constrained, and separate from ML estimation. ML estimates may inform bounded rules; they must not bypass safety invariants.
- Represent phases and allowed transitions explicitly. Require minimum/maximum green durations, yellow and all-red clearance intervals, incompatible-movement exclusion, and bounded timing changes. Validate all timing parameters and units; do not invent universal real-world-safe timings.
- Never switch conflicting movements directly from green to green. Enforce clearance intervals in the simulator, maximum waiting/starvation limits, and a documented safe virtual fallback for invalid or missing estimates. Define precedence for constraints and reject infeasible configurations.
- Test phase transitions and invariants across steps, boundary timings, invalid input, starvation cases, and reproducible synthetic scenarios. Report queue length, throughput, waiting time, and constraint violations against a fixed-time virtual baseline.

## Workflow

- Inspect existing code and manifests before installing dependencies; preserve existing work. Use the project venv and local tools when available. Ask before privileged installs, login, or browser authorization.
- Add only dependencies required by an agreed implementation. Record exact setup/run/check commands and reproducibility settings. Avoid claims of successful execution unless checks actually ran.
- Keep scope clear in the README: educational simulation, provisional syllabus alignment, and implementation status. Require meaningful tests for data leakage and controller invariants when implemented.
- Do not add the assistant as a contributor or add AI co-author attribution to commits. Never fabricate Git identity. Commit only reviewed task changes when a user identity is configured; do not push without authorization.
