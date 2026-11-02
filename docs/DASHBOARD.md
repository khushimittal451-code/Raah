# Backend-driven virtual dashboard

The active React application no longer loads the bundled recording. All displayed
measurements, indications, timers, predictions and model metrics come from backend
responses. No frontend random traffic, guessed countdowns or fallback sample values
are generated. Public replay assets/export tools remain only for historical testing.
The interface is explicitly SIMULATED DATA, virtual-only and syllabus UNVERIFIED.

## Data contracts

| Display | Backend source |
|---|---|
| Scenario/controller options, seed, default duration | GET /simulation/config |
| Clock, road congestion, lamps, queues, speeds, red ages | GET /simulation/state or POST /simulation/step response |
| Per-approach countdown/value semantics | approaches[].signal_color, countdown_seconds, countdown_kind |
| Queue/speed charts | Up to 120 received backend snapshots, using totals.vehicle_count and totals.mean_speed_kmh |
| Model predictions | state.prediction_display, generated every ten virtual seconds |
| Selected model metrics | GET /model-metrics, saved test aggregates only |
| Classifier/regressor comparison | Same metrics endpoint, hash-verified saved validation CSVs |
| Controller comparison | POST /simulation/benchmark, paired current-scenario results |

Road congestion is the backend's existing congestion-v1 rule on current synthetic
observations; it is not an ML prediction. Predictions have their own panel and
generation timestamp/horizon. The backend now creates advisory predictions for all
controller modes, but fixed/rule-only decisions never use them. Advisory failure
does not stop those modes. A negative regression value is shown unmodified with a
nonphysical warning; the ML control policy still rejects it. Missing model output
is explicitly unavailable, never converted to zero or an invented class.

Fixed-time next-green countdowns are computable from the schedule. Adaptive red
next-green times are not known while the opposing green can extend, so the API
returns null and the card says Not scheduled. Adaptive green countdowns mean time
to the next review and may extend; they do not promise green termination. Known
yellow/all-red clearances use exact backend timing. Countdown text does not tick
in the browser when the simulation is paused.

Speeds are synthetic stopped-queue samples in the simplified point-queue engine,
not network travel speeds. Empty coverage stays null. Charts retain received
values only, never invent missing speed samples, and restart history on generation
changes or discontinuous/external clock jumps. Duplicate paused polls add no chart
points. X-axis is virtual time, not wall-clock elapsed time.

## Controls and request lifecycle

The app reads existing state on mount and does not automatically reset shared
state. Initialize & run creates the selected scenario if none exists; Run on an
existing demo advances one backend tick per successful polling cycle. Pause allows
an already submitted tick to finish, then performs only reads. Reset explicitly
applies selected scenario/controller/fallback options and creates a new generation.
Changing selectors pauses the loop; Run remains disabled until Reset applies the
pending choices. The checkbox explicitly authorizes rule-only fallback, including
for comparisons. The app never retries a failed mutation with a different policy.

Polling uses a recursive timeout after the preceding request finishes, not an
overlapping interval. Step bodies carry generation and expected_tick. Stale or
failed mutations pause the app; subsequent reads can resynchronize state, while
the error remains visible until explicit refresh/reset. A timed-out request is not
automatically retried as a mutation. Last received data is identified as such on
errors. Simulation completion stops stepping. Unmount clears polling timeouts and
aborts outstanding requests; late responses are ignored. Reset waits for existing
requests before issuing its mutation.

The API remains a single-user/single-worker in-memory demo. All browser clients in
that worker share state; another client can reset or advance it. This is not a
production multi-user control service or physical signal interface.

## Saved model evidence

GET /model-metrics reads only metrics.json, selection/feature metadata and aggregate
validation comparison CSVs. It checks the selection version, pipeline hashes,
comparison-file hashes and split labels. It does not open train/validation/test
observation CSVs, cached individual test predictions or the test usage ledger, and
does not call fit/evaluate. Missing/mismatched metrics return explicit 503 or a
section-level unavailable result; the UI does not supply replacement scores.

The selected model panel explicitly labels cached test metrics and their evaluation
date. Classifier/regressor tables are validation-only and keep different units
separate. Weak MEDIUM recall, derived labels, negative waits and UNVERIFIED status
are visible. Changing a controller does not retrain/select a different estimator
or regenerate these saved scores. Controller comparisons use actual bounded API
measurements and disclose effective fallback policy and censoring.

## Map and layout

The attributed OpenStreetMap map retains its bounded/conservative tile settings and
offline schematic fallback. Tile layers do not remount when backend data changes.
Congestion line colors and virtual signal lamps remain separate. Scenario panels,
signal cards, charts and metrics grids collapse at the existing mobile breakpoints;
wide tables scroll inside their panels. The app uses no external webfonts or paid keys.

## Run and verify

```powershell
.\ml-service\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir ml-service --host 127.0.0.1 --port 8000 --workers 1
npm --prefix client run dev
npm --prefix client test
npm --prefix client run build
```

Use the existing npm.cmd/workspace npm CLI if npm is not on PATH. The dev proxy maps
/api to the service. Separately deployed static builds need their configured public
API base URL/CORS. No additional dependencies were required for this change.

See DASHBOARD_TEST_REPORT.md for actual checks and the blocked browser/screenshot step.
