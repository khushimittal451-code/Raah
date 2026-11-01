# Synthetic junction generation report

Date: 2026-11-02 (Asia/Calcutta). Working project: Desktop `raah`.

## Outcome

Implemented and ran `simulation/generate_data.py` for a synthetic four-approach junction.
Thirty independent runs use master seed **57** and distinct derived run seeds, with six
rollouts per scenario: low, medium, high, asymmetric rush-hour-like demand and incident.
Each labeled window covers t=0..1200 seconds on a 10-second grid; the simulator runs at
1-second resolution through t=1260 for complete, exact 60-second target generation.

No live GPS, real private trajectories, paid APIs, physical signals, RL or deep learning
are used. Counts/queues/waiting are simulator truth; noisy sampled speeds are explicitly
synthetic GPS-like aggregates. A fixed-time virtual signal plan is implemented as a
baseline, with no adaptive controller or claim of real-world safety/calibration.
All provisional syllabus topics remain UNVERIFIED.

## Commands and actual output

Run from the project root using the existing Python 3.12 service venv; no packages added.

```powershell
.\ml-service\.venv\Scripts\python.exe simulation/generate_data.py
```

```json
{
  "class_balance": {
    "high": 6044,
    "low": 6985,
    "medium": 1491
  },
  "files": {
    "phase_events.csv": "C:\\Users\\Hrishit Vats\\OneDrive\\Desktop\\raah\\ml-service\\data\\phase_events.csv",
    "run_metadata.csv": "C:\\Users\\Hrishit Vats\\OneDrive\\Desktop\\raah\\ml-service\\data\\run_metadata.csv",
    "traffic_observations.csv": "C:\\Users\\Hrishit Vats\\OneDrive\\Desktop\\raah\\ml-service\\data\\traffic_observations.csv",
    "traffic_sample.csv": "C:\\Users\\Hrishit Vats\\OneDrive\\Desktop\\raah\\ml-service\\data\\traffic_sample.csv",
    "traffic_source_snapshots.csv": "C:\\Users\\Hrishit Vats\\OneDrive\\Desktop\\raah\\ml-service\\data\\traffic_source_snapshots.csv"
  },
  "independent_runs": 30,
  "labeled_rows": 14520,
  "master_seed": 57,
  "phase_event_rows": 3061,
  "sample_rows": 20,
  "scenario_runs": {
    "asymmetric_rush_hour": 6,
    "high": 6,
    "incident": 6,
    "low": 6,
    "medium": 6
  },
  "source_snapshot_rows": 15240
}
```

```powershell
$env:TEMP = (Resolve-Path work/tmp).Path
$env:TMP = $env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_generate_data.py -q
```

```text
........................                                                 [100%]
24 passed in 4.41s
```

```powershell
.\ml-service\.venv\Scripts\python.exe -m pytest -q -o faulthandler_timeout=15
```

```text
........................................................................ [ 33%]
........................................................................ [ 66%]
........................................................................ [ 99%]
..                                                                       [100%]
218 passed in 4.89s
```

All final commands exited 0. `git diff --check` passed. Tests use project-local temporary
storage; the existing API tests need Windows asyncio loopback permission. The generator
and its tests do not access any traffic service, and no servers are started here.

## Class balance (rule-derived current congestion)

| Class | Rows | Share |
| --- | ---: | ---: |
| low | 6,985 | 48.11% |
| medium | 1,491 | 10.27% |
| high | 6,044 | 41.63% |

This is intentionally not a balanced benchmark. Demand archetypes are scenario metadata,
not the congestion target. Labels apply the existing congestion-v1 thresholds; predicting
that label from its defining inputs measures rule imitation, not independent empirical
congestion accuracy. Future wait is the exact matching source snapshot's queue wait at
t+60, not a next-minute average or total travel delay. No model metrics are reported.

## Export sizes and SHA-256

