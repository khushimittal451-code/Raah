# Final QA report

Date: **2026-11-02, Asia/Calcutta**. Repository: Desktop/raah.

**PASS for the executed educational-simulation checks, after two defects were
fixed.** Final Python suite: **654 passed, 1 skipped**. Client: **42 passed** and
production build passed. This is not certification of real-road safety, live GPS
accuracy, model superiority, official syllabus coverage or production readiness.

AGENTS.md was read before execution. Existing dashboard, simulation API and SUMO
work was preserved. No dependencies were installed, no login/privileged action was
performed, and no Git identity, contributor attribution, commit or push was added.

## Audit results

| Area | Result | Evidence and limits |
| --- | --- | --- |
| Run-group split separation | PASS | 30 independent declared runs: train 18/8,712 rows; validation 6/2,904; test 6/2,904. Pairwise run overlap zero. Rebuilt CSV splits are byte-identical to saved splits. |
| Label provenance and leakage | PASS with disclosed limits | Preparation verifies exact same-run/junction/approach t+60 future-wait source, unique snapshot keys, time order, current values, unique run seeds and nonidentical renamed trajectories. All audit assertions passed. Current congestion is still a deterministic synthetic feature-derived index. |
| Prediction-time feature lists | PASS | Classification selects only incoming/outgoing counts, phase, elapsed phase time and time of day; identifiers, targets, five direct label-rule inputs and GPS sample-count proxy are excluded. Regression selects 11 current fields, excludes identifiers/targets/future values, and retains current wait as a valid persistence covariate. |
| Train-only transforms | PASS | Full tests instrument estimator/transformer fits, missing values, unseen categories, canonical ordering and unchanged learned state. Imputation/scaling/encoding/polynomial expansion fit train only during comparisons; PCA/clustering fit train only. No tuning was added; future tuning must use grouped folds. |
| Frozen final-test protocol | PASS | Completed receipt still records one test CSV read and one prediction batch per selected model. All 28 protected raw/split/final files retain their pre-QA hashes. No real held-out predictions, scoring, selection or refit were repeated. Final-evaluation unit tests operate on temporary synthetic fixtures. Split auditing reads group/source records for integrity, not model selection. |
| Reproducibility | PASS within this environment | Seed 57 retained. Generator tests compare all exports byte-for-byte. Split reconstruction matches. Fresh validation classification metrics match saved values within 1e-12, regression within 1e-9. Two complete benchmarks produce 116 byte-identical artifacts. Timing/BLAS/platform and version changes can still change runtime or floating-point results. |
| Phase conflicts, clearance and starvation | PASS for virtual assumptions | Full invariant tests and 75 benchmark rollouts: zero constraint violations. Explicit legal phase sequence, minimum/maximum green, yellow/all-red and fairness constraints remain active. Maximum observed axis red 68 s, below the configured 75 s bound. This bounds signal opportunity, not vehicle waiting under overload. |
| Model/API failure handling | PASS after fix | Missing/corrupt artifacts produce explicit unavailable responses; invalid requests return 422; no fake predictions. Batch cap 100, atomic step/reset, generation/tick conflicts, explicit ML fallback and benchmark caps are covered. Changed/incomplete metrics evidence now returns 503. Real HTTP checks: 14 inference/health cases and 48 simulation cases passed; all four owned server threads stopped and ports closed. |
| OSM attribution and usage | PASS for inspected implementation | Visible map attribution and a persistent contributor link, HTTPS tile URL, normal browser caching/referrer, bounded zoom/extent, no prefetch and schematic fallback. Leaflet component/integration tests passed. No tiles were bulk downloaded. Browser/network deployment behavior was not visually verified during this audit. |
| Simulated vs live labels | PASS | Dashboard/map explicitly show SIMULATED DATA, backend observations/virtual lamps, no live GPS/physical-control claims. Actual synthetic congestion, advisory predictions and lamp indications are separate. No frontend random traffic or recording substitution is used at runtime. |
| Secrets/exclusions | PASS after fix, scoped scan | No candidate credentials in 112 scanned current reviewable text files; no tracked .env/private-key containers. Only public .env.example files found at root/client/service lookup locations. Git integration verifies sensitive paths at root and service depth are excluded while public config/synthetic CSV remain reviewable. This is a heuristic current-tree audit, not a Git-history or comprehensive credential-security certification. |
| Tests and dependency consistency | PASS | Full Python/client suites, imports, pip check, lockfile comparison and client build passed. Git diff whitespace check passed. No locked Python package mismatches. |
| Optional SUMO | SKIPPED | Runtime smoke skips because sumo/netconvert are unavailable. Its feature-gate/configuration/safety unit checks passed; the main simulator remains independent. |
| Official syllabus | UNVERIFIED | No official evidence supplied. Provisional methods remain labeled; IQR/z-score exploration remains SKIPPED_UNVERIFIED. No RL, deep learning, hardware integrations or paid traffic APIs were added. |

