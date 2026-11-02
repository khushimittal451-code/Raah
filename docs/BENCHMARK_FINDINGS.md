# Paired virtual benchmark findings

Status: executed. All models remain PROVISIONAL / UNVERIFIED.

Master seed 57; 5 independent derived run seeds per scenario, five scenarios, 75 policy rollouts. Every run has 180s warm-up and 600s measurement. Queues, phase state and fairness clocks continue through warm-up.

All arrival counts, capacity and synthetic aggregate-speed noise were generated and saved before any policy was run. Every policy replays the same hash-verified, read-only arrays for a trace. These are new FIFO point queues, not live GPS or held-out ML observations. No retraining, parameter tuning, physical control, RL, deep learning or paid APIs were used.

## Metrics and uncertainty

Primary mean/p95/max waits use vehicles arriving during measurement. Completed vehicles contribute their complete queue delay; unfinished vehicles contribute only waiting accumulated to the horizon and are explicitly right-censored. These are observed finite-horizon waits, not estimates of eventual completed delay. Completed-only mean/p95 are saved separately and have selection bias. The cohort wait sum equals the integral of that cohort's queue exactly (asserted). Mean/p95/max queues include warm-up backlog. Throughput counts all departures within measurement, including vehicles that arrived during warm-up; cohort completions are also saved separately.

Fairness includes maximum continuous axis red (yellow/all-red included), Jain's index of per-approach cohort completion fractions, minimum completion fraction and the approach mean-wait gap. Empty-demand approaches are omitted from Jain's index; no service or no demand produces an undefined index, never a fabricated perfect score. Red intervals overlapping measurement retain pre-warm-up ages; terminal red intervals are flagged as censored. Phase changes count every enum transition in measurement.

Each scenario/policy metric has run mean, sample standard deviation, min/max and a 95% percentile bootstrap interval (2000 resamples, seed 57). The resampling unit is an independent trace/run, not correlated vehicles or time rows. Paired deltas subtract the same-trace fixed baseline before resampling. Runs receive equal weight. 5 runs per scenario is a small exploratory sample: intervals do not establish general superiority, and no multiple-comparison correction or real-world validity is claimed.

## Results

Entries below are means across independent runs. Complete uncertainty is in summary.csv and paired_summary.csv.

| Scenario | Policy | Mean wait (s) | p95 wait (s) | Mean queue | Throughput | Censored fraction | Max red (s, worst run) |
|---|---|---:|---:|---:|---:|---:|---:|
| low | FixedTimeController | 14.237 | 37.910 | 2.321 | 94.600 | 0.025 | 38 |
| low | RuleOnlyAdaptiveController | 9.157 | 24.170 | 1.483 | 95.800 | 0.012 | 23 |
| low | MLAdaptiveController | 9.498 | 24.170 | 1.539 | 95.800 | 0.012 | 28 |
| medium | FixedTimeController | 21.549 | 43.340 | 17.958 | 491.800 | 0.033 | 38 |
| medium | RuleOnlyAdaptiveController | 35.038 | 69.610 | 29.269 | 479.600 | 0.064 | 43 |
| medium | MLAdaptiveController | 33.213 | 66.740 | 27.743 | 479.600 | 0.059 | 43 |
| high | FixedTimeController | 200.151 | 342.820 | 385.443 | 638.000 | 0.563 | 38 |
| high | RuleOnlyAdaptiveController | 238.509 | 405.170 | 467.241 | 520.000 | 0.692 | 38 |
| high | MLAdaptiveController | 236.920 | 403.200 | 463.917 | 522.800 | 0.688 | 43 |
| asymmetric_rush_hour | FixedTimeController | 94.355 | 216.050 | 73.642 | 373.000 | 0.210 | 38 |
| asymmetric_rush_hour | RuleOnlyAdaptiveController | 33.177 | 71.440 | 26.013 | 465.200 | 0.011 | 68 |
| asymmetric_rush_hour | MLAdaptiveController | 33.123 | 71.230 | 25.973 | 465.600 | 0.012 | 68 |
| incident | FixedTimeController | 53.342 | 213.060 | 51.979 | 529.200 | 0.120 | 38 |
| incident | RuleOnlyAdaptiveController | 93.520 | 254.540 | 91.357 | 459.800 | 0.254 | 58 |
| incident | MLAdaptiveController | 90.891 | 249.430 | 88.731 | 465.200 | 0.244 | 48 |

Independent trace/inventory audits recorded **0 constraint violations**. Maximum observed red was 68s; configured bound is 75s. This bounds service opportunities, not individual queue delays under overload.

