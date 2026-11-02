# Virtual simulation API

These endpoints run educational **synthetic-only, virtual-only** demos. They never
connect to physical infrastructure, collect GPS, use paid services, fit models or
read offline ML evaluation observations. Syllabus status remains UNVERIFIED.
The current dashboard uses these endpoints for the virtual demo; it sends no
physical signal commands. See DASHBOARD.md for client lifecycle and data provenance.

## State and deployment contract

Run locally using **one worker**:

```powershell
.\ml-service\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir ml-service --host 127.0.0.1 --port 8000 --workers 1
```

There is one demo and one cached benchmark per FastAPI application/process. All
clients in that process share them. This is an explicitly **single-user demo**,
not authenticated multi-user storage. Resets affect every client. Separate app
instances have isolated state. Restart/reload clears all state; multiple workers
are unsupported because their memory would diverge. Generation numbers are valid
only within the current process. Re-fetch state after reconnect/restart.

A reentrant lock serializes reset/step/state access. Step mutations are staged on
copied mutable state and committed only if every requested second succeeds. Failed
reset or step requests preserve the old demo, generation, tick and action history.
Model inference attempts may have occurred before a failure; they do not train or
change the fitted models. A separate nonblocking lock permits one benchmark at a
time; another benchmark request returns 409. Benchmarks do not change the active demo.

No clock runs in the background. GET requests do not advance time. Reset processes
t=0 with an empty junction and returns tick 0. Each step advances exact consecutive
one-second ticks; batching N seconds matches N one-second calls. The seed is fixed
at 57; replicate selects a deterministic independent child stream. All arrivals,
synthetic speed noise and capacities are generated before stepping and remain
read-only. Responses include a trace SHA-256. Derived 64-bit run seeds are decimal
strings to avoid JavaScript integer rounding; master seed and ticks are small integers.

## Routes

| Method | Path | Behavior |
|---|---|---|
| POST | /simulation/reset | Replace the active demo after successful initialization |
| POST | /simulation/step | Atomically advance 1-100 seconds using an optimistic clock guard |
| GET | /simulation/state | Read the current snapshot without mutation |
| POST | /simulation/benchmark | Execute a bounded, paired in-memory comparison |
| GET | /simulation/benchmark | Read the most recent successful comparison; no rerun |

Before initialization, state/step return 409 simulation_not_initialized. Before a
successful benchmark, GET benchmark returns 409 benchmark_not_run. Application
startup must complete before these routes are usable. `/health` remains liveness
only and now reports controller=virtual-demo, not model or demo readiness.

### Reset

```json
{
  "scenario": "medium",
  "controller": "ml_assisted",
  "seed": 57,
  "replicate": 0,
  "duration_seconds": 600,
  "model_fallback": "rule_only"
}
```

All fields have defaults: medium, fixed_time, 57, replicate 0, 600 seconds and
model_fallback=error. Controllers: fixed_time, rule_only, ml_assisted. Scenarios:
low, medium, high, asymmetric_rush_hour, incident. Duration is 60-1800 seconds;
replicate is 0-99. Strict integer types reject booleans/floats. Unknown scenarios,
controllers, seed values, fallback names and extra fields return 422. There is no
request field for arbitrary phases, physical signals, raw GPS or filesystem paths.

The reset generation increments only on success. To select ML, both frozen pipelines
must be usable. With the default error policy, missing artifacts, failed inference
or rejected predictions produce **503 model_unavailable**, preserving old state.
This includes negative polynomial outputs even when model files are present.

The caller must explicitly choose **model_fallback=rule_only** to permit queue-only
decisions when ML is unavailable or invalid. Responses show requested versus
effective controller, fallback flag/reason, loaded model version/availability and
accepted prediction provenance. Predictions are null when none are accepted; no
zero waits or fabricated classes replace them. Rejected estimates are never clipped.
Fixed-time/rule-only modes need no trained artifacts and do not invent ML predictions.

### Step

Use generation and tick from the latest reset/state response:

```json
{"generation": 1, "expected_tick": 0, "steps": 10}
```

Steps default to 1 and are capped at 100 per request. Requests exceeding the remaining
configured duration return 409 without advancing or silently truncating. Stale
generation or expected_tick returns 409 generation_mismatch / tick_mismatch; this
prevents stale/retried requests from advancing twice. A successful response contains
executed_steps, the final state and every micro-step action/reason, including yellow
and all-red states that fall between the starting and ending snapshot.

## Serialized state and tick semantics

The response schema simulation-state-v1 includes:

- Generation, tick, completion flag, duration, scenario/controller/seed provenance,
  trace hash, data mode, virtual-only flag and single-user scope.
