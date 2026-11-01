# Synthetic virtual junction generator

`generate_data.py` implements a **synthetic, single-junction, four-approach point-queue
simulation**, not live GPS, a calibrated traffic model, or physical traffic control.
It uses only through movements; no turns, pedestrians, lane changes, spillback, network
routing, real GPS coordinates, paid services, RL or deep learning are included.
All provisional syllabus topics remain UNVERIFIED.

## Generate from the repository root

```powershell
.\ml-service\.venv\Scripts\python.exe simulation/generate_data.py --seed 57 --runs 30 --duration-seconds 1200
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_generate_data.py -q
```

The CLI defaults to `ml-service/data/`, prints absolute file paths, row counts and class
balance, and overwrites only its five named generated CSVs on rerun. Use `--output-dir`
to compare another export. It preserves `schema.json` and other project files.
At least 30 runs are required; supported counts are 30–1000. Each labeled run spans
0–1200 seconds inclusive by default; durations must be multiples of ten in [120,3000].
The upper limit keeps this deliberately small experiment within the existing schema bounds.

## Export contract

| CSV in ml-service/data | Contents for default settings |
| --- | --- |
| `traffic_observations.csv` | 14,520 fully labeled rows: 30 runs x 121 snapshots x 4 approaches, including congestion_level and future_wait_seconds. |
| `run_metadata.csv` | 30 rows: canonical provenance plus independent run seed, scenario, all configuration parameters as sorted JSON, counts, policy, generator SHA-256, Python and NumPy versions. |
| `traffic_sample.csv` | 20 labeled rows: the four approaches at t=600 from the first run of each scenario. |
| `traffic_source_snapshots.csv` | 15,240 unlabeled source observations through t=1260, allowing every exact 60-second target join to be audited. |
| `phase_events.csv` | Each phase-entry event, including t=0, and its planned duration; preserves yellow/all-red intervals shorter than the observation interval. |

The main CSV implements `LabeledTrafficRecord`; the source CSV implements
`TrafficObservation`. A blank speed cell means no GPS-like samples, not zero speed.
Metadata is a superset of `RunProvenance`: extract its nine canonical columns when
validating that Pydantic model, as other audit/config columns are intentionally separate.
See [data dictionary](../docs/DATA_DICTIONARY.md) for exact units, label rules and bounds.

The generator simulates **60 additional seconds** beyond the exported labeled window;
those tail snapshots are saved only as source observations. Labels therefore have no
missing-horizon imputation or cross-run shift. If later exporting the final source tail
as labeled data, it must be censored unless more future snapshots are simulated.
Congestion classes are a deterministic rule-derived index, not independently measured
traffic ground truth. Do not call rule-reproduction performance empirical congestion accuracy.

## Mechanics and assumptions

- A 1-second internal step drives independent Poisson arrivals. Per-run rates and reference
  speeds, lengths, sampling coverage and timings vary. Entry-to-stop-line travel time
  has bounded jitter. Vehicles follow FIFO order without overtaking.
- After arriving at the stop line, vehicles are stopped while awaiting service. They
  become queue members after 5 seconds below 1 km/h; reported waiting is time since
  membership began, matching the dictionary. Moving vehicles remain in approach inventory.
- A fixed-time virtual baseline alternates `ns_green -> ns_yellow -> all_red_to_ew ->
  ew_green -> ew_yellow -> all_red_to_ns`. Greens are sampled once per run in [25,40]
  seconds, within validated [20,45] limits. Yellow is 3 seconds, all-red 2 seconds and
  green startup loss 2 seconds. No departures occur in clearance phases or on the
  conflicting axis. Fractional service credit retains the remainder after discharge;
  no unused service credit accumulates across phases or empty queues.
- Saturation rates are 0.55–0.75 vehicles/second per approach, active only on its green.
  The clock-based phase plan gives both axes regular service opportunities. High demand
  can still grow queues; this is not a guarantee of bounded individual vehicle delay or
  an adaptive congestion-reduction controller. No real-world-safe timings are claimed.
- Low/medium/high base arrivals are approximately 0.035/0.17/0.43 vehicles/second per
  approach with independent per-approach variation. Asymmetric rush-hour profiles add
  a Gaussian pulse to one opposing axis. This is a compressed **rush-hour-like waveform
  within the synthetic run**, not actual rush-hour observations at a real location/time.
- Incident runs increase demand by 30% on one approach during 35–70% of the labeled
  duration, reduce its service capacity to 12%, and increase travel time by 80% for
  vehicles entering during the incident. The interval/approach are recoverable from config.
- GPS-like samples independently cover 35–85% of present vehicles per run. Each sampled
  moving speed has Gaussian noise (SD 6% of configured free-flow speed); stopped speed
  noise is clipped below 1 km/h. Values are synthetic aggregates, not individual GPS logs.
  Counts, queues and waiting are simulator truth, so the dataset is not GPS-only sensing.

## Reproducibility and splitting

Master seed is fixed at **57**, as required by the provenance contract. Each independent
run derives a distinct 64-bit seed with `SeedSequence([57, run_index])`; configuration,
traffic and GPS use separate child streams. Sampling changes cannot change traffic
arrivals or movements. No wall-clock timestamps, Python randomized hashes or unseeded
random calls enter exports. Fixed row/column order, newline convention and rounding
make all five CSVs byte-identical on rerun under the recorded Python/NumPy/code version.
Cross-version/platform binary equality is not promised; record versions and inspect
numerical equivalence before comparing environments.

Thirty default runs give six independent rollouts per scenario; scenario order cycles
through low, medium, high, asymmetric rush hour and incident. Keep every row and its
look-ahead within the same run group for train/validation/test splits; fit preprocessing
only on training groups. Do not use run seeds, scenario metadata or targets as features.
Use a held-out demand archetype when testing stronger scenario generalization.

Tests verify exported bounds/schema, time ordering, inventory conservation, future joins,
phase sequence/durations, conflicting-axis exclusion, startup clearance, actual fractional
capacity, incident discharge effects, demand diversity, independent sampling and byte
reproducibility. See [generation report](../docs/SYNTHETIC_DATA_REPORT.md) for measured
counts, hashes and command output. No model or controller benefit is evaluated here.
