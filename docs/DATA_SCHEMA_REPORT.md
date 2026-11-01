# Data contract verification report

Date: 2026-11-02 (Asia/Calcutta). Project: Desktop `raah`.

## Delivered

- `docs/DATA_DICTIONARY.md`: all 16 current-time fields and both labels, units, bounds,
  synthetic provenance, observed-proxy versus simulator-truth distinctions, and leakage risks.
- `ml-service/app/schemas.py`: strict `TrafficObservation`, `LabeledTrafficRecord`,
  `RunProvenance`, and `LabeledRun` Pydantic models; deterministic `congestion-v1` and
  exact grouped future-snapshot labeling helper.
- `ml-service/data/schema.json`: generated Draft 2020-12 structural schema, rooted at
  the provenance-plus-records run envelope, with standalone model definitions in `$defs`.
- `ml-service/export_schema.py`: repeatable export from the canonical Pydantic models.
- `tests/test_data_schema.py`: 190 parameterized contract checks.

Rows use a 10-second synthetic snapshot grid and a 60-second exact future-wait horizon.
Seed is fixed at 57 in run provenance. Missing GPS-like speed is explicitly null only
when there are no sampled vehicles. Labels with unavailable future snapshots are censored,
not filled with zero. The current congestion rule is inclusive and evaluates high before
medium. It is a toy operational index, not independent empirical traffic ground truth.

## Checks executed

Environment: existing Python 3.12.14 service venv, Pydantic 2.14.2, pytest 9.2.0.
No new dependencies installed. Commands ran in PowerShell from the Desktop project root.

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/export_schema.py
.\ml-service\.venv\Scripts\python.exe -c "import json; from pathlib import Path; s=json.loads(Path('ml-service/data/schema.json').read_text()); print('JSON Schema parsed:', s['title'])"
```

```text
Exported ...\raah\ml-service\data\schema.json
JSON Schema parsed: Raah synthetic traffic run, schema 1.0.0
```

```powershell
$env:TEMP = (Resolve-Path work/tmp).Path
$env:TMP = $env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_data_schema.py -q
```

```text
........................................................................ [ 37%]
........................................................................ [ 75%]
..............................................                           [100%]
190 passed in 0.25s
```

```powershell
.\ml-service\.venv\Scripts\python.exe -m pytest -q -o faulthandler_timeout=15
```

```text
........................................................................ [ 37%]
........................................................................ [ 74%]
..................................................                       [100%]
194 passed in 0.52s
```

Both final test commands exited 0, with no warnings. Outputs were captured using
`Tee-Object` in ignored `work/schema/`. `git diff --check` also exited 0.

## Coverage and fixes

Tests exercise missing fields for every observation and provenance field and both targets;
negative/oversized/nonfinite values, strings/booleans instead of numbers, fractional counts,
invalid identifiers/phases, zero free-flow reference, null handling, queue/sample subset
constraints, timestamp grid and synthetic clock rollover, empty initial inventory,
congestion threshold boundaries and sparse-count gating, target consistency, wrong
run/intersection/approach and wrong horizons, constant free-flow configuration, duplicate
keys, intersection phase consistency, inference target exclusion and JSON export parity.

The first schema run found Pydantic literal-number equality accepted `seed=57.0` as `57`.
Added before-validation requiring exact integer types for seed, interval and horizon.
Regression cases now cover all three constants. Final schema run: 190 passed.

The first broader run stalled in existing health tests. A faulthandler trace located
Windows asyncio's loopback socketpair setup under restricted network access. Interrupted
the stalled test runs; reran with network permission for loopback setup. No health-test
source change, external service, login or browser authorization was needed. Final full
suite: 194 passed. These are in-process API tests; no test servers were started in this task.

## Limits

The JSON file is generated from and checked for exact parity with the canonical models;
this task does not claim independent third-party JSON Schema validator testing. Generic
JSON Schema checks structure and per-field bounds; Pydantic enforces arithmetic and
cross-field invariants. Label generation additionally needs the matching t+60 snapshot.
An isolated labeled row cannot prove future-label provenance. Declared synthetic metadata
cannot prove actual data origin. The future generator must retain source snapshots and
versioned configuration for audit.

No synthetic generator, ML training, preprocessing pipeline or virtual controller is
implemented by this task. Flow conservation, queue membership history, group-split
execution and temporal signal safety require later implementation and tests. Thresholds,
bounds, and queue definitions are explicit provisional simulation assumptions. Current
congestion evaluation with its defining inputs measures rule imitation; future waiting
is a separate forecasting target. Every syllabus topic remains UNVERIFIED.

Changes are saved locally, uncommitted and not pushed. Existing Phase 1 work is preserved;
there is no assistant contributor or co-author attribution.