- Four approach records: vehicle_count, queue_length_vehicles, mean_speed_kmh,
  free_flow_speed_kmh, gps_sample_count, mean_wait_seconds, incoming/outgoing counts.
- Current phase, allowed vehicle greens, elapsed phase time, planned boundary,
  clearance versus green-plan timer kind and both red clocks.
- Pedestrian indication/axis with the documented parallel-crossing assumptions,
  complete timing config, cumulative arrival/departure/inventory totals.
- Last completed interval, service phase, per-approach arrivals/departures and the
  latest immutable controller action with reason and accepted forecast evidence.

Dashboard extensions include backend-derived current congestion and per-approach
signal_color/countdown_seconds/countdown_kind/red_wait_seconds. Unknown adaptive
next-green times are null. Green review countdowns are explicitly not fixed ends.
totals.mean_speed_kmh is sample-weighted or null with no coverage. prediction_display
contains advisory model outputs for all modes, with raw nonphysical values flagged;
advisory failure never forces fixed/rule-only control to fail. ML control still
requires the original explicit fallback policy and rejects invalid estimates.

The demo engine is **demo-interval-end-v1**. At t>0, arrivals/service in (t-1,t]
complete under the previous interval's phase, then current observations are used
for the decision at t, which governs the next interval. This makes outgoing flow
known at prediction time. The last_interval.service_phase is explicit: a nonzero
past departure count does not imply a departure under the newly entered yellow/red.
Incoming/outgoing counts cover the last up-to-ten completed seconds, not just one
tick. Counts, queues and mean waits are after service at the returned tick.

The point-queue model has no moving/travelling vehicles: vehicle_count equals queue
length. Speeds are noisy synthetic stopped aggregates (0-0.9 km/h), or null with zero
samples. Free-flow 60 km/h is a reference, not measured flow. Nominal discharge is
0.65 vehicles/second with 2s startup loss; incident north capacity is reduced to 20%.
No per-person or per-vehicle identifiers/timestamps are exposed by the state API.

ML inputs are validated current-only TrafficObservation snapshots on the 10s grid
immediately before the control decision. Fitted pipelines preserve their original
feature schema. Cached estimates age normally between refreshes; phase choices
still pass through min/max green, yellow/all-red, fairness and pedestrian guards.
The active controller's red bound is 75s, not a bound on an individual vehicle's
delay under overload. There is no real-road safety certification or wall-clock
signal scheduler.

## Bounded benchmark

```json
{
  "scenarios": ["low", "medium", "high", "asymmetric_rush_hour", "incident"],
  "seed": 57,
  "runs_per_scenario": 2,
  "warmup_seconds": 30,
  "measurement_seconds": 120,
  "model_fallback": "rule_only"
}
```

Those are the default scenarios/runs/durations, but fallback defaults to error unless
explicitly supplied. Unique scenarios: 1-5. Runs per scenario: 2-3. Warm-up: 1-120s;
measurement: 1-300s. The combined budget is **6000 controller-ticks**, including all
three controllers, warm-up, scenarios and replicates. Invalid/oversized combinations
return 422 before computation. The default executes 30 paired rollouts / 4500 ticks.

This quick endpoint reuses the existing **paired-virtual-benchmark-v1** measurement
engine (decision then interval discharge), not the demo snapshot engine. Its
immutable exogenous traces match the offline benchmark generator for equal config;
the clock convention is named explicitly so snapshots are not mistaken for replay
of offline trajectories. Use the standalone benchmark command for the longer study.

All traces are prepared in memory before policies run. The result includes actual
per-run/censored wait, queue, throughput, fairness and phase-change metrics;
run-level bootstrap summaries; paired differences; trace/model provenance and
fallback counters. Requested and effective controller are distinguished. Queue-only
fallback is never claimed as ML-assisted improvement. An error policy rejects any
ML fallback, including one that occurred only during warm-up. Failed or busy requests
leave the previous cached result intact. Successful results replace that cache.

No plots, training, subprocesses, exports or model fitting run in this endpoint.
The active demo and existing benchmark artifacts are not modified. Small run counts,
right-censored waits, simplified queues and model/controller distribution shift limit
interpretation; no improvement is assumed.

## Example PowerShell use

```powershell
$demo = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/simulation/reset -ContentType application/json -Body '{"scenario":"medium","controller":"ml_assisted","model_fallback":"rule_only"}'
$body = @{ generation=$demo.generation; expected_tick=$demo.tick; steps=10 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/simulation/step -ContentType application/json -Body $body
Invoke-RestMethod http://127.0.0.1:8000/simulation/state
```

See SIMULATION_API_TEST_REPORT.md for executed test/HTTP evidence and exact limitations.
