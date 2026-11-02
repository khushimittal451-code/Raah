# Optional SUMO mode

Status on **2026-11-02: SKIPPED — SUMO and netconvert unavailable**. The existing
Raah simulator/API is independent and remains usable. No installation, privileged
command, login, browser authorization, new Python dependency or model evaluation
was performed. Syllabus coverage remains UNVERIFIED.

## Installation detection and opt-in

`simulation/sumo_adapter.py` is a standalone command, not an API controller option.
It uses only Python's standard library and the existing TimingConfig. It discovers
`sumo` and `netconvert` on PATH, then in SUMO_HOME/bin and standard Windows SUMO
installation folders. It does not scan the disk, download binaries or install them.
Importing the module launches no processes. Running a smoke simulation requires
the exact flag `RAAH_ENABLE_SUMO=1`; the default is disabled. The example env file
does not automatically set shell variables.

The local inspection found no executables on PATH, SUMO_HOME unset, and no SUMO
folders at C:/Program Files[/ (x86)]/Eclipse/Sumo or /Sumo. This is an absence from
the supported lookup locations, not proof that no copy exists anywhere on disk.
If you already have a local installation, expose its bin directory on PATH or set
SUMO_HOME. Otherwise install SUMO yourself from the official distribution, or ask
for a separately authorized nonprivileged installation. Nothing is installed here.

From the Raah root, using the existing venv:

```powershell
.\ml-service\.venv\Scripts\python.exe -m simulation.sumo_adapter --status
$env:RAAH_ENABLE_SUMO='1'
.\ml-service\.venv\Scripts\python.exe -m simulation.sumo_adapter --output artifacts/sumo/run-001
Remove-Item Env:RAAH_ENABLE_SUMO
```

Use a fresh empty output directory: existing files are never overwritten. The flag
only authorizes this adapter; it does not change the main simulator. Disabled or
missing tools produce explicit skipped JSON and exit code 2. Runtime/tool/schema
errors fail visibly; they are not converted to a passing smoke result. Each child
process has a 60-second timeout and uses an argument vector without a shell.

## Supported virtual junction

The smoke fixture is generated locally: four approaches, one lane per direction,
synthetic periodic arrivals, no turns, no pedestrian/cyclist movements, no real
GPS or observed traffic. Seed is 57, step length one simulated second. Connections
are explicitly indexed N=0, E=1, S=2, W=3, going straight to the opposite exit.
The fixed-time virtual cycle is:

| Virtual phase | SUMO state N/E/S/W | Duration |
| --- | --- | --- |
| NS green | GrGr | 30 s |
| NS yellow | yryr | 3 s |
| All red toward EW | rrrr | 1 s |
| EW green | rGrG | 30 s |
| EW yellow | ryry | 3 s |
| All red toward NS | rrrr | 1 s |

These are illustrative settings from Raah TimingConfig (15 s minimum/60 s maximum
green), not universal real-road-safe timings. Every cross-axis switch traverses
yellow and all-red; the cycle bounds red waiting for this through-only fixture.
No crossings are present, so this smoke does not validate pedestrian safety.
Adding crossings/turns requires a reviewed conflict matrix, separate permissions
and clearance tests; never apply these four-character states to another network.

Before launching SUMO, the adapter audits the compiled connection mapping and
phase durations. It then checks all 136 reported ticks (two cycles) against the
expected phase/time sequence and requires at least one completed synthetic trip.
It saves input XML, the converted network, tls_states.xml, tripinfo.xml, versions,
exact commands and stdout/stderr in smoke_report.json under the output directory.
No arbitrary imported network/configuration is accepted by the adapter.

This is an optional fixed-time integration smoke, not support for ML-adaptive SUMO
control, a congestion model validation or a comparative benchmark. Main API/UI
state continues to come from the original simulator. No TraCI server, hardware
connection or external signal control is opened. Across SUMO versions/platforms,
floating-point dynamics and network conversion can differ: keep versions and
generated inputs with results before comparing runs; no cross-version byte
equivalence is claimed.

## OSM geometry import (documentation only)

Public OSM road geometry may provide an optional offline network layout. It is not
traffic demand or GPS observation. The adapter uses a schematic and does not fetch
OSM data. To explore separately, obtain a small public OSM export, retain its date,
bounds, checksum, OSM attribution/license and conversion options, then run locally:

```powershell
netconvert --osm-files junction.osm.xml --output-file junction.net.xml
```

Inspect topology, speed limits, lane connections and signal indices in netedit.
OSM-imported/generated phases require manual virtual conflict/clearance review;
they are not certified safe or accepted automatically. Build only synthetic route
demand with seed 57. Do not fetch private GPS, paid APIs or connect to real signals.
Imported OSM integration remains unimplemented; it is not covered by this smoke.

Primary references: [SUMO netconvert](https://sumo.dlr.de/docs/netconvert.html),
[OSM import](https://sumo.dlr.de/docs/Networks/Import/OpenStreetMap.html),
[connection indices](https://sumo.dlr.de/docs/Networks/SUMO_Road_Networks.html),
and [TLS state output](https://sumo.dlr.de/docs/Simulation/Output/Traffic_Lights.html).

## Executed checks

The core gate passed before SUMO lookup or adapter creation:

```powershell
$env:TEMP=(Resolve-Path work/tmp).Path
$env:TMP=$env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_dashboard_api.py tests/test_simulation_api.py tests/test_api.py tests/test_health.py tests/test_controllers.py tests/test_controller_comparison.py tests/test_benchmark.py -q --basetemp=work/tmp/sumo-core-network
```

Output: **295 passed in 10.41s**. Earlier attempts were stopped: one logging
attempt could not write before folder permission was granted; later Windows
asyncio startup stalled in socket._fallback_socketpair/accept without networking.
A 15-second faulthandler dump identified the loopback wait. After explicit network
permission, the unchanged core suite passed. No application code was changed to
work around the restriction, and no hung test process was left running.

Adapter verification:

```powershell
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_sumo_adapter.py -q --basetemp=work/tmp/sumo-adapter
.\ml-service\.venv\Scripts\python.exe -m simulation.sumo_adapter --status
```

Output: **5 passed, 1 skipped in 0.09s**. Runtime skip reason:
`SUMO runtime unavailable: sumo, netconvert`.
Status JSON: `enabled: false`, `available: false`, both tool paths null.
Unit checks cover disabled/no-side-effect behavior, explicit missing tools,
phase/timing/conflict trace rejection, compiled link mapping, and preserving
existing output. Synthetic XML test doubles establish adapter checks only;
they do not establish compatibility with an actual installed SUMO version.

Run the smoke test again after providing the executables. A failed installed
runtime smoke is a failure, not a skip. Current mode is **SKIPPED**, not working.

Final combined regression check:

```powershell
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_sumo_adapter.py tests/test_dashboard_api.py tests/test_simulation_api.py tests/test_api.py tests/test_health.py tests/test_controllers.py tests/test_controller_comparison.py tests/test_benchmark.py -q --basetemp=work/tmp/sumo-final
```

Output: **300 passed, 1 skipped in 10.93s**; skip reason unchanged.
The disabled CLI was also executed: `python -m simulation.sumo_adapter --output
artifacts/sumo/disabled-check` returned skipped JSON explaining the flag, exit 2,
without creating its output directory. No SUMO processes or servers were started.
`git diff --check` passed after removing a trailing blank line in README. Existing
unrelated changes were preserved; no commit, push or attribution was added.