The authoritative 60/20/20 split protects final-test groups from the earlier EDA
training pool. **Two validation runs were previously explored in EDA**:
run-57-0026 and run-57-0028. Validation is a development set, not a pristine holdout.
Earlier notebooks retain their documented historical split; they were not rerun or
silently reinterpreted in this QA. Synthetic simulator truth for counts/queues/wait
does not establish GPS-only sensing, independence of real traffic or live accuracy.

## Defects reproduced and fixed

| Defect | Before | Change | After |
| --- | --- | --- | --- |
| Saved dashboard metrics could be edited while retaining matching selection/pipeline references | FAIL: five new cases did not raise on altered metrics, missing/incomplete receipt, wrong receipt selection or repeated-read count | dashboard_api reads metrics once, verifies its SHA-256 against the COMPLETE test-access receipt, matching selection and exact single-read/single-batch counters; invalid evidence stays unavailable | PASS: all cases rejected, including HTTP 503 metrics_unavailable; legitimate saved metrics and both validation comparisons still load |
| Sensitive-data ignores matched only root data folders | FAIL: Git integration showed ml-service/data/raw, private and sensitive paths were unprotected | Replace root-relative data exclusions with **/data/raw/, **/data/private/ and **/data/sensitive/ | PASS: Git exclusion integration and audit both pass; canonical synthetic CSVs remain reviewable |

Task changes are limited to .gitignore, ml-service/app/dashboard_api.py,
tests/test_dashboard_api.py, tests/test_repository_hygiene.py and this report.
QA scripts/logs live in ignored work/final-qa; fresh experiment outputs live in
ignored artifacts/final_qa. Training, frozen models, raw data and controller code
were not rewritten. A Windows newline issue in the temporary ignore-audit harness
was corrected by using NUL-delimited Git stdin/output before diagnosing real gaps.

## Executed checks and commands

All commands ran from the project root with existing tools. Project venv Python
3.12.14; Node 24.22.1; workspace npm CLI 12.2.1; Git 2.53.0.windows.3.

Python packages: numpy 2.5.4, pandas 3.1.0, scikit-learn 1.9.1, FastAPI 0.162.0,
pytest 9.2.0, httpx 0.28.1, joblib 1.6.0, matplotlib 3.11.2, seaborn 0.13.2.
The complete installed Python lockfile comparison found no mismatches.

### All tests and compilation

```powershell
$env:TEMP=(Resolve-Path work/tmp).Path
$env:TMP=$env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest -q --basetemp=work/tmp/final-qa-complete
node work/tools/npm/package/bin/npm-cli.js --prefix client test
node work/tools/npm/package/bin/npm-cli.js --prefix client run build
.\ml-service\.venv\Scripts\python.exe -m pip check
.\ml-service\.venv\Scripts\python.exe -c "import fastapi,pandas,numpy,sklearn,joblib,matplotlib,seaborn,pytest,httpx,uvicorn; print('IMPORT SMOKE PASS')"
git diff --check
```

Actual final output:

```text
654 passed, 1 skipped in 35.80s
SKIPPED: SUMO runtime unavailable: sumo, netconvert
Client: Test Files 4 passed (4); Tests 42 passed (42); Duration 6.82s
Build: 669 modules transformed; built in 4.60s
No broken requirements found.
IMPORT SMOKE PASS
git diff --check: exit 0 (LF/CRLF notices only)
```

