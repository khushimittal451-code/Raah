# Local deployment and reproducibility notes

Prepared 2026-11-03 from the actual repository. **No hosted deployment was performed.**
The implemented target is a local/private single-user educational simulation, not
an authenticated multi-user production traffic service. No Docker/Compose files,
hosted deployment workflow, authentication, database or paid services are supplied.
Syllabus topics remain UNVERIFIED; no physical signal integration is allowed.

## Runtime setup

Use the [README setup commands](../README.md#setup-and-local-run) in the repository
root: Python 3.12 venv, `requirements.lock.txt`, Node matching `client/package.json`
and `npm --prefix client ci`. Inspect manifests before installation. Preserve an
existing working environment. Existing local fallback npm is under ignored `work/`
and is not available automatically on a fresh checkout.

Saved experiment versions include Python 3.12.14, numpy 2.5.4, pandas 3.1.0 and
scikit-learn 1.9.1. The latest QA checked all Python lock entries and found no
mismatches. Reuse the matching environment for trusted joblib artifacts; package/
platform changes can change compatibility or numerical behavior. No cross-version
byte-equivalence or universally fixed latency is promised.

## Trusted artifacts and readiness

`artifacts/`, venvs, caches, secrets, raw-sensitive directories and client `dist/`
are ignored by Git. The tracked synthetic data is not a substitute for model files.
For a model-enabled demo, restore a **trusted local** bundle; never load uploaded or
untrusted joblib files. Deserialization can execute code. The application checks
file hashes and schema/order consistency, not an external signature/trust authority.

Default layout:

```text
artifacts/
  final/
    classification_pipeline.joblib
    regression_pipeline.joblib
    feature_schema.json
    selection_manifest.json
    metrics.json
    test_access_claim.json
  classification/model_comparison.csv
  regression/regression_comparison.csv
```

The first four final files supply hash-checked inference pipelines and canonical
feature order. The metrics endpoint additionally requires the COMPLETE receipt,
matching selection hash, one-read/one-batch counters and matching metrics SHA-256.
The two sibling comparison CSVs must match the frozen selection hashes; if absent,
their comparison sections are explicitly unavailable. Preserve the original full
audit ledger and frozen assessment elsewhere with the experiment, including
`test_usage_events.jsonl`; do not delete/rewrite receipts or rerun a consumed test.
Raw held-out snapshots/predictions are not runtime inference prerequisites.

`RAAH_MODEL_DIR` overrides the final directory. Comparison lookup remains relative
to its parent, so keep the sibling layout. Use an absolute directory when launching
from a different working directory. Without artifacts, `/health` still returns 200,
`/model-info` describes unavailable tasks, inference and `/model-metrics` return
explicit 503, and fixed/rule-only demo simulation remains available. ML-assisted
demo/benchmark require valid estimates or explicit `model_fallback=rule_only`.

## Development mode

For the three-minute handoff, a combined local preview is also implemented:
build the client and run `python simulation/walkthrough.py --serve --port 5173`
with the project venv Python. It serves the actual API under `/api`, the compiled
client at `/` and saved training/benchmark figures under `/evidence`. It binds
only loopback, uses one process and is stopped with Ctrl+C. This is not hosted
deployment or multi-user isolation. See [HANDOFF.md](HANDOFF.md) for current
acceptance results and [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for the timed presentation.

Run these in separate PowerShell terminals from the root:

```powershell
# API terminal; state is shared within this one process
.\ml-service\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir ml-service --host 127.0.0.1 --port 8000 --workers 1
```

```powershell
# Client terminal
$env:RAAH_API_TARGET='http://127.0.0.1:8000'
npm --prefix client run dev
```

Open <http://127.0.0.1:5173>. Vite's development proxy forwards `/api/...` to the
API after stripping `/api`. No extra prefix is registered by FastAPI itself.
These shell variables are per process/terminal; root `.env.example` is not loaded
by the API. Starting a second API worker creates unrelated state and is unsupported.
Every tab/client shares one demo per worker; a reset replaces it. Process restart
loses state and cached last benchmark. Keep the demo local or within a controlled
private access boundary: CORS is not authentication or a multi-user safety mechanism.

## Compile and inspect a static build locally

Example using direct API access from a local preview, without relying on a production
proxy. Start the API terminal with the matching allowed origin:

```powershell
$env:RAAH_CORS_ORIGINS='http://127.0.0.1:4173'
.\ml-service\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir ml-service --host 127.0.0.1 --port 8000 --workers 1
```

In the client terminal:

```powershell
$env:VITE_API_BASE_URL='http://127.0.0.1:8000'
npm --prefix client run build
npm --prefix client run preview -- --host 127.0.0.1 --port 4173
```

Open <http://127.0.0.1:4173>. This is a local preview recipe, not a claimed hosted
deployment or a permanent public serving strategy. Remove temporary shell variables
or open fresh terminals before returning to dev mode. `VITE_API_BASE_URL` is baked
into the build, so changing a server variable after compilation does not change it.

For a separately managed static host, serve `client/dist`, configure the public
API base URL at build time, and set exact frontend origins in `RAAH_CORS_ORIGINS`
(comma-separated). For a same-origin `/api` layout, the serving layer must forward
and strip that prefix; Vite's dev proxy is not embedded in static files. HTTPS pages
need an HTTPS-compatible API; TLS/reverse-proxy configuration and hosted verification
are **not implemented here**. Do not expose this unauthenticated stateful demo as a
shared public application while describing it as isolated or production-ready.

## Configuration reference

| Variable | Consumed by | Actual role |
| --- | --- | --- |
| RAAH_MODEL_DIR | API at startup | Trusted final artifact directory; default repository artifacts/final |
| RAAH_CORS_ORIGINS | API at creation | Comma-separated allowed origins; defaults localhost and 127.0.0.1 port 5173 |
| RAAH_API_TARGET | Vite dev process | Proxy backend target; default http://127.0.0.1:8000 |
| VITE_API_BASE_URL | Client build/dev | Public HTTP base; defaults /api |
| RAAH_ENABLE_SUMO | Standalone SUMO adapter | Exact 1 enables smoke execution; main API never imports it |
| SUMO_HOME | Optional adapter lookup | Local installation root containing bin/ |

Never store secrets in `VITE_` values or commit `.env` files. No paid key is required.
OpenStreetMap tiles require visible contributor attribution and conservative usage;
the schematic fallback needs no tile service. The client does not prefetch/download
tiles for offline use. OSM geometry-import instructions in SUMO_SETUP are manual,
not an implemented automatic network-import feature.

## Acceptance and cleanup

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/model-info
Invoke-RestMethod http://127.0.0.1:8000/model-metrics
.\ml-service\.venv\Scripts\python.exe -m pytest -q
npm --prefix client test
npm --prefix client run build
```

Use [DEMO_SCRIPT.md](DEMO_SCRIPT.md) to check controls, explicit fallback, stale/error
states and map attribution. Model readiness is separate from liveness; cached metrics
are not live accuracy. Tests use synthetic fixtures; final-evaluation tests do not
repeat the real assessment. Windows asyncio tests need loopback access; restricted
networking previously stalled local socket-pair initialization. Stop local servers
with Ctrl+C. The HTTP check scripts stop owned servers in finally blocks.

Latest historical QA (2026-11-02): **654 Python passes, 1 unavailable-SUMO skip,
42 client passes, production build pass**. No new server, build, training or test
assessment was run to author these notes. Real-browser visual verification remains
unverified; analysis figures are not screenshots.

## Reproduce development experiments without consuming test again

The following commands use the saved train/validation splits, fresh output locations
and new findings files. They are optional instructions, **not executed for this
documentation**. Choose a fresh experiment directory rather than overwrite originals:

```powershell
New-Item -ItemType Directory -Path work/reproduction -Force | Out-Null
.\ml-service\.venv\Scripts\python.exe ml-service/training/train_regression.py --output-dir artifacts/reproduction/regression --findings-path work/reproduction/regression.md
.\ml-service\.venv\Scripts\python.exe ml-service/training/train_classification.py --output-dir artifacts/reproduction/classification --findings-path work/reproduction/classification.md
.\ml-service\.venv\Scripts\python.exe ml-service/training/unsupervised.py --output-dir artifacts/reproduction/unsupervised --findings-path work/reproduction/unsupervised.md
.\ml-service\.venv\Scripts\python.exe simulation/benchmark.py --output-dir artifacts/reproduction/benchmark --findings work/reproduction/benchmark.md
```

Regression/classification read train+validation only; unsupervised reads train only;
benchmark uses new synthetic traces and frozen inference models. The optional SUMO
runtime smoke is documented separately in [SUMO_SETUP.md](SUMO_SETUP.md), last skipped
because sumo/netconvert were unavailable. It does not support ML-adaptive control.

To regenerate dataset/splits for audit, use new directories rather than replace the
tracked dataset:

```powershell
.\ml-service\.venv\Scripts\python.exe simulation/generate_data.py --seed 57 --output-dir artifacts/reproduction/data
.\ml-service\.venv\Scripts\python.exe ml-service/training/prepare_data.py --data-dir artifacts/reproduction/data --output-dir artifacts/reproduction/splits --audit-path work/reproduction/leakage.md
```

Do not use `final_evaluation.py --evaluate` in a casual setup/demo, delete its receipt,
or choose a different output directory to repeat the consumed held-out assessment.
Any future claim after tuning needs a genuinely new independent holdout and a new
documented selection/evaluation protocol. Reading saved aggregate metrics/plots is
sufficient for this handoff.
