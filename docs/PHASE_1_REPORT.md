# Phase 1 report

Date: 2026-11-01 (Asia/Calcutta). Working project: Desktop `raah`.

## Status

Phase 1 scaffold and requested verification completed. This is not a trained congestion
model or functioning traffic controller. All provisional syllabus topics remain
**UNVERIFIED**; no complete coverage is claimed. Seed **57** is declared by the API and
project guidance. No stochastic experiment is run in this phase.

## Implemented

- `ml-service/`: FastAPI GET `/health`, explicit not-implemented controller status,
  local-origin CORS, import smoke check and isolated Python 3.12 environment.
- `client/`: React/Vite JS, axios health connection, Leaflet abstract virtual network
  using CRS.Simple and no external map tiles, and an empty Recharts results view.
- Root Python requirements and exact tested freeze, npm package manifest/lockfile,
  root/client `.env.example`, pytest configuration, API tests and live runtime checker.
- `simulation/`: documented placeholder for future synthetic scenarios and constrained
  rule-based virtual control; no physical signal integration.
- Ignore rules cover nested venvs, caches, node_modules, builds, local env files, keys,
  raw/private/sensitive data directories, scratch tools and generated model artifacts.
- No MongoDB, Stripe, auth integration, paid services, real private GPS, RL or deep learning.

## Installation and environment

The default Python is prerelease 3.15.0a7. An available bundled stable Python **3.12.14**
was used without a privileged install, preserving the earlier root `.venv`. The service
venv is `ml-service/.venv`. Node **24.22.1**, local npm/npx **12.2.1**, Windows 10.0.26200.
The local npm launcher depends on ignored tools in `work/`; normal npm works in a fresh
checkout once installed. Public project packages were installed after manifests were
created and inspected. No login or browser authorization was needed.

Executed from the repository root in PowerShell:

```powershell
New-Item -ItemType Directory -Force work/tmp,work/phase1
$env:TEMP = (Resolve-Path work/tmp).Path
$env:TMP = $env:TEMP
& 'C:/Users/Hrishit Vats/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m venv ml-service/.venv
.\ml-service\.venv\Scripts\python.exe -m pip install -r requirements.txt --disable-pip-version-check
.\npm.cmd --prefix client install --cache work/npm-cache --no-fund --no-audit
.\ml-service\.venv\Scripts\python.exe -m pip freeze
```

Outputs were captured with `Tee-Object` into ignored `work/phase1/*.log`; the freeze is
saved as `requirements.lock.txt`. The exact Python freeze is tested on Windows/Python 3.12;
it is not a universal cross-platform lock. Use `npm ci` with `client/package-lock.json`
for reproducible client installation. Installation summaries:

```text
Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
Installing collected packages: tzdata, typing-extensions, threadpoolctl, pyparsing, pygments, pluggy, pillow, packaging, numpy, narwhals, kiwisolver, iniconfig, idna, h11, fonttools, cycler, colorama, cloudpickle, click, certifi, annotated-types, annotated-doc, uvicorn, typing-inspection, scipy, python-dateutil, pytest, pydantic-core, opentelemetry-api, joblib, httpcore, contourpy, anyio, starlette, scikit-learn, pydantic, pandas, matplotlib, httpx, seaborn, fastapi
Successfully installed annotated-doc-0.0.5 annotated-types-0.8.0 anyio-4.16.0 certifi-2026.10.23 click-8.5.0 cloudpickle-3.1.2 colorama-0.4.6 contourpy-1.4.0 cycler-0.12.1 fastapi-0.162.0 fonttools-4.68.0 h11-0.16.0 httpcore-1.0.9 httpx-0.28.1 idna-3.20 iniconfig-2.3.1 joblib-1.6.0 kiwisolver-1.5.1 matplotlib-3.11.2 narwhals-2.28.0 numpy-2.5.4 opentelemetry-api-1.45.2 packaging-26.3 pandas-3.1.0 pillow-13.0.0 pluggy-1.7.0 pydantic-2.14.2 pydantic-core-2.50.2 pygments-2.21.0 pyparsing-3.3.3 pytest-9.2.0 python-dateutil-4.0.0 scikit-learn-1.9.1 scipy-1.18.1 seaborn-0.13.2 starlette-1.10.0 threadpoolctl-3.7.0 typing-extensions-4.16.0 typing-inspection-0.4.4 tzdata-2026.6 uvicorn-0.54.0
added 132 packages in 20s
npm warn install-scripts 1 package had install scripts blocked because they are not covered by allowScripts:
npm warn install-scripts   esbuild@0.28.2 (postinstall: node install.js)
npm warn install-scripts
npm warn install-scripts Run `npm install-scripts ls` to review, or `npm install-scripts approve <pkg>` to allow.
```

## Fixes and interpretation

- Initial pytest passed with a Starlette test-client deprecation warning. Replaced the
  wrapper with direct httpx.AsyncClient/ASGITransport; the final four tests pass cleanly.
