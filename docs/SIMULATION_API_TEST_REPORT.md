# Simulation API integration report

Status: PASS. Generated UTC: 2026-11-02T11:10:25.169338+00:00.

Implemented POST /simulation/reset, POST /simulation/step, GET /simulation/state and GET/POST /simulation/benchmark. FastAPI service version is 0.3.0. No dependencies were installed. These are virtual-only, synthetic-only endpoints, with no physical signal infrastructure, real private GPS or paid APIs.

## State contract and bounds

One shared single-user demo and one successful benchmark cache live in each API process. Use --workers 1 on localhost. Multiple workers, public multi-user sharing, persistent storage and resume across restarts are unsupported. Separate FastAPI application instances are isolated. All response state exposes state_scope=single-user-per-process; generation is process-local. The existing frontend remains a recorded replay, not a controller client.

- Seed is exactly 57; validated scenarios are low, medium, high, asymmetric_rush_hour and incident. Replicates 0-99 select deterministic independent child streams. Derived 64-bit seed strings and SHA-256 traces preserve exact provenance for JavaScript clients.
- Reset initializes t=0. Each step processes consecutive 1-second ticks with no background clock. Strict step count 1-100; demo duration 60-1800 seconds. Out-of-horizon work returns 409 without clipping.
- Required generation and expected_tick reject stale/retried requests. Shared state is locked; reset/step are staged and committed atomically. A later inference failure within an N-tick request does not leave partial progress or action history.
- The state includes vehicle/queue counts, synthetic speed/sample coverage, mean queue wait, past ten-second flows, phase/allowed greens, timers/red clocks, pedestrian assumptions, totals and latest interval/action. Every micro-step action/reason is returned from step.
- Error is the default ML policy. Unavailable or rejected predictions return 503. Only explicit model_fallback=rule_only permits queue-only decisions; responses distinguish requested/effective controller, fallback reason, model availability/version and nullable accepted predictions.
- Quick benchmarks pre-generate identical immutable arrivals/noise/capacity for all three policies, include warm-up, and are capped at 6000 controller-ticks. Default: 5 scenarios x 2 seeds x 3 policies x 150 seconds = 4500 ticks. One benchmark runs at a time; a second request returns 409. Results are actual measurements and run-level bootstrap summaries; cached GETs do not rerun work. Failed requests preserve the previous cache and all benchmark requests leave the active demo unchanged.

See SIMULATION_API.md for request examples, flow/tick semantics, the explicitly named demo versus benchmark engine conventions, and the limits of service-opportunity fairness and right-censored waits. The API does not read cached offline evaluation observations, fit preprocessing/models or write benchmark artifacts.

## Executed checks

From the Desktop raah repository, using the existing project venv:

```powershell
$env:TEMP=(Resolve-Path work/tmp).Path
$env:TMP=$env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_simulation_api.py tests/test_api.py tests/test_health.py tests/test_controllers.py tests/test_controller_comparison.py tests/test_benchmark.py -q --basetemp=work/tmp/simulation-api-evidence
.\ml-service\.venv\Scripts\python.exe -u tests/check_simulation_runtime.py
git diff --check
```

Final pytest output:

```text
........................................................................ [ 24%]
........................................................................ [ 49%]
........................................................................ [ 74%]
........................................................................ [ 98%]
...                                                                      [100%]
291 passed in 23.28s
```

The 291 focused tests cover new and existing APIs, all five scenarios/three controllers, seed determinism, 1-second versus batched stepping, strict input/work caps, initialization, finite serialization, conservation, legal phases, incompatible-green exclusion, red fairness, service under the prior completed interval's phase, stale clocks/generations, end-of-run bounds, missing-model opt-in, rejected estimates, transactional multi-tick rollback, concurrency, separate app isolation, current-only prediction feature timing, benchmark pairing/cache/reproducibility/busy protection, warm-up-only fallback rejection and denial of any offline train/validation/test/ledger file access. The controller and benchmark invariant suites are included. The health contract test was updated deliberately for controller=virtual-demo; prediction API behavior is preserved.

The first API-focused run passed 82 cases; the broader suite includes the added offline-data guard and existing invariant tests. No failed integration assertion remains. No full offline final-evaluation suite was rerun.

## Real localhost HTTP checks

Temporary Uvicorn servers were started with real sockets, first with saved model artifacts, then with an intentionally absent bundle. httpx made real HTTP requests; this was separate from the ASGITransport tests. All **48 requests** returned their asserted status/body contracts, including real 503/422/409 responses.