Before new regression tests, the unchanged Python suite passed 648 tests with the
same SUMO skip. The five metrics regression cases and one exclusion integration
test account for the final increase. The receipt repair was followed by a full
653-pass suite; the exclusion repair was followed by the final 654-pass suite.
No failed implementation checks remain in the final run.

Production bundle: index JS 238.31 kB, map 166.73 kB, charts 358.90 kB, CSS 26.62 kB.
Compilation and jsdom/Leaflet tests do not establish real-browser visual appearance;
no new browser end-to-end or screenshot success is claimed here.

### Split and training smoke checks

```powershell
.\ml-service\.venv\Scripts\python.exe ml-service/training/prepare_data.py --output-dir artifacts/final_qa/splits-audit --audit-path work/final-qa/leakage-audit.md
.\ml-service\.venv\Scripts\python.exe ml-service/training/train_classification.py --output-dir artifacts/final_qa/classification --findings-path work/final-qa/classification-findings.md --batch-repeats 1 --single-repeats 2
.\ml-service\.venv\Scripts\python.exe ml-service/training/train_regression.py --output-dir artifacts/final_qa/regression --findings-path work/final-qa/regression-findings.md
.\ml-service\.venv\Scripts\python.exe ml-service/training/unsupervised.py --output-dir artifacts/final_qa/unsupervised --findings-path work/final-qa/unsupervised-findings.md
```

All exited 0. Classification/regression explicitly printed
`Test opened/scored: False False`. Unsupervised printed
`Validation/test opened: False False`. No source data or original experiment
artifacts were replaced. Preprocessing factories and full train-only workflows
were exercised by the full test suite.

| Fresh validation classifier | Accuracy | Macro-F1 |
| --- | ---: | ---: |
| LogisticRegression | 0.700069 | 0.489339 |
| KNN | 0.704890 | 0.537601 |
| GaussianNB | 0.662190 | 0.472884 |
| SVC | 0.730372 | 0.510306 |
| DecisionTreeClassifier | 0.724518 | 0.509029 |
| RandomForestClassifier | 0.729683 | 0.526603 |

| Fresh validation regression | MAE seconds | RMSE seconds | Negative predictions |
| --- | ---: | ---: | ---: |
| Current-wait persistence | 10.102998 | 13.315676 | 0 |
| Linear regression | 7.017311 | 9.549969 | 350 |
| Degree-2 polynomial linear regression | 6.139516 | 8.390615 | 289 |

Fresh validation metrics reproduce the existing saved comparisons; latency and
training duration are machine/load dependent and were not used to alter selection.
No new tuning or frozen-model promotion occurred.

Train-only unsupervised smoke: K-Means fit 8,712 rows, sampled silhouette 0.184828;
hierarchical fit the disclosed 2,000-row training sample, sampled silhouette
0.153415. DBSCAN found one non-noise cluster and 1,404 noise rows, so its silhouette
is undefined and not fabricated. PCA first-two-component variance fraction:
0.5633753244. Cluster IDs are not ground-truth congestion labels.

### Paired benchmark and reproducibility

```powershell
.\ml-service\.venv\Scripts\python.exe simulation/benchmark.py --output-dir artifacts/final_qa/benchmark-a --findings work/final-qa/benchmark-findings.md
.\ml-service\.venv\Scripts\python.exe simulation/benchmark.py --output-dir artifacts/final_qa/benchmark-b --findings work/final-qa/benchmark-repeat.md --verify-against artifacts/final_qa/benchmark-a
```

Both exited 0. Defaults: seed 57, five scenarios, five independent derived seeds
each, 180 s warm-up plus 600 s measurement, three policies, 2,000 run-bootstrap
resamples. All exogenous arrival/capacity/noise traces are saved before policy
rollouts and shared by hash. Run-level uncertainty, p95/max waiting, queues,
throughput, fairness, phase changes, censoring and adverse cases were exported.

```text
PASS 75 rollouts; 0 constraint violations; 30 adverse wait pairs; 116 hashed artifacts
REPRODUCIBILITY PASS: 116 artifacts byte-identical, including plots, traces and compressed logs
```

Scenario mean observed waits, averaging five runs (seconds):

