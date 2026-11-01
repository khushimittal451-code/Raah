# EDA findings

- Input: **14,520 rows x 17 columns**, comprising 15 current-time observation fields and two targets. Thirty synthetic runs, one virtual junction, four approaches. **Not live GPS.**
- Structural audit: 2,761 speed nulls (19.02%), exactly matching zero sample coverage. Other columns have no nulls. Exact duplicate rows: 0; duplicate observation keys: 0. No imputation or deletion.
- Group split: 20 training / 5 validation / 5 test runs, stratified by demand archetype with seed 57. Charts use only **9,680 training rows**. Mapping: `artifacts/eda/run_split.csv`. Held-out values are not used for feature/target EDA or tuning.
- Road/time patterns: one abstract junction, not a real road network. High-demand training rows average 110.64 queued vehicles per approach versus 0.43 for low demand. The rush-hour-like pulse is compressed into synthetic run time; no real commute-hour claim.
- Distributions: training queues have 34.2% zeros and a maximum of 366. Future wait median 11.0s; 95th percentile 223.7s. Missing speeds remain missing; observed-only speed statistics can be coverage-biased.
- Training classes: low 4,634, medium 957, high 4,089. Medium represents 9.89%; balanced scenario counts do not mean balanced labels.
- **Feature-derived label warning:** congestion-v1 is computed from speed/reference-speed ratio, count, queue and current wait. Direct-rule agreement is 100% **by construction, not model accuracy**. A classifier using those inputs can inflate apparent accuracy if presented as independent congestion detection. Group splits do not remove this circular definition.
- Current/future wait correlation is 0.99 in training rows. Correlation reflects persistence and simulator assumptions, not causation; pairwise-complete calculations have varying sample sizes. No features are selected or preprocessing fitted here.
- Later forecasting should evaluate the exact +60s wait target, current-wait persistence baseline, MAE/RMSE in seconds, per-run variation and held-out groups. Exclude future outcomes and metadata IDs/seeds from predictors. Fit preprocessing only on training folds.
- Nine charts are saved under `artifacts/eda/` and embedded when supported. Plain-English takeaways accompany every chart. SHA-256 of all five input CSVs is unchanged. All syllabus topics remain **UNVERIFIED**; no model score or complete coverage is claimed.

## Execution checks

Command: `./ml-service/.venv/Scripts/python.exe ml-service/notebooks/execute_eda.py`.

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
  "code_cells": 11,
  "executed_code_cells": 11,
  "cell_errors": 0,
  "embedded_charts": 9,
  "checks": {
    "all_code_cells_executed": true,
    "no_cell_errors": true,
    "nine_embedded_charts": true,
    "nine_saved_charts": true,
    "valid_png_signatures": true,
    "all_input_csv_hashes_unchanged": true
  },
  "elapsed_seconds": 6.162,
  "error": null,
  "official_nbformat_validation": false
}
```

No packages installed and no raw input files changed. No model was trained. Charts are derived artifacts.

Saved notebook JSON/AST, execution order, all nine chart takeaways and input hashes were independently rechecked: PASS.