| Mode | Method | Endpoint | HTTP |
|---|---|---|---:|
| saved-models | GET | /health | 200 |
| saved-models | GET | /model-info | 200 |
| saved-models | GET | /simulation/state | 409 |
| saved-models | GET | /simulation/benchmark | 409 |
| saved-models | POST | /simulation/reset | 200 |
| saved-models | POST | /simulation/step | 200 |
| saved-models | POST | /simulation/step | 409 |
| saved-models | POST | /simulation/step | 422 |
| saved-models | POST | /simulation/reset | 422 |
| saved-models | GET | /simulation/state | 200 |
| saved-models | POST | /simulation/reset | 503 |
| saved-models | GET | /simulation/state | 200 |
| saved-models | POST | /simulation/reset | 200 |
| saved-models | POST | /simulation/step | 200 |
| saved-models | GET | /simulation/state | 200 |
| saved-models | POST | /simulation/benchmark | 200 |
| saved-models | GET | /simulation/benchmark | 200 |
| saved-models | GET | /simulation/state | 200 |
| saved-models | POST | /simulation/reset | 200 |
| saved-models | POST | /simulation/step | 200 |
| saved-models | POST | /simulation/step | 200 |
| saved-models | POST | /simulation/step | 200 |
| saved-models | POST | /simulation/step | 200 |
| saved-models | POST | /simulation/step | 200 |
| missing-models | GET | /health | 200 |
| missing-models | GET | /model-info | 200 |
| missing-models | GET | /simulation/state | 409 |
| missing-models | GET | /simulation/benchmark | 409 |
| missing-models | POST | /simulation/reset | 200 |
| missing-models | POST | /simulation/step | 200 |
| missing-models | POST | /simulation/step | 409 |
| missing-models | POST | /simulation/step | 422 |
| missing-models | POST | /simulation/reset | 422 |
| missing-models | GET | /simulation/state | 200 |
| missing-models | POST | /simulation/reset | 503 |
| missing-models | GET | /simulation/state | 200 |
| missing-models | POST | /simulation/reset | 200 |
| missing-models | POST | /simulation/step | 200 |
| missing-models | GET | /simulation/state | 200 |
| missing-models | POST | /simulation/benchmark | 200 |
| missing-models | GET | /simulation/benchmark | 200 |
| missing-models | GET | /simulation/state | 200 |
| missing-models | POST | /simulation/reset | 200 |
| missing-models | POST | /simulation/step | 200 |
| missing-models | POST | /simulation/step | 200 |
| missing-models | POST | /simulation/step | 200 |
| missing-models | POST | /simulation/step | 200 |
| missing-models | POST | /simulation/step | 200 |

Full command transcript:

```text
START saved-models 127.0.0.1:53943
saved-models GET /health 200
saved-models GET /model-info 200
saved-models GET /simulation/state 409
saved-models GET /simulation/benchmark 409
saved-models POST /simulation/reset 200
saved-models POST /simulation/step 200
saved-models POST /simulation/step 409
saved-models POST /simulation/step 422
saved-models POST /simulation/reset 422
saved-models GET /simulation/state 200
saved-models POST /simulation/reset 503
saved-models GET /simulation/state 200
saved-models POST /simulation/reset 200
saved-models POST /simulation/step 200
saved-models GET /simulation/state 200
saved-models POST /simulation/benchmark 200
saved-models GET /simulation/benchmark 200
saved-models GET /simulation/state 200
saved-models BENCHMARK 30 runs 4500 ticks fallback_used True
saved-models POST /simulation/reset 200
saved-models POST /simulation/step 200
saved-models POST /simulation/step 200
saved-models POST /simulation/step 200
saved-models POST /simulation/step 200
saved-models POST /simulation/step 200
saved-models REPRODUCIBILITY PASS: 35 ticks == 5 requests x 7 ticks
STOPPED {"mode": "saved-models", "port": 53943, "thread_stopped": true, "port_closed": true}
START missing-models 127.0.0.1:64652
missing-models GET /health 200
missing-models GET /model-info 200
missing-models GET /simulation/state 409
missing-models GET /simulation/benchmark 409
missing-models POST /simulation/reset 200
missing-models POST /simulation/step 200
missing-models POST /simulation/step 409
missing-models POST /simulation/step 422
missing-models POST /simulation/reset 422
missing-models GET /simulation/state 200
missing-models POST /simulation/reset 503
missing-models GET /simulation/state 200
missing-models POST /simulation/reset 200
missing-models POST /simulation/step 200
missing-models GET /simulation/state 200
missing-models POST /simulation/benchmark 200
missing-models GET /simulation/benchmark 200
missing-models GET /simulation/state 200
missing-models BENCHMARK 6 runs 420 ticks fallback_used True
missing-models POST /simulation/reset 200
missing-models POST /simulation/step 200
missing-models POST /simulation/step 200
missing-models POST /simulation/step 200
missing-models POST /simulation/step 200
missing-models POST /simulation/step 200
missing-models REPRODUCIBILITY PASS: 35 ticks == 5 requests x 7 ticks
STOPPED {"mode": "missing-models", "port": 64652, "thread_stopped": true, "port_closed": true}
```

