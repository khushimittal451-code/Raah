# Synthetic traffic data dictionary â€” schema 1.0.0

Raah uses **synthetic data only**, with seed **57**. No real private GPS, geographic
coordinates, paid traffic feeds, or physical signal integration is permitted. The
contract defines data to implement next; it does not establish that a generator,
trained model, empirical traffic measurement, or safe controller already exists.
All proposed syllabus topics remain **UNVERIFIED**.

## Record grain, clock and storage

One observation represents one inbound approach at one virtual intersection at snapshot
`t`. The unique key is `(run_id, timestamp_seconds, intersection_id, approach_id)`.
Snapshots use a **10-second grid**, including initialization `t=0`. Runs start at a
synthetic midnight; no real date, location, timezone, or personal identity is recorded.
Runs may span up to seven synthetic days (604800 seconds). Flow counts cover `(t-10,t]`;
at `t=0` both flow counts are zero and vehicle inventory is initialized separately.

- `TrafficObservation`: all 15 current-time fields below, suitable for a future inference
  input. No target field is accepted here.
- `LabeledTrafficRecord`: the same required fields plus both required targets, for offline
  training/evaluation only. No field may be omitted or added; null is permitted only for
  `mean_speed_kmh`, and only when `gps_sample_count=0`.
- `RunProvenance`: required run-level companion metadata.
- `LabeledRun`: primary storage document, `{ "provenance": {...}, "records": [...] }`,
  with at least one labeled row. It binds every row to the metadata's run ID and rejects
  duplicate keys, inconsistent same-time intersection phases, and changing free-flow
  configuration within a run/approach. A partial record list is permitted; completeness
  and flow conservation require the eventual simulation validator.

