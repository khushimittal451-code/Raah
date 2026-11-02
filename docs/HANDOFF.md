# Raah handoff

Date: **2026-11-03 (Asia/Calcutta)**. Educational **synthetic-only, virtual-only**
project. Seed **57**. Official syllabus topics remain **UNVERIFIED**. No RL/deep
learning, real private GPS, paid traffic services or physical signal integration.

## What is ready

- A [three-minute presenter script](DEMO_SCRIPT.md) covering scenario selection,
  fixed-time, identical-arrival reset, ML-assisted operation, comparison charts,
  classification evidence, training clusters/PCA and safety limitations.
- `simulation/walkthrough.py --verify`: private-service, exact 60-tick paired
  replay with an explicit fallback option; it writes a receipt and checks arrival
  equality, legal phases/clearances, conflicts, pedestrian assumptions and red bounds.
- `simulation/walkthrough.py --serve`: one-process loopback preview of the built
  client, actual `/api` and saved `/evidence` plots. No hosted deployment is created.
- Real saved benchmark/confusion figures plus training K-Means/PCA variance figures
  under `docs/figures/`. The clustering/PCA portion is **saved train-only evidence**,
  not a live dashboard clustering feature or a signal-control input.

The 180-second schedule is verified arithmetically, not a claimed timed browser
recording. Startup, model restoration and loading the evidence tabs are preflight.
Browser visual acceptance is still UNVERIFIED; see the screenshot section below.

## Start the repeatable demo

From the repository root in PowerShell, with the existing Python 3.12 venv and
installed client dependencies:

```powershell
npm --prefix client run build
.\ml-service\.venv\Scripts\python.exe simulation/walkthrough.py --verify --allow-rule-fallback --output artifacts/demo-take-001
.\ml-service\.venv\Scripts\python.exe simulation/walkthrough.py --serve --port 5173
```

Choose a fresh empty verifier output directory for another take; existing evidence
is deliberately preserved. The server stays in the foreground; stop it with Ctrl+C.
It binds only 127.0.0.1 and runs one worker. Do not use multiple workers or concurrent
demo tabs: reset/step state is shared within the process and not persistent.

| Link while preview is running | Use |
| --- | --- |
| <http://127.0.0.1:5173> | Actual dashboard, run/pause/reset and scenario/controller selection |
| <http://127.0.0.1:5173/api/health> | Liveness only |
| <http://127.0.0.1:5173/api/model-info> | Actual model readiness/schema/version |
| <http://127.0.0.1:5173/api/model-metrics> | Hash-verified saved metrics and validation comparisons |
| <http://127.0.0.1:5173/evidence/benchmark_comparisons.png> | Saved 75-rollout comparison plot |
| <http://127.0.0.1:5173/evidence/training_clusters.png> | Saved training K-Means in PCA coordinates |
| <http://127.0.0.1:5173/evidence/training_pca_variance.png> | Saved training PCA explained variance |

For ordinary two-process development use the [README commands](../README.md), not
the combined preview. If npm is missing on PATH in this existing workspace,
substitute `node work/tools/npm/package/bin/npm-cli.js --prefix client ...`.
The ignored workspace tool is not part of a fresh clone.

### Required artifacts and explicit fallback

Trained models/experiment artifacts are Git-ignored. A fresh clone can run fixed/
rule-only simulation but needs a trusted matching bundle for predictions and saved
evidence. See [DEPLOYMENT_NOTES.md](DEPLOYMENT_NOTES.md) for the exact file layout.
The local saved bundle is ready; no model training or final-test scoring was run
for this handoff. Missing models/metrics produce explicit unavailable responses.

The verifier flag `--allow-rule-fallback` applies to its private service instance;
it does **not** pre-check the browser's permission box. Tick that box explicitly
before the scheduled ML run. Invalid/negative estimates must not be described as
working ML inference. Without valid estimates or opt-in, an ML operation returns 503.

## Actual replay evidence

Scenario **medium**, seed **57**, replicate **0**, duration **600 s**, compared
ticks **1–60** after each reset. Fixed and ML runs both received **48 arrivals**.
Their full exogenous trace SHA-256 is:

```text
24c100cbe90914d228fa52b6a4900e7596b70d0027dee2e7b3488f922b28762f
```