## Paired adverse cases

Every paired delta is published; positive wait differences and negative throughput differences are adverse. The following rows are selected mechanically by descending mean-wait delta (up to ten), rather than picking favorable seeds. The adverse-case plot uses the largest delta.

| Trace | Policy | Mean wait delta (s) | p95 wait delta (s) | Throughput delta |
|---|---|---:|---:|---:|
| incident-r04 | RuleOnlyAdaptiveController | +55.104 | +53.700 | -98 |
| incident-r04 | MLAdaptiveController | +54.569 | +51.700 | -97 |
| incident-r05 | RuleOnlyAdaptiveController | +48.523 | +64.700 | -71 |
| incident-r05 | MLAdaptiveController | +43.367 | +69.000 | -68 |
| high-r03 | RuleOnlyAdaptiveController | +40.671 | +62.800 | -126 |
| high-r02 | RuleOnlyAdaptiveController | +39.711 | +70.350 | -120 |
| high-r04 | MLAdaptiveController | +39.622 | +73.450 | -106 |
| high-r04 | RuleOnlyAdaptiveController | +39.040 | +73.000 | -104 |
| high-r05 | MLAdaptiveController | +36.814 | +46.000 | -114 |
| incident-r01 | RuleOnlyAdaptiveController | +36.487 | +24.000 | -80 |

Of 50 paired adaptive-versus-fixed runs, 30 had higher mean observed wait and 30 had lower throughput. Different metrics can disagree. This benchmark does not manufacture improvements or assume that ML-assisted control is best.

Scenario-level paired mean-wait differences with 95% bootstrap intervals:

| Scenario | Policy | Mean delta (s) | 95% interval (s) | Worse-wait runs |
|---|---|---:|---|---:|
| low | RuleOnlyAdaptiveController | -5.079 | [-6.276, -4.144] | 0/5 |
| low | MLAdaptiveController | -4.738 | [-6.180, -3.546] | 0/5 |
| medium | RuleOnlyAdaptiveController | +13.488 | [+5.714, +21.263] | 5/5 |
| medium | MLAdaptiveController | +11.664 | [+5.287, +18.040] | 5/5 |
| high | RuleOnlyAdaptiveController | +38.357 | [+36.754, +39.961] | 5/5 |
| high | MLAdaptiveController | +36.769 | [+35.670, +38.242] | 5/5 |
| asymmetric_rush_hour | RuleOnlyAdaptiveController | -61.178 | [-66.834, -54.864] | 0/5 |
| asymmetric_rush_hour | MLAdaptiveController | -61.232 | [-66.528, -55.039] | 0/5 |
| incident | RuleOnlyAdaptiveController | +40.179 | [+31.609, +48.748] | 5/5 |
| incident | MLAdaptiveController | +37.549 | [+29.129, +47.818] | 5/5 |

## ML provenance and limitations

Model availability: {"classification": true, "regression": true}. Frozen selection version: `e3605e36e02326835d0e762e6a0ddb5cba435968523c74988bd4f6516155f85c`. Only current inputs are supplied to the existing hash-checked pipelines every 10s. Predictions are used by constrained rules; no future source data or test scores are consulted.

Mean ML queue-only fallback fraction during measurement: 0.258. Forecast-call failures over all warm-up and measured ML steps: 0. Negative, stale, missing or invalid estimates are logged and rejected rather than clipped or invented. If models are unavailable, the ML-labelled policy is explicitly queue-only fallback; such a run does not demonstrate ML-assisted performance.

This simulator starts all vehicles at point queues (no travel/spillback), uses 0.65 veh/s nominal discharge with 2s green startup loss, and multiplies north capacity by 0.20 for the incident's middle measurement interval. Poisson demand and near-zero stopped aggregate speeds differ from the training generator. Derived congestion labels, weak class recall, polynomial extrapolation and model/controller distribution shift limit interpretation. The 180s default warm-up is predeclared, not evidence of equilibrium: overloaded and incident queues can grow indefinitely. Pedestrian safety is limited to the documented parallel, no-turns, no-late-entry assumptions. The fixed baseline is one predeclared 30s schedule, not an optimized timing plan.

## Outputs and execution

Artifacts: `C:/Users/Hrishit Vats/OneDrive/Desktop/raah/artifacts/benchmark`.

