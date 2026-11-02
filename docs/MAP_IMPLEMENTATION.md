# Recorded virtual junction map

The React client renders a Leaflet map with congestion road lines and **separate
virtual signal lamps**. Header and map both say **SIMULATED DATA**. It never claims
live traffic, measured GPS, real Berlin signal states, or physical actuation.
All syllabus/model coverage remains UNVERIFIED.

## Geography and tile policy

The optional geographic context is an illustrative public location near
Friedrichstrasse / Unter den Linden, Berlin, centered approximately at
52.5170, 13.3890 ([OpenStreetMap location](https://www.openstreetmap.org/#map=18/52.5170/13.3890)).
The straight approach overlays are schematic projections around this example
center, not surveyed street centerlines or modeled turning lanes. The recording
does not describe traffic at this location. There is no geocoding, user location
request, paid key, or private GPS ingestion.

OSM Standard tiles use HTTPS with visible copyright attribution. Requests preserve
the browser's normal HTTP cache and an origin referrer; there is no prefetch,
bulk download, offline tile store, cache-busting or automatic retry. These choices
follow the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/).
Best-effort tile availability is not a dependency for replay data.

Implementation settings:

- One bounded junction viewport, zoom 17-18, no world wrapping or retina duplication.
- Leaflet keepBuffer=0, updateWhenIdle=true and updateWhenZooming=false.
- Wheel, double-click, touch pinch and box zoom are disabled; explicit zoom buttons
  and bounded dragging remain available.
- Tile errors switch immediately to an independent CRS.Simple schematic. An 8s
  timeout does the same. No retry loop is scheduled; users can explicitly choose
  Load OpenStreetMap or Use offline schematic.
- A stable TileLayer is retained across replay ticks; overlays update without
  remounting the tile layer. ResizeObserver invalidates only the viewport size.
- Leaflet attribution control stays enabled. An additional, visible copyright link
  remains outside the map, where overlays cannot hide it.

These are deliberate small-demo limits, not a guarantee of unrestricted use of
OSM's public servers. Reference: [Leaflet TileLayer options](https://leafletjs.com/reference.html#tilelayer).

## Traffic, lamps and provenance

The bundled `client/public/data/junction-replay.json` is a 120-second excerpt
(t=180..299) from the new seed-57-derived `medium-r01` paired benchmark trace.
Its model version and input-trace SHA-256 are included in the file. Lamp phases
are actual recorded MLAdaptiveController states, including every 3s yellow and 1s
all-red clearance at one-second resolution. No backend controller is running when
the recording plays. Seeking is inspection of history, not a signal command.

Congestion lines use the canonical congestion-v1 rule on validated synthetic
TrafficObservation snapshots at 10s intervals. They are **not model predictions**.
The current observation timestamp and snapshot age are shown separately from the
one-second signal clock. Mean speed is an aggregate of synthetic stopped-speed
samples; missing speed is shown as No samples, not zero. Counts/waits are synthetic.

| Visual | Values | Meaning |
|---|---|---|
| Thick road lines | LOW green, MEDIUM amber, HIGH red | Synthetic rule-derived congestion |
| Round map lamps and separate three-bulb cards | RED, YELLOW, GREEN | Recorded controller indications |

Each visual has its own text legend. A highly congested red road can have a green
virtual signal. North/south and east/west greens never overlap; clearance phases
have no green. Tooltips, labeled signal cards and a scrollable observation table
provide alternatives to reading color alone.

The chosen excerpt contains LOW and HIGH congestion and all six signal phases.
MEDIUM styling is included in the legend and tested with an explicit component
fixture; no MEDIUM observations were inserted into the recording to improve a demo.

Replay JSON is validated before display: version/seed, complete unique approaches,
known congestion/phase enums, finite measurement ranges, consecutive clocks,
snapshot age, phase progression, minimum/maximum green and complete clearances.
Invalid or missing recordings display an error and Retry simulation data button;
traffic and lamps are not replaced with fabricated values. API liveness is a
separate check and is not interpreted as model/controller readiness.

Loading states cover recording and tiles. A map rendering error boundary keeps the
signal cards/table available. Layout switches at 950px and 600px; tables scroll
inside their panel, controls wrap, focus rings remain visible, and no external
webfonts are requested. Replay starts paused, advances at one recorded second per
second, stops at its final frame and never wraps through an unsafe-looking phase jump.

## Reproduce and verify

```powershell
node work/tools/npm/package/bin/npm-cli.js --prefix client test
node work/tools/npm/package/bin/npm-cli.js --prefix client run build
```

Or use the installed npm command with `--prefix client` where available. The four
new dev dependencies are Vitest, Testing Library React, jest-dom and jsdom; exact
resolution is in package-lock.json. No production dependency or paid service was added.

To regenerate the recording after producing the default benchmark and frozen local
model bundle:

```powershell
.\ml-service\.venv\Scripts\python.exe client/scripts/export_map_replay.py
```

The exporter replays the saved immutable arrival trace, uses the existing model
pipelines for inference only, captures current synthetic snapshots, computes
congestion-v1, and checks all resulting phases against the saved benchmark action
log. It never reads held-out ML observations, trains a model or changes the original
benchmark artifacts. Default browser use needs only the bundled recording, not
Python, model files, benchmark artifacts or a reachable ML service.

See MAP_TEST_REPORT.md for executed command results and the browser-routing limitation.