The byte-reproducibility test independently generates the complete default dataset twice
in different directories and compares SHA-256 for every export. All five match. Paths
below are relative to `ml-service/data/`; absolute paths were printed by the generator.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `phase_events.csv` | 90,195 | `85bd0180a6cc41fbee9017fad124630ae2e47ebeced25806053fdc6644df871f` |
| `run_metadata.csv` | 25,443 | `895e7b3a234335586c3ddb26804b9210377f4862a7d00f0988f8fd1bc8ebe546` |
| `traffic_observations.csv` | 1,405,338 | `627a17465cc4b86b579305cddd2c7d2d00e5f7aa4dd06b2cf8f68597c6a4c554` |
| `traffic_sample.csv` | 2,259 | `63a54df7686aae0e62db91aa9d1c6ad4b6187b1f97df6c0a4bfd48d0b6ec8403` |
| `traffic_source_snapshots.csv` | 1,320,852 | `f9d24d3e1e258661be07d18014837277861fbb5ee1b8f4346120dc44cbdc21d0` |

`traffic_observations.csv` has 14,520 fully labeled records. `run_metadata.csv` has 30
metadata/config rows. `traffic_sample.csv` has 20 representative midpoint rows across
all five scenarios. The additional `traffic_source_snapshots.csv` has 15,240 current-only
records, retaining future-label evidence; `phase_events.csv` has 3,061 transition events,
so clearance intervals shorter than the aggregate window can be audited.

## Invariants tested and repair

The 24 generator cases test all exported rows against canonical Pydantic bounds, count
and queue/sample consistency, per-run time order, unique IDs/seeds, all four approaches,
per-window inventory conservation, exact future joins, finite initial state and required
provenance. They verify every event follows the six-phase sequence with full 3s yellow
and 2s all-red clearance, validated green durations, 2s startup loss, no conflicting-axis
departures and periodic green service opportunities. Saturation-budget and fully backlogged
phase tests verify both no extra service and realization of fractional discharge capacity.

Scenario tests verify actual arrival/queue differences, asymmetric pulse shape, and
incident-induced reduced discharge under matched arrivals. GPS sampling changes do not
change traffic because it has an independent random stream. Invalid timings/configuration,
fewer than 30 runs and unsupported master seeds are rejected. Every CSV is byte-identical
on seeded repeat generation under the same code/Python/NumPy environment.

Review identified a service-credit error before final validation: clipping accumulated
credit at one would discard its fractional remainder and incorrectly quantize saturation
rates. Preserved that remainder, added a backlogged-capacity regression test, regenerated
all output files, and reran the 24 generator tests plus the full 218-test suite successfully.
The counts/hashes above reflect the repaired generator, not its initial draft.

## Interpretation and remaining work

- This is a small FIFO point-queue educational model with through movements only. It lacks
  calibrated car-following, finite approach storage/spillback, turns, pedestrians, routing
  and real sensors. Arrivals can exceed capacity, so residual queues and long waits are
  expected; bounded green opportunities do not guarantee bounded per-vehicle delays.
- The asymmetric scenario compresses a rush-hour-like demand pulse into the synthetic
  window beginning at synthetic midnight; it is not a real geographic/time-of-day trace.
- Configuration, per-run seed, versions, generator code hash and signal policy are retained
  in metadata. Reproduction assumes the same recorded versions/source bytes. Cross-version
  bit-for-bit equivalence is not promised; the explicit requirement is tested in this environment.
- Split by independent run before any preprocessing, model selection or tuning. Keep each
  run's four approaches, correlated snapshots and future-label look-ahead together; hold
  out archetypes for stronger scenario generalization. Metadata and targets are not features.
- No training, preprocessing fitting, adaptive signal optimization or model comparison was
  performed. Those later stages require their own leakage and controller-invariant tests.
- Files are saved in the Desktop project, uncommitted and not pushed. No assistant
  contribution/co-author attribution was added. Existing schema/API/client files are preserved.

See `simulation/README.md` for exact mechanics and configurable limits, and
`docs/DATA_DICTIONARY.md` for field/target semantics.
