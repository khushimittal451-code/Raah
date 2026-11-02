# Virtual controller implementation and test report

Status: PASS for the executed safety checks. Generated UTC: 2026-11-01T22:30:39.654452+00:00.
Python: 3.12.14. Existing project venv; no dependency installs, servers, network requests, physical infrastructure or hardware adapters used.

## Implemented

- simulation/controllers.py: FixedTimeController, RuleOnlyAdaptiveController and MLAdaptiveController share a deterministic six-phase state machine and immutable config/state/action contracts.
- Defaults: min_green=15s, max_green=60s, yellow=3s, all_red=1s, fixed_green=30s, max_red_wait=75s, extension_step=5s. Protected pedestrian entry/clearance is 7+8s. See VIRTUAL_CONTROLLERS.md for strict ranges, feasibility equations, precedence, initial-state and through-only assumptions.
- Both axes get recurring service even with zero reported queues. Fairness bounds continuous red time (including yellow/all-red); it does not promise a maximum individual queue delay under overload.
- Current-queue pressure is supplemented only by bounded, finite, timely, complete ML estimates. Invalid/missing estimates atomically use queue-only rules. No prediction commands a phase directly.
- Every accepted simulation second logs the action/reason, exact queues, phase/timing, red ages, pedestrian state, pressures and valid model evidence/version. Invalid input calls are rejected transactionally.
- simulation/compare_controllers.py provides a paired, new-synthetic-demand comparison and an independent trace/inventory audit.

Existing generate_data.py, its raw exports, training code, saved model bundles and held-out test usage ledger were not modified or regenerated. Model pipelines were used for inference only. This controller work is separate from the frontend and API; no signal-command endpoint was added. Syllabus status remains UNVERIFIED.

## Executed commands and outputs

From the Desktop raah repository:

```powershell
$env:TEMP=(Resolve-Path work/tmp).Path
$env:TMP=$env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_controllers.py tests/test_controller_comparison.py -q --basetemp=work/tmp/controllers-verified
.\ml-service\.venv\Scripts\python.exe simulation/compare_controllers.py
.\ml-service\.venv\Scripts\python.exe simulation/compare_controllers.py --output-dir work/controllers-repro
git diff --check
```

Pytest output:

```text
........................................................................ [ 38%]
........................................................................ [ 76%]
.............................................                            [100%]
189 passed in 3.18s
```

Coverage includes all six phases, exact fixed boundaries, green minimum/maximum, every yellow/all-red transition, conflicting movement exclusion, protected pedestrian walk/clearance, zero queues, saturated asymmetric queues, changing demands, seed-57 randomized inputs, deadline precedence and tight feasible fairness. There are 60 parametrized 700-second traces plus an enumeration of all 576 combinations in a bounded timing/controller grid at 100 seconds each: at least 99,600 checked ticks in these two tests alone. This is exhaustive for the stated finite grid, not a formal certification of every possible configuration or real road.

Additional cases cover invalid/infeasible configuration, malformed queues, skipped/duplicate clocks and unchanged state on rejection, malformed/missing/stale/future/mixed-version forecasts, wrong horizon, NaN/Inf/negative/oversized regression outputs, unknown classes, wait-bonus cap, ML weight zero, immutable action evidence, deterministic JSONL, conservation, censored/empty-wait metrics, missing-model reproducibility and independence from offline train/validation/test files. Negative-output fallback is verified against the exact queue-only trace. Deliberately corrupted traces are rejected by the independent auditor. Tests use new synthetic fixtures and explicit estimator doubles, not fabricated reported model performance.

Initial 160 safety cases passed; expanded comparison/grid/evidence tests brought the suite to 189 passing cases. No controller invariant failure was observed during this implementation, so no failing safety case remains to repair.

Actual 15-rollout execution summary:

```text
rollouts 15
violations 0
model availability {'classification': True, 'regression': True}
ML fallback seconds 620
maximum red 68
PASS: all 17 output files byte-equivalent on repeat with seed 57, including model-backed action logs.
```

The byte comparison covered comparison.csv, summary.json and all 15 action-log files. It compared bytes after reexecuting the model-backed demonstration into a second directory; it did not compare only summaries. Same-environment reproducibility is demonstrated, not cross-platform binary identity. Git diff --check passed, with only a standard LF-to-CRLF conversion notice for README.md.

## Paired synthetic results

Each policy receives identical arrivals/noise within each scenario, generated from seed 57. Each run lasts 600 seconds. These are **15 new demonstration rollouts, one demand stream per scenario**, not an independent multi-seed statistical performance study. The toy simulator starts vehicles at queues and differs from the training generator. The real frozen KNN/polynomial pipelines are loaded using the existing artifact/hash/feature checks, without refitting or reading held-out observations.

