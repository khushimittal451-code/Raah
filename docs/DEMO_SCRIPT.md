# Repeatable three-minute Raah demo

Date: 2026-11-03 (Asia/Calcutta). This is a **180-second presenter schedule** with
preflight outside the clock. Backend replay and acceptance are verified; browser
rehearsal/timing remains unverified because browser automation could not reach the
local preview. Every traffic value is backend-generated synthetic state. No fake
screenshots, live GPS or physical signals. Syllabus: **UNVERIFIED**.

## Preflight — before starting the stopwatch

1. Build the existing client, then start the one-process preview from the root:

   ```powershell
   npm --prefix client run build
   .\ml-service\.venv\Scripts\python.exe simulation/walkthrough.py --serve --port 5173
   ```

   Open <http://127.0.0.1:5173>. This serves the compiled client, `/api` and saved
   `/evidence` figures on loopback. It needs the trusted model bundle described in
   [deployment notes](DEPLOYMENT_NOTES.md); no hosted deployment is performed.
   Stop it with Ctrl+C. Keep other demo tabs closed: state is single-user/shared.
2. Pre-open three saved-evidence tabs so loading is outside the three minutes:
   [benchmark comparison](http://127.0.0.1:5173/evidence/benchmark_comparisons.png),
   [training clusters](http://127.0.0.1:5173/evidence/training_clusters.png),
   [training PCA variance](http://127.0.0.1:5173/evidence/training_pca_variance.png).
   These are genuine saved plots, **not live clustering or UI screenshots**.
3. Verify the repeatable pair in a private service instance, without disturbing
   the running UI. Use a fresh output directory each time:

   ```powershell
   .\ml-service\.venv\Scripts\python.exe simulation/walkthrough.py --verify --allow-rule-fallback --output artifacts/demo-take-001
   ```

   This compares the exact first 60 ticks after two resets: scenario medium,
   seed 57, replicate 0, duration 600; fixed-time versus ML-assisted. The explicit
   flag permits queue-only fallback. It saves arrival vectors, trace/hash, policy
   counts, final states and invariant results. It never trains or scores heldout data.
4. Check `/api/health`, `/api/model-info` and `/api/model-metrics` separately. A
   healthy process can have missing models. Keep the checklist available if browser
   capture is blocked: [SCREENSHOT_CHECKLIST.md](SCREENSHOT_CHECKLIST.md).

## Stopwatch script — exactly 180 seconds allocated

| Time | Action | Short narration / evidence |
| --- | --- | --- |
| 00:00–00:15 (15 s) | Select **medium**, **fixed time**. Explicitly tick the queue-only fallback permission for the later ML run, then **Reset simulation**. | “Synthetic data, seed 57, virtual signals only. This scenario is deliberately not a universal adaptive-control success case.” |
| 00:15–00:45 (30 s) | **Run** fixed-time; pause at approximately t=20 (allow spare time for polling). Point to map, lamp colors, countdowns and queue/speed charts. | “Congestion overlays and virtual lamps are different. Every tick comes from the API.” If slow, pause at the current tick and use the verified receipt; do not invent an ending state. |
| 00:45–01:00 (15 s) | Select **ml assisted**, leave the scenario/fallback unchanged, **Reset simulation**. | “Reset restarts t=0. Controller choice is excluded from the arrival-seed construction; seed, scenario, replicate and duration match.” Cite the preflight trace receipt, not a guessed frontend value. |
| 01:00–01:30 (30 s) | **Run** ML-assisted and pause at the same tick as fixed if feasible. Show predictions and requested/effective controller. | “ML adds bounded pressure to rules. Invalid estimates use the explicitly permitted queue-only fallback; that is not successful ML inference.” The receipt provides exact equal-tick replay evidence independently of wall-clock polling. |
| 01:30–01:55 (25 s) | Switch to the pre-opened **saved benchmark comparison** chart. | “Five scenarios, five seeds each, 75 rollouts; 180 s warm-up and 600 s measurement. Zero violations, but 30/50 adaptive-vs-fixed pairs have worse mean wait.” For medium: fixed 21.549 s, rule-only 35.038 s, ML-assisted 33.213 s. These are offline benchmark numbers, not this short UI run. |
| 01:55–02:20 (25 s) | Return to the dashboard's **saved model evidence** section; point to validation comparison and final-test cards. | “Validation macro-F1 chose KNN at 0.537601. Saved final macro-F1 is 0.503522 and MEDIUM recall only 0.055363. Reading cached metrics does not evaluate test again.” |
| 02:20–02:45 (25 s) | Show the saved **training clusters** then **PCA variance** tabs. | “K-Means is exploratory, IDs are arbitrary. PCA's first two components explain 0.563375 of training variance. They do not drive signals. IQR/z-score remain SKIPPED_UNVERIFIED.” |
| 02:45–03:00 (15 s) | Close with safety/limitations; leave the demo paused. | “15–60 s green, 3 s yellow, 1 s all-red, 75 s maximum axis red. Parallel pedestrians/no turns/no late WALK are assumptions. Synthetic derived labels, negative regression, censored waits and weak MEDIUM recall limit conclusions. Official syllabus unverified.” |

The table sums to **180 seconds**. It does not claim an automated timed browser
recording was captured. Preflight, startup, artifact restoration and screenshots
are outside that schedule. Do not claim equal observed queue outcomes merely
because arrivals match: controllers intentionally change departures and waits.

## Verified replay for this handoff

The executed 60-tick pair received **48 arrivals in both runs** and **0 controller
violations**. Exogenous trace SHA-256:
`24c100cbe90914d228fa52b6a4900e7596b70d0027dee2e7b3488f922b28762f`.
The ML run used ML pressure for **41 ticks**, queue-only fallback for **19 ticks**.
Both full receipt files were byte-identical across two independent invocations.
This verifies replay/invariants, not statistical controller superiority.

## Failure route

- Missing/unverifiable models or metrics: show the explicit unavailable state and
  the labeled saved README figures; do not fabricate on-screen scores. Without a
  trusted bundle, the complete model-enabled demo is blocked, though fixed/rule-only
  simulation still works.
- Stale/reset-conflict 409 or API error: pause, refresh backend state, then reset
  deliberately. Never blindly repeat a failed/timed-out mutation.
- Tiles unavailable: select **Use offline schematic**; do not download tiles for
  offline caching. Keep SIMULATED DATA and OSM attribution where applicable.
- Comparison button: the live API comparison is optional and outside this fixed
  schedule. It uses two runs/active scenario with shorter defaults; it must not be
  confused with the saved 75-rollout benchmark presented above.
- No browser connectivity: use the checklist, receipt and actual saved figures;
  mark visual acceptance unverified. Never relabel analysis plots as screenshots.

See [HANDOFF.md](HANDOFF.md) for acceptance commands, outcomes, missing approvals,
commit policy and next steps. No physical infrastructure or paid API is permitted.