- Initial live HTTP checks passed, but cleanup detected a child process still listening.
  Windows cleanup now terminates the owned process tree and polls for port closure;
  the final live check passes and confirms both servers stopped.

- Used a workspace temporary directory for tool operations, following the earlier
  resolved sandbox temporary-directory permission issue.
- npm 12 blocked esbuild's postinstall script. The available platform binary was sufficient;
  compilation succeeded without enabling the script or bypassing this policy.
- The first build succeeded with a >500 kB chunk warning. Split map/chart vendor chunks;
  removed an empty React chunk. The final build completes without those warnings.
- No dependency audits, model evaluations, browser-rendering/accessibility tests or
  real-world safety certification are claimed. Verification covers imports, API behavior,
  compilation and live HTTP integration. The frontend chart is deliberately empty.

## Verification outputs

Every command below exited 0. The live checker starts loopback-only processes on temporary
ports, terminates them in `finally`, waits for exit, and verifies both ports are closed.
API liveness does not establish model/controller readiness.

### Python import smoke check

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/smoke_imports.py
```

```text
{
  "python": "3.12.14",
  "fastapi": "0.162.0",
  "uvicorn": "0.54.0",
  "pandas": "3.1.0",
  "numpy": "2.5.4",
  "scikit-learn": "1.9.1",
  "joblib": "1.6.0",
  "matplotlib": "3.11.2",
  "seaborn": "0.13.2",
  "pytest": "9.2.0",
  "httpx": "0.28.1"
}
```

### Python dependency consistency

```powershell
.\ml-service\.venv\Scripts\python.exe -m pip check
```

```text
No broken requirements found.
```

### API tests

```powershell
.\ml-service\.venv\Scripts\python.exe -m pytest -q
```

```text
....                                                                     [100%]
4 passed in 0.38s
```

### Frontend production compilation

```powershell
.\npm.cmd --prefix client run build
```

```text
npm notice run raah-client@0.1.0 build
npm notice run vite build
vite v7.3.7 building client environment for production...
transforming...
✓ 721 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.60 kB │ gzip:  0.34 kB
dist/assets/index-C5JK7Z2K.css   17.70 kB │ gzip:  7.18 kB
dist/assets/map-DP-6SPKH.js     166.07 kB │ gzip: 48.91 kB
dist/assets/index-DwLtj1UW.js   273.95 kB │ gzip: 89.49 kB
dist/assets/charts-CkzeTGnj.js  321.65 kB │ gzip: 96.54 kB
✓ built in 2.67s
```

### Frontend dependency versions

```powershell
.\npm.cmd --prefix client ls --depth=0
```

```text
raah-client@0.1.0 C:\Users\Hrishit Vats\OneDrive\Desktop\raah\client
├── @vitejs/plugin-react@5.2.0
├── axios@1.21.0
├── leaflet@1.9.4
├── react-dom@19.3.1
├── react-leaflet@5.0.0
├── react@19.3.1
├── recharts@3.10.1
└── vite@7.3.7
```

### Live API / frontend proxy and cleanup

```powershell
.\ml-service\.venv\Scripts\python.exe tests/check_runtime.py
```

```text
START "C:\Users\Hrishit Vats\OneDrive\Desktop\raah\ml-service\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir ml-service --host 127.0.0.1 --port 56733
GET /health 200 {"status": "ok", "service": "raah-ml-service", "seed": 57, "data_mode": "synthetic-only", "controller": "not-implemented", "syllabus": "UNVERIFIED"}
START "C:\Users\Hrishit Vats\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.EXE" client/node_modules/vite/bin/vite.js client --host 127.0.0.1 --port 56734 --strictPort
GET frontend / 200 React entry HTML verified
GET frontend /api/health 200 Vite proxy matches API
STOPPED 49240 exit 1
STOPPED 37572 exit 1
PASS: temporary servers stopped; both ports closed
```

## Repository and limitations

`git check-ignore` confirmed service venv, client dependencies/builds, `.env`,
`client/.env.local`, `data/raw/private.csv` and a private-key path are excluded.
Root/client environment examples remain trackable. Ignore rules are preventative;
only synthetic data is allowed regardless of filename or directory.

Earlier `SETUP_STATUS.md` is historical; this report supersedes its no-manifests status.
No dataset, training, metrics, group split, preprocessing pipeline or controller exists
in Phase 1. These must later implement group separation, train-only fitting, reproducible
seed-57 scenarios and safe phase/clearance/starvation constraints with meaningful tests.
Production hosting must explicitly configure the public API base URL and CORS; the Vite
dev proxy is not part of a production build. No servers are left running by these checks.

Git identity is configured for the user's account. The Phase 1 commit includes project
source/manifests/docs only, without assistant contribution or co-author attribution.
No push is performed in this phase. The original Documents workspace is unchanged;
this phase lives in the requested Desktop copy.

Next action: provide the official syllabus to verify model permissions before implementing
semester model comparisons. Synthetic generation and controller implementation are later phases.
