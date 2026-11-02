# Map implementation test report

Build: PASS. Component/DOM integration tests: PASS. Compiled {
  "checks": [
    {
      "path": "/",
      "status": 200
    },
    {
      "path": "/assets/index-DZCc6vhf.js",
      "status": 200
    },
    {
      "path": "/assets/map-CnoyBNlh.js",
      "status": 200
    },
    {
      "path": "/assets/index-BIqOXfg2.css",
      "status": 200
    },
    {
      "path": "/data/junction-replay.json",
      "status": 200,
      "frames": 120
    }
  ],
  "external_tile_requests": 0
} smoke: PASS.
Visual browser smoke: BLOCKED by localhost routing; no visual pass or screenshot is claimed.

## Implemented and preserved

React Leaflet now displays attributed OSM tiles at a documented illustrative Berlin junction, bounded conservative tile behavior and automatic offline schematic fallback. Road bands LOW green / MEDIUM amber / HIGH red are separate from actual recorded RED/YELLOW/GREEN virtual signal lamps. Persistent SIMULATED DATA labels, independent legends, replay controls, signal cards, a timestamped observation table, loading/error/retry states, responsive breakpoints and keyboard focus styles are included. There are no physical signal commands, real private GPS, paid keys, model retraining or held-out evaluation reads.

See MAP_IMPLEMENTATION.md for the [OSM policy](https://operations.osmfoundation.org/policies/tiles/) and [Leaflet reference](https://leafletjs.com/reference.html#tilelayer), example coordinates, caveats and regeneration instructions. Geographic road overlays are approximate schematic geometry, not observed city roads/traffic. The bundled recording is independent of API availability.

## Installed test tooling

Existing client manifests were inspected first. Installed only the four new development requirements: vitest, @testing-library/react, @testing-library/jest-dom and jsdom; package-lock.json records exact resolution. npm added 73 packages. npm reported an esbuild@0.28.2 postinstall script blocked by its allowScripts policy; no policy bypass or script approval was performed. Vitest and the frontend build both worked with the installed native dependencies.

Node v24.22.1; workspace npm 12.2.1. Resolved relevant package versions:

```json
{
  "react": "19.3.1",
  "react-leaflet": "5.0.0",
  "leaflet": "1.9.4",
  "vite": "7.3.7",
  "vitest": "5.0.5",
  "@testing-library/react": "16.3.3",
  "@testing-library/jest-dom": "7.0.1",
  "jsdom": "30.1.3"
}
```

## Executed commands

From the Desktop raah repository:

```powershell
node work/tools/npm/package/bin/npm-cli.js --prefix client install --save-dev vitest @testing-library/react @testing-library/jest-dom jsdom --no-fund --no-audit --cache work/npm-cache
node work/tools/npm/package/bin/npm-cli.js --prefix client test
node work/tools/npm/package/bin/npm-cli.js --prefix client run build
.\ml-service\.venv\Scripts\python.exe client/scripts/export_map_replay.py
.\ml-service\.venv\Scripts\python.exe -u work/map_preview.py
git diff --check
```

Final component-test output:

```text
npm notice run raah-client@0.1.0 test
npm notice run vitest run

 RUN  v5.0.5 C:/Users/Hrishit Vats/OneDrive/Desktop/raah/client


 Test Files  3 passed (3)
      Tests  33 passed (33)
   Start at  04:36:36
   Duration  4.31s (environment 65%, setup 16%, tests 10%, transform 6%, import 3%)
```

The 33 cases cover real replay validation and all six phases; no conflicting greens; exact congestion colors; separate HIGH road/GREEN signal semantics; all-red lamps; tile attribution/options; stable TileLayer across replay ticks; real TileLayer error to offline fallback; timeout with no automatic retry; manual offline/retry controls; data loading/failure/explicit retry; malformed data rejection; snapshot clock/phase limits; playback/seeking and stopping without loop. A separate integration case mounts actual React Leaflet/SVG paths and real attribution controls in jsdom, rather than mocking the map library. SVG feature detection is shimmed only in the DOM test environment. Component tests use no external tile downloads; explicit image error events test fallback.

Final build output:

```text
npm notice run raah-client@0.1.0 build
npm notice run vite build
vite v7.3.7 building client environment for production...
transforming...
✓ 135 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.53 kB │ gzip:  0.32 kB
dist/assets/index-BIqOXfg2.css   23.81 kB │ gzip:  8.77 kB
dist/assets/map-CnoyBNlh.js     166.32 kB │ gzip: 48.89 kB
dist/assets/index-DZCc6vhf.js   286.31 kB │ gzip: 93.49 kB
✓ built in 1.36s
```

The stylesheet was formatted after the first successful build; the final build generated the same asset hashes. The unused chart chunk was removed from the Vite output configuration; no model metric or empty chart is presented as a result.

## Replay provenance and reproducibility

The exporter replays the existing new-synthetic benchmark medium-r01 trace, captures current-only snapshots and verifies all one-second controller phases against its saved action log. It does not modify the benchmark, frozen model files or the ML test ledger. The 120 frames span t=180..299 and include all six phases. Road congestion uses the existing congestion-v1 rule; it is not labelled as an ML prediction. Snapshot age is shown because observations update every 10s while lamps update every second.

The selected recording contains LOW and HIGH road states. MEDIUM amber is rendered in the legend and explicitly exercised in component/integration tests; no fictitious MEDIUM rows were inserted into the recording.

Exporting twice produced the same bundled JSON SHA-256:

```text
a2425627ffdae31439caefbfe26d5f46c5109dca46c0bc26d9a93a37b0efbf57
```

## Compiled {
  "checks": [
    {
      "path": "/",
      "status": 200
    },
    {
      "path": "/assets/index-DZCc6vhf.js",
      "status": 200
    },
    {
      "path": "/assets/map-CnoyBNlh.js",
      "status": 200
    },
    {
      "path": "/assets/index-BIqOXfg2.css",
      "status": 200
    },
    {
      "path": "/data/junction-replay.json",
      "status": 200,
      "frames": 120
    }
  ],
  "external_tile_requests": 0
} checks and browser limitation

