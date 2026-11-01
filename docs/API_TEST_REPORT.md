# API test report

Status: PASS. Generated UTC: 2026-11-01T21:49:39.414599+00:00.

Implemented GET /health, GET /model-info, POST /predict/congestion, POST /predict/wait and POST /predict/batch.
No dependencies were installed. Used the existing Python 3.12 project venv, FastAPI, pandas, NumPy, joblib, pytest, httpx and Uvicorn.

## Request and model contract

Both single prediction endpoints require the complete existing TrafficObservation object below. Extra fields (including targets) are forbidden. The strict canonical schema validates ranges, types, required fields, counts, phase enums, the 10-second timestamp grid, timestamp/time-of-day agreement and snapshot consistency. Speed may be null only with zero GPS-like samples. Missing required fields return 422. These are synthetic aggregates, never live GPS.

```json
{
  "run_id": "api-smoke-57",
  "timestamp_seconds": 600,
  "intersection_id": "junction-1",
  "approach_id": "north",
  "mean_speed_kmh": 50.0,
  "free_flow_speed_kmh": 60.0,
  "vehicle_count": 20,
  "queue_length_vehicles": 4,
  "mean_wait_seconds": 10.0,
  "incoming_vehicles": 2,
  "outgoing_vehicles": 1,
  "current_phase": "ns_green",
  "seconds_in_phase": 10.0,
  "time_of_day": 0.16666666666666666,
  "gps_sample_count": 10
}
```

Batch request: `{"observations": [<observation>, ...]}` with 1-100 items. Invalid rows reject the entire request with 422. Results retain input order via zero-based `index`; each includes both congestion and future wait. Missing either model makes the entire batch unavailable (503), without partial or fabricated predictions.

The API projects validated observations into the exact saved task feature order; identifiers and target fields never reach models. Classification uses five inputs: incoming_vehicles, outgoing_vehicles, current_phase, seconds_in_phase, time_of_day. Regression uses eleven inputs: mean_speed_kmh, free_flow_speed_kmh, vehicle_count, queue_length_vehicles, mean_wait_seconds, incoming_vehicles, outgoing_vehicles, current_phase, seconds_in_phase, time_of_day, gps_sample_count. Saved transformed feature order and fitted pipeline input order are also checked. Nothing is fitted at startup or request time.

Startup reads selection_manifest.json, feature_schema.json and each task's joblib from `artifacts/final`, or the directory specified by RAAH_MODEL_DIR. Artifact SHA-256 hashes, selection consistency and schema version/order must agree before loading a task. Model version is the SHA-256 of the frozen selection manifest: `e3605e36e02326835d0e762e6a0ddb5cba435968523c74988bd4f6516155f85c`. Only trusted local joblib files are supported; no model-upload endpoint exists. CORS permits configured local origins and GET/POST.

GET /health reports liveness independently of model readiness. GET /model-info returns task availability, failure reasons, version, feature lists, selected model names and artifact hashes. Missing/corrupt/mismatched models or failed/nonfinite predictions return HTTP 503 with `detail.code=model_unavailable`. Validation still returns 422 when models are missing.

## Executed commands

From the Desktop raah repository in PowerShell:

```powershell
$env:TEMP=(Resolve-Path work/tmp).Path
$env:TMP=$env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_health.py -q --basetemp=work/tmp/api-pytest-final
.\ml-service\.venv\Scripts\python.exe tests/check_api_runtime.py
git diff --check
```

Pytest output:

```text
...............................                                          [100%]
31 passed in 1.47s
```

Tests cover the five routes, exact feature projection/order, version consistency, batch ordering and 0/100/101 boundaries, invalid rows/ranges/types/phase/missing fields/target extras, valid null sampled speed, missing metadata and a single missing model, corrupt hashes, input/transformed schema drift, inference exceptions/nonfinite outputs, explicit negative-wait warnings and POST CORS. Estimator doubles use only tiny synthetic fixtures; actual saved pipelines are checked through real localhost HTTP below. The existing health tests also pass.