With saved models, the default quick benchmark completed **30 measured rollouts / 4500 controller-ticks** with zero constraint violations and explicit fallback reported. With missing models, the smaller requested comparison completed **6 rollouts / 420 ticks** using explicit queue-only fallback; ML-labelled requests were marked effective_controller=rule_only. These are freshly executed simulation metrics, not fabricated scores or new held-out ML accuracy results. No policy superiority is asserted.

For both saved and missing models, one 35-tick request and five 7-tick requests following the same reset produced identical final traffic/phase/timer/prediction state after excluding only the reset generation. Benchmark cache reads matched POST output exactly, and the active demo state before/after benchmarking matched exactly.

## Actual nonphysical-model failure

The current saved artifacts loaded successfully, but the regressor emitted a negative estimate at the empty-junction reset. Default ML mode therefore rejected the request and preserved the previous demo:

```json
{
  "detail": {
    "code": "model_unavailable",
    "reason": "simulation prediction rejected; explicitly choose model_fallback=rule_only: fallback_queue_only: negative_future_wait_seconds"
  }
}
```

Explicit rule-only fallback then succeeded. Predictions remained null when rejected/unavailable; no zeros or substitute congestion labels were supplied as model output. Loaded-model readiness and prediction validity are distinct, as shown in state/model-info responses.

## Example actual serialized state

Selected fields from the real saved-model service's first fixed-time 35-step response:

```json
{
  "generation": 1,
  "engine": "demo-interval-end-v1",
  "tick": 35,
  "current_phase": "ew_green",
  "vehicle_greens": [
    "east",
    "west"
  ],
  "timers": {
    "seconds_in_phase": 1,
    "planned_green_seconds": 30,
    "seconds_to_planned_boundary": 29,
    "timer_kind": "green_plan",
    "ns_red_seconds": 5,
    "ew_red_seconds": 0,
    "maximum_red_seconds": 75
  },
  "approaches": [
    {
      "approach_id": "north",
      "vehicle_count": 4,
      "queue_length_vehicles": 4,
      "mean_speed_kmh": 0.09833157492378182,
      "free_flow_speed_kmh": 60.0,
      "gps_sample_count": 4,
      "mean_wait_seconds": 3.5,
      "incoming_vehicles": 5,
      "outgoing_vehicles": 1
    },
    {
      "approach_id": "south",
      "vehicle_count": 1,
      "queue_length_vehicles": 1,
      "mean_speed_kmh": 0.26949454062862604,
      "free_flow_speed_kmh": 60.0,
      "gps_sample_count": 1,
      "mean_wait_seconds": 5.0,
      "incoming_vehicles": 1,
      "outgoing_vehicles": 0
    },
    {
      "approach_id": "east",
      "vehicle_count": 10,
      "queue_length_vehicles": 10,
      "mean_speed_kmh": 0.0837826410431389,
      "free_flow_speed_kmh": 60.0,
      "gps_sample_count": 10,
      "mean_wait_seconds": 10.7,
      "incoming_vehicles": 6,
      "outgoing_vehicles": 0
    },
    {
      "approach_id": "west",
      "vehicle_count": 9,
      "queue_length_vehicles": 9,
      "mean_speed_kmh": 0.1658084095611451,
      "free_flow_speed_kmh": 60.0,
      "gps_sample_count": 9,
      "mean_wait_seconds": 21.555555555555557,
      "incoming_vehicles": 1,
      "outgoing_vehicles": 0
    }
  ],
  "totals": {
    "arrivals": 35,
    "departures": 11,
    "vehicle_count": 24
  },
  "last_interval": {
    "from_seconds": 34,
    "to_seconds": 35,
    "service_phase": "ew_green",
    "arrivals": [
      1,
      0,
      0,
      1
    ],
    "departures": [
      0,
      0,
      0,
      0
    ]
  }
}
```

Flow counts are over the last up-to-ten completed seconds. The service_phase is the phase governing the completed interval, while current_phase governs the next interval; a past flow count is not a claim of discharging conflicting vehicles during clearance. Speeds are synthetic stopped aggregates, not live geographic GPS. All vehicles in this simplified demo are at point queues.

## Saved evidence and cleanup

The complete response bodies are preserved without numeric conversion in docs/SIMULATION_API_HTTP_OUTPUT.json.gz. Gzip has a fixed timestamp and round-trip JSON equality was verified against work/simulation-api/http_evidence.json. Archive SHA-256: 5350a5db693cab64d52ec54ee210f59aa18925a2ccea1f3bbc90abb9709cc459.

Cleanup verification:

```json
[
  {
    "mode": "saved-models",
    "port": 53943,
    "thread_stopped": true,
    "port_closed": true
  },
  {
    "mode": "missing-models",
    "port": 64652,
    "thread_stopped": true,
    "port_closed": true
  }
]
```

Both owned Uvicorn threads stopped and both ports closed. No temporary test servers remain. git diff --check passed with ordinary LF-to-CRLF notices only. No login, privileged install or browser authorization was attempted. Existing model bundles, raw data, frozen ML test ledger and benchmark exports were not changed. No commit or push was requested for this task.