The canonical runtime models are `ml-service/app/schemas.py`. The generated
`ml-service/data/schema.json` is Draft 2020-12, rooted at `LabeledRun`. Its `$defs` also
expose the standalone observation, labeled record and provenance contracts. Export with:

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/export_schema.py
```

JSON Schema enforces structural requirements, enumerations and individual bounds.
Pydantic additionally enforces cross-field arithmetic and label consistency. A generic
JSON Schema validator alone does **not** enforce these Python validators or an exact
future-row join. Reject numeric strings, booleans as numbers, NaN and infinity at runtime.
Bounds below are **toy simulation contract limits**, not real-world safety parameters.

## Observation fields (all required)

| Field | Type / units / accepted range | Meaning and source provenance |
| --- | --- | --- |
| `run_id` | string, 1â€“64 ASCII letters/digits/underscore/hyphen; first character alphanumeric | Independent synthetic rollout ID, from run configuration. Primary split group, never a model input. Related copies/derivatives must retain this group or share a higher-level scenario-family split. |
| `timestamp_seconds` | integer seconds, 0â€“604800, multiple of 10 | Snapshot time on the synthetic simulator clock. Metadata for joining and ordering; not a default predictor. |
| `intersection_id` | same identifier format as run_id | Abstract simulated junction ID. No GPS coordinate. Group/location metadata, not a default predictor. |
| `approach_id` | `north`, `south`, `east`, `west` | Abstract inbound direction, from network configuration. All approaches of an intersection share the intersection phase state at a given t. |
| `mean_speed_kmh` | finite number, 0â€“160 km/h, or required null | Arithmetic mean of valid synthetic speed samples for currently present vehicles. At most one latest sample per vehicle within the trailing 10-second window; initialization can sample at t=0. A GPS-like observed proxy, not real GPS. Null iff sample count is zero. May exceed configured free-flow speed; do not silently clip the ratio. |
| `free_flow_speed_kmh` | finite number, >0â€“160 km/h | Configured uncongested reference speed, fixed for each run/intersection/approach. Never estimate it from validation/test outcomes. |
| `vehicle_count` | integer vehicles, 0â€“10000 | Total approach inventory at t, from simulator truth or an explicitly simulated counter, not the number of GPS samples. |
| `queue_length_vehicles` | integer vehicles, 0â€“10000 and <= vehicle_count | Queued subset of inventory from simulator state. Queue membership: vehicle has remained below 1 km/h for at least 5 consecutive simulated seconds; queued waiting accumulates while that membership persists. This operational definition must be versioned with the future generator. |
| `mean_wait_seconds` | finite number seconds, 0â€“3600 | Mean elapsed queue-membership duration of vehicles queued at t, from simulator state. Zero if no vehicles are queued; a newly queued vehicle can have zero elapsed wait. Not average lifetime journey delay or mean over vehicles that already departed. |
| `incoming_vehicles` | integer vehicles/window, 0â€“10000 | Approach boundary entries during (t-10,t], from simulator transition counters; zero at t=0. May exceed current inventory if vehicles also exited. |
| `outgoing_vehicles` | integer vehicles/window, 0â€“10000 | Approach boundary exits during (t-10,t], from simulator transition counters; zero at t=0. Not a future discharge estimate. |
| `current_phase` | enumerated string, see phases below | Intersection-wide virtual signal state at t, from simulator/controller state. Not inferred from speed and not a physical signal command. |
| `seconds_in_phase` | finite number seconds, 0â€“3600 and <= timestamp_seconds | Elapsed duration since the virtual intersection entered its current phase; starts at zero. It must match across approaches at the same t. The upper bound is a data-validation cap, not an allowed green duration. |
| `time_of_day` | finite fractional hour, 0 <= value < 24 | Derived only from `(timestamp_seconds / 3600) % 24`; absolute tolerance 1e-6 hours. It is a synthetic clock covariate, not the computer's local time. |
| `gps_sample_count` | integer sampled vehicles, 0â€“10000 and <= vehicle_count | Number of distinct currently present vehicles with one usable synthetic speed sample in the window. A sample-coverage indicator; not packet count and not total traffic count. |

A zero-vehicle snapshot consequently has zero queue, zero sample count, null speed and
zero mean wait. A nonempty approach may have no GPS-like samples: keep speed null and
retain queue/wait truth rather than inventing zero speed. Do not impute inside schema
validation. The later preprocessing pipeline must learn imputations on training data only.

For complete adjacent snapshots of the same approach, the simulator must satisfy
`vehicle_count(t) = vehicle_count(t-10) + incoming_vehicles(t) - outgoing_vehicles(t)`
with no uncounted sources/sinks. The current row validators cannot prove cross-window
inventory conservation, queue membership history or the validity of the speed sampling.

## Virtual phases and temporal safety

Allowed values in order:

`ns_green -> ns_yellow -> all_red_to_ew -> ew_green -> ew_yellow -> all_red_to_ns -> ns_green`.

The four inbound approaches share this intersection state. A phase alone does not
specify permitted turns: the future virtual movement/conflict configuration must define
those explicitly. The schema checks vocabulary and instantaneous consistency only.
Actual safe transitions require the later constrained rule-based controller and temporal
invariant tests, including minimum/maximum green, yellow/all-red clearance, incompatible
movement exclusion, starvation bounds and invalid-input fallback. A 10-second aggregate
stream may miss shorter intermediate phases, so it cannot certify transition safety;
retain a finer-grained simulator event log when that controller is implemented.

## Targets and label generation

| Target | Type / units / horizon | Label source |
| --- | --- | --- |
| `congestion_level` | `low`, `medium`, `high`; current t (zero prediction horizon) | Deterministic `congestion-v1` operational index from the current synthetic observation, as defined below. It is not an independently measured ground-truth class. |
| `future_wait_seconds` | finite number seconds, 0â€“3600; exact **60-second** horizon | The matching future snapshot's `mean_wait_seconds` at t+60 for the same run/intersection/approach. This is the future mean elapsed queue wait, not the integral or average of wait over the next minute. |

For `congestion-v1`, compute `r = mean_speed_kmh / free_flow_speed_kmh` only when speed
is present. Evaluate **high first**, then medium, otherwise low:

1. **high** if queue >= 10 vehicles, or mean wait >= 60 seconds, or
   (`vehicle_count >= 5` and a valid r <= 0.35).
2. **medium** if queue >= 5 vehicles, or mean wait >= 30 seconds, or
   (`vehicle_count >= 5` and a valid r <= 0.70).
3. **low** otherwise. With missing speed, skip the ratio branch and use queue/wait.
   These thresholds and comparisons are inclusive; the high branch takes precedence.

The count gate prevents speed alone from declaring sparse/empty traffic congested.
A sparse approach can still have long waits and be classified high. Thresholds are
provisional toy assumptions, must not be tuned against test data, and are versioned;
changing them creates a new label rule and requires regenerated labels.

`label_observation(current, future)` implements the current rule and future join. It
rejects mismatched run/intersection/approach IDs, any horizon other than exactly 60 seconds,
and changing free-flow configuration. No nearest-time match, cross-run shift, forward fill,
interpolation, missing-future zero or extrapolation is allowed. If the complete t+60
snapshot is unavailable, retain the unlabeled observation but **exclude it from the
fully labeled dataset**. Thus the last 60 seconds of a finite run are censored for this
contract. A fully labeled row cannot encode unknown future wait as null.

An isolated labeled row can verify its current congestion class but cannot prove that
future wait came from a valid future snapshot. Generate labels through the helper and
retain source observations plus run metadata for audit. The future rollout policy and
configuration must be fixed/documented by generator version and scenario ID; it must
not secretly use future predictions or information unavailable at t.

## Run-level provenance (all required)

| Metadata | Contract |
| --- | --- |
| `run_id`, `scenario_id` | Same identifier rules as above; every stored row matches run_id. Scenario ID resolves to a retained, versioned generator configuration. Related scenario families need shared split assignments to prevent near-duplicate leakage. |
| `source_kind` | Exactly `synthetic`; no measured/private/paid source option. |
| `generator_version` | Nonempty version/commit string, <=128 characters, of the actual generator or explicit test fixture. Do not present a fixture as a production simulation. |
| `schema_version` | Exactly `1.0.0`. |
| `seed` | Exactly integer 57; derive and record any per-run random streams deterministically from this seed and configuration. |
| `observation_interval_seconds` | Exactly integer 10. |
| `prediction_horizon_seconds` | Exactly integer 60. |
| `label_rule_version` | Exactly `congestion-v1`. |

The configuration referenced by scenario ID must retain topology, approach lengths,
arrival process, free-flow speeds, sampling/dropout/noise, queue-definition parameters,
signal timing and baseline policy. Record code/dependency versions and content hashes
with experiment artifacts. The schema restricts declared provenance; it does not prove
that submitted values were actually generated synthetically.

## Observed proxies versus simulated truth

No field in this project is an actual measured real-world traffic signal. Speed and
sample coverage are **synthetic GPS-like observed proxies**. Counts, queue membership,
waiting time and flows are **simulator truth or explicitly simulated sensor aggregates**;
phase and elapsed phase time are **virtual controller state**; free-flow speed is
**configuration**; time_of_day is **derived clock information**; labels are **derived
oracle outcomes**. GPS speed alone does not directly measure total queue length, waiting
time, flows or traffic inventory. Experiments using those oracle covariates must say so
and must not claim GPS-only deployment performance. Missing samples do not imply no traffic.

## Leakage and evaluation rules

- Split by independent `run_id` before fitting transformations, tuning or model selection;
  keep all approaches, windows, duplicates and label look-ahead from a run together. Use
  a broader scenario-family group for correlated/reused rollout variants. Persist the
  split mapping. Never randomly split individual rows from one rollout across folds.
- Fit imputation, scaling, polynomial features, PCA, outlier thresholds and selection
  on training groups only, inside each grouped validation fold. No test-derived free-flow
  speeds, summary statistics, or label thresholds. Use grouped cross-validation.
- Inference accepts **only TrafficObservation**. Exclude both targets, all future rows,
  future phases/actions, future realized flows and full-run summary statistics from input.
  run/intersection identifiers and timestamp are metadata by default. Time-of-day and
  controller-state covariates may confound scenario/policy effects; report generalization
  limitations. Future wait uses a fixed known rollout policy, not clairvoyant future controls.
- Current congestion is a deterministic function of speed, reference speed, count, queue
  and wait. Training on these features chiefly measures rule imitation; a direct-rule
  baseline reproduces the label exactly. Never call that independent congestion discovery
  or empirical accuracy. For genuine forecasting, use the future-wait target and report
  MAE/RMSE in seconds, a persistence baseline (`mean_wait_seconds(t)`), and per-run results.
- Do not interpret future wait as per-vehicle delay, total travel time or a traffic-safety
  objective. Report units, censoring, missing-sample rates, bounds and synthetic assumptions.
  Group separation protects look-ahead overlap; it does not establish realism or causal
  controller benefits. Controller comparisons require matched seeded simulations later.

## Tests and present limits

Schema tests cover required fields, strict types, finite ranges, snapshot consistency,
label boundaries, exact grouped future joins, run provenance and generated JSON parity.
No generator or ML training pipeline is introduced here, and no model metrics are claimed.
See `docs/DATA_SCHEMA_REPORT.md` for executed checks and actual results.

## Implemented synthetic generator

`simulation/generate_data.py` now implements this contract with 1-second virtual steps
and 10-second aggregates. `traffic_observations.csv` is the complete labeled window;
`traffic_source_snapshots.csv` retains the extra 60 seconds needed for audit. Metadata
and phase-entry logs are saved alongside them. The earlier implementation-status text
above describes the contract-design stage; see `simulation/README.md` and
`docs/SYNTHETIC_DATA_REPORT.md` for the generator's present scope and checks. The phase
plan is a fixed-time virtual baseline, not an adaptive controller or a real signal system.