Git diff check: exit 0; no whitespace errors. Git emitted existing LF-to-CRLF conversion notices. Existing unrelated modifications were preserved. No commit or push was made for this request.

## Local HTTP results

| Mode | Request | HTTP | Expected |
|---|---|---:|---:|
| saved-models | GET /health | 200 | 200 |
| saved-models | GET /model-info | 200 | 200 |
| saved-models | POST /predict/congestion | 200 | 200 |
| saved-models | POST /predict/wait | 200 | 200 |
| saved-models | POST /predict/batch | 200 | 200 |
| saved-models | POST /predict/wait | 422 | 422 |
| saved-models | POST /predict/batch | 422 | 422 |
| missing-models | GET /health | 200 | 200 |
| missing-models | GET /model-info | 200 | 200 |
| missing-models | POST /predict/congestion | 503 | 503 |
| missing-models | POST /predict/wait | 503 | 503 |
| missing-models | POST /predict/batch | 503 | 503 |
| missing-models | POST /predict/wait | 422 | 422 |
| missing-models | POST /predict/batch | 422 | 422 |

Actual console output:

```text
START saved-models Uvicorn on 127.0.0.1:60721
saved-models GET /health 200 {"status": "ok", "service": "raah-ml-service", "seed": 57, "data_mode": "synthetic-only", "controller": "not-implemented", "syllabus": "UNVERIFIED"}
saved-models GET /model-info 200 {"model_version": "e3605e36e02326835d0e762e6a0ddb5cba435968523c74988bd4f6516155f85c", "status": "PROVISIONAL_UNVERIFIED", "data_mode": "synthetic-only", "prediction_horizon_seconds": 60, "tasks": {"classification": {"available": true, "input_features": ["incoming_vehicles", "outgoing_vehicles", "current_phase", "seconds_in_phase", "time_of_day"], "error": null, "model": "KNN", "pipeline_sha256": "a2d174ddaab0df5d2429c110517a204d5859216c794988fa1df0191106831fa0"}, "regression": {"available": true, "input_features": ["mean_speed_kmh", "free_flow_speed_kmh", "vehicle_count", "queue_length_vehicles", "mean_wait_seconds", "incoming_vehicles", "outgoing_vehicles", "current_phase", "seconds_in_phase", "time_of_day", "gps_sample_count"], "error": null, "model": "polynomial_degree2", "pipeline_sha256": "502e01753d81ac8112cd54b29219cbf94472767704b17aee5d833a362a1dd2d7"}}}
saved-models POST /predict/congestion 200 {"model_version": "e3605e36e02326835d0e762e6a0ddb5cba435968523c74988bd4f6516155f85c", "congestion_level": "HIGH"}
saved-models POST /predict/wait 200 {"model_version": "e3605e36e02326835d0e762e6a0ddb5cba435968523c74988bd4f6516155f85c", "future_wait_seconds": 24.236191260270466, "prediction_horizon_seconds": 60, "nonphysical_wait": false, "warning": null}
saved-models POST /predict/batch 200 {"model_version": "e3605e36e02326835d0e762e6a0ddb5cba435968523c74988bd4f6516155f85c", "predictions": [{"index": 0, "congestion_level": "HIGH", "future_wait_seconds": 24.236191260270452, "prediction_horizon_seconds": 60, "nonphysical_wait": false, "warning": null}, {"index": 1, "congestion_level": "HIGH", "future_wait_seconds": 22.948493533102514, "prediction_horizon_seconds": 60, "nonphysical_wait": false, "warning": null}]}
saved-models POST /predict/wait 422 ["Input should be greater than or equal to 0"]
saved-models POST /predict/batch 422 ["List should have at most 100 items after validation, not 101"]
STOPPED saved-models thread_stopped True port_closed True
START missing-models Uvicorn on 127.0.0.1:60727
missing-models GET /health 200 {"status": "ok", "service": "raah-ml-service", "seed": 57, "data_mode": "synthetic-only", "controller": "not-implemented", "syllabus": "UNVERIFIED"}
missing-models GET /model-info 200 {"model_version": null, "status": "PROVISIONAL_UNVERIFIED", "data_mode": "synthetic-only", "prediction_horizon_seconds": 60, "tasks": {"classification": {"available": false, "input_features": ["incoming_vehicles", "outgoing_vehicles", "current_phase", "seconds_in_phase", "time_of_day"], "error": "bundle_metadata_unavailable: FileNotFoundError"}, "regression": {"available": false, "input_features": ["mean_speed_kmh", "free_flow_speed_kmh", "vehicle_count", "queue_length_vehicles", "mean_wait_seconds", "incoming_vehicles", "outgoing_vehicles", "current_phase", "seconds_in_phase", "time_of_day", "gps_sample_count"], "error": "bundle_metadata_unavailable: FileNotFoundError"}}}
missing-models POST /predict/congestion 503 {"detail": {"code": "model_unavailable", "reason": "classification: bundle_metadata_unavailable: FileNotFoundError"}}
missing-models POST /predict/wait 503 {"detail": {"code": "model_unavailable", "reason": "regression: bundle_metadata_unavailable: FileNotFoundError"}}
missing-models POST /predict/batch 503 {"detail": {"code": "model_unavailable", "reason": "classification: bundle_metadata_unavailable: FileNotFoundError"}}
missing-models POST /predict/wait 422 ["Input should be greater than or equal to 0"]
missing-models POST /predict/batch 422 ["List should have at most 100 items after validation, not 101"]
STOPPED missing-models thread_stopped True port_closed True
```