- trace_manifest.json and traces/: seeds, capacities, arrivals, noise and SHA-256 provenance.
- run_metrics.csv, approach_metrics.csv, vehicle_waits.csv.gz, red_intervals.csv and trajectories.csv.
- summary.csv, paired_runs.csv, paired_summary.csv and adverse_cases.csv.
- action_logs/*.jsonl.gz: every action and its reason, including warm-up and model evidence.
- plots/: comparisons, paired differences, censoring/fairness and worst paired trajectory.
- run_manifest.json and artifact_hashes.json: config, versions, source/model provenance and reproducibility hashes.

```powershell
.\ml-service\.venv\Scripts\python.exe simulation/benchmark.py
.\ml-service\.venv\Scripts\python.exe simulation/benchmark.py --output-dir work/benchmark-repro --findings work/benchmark-repro-findings.md --verify-against artifacts/benchmark
```

No training data, validation data, held-out observations or final evaluation ledger is modified.

## Executed verification and plot review

The benchmark and controller suite ran using the existing project venv; no dependencies were installed:

```powershell
$env:TEMP=(Resolve-Path work/tmp).Path
$env:TMP=$env:TEMP
$env:MPLCONFIGDIR=(Resolve-Path work/matplotlib).Path
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_benchmark.py tests/test_controllers.py tests/test_controller_comparison.py -q --basetemp=work/tmp/benchmark-tests-fixed
```

```text
........................................................................ [ 34%]
........................................................................ [ 69%]
................................................................         [100%]
208 passed in 3.88s
```

The first run had one failing warm-up fixture: its observation window stopped before 2s startup loss and fractional discharge credit could produce the first departure. The fixture was extended from 6s to 8s of measurement; simulator dynamics were preserved. CSV trace replay uses Python's round-trip float parsing, removing a deprecated pandas parser option. The final suite completed without warnings. Checks cover exact hand-calculated warm-up/censoring accounting, cohort wait-area equality, no-demand/all-censored cases, independent seeds, immutable paired traces, trace tamper rejection, run-level bootstrap statistics, paired differences, missing-model fallback, compressed logs and full output hash verification.

Actual full benchmark and fresh-process replay output:

```text
PREGENERATED 25 traces; all files persisted before rollouts
PASS 75 rollouts; 0 constraint violations; 30 adverse wait pairs; 116 hashed artifacts
PASS 75 rollouts; 0 constraint violations; 30 adverse wait pairs; 116 hashed artifacts
REPRODUCIBILITY PASS: 116 artifacts byte-identical, including plots, traces and compressed logs
```

The repeat regenerated all 25 input traces and reran all 75 policies into work/benchmark-repro. Both output trees were checked against their hash manifests and each other: **116 artifacts were byte-identical**, including the four PNG plots and all compressed action logs. Reproducibility manifests exclude wall-clock durations and timestamps. This demonstrates the recorded environment, not arbitrary cross-platform byte equality. Existing held-out evaluation data and the final-test ledger were not accessed or reset.

All four plots were opened and visually inspected: labels/legends, units, warm-up shading, paired-difference directions and bootstrap error bars are legible. Undefined metrics stay undefined rather than becoming zero.

Recorded package versions:

```json
{
  "joblib": "1.6.0",
  "matplotlib": "3.11.2",
  "numpy": "2.5.4",
  "pandas": "3.1.0",
  "python": "3.12.14",
  "scikit-learn": "1.9.1"
}
```

### Interpretation of adverse operation

The adaptive policies had higher mean observed wait in every medium, high and incident seed (30 of 50 adaptive-versus-fixed pairs), and lower throughput in those same 30 pairs. They reduced wait in every low and asymmetric-rush seed in this sample. This does not establish general superiority for any policy.

In high demand, fixed-time averaged 52 phase changes and 638 departures per measurement window, versus 88.8/520 for rule-only and 87.6/522.8 for ML-assisted. More frequent clearances/startup losses are a plausible contributor to reduced discharge, consistent with the toy model's explicit lost service intervals; this is an interpretation, not a separately isolated causal experiment. No controller settings were changed to improve the reported benchmark. High-demand censoring was also substantial: approximately 56.3% fixed, 69.2% rule-only and 68.8% ML-assisted cohort vehicles remained unfinished. Therefore even the reported p95/max observed waits understate the unknown eventual waiting for unfinished vehicles.

The worst paired mean-wait increase was incident-r04 for rule-only (+55.10s); the adverse plot shows all three policies on that same saved trace. Jain service-fraction indices can remain near one while every approach experiences poor service or long waits; they must be interpreted with completion fractions, queues and red-time bounds.

Git diff --check passed; an existing README LF/CRLF conversion notice is informational. Current changes remain local; no commit or push was requested in this benchmark task.