| Scenario | Fixed-time | Rule-only | ML-assisted |
| --- | ---: | ---: | ---: |
| Low | 14.237 | 9.157 | 9.498 |
| Medium | 21.549 | 35.038 | 33.213 |
| High | 200.151 | 238.509 | 236.920 |
| Asymmetric rush-hour | 94.355 | 33.177 | 33.123 |
| Incident | 53.342 | 93.520 | 90.891 |

Both adaptive controllers have worse mean wait than fixed-time in every one of
the five medium, high and incident runs: **30/50 adverse policy/trace pairs**.
No universal improvement is supported. ML falls back to queue-only rules for an
average 25.8% of ticks across its 25 runs, including warm-up, due to rejected or
unavailable estimates. Maximum observed vehicle wait is 473 s despite maximum red
being 68 s: overloaded queues are not eliminated by signal fairness. Finite-horizon
waits are right-censored, not eventual complete delays. Simplified point-queue
dynamics differ from the training generator and limit transfer claims.

### HTTP runtime and repository integrity

```powershell
.\ml-service\.venv\Scripts\python.exe tests/check_api_runtime.py
.\ml-service\.venv\Scripts\python.exe tests/check_simulation_runtime.py
.\ml-service\.venv\Scripts\python.exe work/final-qa/audit_repository.py
```

All exited 0 after repairs. Real HTTP: 14 health/inference cases and 48 simulation
cases across saved/missing-model modes, including 200/409/422/503 behavior,
explicit fallback, unchanged state on failed atomic steps and deterministic
35-tick replay versus five seven-tick requests. Every owned server reports
thread_stopped=true and port_closed=true. Metrics tamper/missing-receipt responses
are additionally checked through ASGI HTTP tests.

Current-tree secret scan uses private-key markers, recognizable provider tokens
and long credential assignments, reporting only file/line/type with values
redacted. It scanned 112 Git-reviewable text files before this report was added;
no candidates or tracked secret-key/.env files were found. Thirteen representative
ignore paths passed the audit; the regression test covers sixteen protected and
three intentionally public paths. Git history, ignored local caches and arbitrary
external directories were not scanned. The only discovered env files in root,
client and service directories were root/client .env.example files.

Raw data, splits, final pipelines, feature schema, saved metrics, selection,
test-access receipt and usage ledger: **28/28 protected hashes unchanged**. The
three rebuilt split CSVs match their originals byte-for-byte. Completed test
receipt counters remain 1/1/1; no held-out performance was recomputed for QA.

## Remaining limitations and evidence locations

- Saved final aggregates, read without re-evaluation, already show KNN macro-F1
  0.503522 and MEDIUM recall 0.055363. This is weak minority-class behavior, not a
  reliable congestion classifier for real deployment. No acceptance threshold was
  invented and no model was retuned using those results.
- Saved regression has 441 negative held-out predictions. API output remains raw
  and explicitly flagged; the ML controller rejects unsafe estimates and applies
  the documented fallback only when requested. Validation smoke also retains its
  289 negative polynomial predictions without clipping or hiding them.
- Controller safety is virtual, with simplified opposing through movements,
  parallel crossings, no turning conflicts and no late WALK entry. The fixture
  does not validate real pedestrian behavior or physical signal operation.
- Simulation API is one shared single-user state per process; use one worker.
  It is a local educational demo, without authentication or a multi-user tenancy
  guarantee. Advisory forecasts do not change fixed/rule-only decisions.
- SUMO runtime and real-browser visual verification remain unavailable/unverified;
  neither blocks the original simulator or changes the automated pass results.
- Official syllabus remains UNVERIFIED, and benchmark superiority is not claimed.

Full logs, the audit script, version/protected-hash snapshot and machine-readable
audit evidence are in work/final-qa. Training/benchmark outputs and plots are in
artifacts/final_qa. This report and a compact evidence archive are also copied to
the chat's outputs directory for review.

OSM inspection was checked against the current primary
[OSMF tile usage policy](https://operations.osmfoundation.org/policies/tiles/):
the map retains visible attribution, normal browser requests, conservative usage
and no tile-download/offline-cache feature. The offline mode is a schematic.