The smoke script starts Uvicorn with a pre-bound 127.0.0.1 socket in an owned thread and makes HTTP requests using httpx (not an in-process ASGI transport). It loads the saved bundle first, then an intentionally absent bundle. It sets should_exit, joins the server thread and verifies closed ports in finally blocks. Cleanup results:

```json
[
  {
    "mode": "saved-models",
    "port": 60721,
    "port_closed": true,
    "thread_stopped": true
  },
  {
    "mode": "missing-models",
    "port": 60727,
    "port_closed": true,
    "thread_stopped": true
  }
]
```

Raw HTTP response bodies, including full 422 diagnostics, are stored in `docs/API_HTTP_OUTPUT.json`. Command transcripts remain in `work/api-pytest.txt` and `work/api-http-output.txt`.

## Initial failure and repair

The first subprocess-based smoke attempt returned correct saved-model endpoint responses, but Windows taskkill failed with exit 1 (the shell reported incorrect user name/password). A follow-up socket check confirmed that first port 49927 was closed and the owned process was no longer present. No login or privileged action was attempted. The smoke harness was changed to own Uvicorn in the same process, eliminating the Windows launcher/process-tree dependency. The final two-server run above passed all requests and explicit cleanup checks.

## Limitations and evaluation isolation

Models remain PROVISIONAL_UNVERIFIED; no official syllabus coverage is asserted. The congestion labels are synthetic rule-derived labels, and inference does not establish real-world accuracy. The regression predicts mean queue waiting at exact t+60 seconds. Raw polynomial predictions can be negative; responses preserve them and set nonphysical_wait=true plus warning=negative_model_output. Consumers must heed that flag. No physical signal or virtual controller action is performed.

The smoke request is newly authored synthetic data. No held-out CSV, held-out prediction table or held-out metrics were opened, scored or used for tuning. The frozen selection, schemas and joblib files were read without modification. The focused pytest suite avoids rerunning offline evaluation tests. Single versus batch floating-point predictions can differ at machine precision.

Next action: none required for this API task. For manual use, start locally with `.\ml-service\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir ml-service --host 127.0.0.1 --port 8000`; interactive API documentation is at http://127.0.0.1:8000/docs while running.