Both controller runs recorded **zero invariant violations**. The ML run's effective
policy was ML-assisted for **41 ticks**, queue-only for **19 ticks**. These are
observed fallback counts, not fabricated ML success. Two independent receipt files
were byte-identical (SHA-256 below); receipt equality does not imply the two policies
have identical queues/departures, only that repeating the whole experiment agrees.

```text
d97fb550210dde99a9df778c1f40ada7e5c461243763642c5b31632edbe3d175
```

Receipts: `artifacts/handoff/replay-a/receipt.json` and
`artifacts/handoff/replay-b/receipt.json`. Sixty ticks validate deterministic replay
and invariants; the short sequence is not a statistical performance benchmark.
No new held-out evaluation was performed; frozen test receipt/data/models are retained.

## Final acceptance commands and outcomes

Commands below actually ran in the existing environment. No dependencies were
installed. Python imports and `pip check` passed. The exact local npm fallback was
used for client commands. Outputs are retained under ignored `work/handoff/`.

```powershell
New-Item -ItemType Directory -Path work/tmp,work/handoff -Force | Out-Null
$env:TEMP=(Resolve-Path work/tmp).Path
$env:TMP=$env:TEMP
.\ml-service\.venv\Scripts\python.exe -m pytest -q --basetemp=work/tmp/handoff-final
node work/tools/npm/package/bin/npm-cli.js --prefix client test
node work/tools/npm/package/bin/npm-cli.js --prefix client run build
.\ml-service\.venv\Scripts\python.exe ml-service/smoke_imports.py
.\ml-service\.venv\Scripts\python.exe -m pip check
.\ml-service\.venv\Scripts\python.exe tests/check_api_runtime.py
.\ml-service\.venv\Scripts\python.exe tests/check_simulation_runtime.py
.\ml-service\.venv\Scripts\python.exe tests/check_walkthrough_runtime.py
.\ml-service\.venv\Scripts\python.exe simulation/walkthrough.py --verify --allow-rule-fallback --output artifacts/handoff/replay-a
.\ml-service\.venv\Scripts\python.exe simulation/walkthrough.py --verify --allow-rule-fallback --output artifacts/handoff/replay-b
.\ml-service\.venv\Scripts\python.exe simulation/benchmark.py --output-dir artifacts/handoff/benchmark --findings work/handoff/benchmark.md
.\ml-service\.venv\Scripts\python.exe -m simulation.sumo_adapter --status
git diff --check
```

Output directories named above now exist; choose new ones to repeat the verifier
or offline benchmark. Git diff checking is read-only. None of these commands pushes.

| Check | Result | Actual evidence |
| --- | --- | --- |
| Full Python suite | PASS | **657 passed, 1 skipped in 40.58 s**; only skip is missing sumo/netconvert |
| Client tests | PASS | **4 files, 42 tests**, 7.26 s |
| Client build | PASS | **669 modules**, built in 4.71 s |
| Imports / package consistency | PASS | Python 3.12.14, expected FastAPI/numpy/pandas/sklearn/joblib/plotting/test imports; no broken requirements |
| Real inference/health HTTP | PASS | 14 cases across saved/missing-model modes; 200/422/503 behavior; owned servers stopped |
| Real simulation HTTP | PASS | 48 cases, deterministic step batching, state/benchmark guards, explicit fallback; owned servers stopped |
| Combined preview HTTP | PASS | Eight GET routes/assets plus paired reset/60-tick requests; all expected statuses and 48-arrival equality; server/thread stopped and port closed |
| Paired replay repeatability | PASS | Same trace and per-tick arrival vectors across policies; independent full receipts byte-identical; zero violations |
| Fresh offline benchmark | PASS | **75 rollouts**, **0 constraint violations**, **30 adverse mean-wait pairs**, 116 hashed artifacts |
| Whitespace / protected inputs | PASS | Diff check clean; raw data, splits and frozen assessment protected by hash checks |
| Real browser screenshots/E2E | BLOCKED / UNVERIFIED | In-app browser creation/navigation timed out on local preview; checklist supplied; no fake images |
| Optional SUMO runtime | SKIPPED | Enabled false; sumo/netconvert unavailable; feature-gate tests pass |