A temporary localhost server served the final built assets and bundled replay. Each request returned 200; fixture bytes matched the source exactly:

```json
{
  "checks": [
    {
      "path": "/",
      "status": 200
    },
    {
      "path": "/assets/index-DZCc6vhf.js",
      "status": 200
    },
    {
      "path": "/assets/map-CnoyBNlh.js",
      "status": 200
    },
    {
      "path": "/assets/index-BIqOXfg2.css",
      "status": 200
    },
    {
      "path": "/data/junction-replay.json",
      "status": 200,
      "frames": 120
    }
  ],
  "external_tile_requests": 0
}
```

The in-app browser automation tool was asked to open http://127.0.0.1:5173/ while the preview was running. It reported:

```text
Browser Use cannot open http://127.0.0.1:5173 in tab 4.
Browser reported: net::ERR_CONNECTION_TIMED_OUT
```

The same preview's local {
  "checks": [
    {
      "path": "/",
      "status": 200
    },
    {
      "path": "/assets/index-DZCc6vhf.js",
      "status": 200
    },
    {
      "path": "/assets/map-CnoyBNlh.js",
      "status": 200
    },
    {
      "path": "/assets/index-BIqOXfg2.css",
      "status": 200
    },
    {
      "path": "/data/junction-replay.json",
      "status": 200,
      "frames": 120
    }
  ],
  "external_tile_requests": 0
} checks succeeded within its execution environment. Cross-session/browser localhost routing remains blocked in this environment. No firewall/security settings, authentication or browser authorization were changed. No native-browser screenshot, desktop/mobile visual pass, live OSM tile rendering or measured external tile request count is asserted. Responsive behavior is implemented in CSS but still needs a human/browser visual check on a host that can reach the preview.

The temporary preview was stopped using its stop flag; the server reported PREVIEW STOPPED. There are no test servers left running from this task. git diff --check passed; Git emitted ordinary LF-to-CRLF notices. Existing backend/controller/benchmark work was preserved. No commit or push was requested.

For a host-accessible manual visual check, start the API if desired, run the client dev server with npm --prefix client run dev, and inspect desktop and mobile widths at http://127.0.0.1:5173. Verify attribution stays visible, toggle the offline schematic, inspect both legends, and play/seek through yellow/all-red phases. The API can be unavailable while recorded replay remains usable.
