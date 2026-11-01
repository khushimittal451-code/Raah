# Provisional syllabus checklist

The official syllabus has not been provided. **Every topic below is UNVERIFIED.** Listing a topic does not establish permission, implementation, or complete syllabus coverage. No coverage claim is made.

| Provisional topic | Syllabus status | Potential role (subject to official confirmation) |
| --- | --- | --- |
| Linear regression | UNVERIFIED | Single-feature congestion regression baseline |
| Multiple regression | UNVERIFIED | Aggregate speed, count, and queue regression |
| Polynomial regression | UNVERIFIED | Nonlinear feature expansion with controlled complexity |
| Logistic regression | UNVERIFIED | Congestion category classification |
| KNN | UNVERIFIED | Scaled-feature supervised comparison |
| Naive Bayes | UNVERIFIED | Classification with explicit distribution assumptions |
| SVM | UNVERIFIED | Classification or regression as permitted |
| Decision tree | UNVERIFIED | Interpretable supervised comparison |
| Random forest | UNVERIFIED | Ensemble supervised comparison |
| K-Means | UNVERIFIED | Exploratory grouping of synthetic traffic regimes |
| Hierarchical clustering | UNVERIFIED | Exploratory regime hierarchy |
| DBSCAN | UNVERIFIED | Density clusters and explicit noise handling |
| PCA | UNVERIFIED | Train-fitted dimensionality reduction |
| Outlier detection | UNVERIFIED | Synthetic anomaly analysis; train-fitted rules |
| Preprocessing | UNVERIFIED | Train-only imputation, encoding, scaling and transforms |
| EDA | UNVERIFIED | Training-set distributions, relationships and generation checks |
| Evaluation | UNVERIFIED | Group-separated evaluation and transparent metrics |

## Verification procedure

1. Obtain the official syllabus from the user and record its title, version/date, and source.
2. Map each topic to an exact section/page and any limits on permitted algorithms or depth. Resolve missing or ambiguous topics with the user.
3. Record syllabus verification separately from implementation and test evidence. Retain UNVERIFIED wherever official evidence is absent. Add omitted official topics rather than asserting the provisional list is exhaustive.
4. Compare permitted semester models using seed **57**, consistent group-separated splits, training-only preprocessing, baselines, and task-appropriate metrics. Keep unsupervised exploration separate from supervised prediction results.

## Mandatory project constraints

- Synthetic GPS-like aggregate speed, counts and queues only; no real private GPS or paid traffic APIs.
- Virtual signals only, with constrained rule-based control and safe simulated phase transitions; no physical signal control.
- No reinforcement learning or deep learning.
- Record dataset generation assumptions, units, group identifiers, split assignments, configurations, library versions and seed 57 for reproducibility.
- Document leakage checks, controller invariant checks, limitations and actual results. No results or implementation coverage are established by this checklist.