One initial new test exposed a JSON round-trip difference (Python tuples versus
persisted lists in the receipt). The verifier now returns the same normalized JSON
types it writes, and the full suite then passed. No controller/training logic was
changed to force a favorable result. Separate-process loopback requests timed out
in this environment; the same-process real HTTP check passed. This does not establish
browser reachability. Temporary preview/test servers were stopped.

## Evidence to present honestly

- Classification: saved validation chose KNN by macro-F1 **0.537601**; saved final
  macro-F1 **0.503522**, accuracy **0.684229**, MEDIUM recall **0.055363**. SVC's
  higher validation accuracy was not the selection objective. No test retuning.
- Regression: saved final MAE **5.973365 s**, RMSE **8.190121 s**, **441** negative
  outputs retained/flagged. High synthetic R2 is not real-world validity.
- Clustering/PCA: train-only, arbitrary IDs; first-two explained-variance fraction
  **0.563375**. No cluster-based signal control. IQR/z-score SKIPPED_UNVERIFIED.
- Offline controller benchmark: five scenarios, five seeds each, 180 s warm-up +
  600 s measurement. Medium mean wait fixed **21.549 s**, rule-only **35.038 s**,
  ML-assisted **33.213 s**. Thirty of 50 adaptive pairs are adverse. Waits are
  right-censored and five runs/scenario is small; no universal improvement claim.
- Default virtual safety: 15–60 s green, 3 s yellow, 1 s all-red, <=5 s extensions,
  75 s maximum axis red. Parallel pedestrians/no turns/no late WALK are assumptions.
  Bounded red does not bound every vehicle's wait under overload. The offline
  training generator uses different randomized greens and 2 s all-red.

## Screenshots and missing approvals

Use [SCREENSHOT_CHECKLIST.md](SCREENSHOT_CHECKLIST.md) for actual local-browser
captures. Every screenshot item remains unchecked. Saved PNG analysis figures are
genuine but are not UI screenshots. Do not change security settings or authorize a
browser/login merely to obtain images without the user's involvement.

| Item | Status / next requirement |
| --- | --- |
| Local code, tests, preview and commit | Authorized; Git user identity is configured. No identity was fabricated and no assistant/co-author attribution is added. |
| GitHub push | **Not authorized for this handoff. Do not push.** A new explicit user instruction is required before uploading commits. |
| Official syllabus verification | User must supply official title/version/source/sections before any topic becomes VERIFIED. No complete coverage claim. |
| Browser visual sign-off | Local user browser must reach the app; capture and review the checklist. No verified browser rehearsal exists. |
| SUMO runtime | Optional missing executables. No install attempted; privileged install, login or interactive authorization would require asking first. Does not block main demo. |
| Hosting/multi-user use | Not implemented or approved here; no public deployment, authentication or isolated persistent sessions supplied. |

Git review/receipt commands:

```powershell
git status --short
git diff --check
git diff --cached --stat
git log -1 --format=fuller
```

Reviewed safe project changes are eligible for the requested local commit using the
existing configured identity. The actual commit SHA/outcome is recorded in the final
handoff receipt after commit, rather than inventing a self-referential SHA here.
No push, remote login, artifact upload or assistant contributor entry is performed.

## Next steps, in order

1. On the presenting machine, restore the trusted ignored model bundle if absent,
   build, run the local preview, check readiness and rehearse the 180-second schedule.
2. Capture/review real screenshots and sign off desktop/mobile controls and errors;
   preserve SIMULATED DATA, provenance, fallback and attribution labels.
3. Obtain the official syllabus and update verification evidence; keep every topic
   UNVERIFIED meanwhile. Do not add methods simply to claim coverage.
4. If further modeling is authorized, address minority recall, negative regression
   and controller adverse cases using development data/grouped folds. Do not reuse
   the consumed final test for tuning or another final claim.
5. Review the local commit. Push only after a new explicit user instruction. Real
   private GPS, hardware signals, paid traffic APIs, RL and deep learning remain
   outside the permitted scope.

Further reading: [README](../README.md), [20 viva Q&As](VIVA_NOTES.md),
[syllabus evidence map](SYLLABUS_COVERAGE_REPORT.md),
[final QA](FINAL_QA_REPORT.md), [final-test audit](FINAL_TEST_AUDIT.md),
[virtual controllers](VIRTUAL_CONTROLLERS.md), [optional SUMO](SUMO_SETUP.md).