| Scenario | Policy | Throughput | Mean total queue | Restricted mean wait (s) | Max red (s) | Violations |
|---|---|---:|---:|---:|---:|---:|
| low | FixedTime | 111 | 2.67 | 14.29 | 38 | 0 |
| low | RuleOnlyAdaptive | 111 | 1.98 | 10.61 | 23 | 0 |
| low | MLAdaptive | 110 | 2.21 | 11.82 | 28 | 0 |
| medium | FixedTime | 441 | 16.11 | 21.01 | 38 | 0 |
| medium | RuleOnlyAdaptive | 442 | 17.91 | 23.35 | 28 | 0 |
| medium | MLAdaptive | 442 | 16.31 | 21.27 | 28 | 0 |
| high | FixedTime | 628 | 266.12 | 139.33 | 38 | 0 |
| high | RuleOnlyAdaptive | 521 | 310.67 | 162.65 | 38 | 0 |
| high | MLAdaptive | 519 | 313.24 | 164.00 | 38 | 0 |
| asymmetric_rush_hour | FixedTime | 361 | 50.85 | 73.70 | 38 | 0 |
| asymmetric_rush_hour | RuleOnlyAdaptive | 412 | 14.21 | 20.59 | 68 | 0 |
| asymmetric_rush_hour | MLAdaptive | 409 | 13.20 | 19.13 | 68 | 0 |
| incident | FixedTime | 549 | 63.95 | 59.86 | 38 | 0 |
| incident | RuleOnlyAdaptive | 469 | 96.86 | 90.66 | 33 | 0 |
| incident | MLAdaptive | 471 | 96.02 | 89.88 | 38 | 0 |

Restricted mean wait = queued vehicle-seconds / all arrivals during the finite run. It includes waiting accumulated by unfinished vehicles up to the horizon, but not their eventual future delay. Completed-vehicle means and ending/max queues are also saved in comparison.csv; completed-only waits have censoring bias. Throughput is the number of departed vehicles. Maximum red is independently reconstructed from phase traces, including a whole red interval when green returns.

Both adaptive policies help the asymmetric scenario in this small demonstration, but fixed-time gives higher throughput and lower restricted waiting in high demand and incident scenarios. These results do not justify claiming adaptive superiority or control readiness. No settings were tuned using these outcomes. Queue growth under overload is possible despite bounded red intervals.

ML fallback status counts (of its 3,000 simulated seconds):

```json
{
  "fallback_queue_only: negative_future_wait_seconds": 620
}
```

All 620 fallback seconds came from at least one rejected negative waiting-time estimate in the four-approach forecast batch. They are explicit queue-only fallback decisions; no negative estimate was clipped or replaced by invented model output. The forecast calls themselves did not fail. Predicted class labels remain derived-label model estimates; they are not independently measured traffic ground truth.

One actual logged ML extension, with its exact accepted prediction evidence:

```json
{
  "action": "EXTEND",
  "controller": "MLAdaptiveController",
  "ew_pressure": 3.037999025097392,
  "ns_pressure": 7.41705584411158,
  "pedestrian_axis": null,
  "pedestrian_state": "dont_walk",
  "phase": "ns_green",
  "planned_green_seconds": 20,
  "prediction_inputs": [
    {
      "approach": "north",
      "congestion_level": "LOW",
      "future_wait_seconds": 15.623129808321828,
      "generated_at_seconds": 160,
      "prediction_horizon_seconds": 60
    },
    {
      "approach": "south",
      "congestion_level": "LOW",
      "future_wait_seconds": 17.74133772060457,
      "generated_at_seconds": 160,
      "prediction_horizon_seconds": 60
    },
    {
      "approach": "east",
      "congestion_level": "LOW",
      "future_wait_seconds": 1.479850360701839,
      "generated_at_seconds": 160,
      "prediction_horizon_seconds": 60
    },
    {
      "approach": "west",
      "congestion_level": "LOW",
      "future_wait_seconds": 1.5600716470894938,
      "generated_at_seconds": 160,
      "prediction_horizon_seconds": 60
    }
  ],
  "prediction_model_version": "e3605e36e02326835d0e762e6a0ddb5cba435968523c74988bd4f6516155f85c",
  "prediction_status": "valid_bounded_ml_supplement",
  "previous_phase": "ns_green",
  "queues": [
    4,
    3,
    2,
    1
  ],
  "reason": "active_pressure_higher_bounded_extension",
  "red_seconds": [
    0,
    19
  ],
  "seconds_in_phase": 15,
  "timestamp_seconds": 167,
  "virtual_only": true
}
```

## Files and practical limits

- docs/VIRTUAL_CONTROLLERS.md: full usage, safety/fairness derivation, pedestrian and prediction contract.
- artifacts/controller_demo/comparison.csv: all measured virtual comparison metrics.
- artifacts/controller_demo/summary.json: configuration, loaded model version/hashes, availability and call failures.
- artifacts/controller_demo/<scenario>_<controller>.jsonl: complete per-second reason logs.
- work/controllers-tests.txt and work/controllers-comparison-output.json: command transcripts.

No physical signals, real GPS, paid traffic services, RL or deep learning are used. Pedestrian safety depends on the explicitly modeled parallel crossing, no turns, no late WALK entry and complete clearance before yellow; no crossing-distance or real-road calibration is asserted. Maximum red is a service-opportunity guarantee on the consecutive simulation clock, not wall-clock resilience or a per-vehicle delay bound. Frontend integration, richer pedestrian requests and a calibrated multi-seed controller study are outside this change.
