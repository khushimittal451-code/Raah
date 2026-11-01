# Leakage audit

Seed **57**. Synthetic traffic only, never live GPS. No model or preprocessing is fitted.
All syllabus topics remain **UNVERIFIED**. `ml-service/data/splits/split_manifest.json`
is the authoritative training split, superseding the historical EDA 20/5/5 map.

## Persisted raw splits

| Split | Independent runs | Rows | Run share |
| --- | ---: | ---: | ---: |
| train | 18 | 8,712 | 60.0% |
| validation | 6 | 2,904 | 20.0% |
| test | 6 | 2,904 | 20.0% |

Files: `C:\Users\Hrishit Vats\OneDrive\Desktop\raah\ml-service\data\splits`: `train.csv`, `validation.csv`, `test.csv`, `split_manifest.json`. Raw CSVs retain all original columns and targets for audit/storage; **training must select only the approved task feature list**, not every non-target column. Original cell strings, null-speed blanks and row order within each run are preserved.

## Historical EDA exposure

The earlier notebook explored 20 runs (four per demand archetype). The seed-57 split
reconstructs that feature-blind policy without inspecting targets, protects never-explored
groups for final test, and verifies the saved EDA map when present. Existing test runs
are preferred, followed by old validation runs. Training groups are selected preferentially
from the previous EDA training pool. No target-dependent balancing or outcome-based choice
is made. No observations within a run are divided, including across approaches.

Previously explored runs now in validation: **2** (run-57-0026, run-57-0028). Validation is an explicitly exposed development set, **not a pristine holdout**. Final test overlap with previous EDA training: **0**. Rerunning EDA cannot undo prior exposure. No model/transform fitting or tuning has occurred. Keep future feature EDA within the new train groups; never treat the old 20-run EDA mask as the current training mask.

## Prediction-time features

Classification target: `congestion_level` at t. Approved fields:

`incoming_vehicles`, `outgoing_vehicles`, `current_phase`, `seconds_in_phase`, `time_of_day`.

Excluded are both targets; run/intersection/approach IDs and raw timestamp; all five
direct congestion rule inputs (speed, reference speed, count, queue, current wait);
and GPS sample count as a conservative close count proxy. Speed ratios, rule scores,
encoded labels, target statistics and other engineered target-derived values are not
approved. The current label remains synthetic rule-derived; indirect correlation through
flows/phase/time can persist, so scores must not be claimed as independent empirical
congestion discovery. The direct rule is an oracle-definition check, not model accuracy.

Regression target: `future_wait_seconds` at exact t+60. Approved fields:

`mean_speed_kmh`, `free_flow_speed_kmh`, `vehicle_count`, `queue_length_vehicles`, `mean_wait_seconds`, `incoming_vehicles`, `outgoing_vehicles`, `current_phase`, `seconds_in_phase`, `time_of_day`, `gps_sample_count`.

These are current snapshots and counters for the completed (t-10,t] interval. Current
queue/wait/count are simulator truth available at prediction t, not the realized future
outcome; use a current-wait persistence baseline later. This is **not GPS-only sensing**.
`time_of_day` is known synthetic clock information, not a future timestamp. No t+60
row, future phase/action/flow, outcome-derived statistic, full-run aggregate, scenario,
seed or provenance field is an input.

## Assertions and evidence

- Pairwise run intersections are empty; union covers all input runs and every original
  row exactly once. All approaches/neighbors in a run stay together. Overlapping absolute
  synthetic timestamps across different independent runs are expected and are not overlap.
- Canonical Pydantic contracts validate observations, targets and synthetic provenance.
  Declared run seeds are unique; renamed identical whole-run trajectories are rejected.
- Every target uses a matching same-run/intersection/approach t+60 source snapshot;
  source look-ahead inherits the current run split. Tail sources are audit evidence,
  not additional predictors or rows copied into another split.
- Feature allowlists reject IDs, either target, unknown engineered and post-outcome
  columns. Classification additionally rejects its rule-defining inputs and count proxy.
- Split CSV re-read matches original raw cells; split union and source SHA-256 checks
  pass. Null speed is not imputed, no rows dropped or scaled, and no outlier rule learned.
- Imputation, scaling, encoding, PCA/selection and tuning must later be fitted only on
  training groups, inside grouped validation folds. Test is reserved for final evaluation.

Manifest records group assignments, counts, source/output hashes, feature lists and
explicit exposure limits. Group independence follows the synthetic generator design;
it is not proof of realism, causal controller benefit or applicability to physical signals.

## Executed verification (2026-11-02)

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/training/prepare_data.py
$env:TEMP = (Resolve-Path work/tmp).Path
$env:TMP = $env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_prepare_data.py -q
.\ml-service\.venv\Scripts\python.exe -m pytest -q -o faulthandler_timeout=15
```

Preparation exited 0. Focused suite: **35 passed**. Final full-suite output:

```text
........................................................................ [ 28%]
........................................................................ [ 56%]
........................................................................ [ 85%]
.....................................                                    [100%]
253 passed in 6.87s
```

All 253 tests pass, including the 35 new split/feature tests. Tests cover exact 18/6/6
run counts, entire-run membership, raw-row union/null preservation, deterministic output
with or without ignored EDA artifacts, metadata-order invariance, forbidden classification
rule inputs and all-task identifiers/targets/post-outcome features, overlapping/missing
groups, corrupted future labels, reused run seeds, prior-EDA-map mismatch and unsafe
output path. Invalid inputs fail before split outputs are written. No leakage assertion
remains violated. Validation's disclosed historical EDA exposure is a development-set
limitation, not a pristine-holdout claim. No preprocessing is fitted.

Original source CSV hashes and output split hashes are in the manifest. Changes are local,
uncommitted and not pushed. No assistant contribution/co-author attribution is added.
