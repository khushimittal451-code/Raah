# Dashboard implementation and verification

Date: 2026-11-02. Project: Desktop/raah. Status: implemented; automated tests and production compilation passed. Browser visual verification was blocked as described below.

## Delivered behavior

The map, approach cards, countdowns, observed congestion, queue and speed charts, model forecasts, saved model metrics and validation comparisons read backend responses. There are no random frontend traffic values and no bundled-recording fallback. Synthetic observations and virtual lamps remain explicitly labeled SIMULATED DATA. All syllabus coverage remains UNVERIFIED.

Backend configuration supplies scenarios and controller options. Run, pause and reset support fixed-time, rule-only and ML-adaptive controllers. Changed selections require reset; ML fallback requires explicit opt-in. The interface also displays actual controller benchmark results. API errors pause stepping and preserve the last snapshot with an error notice. Unavailable models and metrics remain explicit.

Fixed-time countdowns and known phase transitions come from backend timing. Adaptive green countdowns mean the next review; unscheduled red-to-green times display Not scheduled. Forecasts are distinct from observed congestion; raw negative regression predictions are flagged rather than silently corrected. History contains only received snapshots, with absent speed samples left empty.

Polling is sequential, cleans up timers and aborts requests on unmount, ignores stale results, and does not automatically retry failed mutations. Generation/tick guards prevent duplicate advancement. Demo state is shared within one process and intended for a single user. Mobile styles collapse cards/charts and permit table scrolling. OpenStreetMap attribution, conservative tile usage and schematic fallback remain present.

GET /simulation/config and GET /model-metrics provide configuration and cached aggregate metrics. Model/comparison hashes are checked against the frozen selection manifest. Validation comparisons and saved held-out aggregate metrics are labeled separately. No training or held-out evaluation was performed for this task, and no raw held-out observations were opened.

## Executed checks

Commands ran from the project root using existing dependencies; no installation was required.

```powershell
$env:TEMP=(Resolve-Path work/tmp).Path
$env:TMP=$env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_dashboard_api.py tests/test_simulation_api.py tests/test_api.py tests/test_health.py tests/test_controllers.py tests/test_controller_comparison.py tests/test_benchmark.py -q --basetemp=work/tmp/dashboard-api-final
node work/tools/npm/package/bin/npm-cli.js --prefix client test
node work/tools/npm/package/bin/npm-cli.js --prefix client run build
git diff --check
```

Results:

- Python/API/controller/benchmark suites: **295 passed in 59.96s**.
- Client: **4 test files, 42 tests passed**, 6.14s. Includes actual Leaflet integration, backend-state rendering, controls, error handling, sequential polling, cleanup, explicit fallback and cached comparison rendering.
- Production build: **669 modules transformed; built in 17.57s**. Output chunks: index JS 238.31 kB, map 166.73 kB, charts 358.90 kB; CSS 26.62 kB.
- `git diff --check`: passed after removing an extra blank line at EOF. Git emitted existing LF-to-CRLF normalization notices.

An initial API assertion expected the old totals shape. It was updated for the added backend mean_speed_kmh field; the complete focused suites then passed. No failing checks remain in these suites. Full historical training/final-evaluation suites were deliberately not invoked.

Full command output is appended below. Component fixtures were captured from real backend responses and saved aggregate artifacts, including a real small benchmark. They are test-only and are never loaded by the production application.

## Browser check limitation

Browser automation was available and attempted. The in-app browser could not reach the local preview (ERR_CONNECTION_REFUSED). A temporary local preview was subsequently started, but Windows Computer Use stopped before controls could be exercised because it could not determine the active browser URL confidently enough to enforce policy. No further browser input was issued after that stop. No successful dashboard screenshot was captured, and browser end-to-end/visual verification is **not claimed**. The owned preview was stopped cleanly (DASHBOARD STOPPED, exit 0); the earlier failed helper also exited.

Remaining manual visual check: open the client against the API, inspect desktop/mobile map and cards, run/pause, reset across scenarios/controllers, explicitly allow ML fallback if needed, inspect unavailable/error states, and confirm charts/countdowns advance only with backend ticks. These interactions already have component/API coverage, but real-browser appearance remains unverified.

Source contract: docs/DASHBOARD.md. Existing work was preserved. No commit/push or contributor attribution was added for this request.

## dashboard-api-tests.txt

```text
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 73%]
........................................................................ [ 97%]
.......                                                                  [100%]
295 passed in 59.96s
```

## dashboard-client-tests.txt

```text
npm notice run raah-client@0.1.0 test
npm notice run vitest run

 RUN  v5.0.5 C:/Users/Hrishit Vats/OneDrive/Desktop/raah/client


 Test Files  4 passed (4)
      Tests  42 passed (42)
   Start at  17:13:05
   Duration  6.14s (environment 63%, setup 15%, tests 13%, transform 5%, import 3%)

```

## dashboard-build.txt

```text
npm notice run raah-client@0.1.0 build
npm notice run vite build
vite v7.3.7 building client environment for production...
transforming...
✓ 669 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.60 kB │ gzip:   0.34 kB
dist/assets/index-B2RBR6yv.css   26.62 kB │ gzip:   9.34 kB
dist/assets/map-_Lt5qy3c.js     166.73 kB │ gzip:  49.06 kB
dist/assets/index-UuIPz7OZ.js   238.31 kB │ gzip:  74.70 kB
dist/assets/charts-cN7NZRGR.js  358.90 kB │ gzip: 105.48 kB
✓ built in 17.57s
```
