# Real screenshot checklist — capture pending

Date: 2026-11-03. **No verified dashboard screenshots were captured.** Browser
automation was present, but creating the local-preview tab timed out and a recovered
tab's navigation to 127.0.0.1:5173 returned ERR_CONNECTION_TIMED_OUT. The local
preview itself passed same-process HTTP checks. Cross-process loopback requests
also timed out in this execution environment. No security settings, browser
authorization or firewall configuration were changed to work around the blocker.

The files in `docs/figures/` are actual saved analysis plots, not screenshots.
Do not rename a plot or error page as a successful UI screenshot.

Run the [three-minute preflight](DEMO_SCRIPT.md) on the user's local browser. Capture
the **actual application viewport**, record backend tick/scenario/controller and
capture date in a small receipt, then inspect each image for readability. Leave
each box unchecked until the real image has been reviewed.

| Done | Suggested filename | Required visible evidence |
| --- | --- | --- |
| [ ] | 01-fixed-time.png | SIMULATED DATA, medium, fixed-time, received tick near 20, map/schematic, four approach lamps/countdowns, visible OSM attribution if tiles enabled |
| [ ] | 02-reset-identical-arrivals.png | Actual API reset response or verifier receipt with matching scenario, seed 57, replicate 0, duration 600 and both trace hashes; do not imply the UI displays the hash |
| [ ] | 03-ml-adaptive.png | ML-assisted request, explicit fallback permission, received tick matching fixed where feasible, requested/effective controller and real prediction/fallback state |
| [ ] | 04-comparison.png | Actual saved benchmark chart opened in browser, labeled offline synthetic benchmark; caption notes adverse cases and right-censoring |
| [ ] | 05-classification-metrics.png | Cached test macro-F1/MEDIUM recall and separate validation comparison, model version, no live-accuracy claim |
| [ ] | 06-clustering-pca.png | Actual saved training cluster/PCA plots in browser; caption states train-only, arbitrary cluster IDs, explained variance and UNVERIFIED syllabus |
| [ ] | 07-mobile.png | Real narrow viewport with reachable scenario/run/reset controls, no overlapping cards, readable labels and attribution |
| [ ] | 08-api-error.png | Actual unavailable/error state if reproducible without altering frozen artifacts; paused client and explicit unavailable message, no fabricated traffic |

Suggested storage: `docs/screenshots/` with an accompanying capture receipt. Do not
commit images of unrelated apps, local credentials or authentication dialogs.
For error testing, use the API test scripts' owned missing-model instance instead
of deleting or changing the trusted model bundle. Do not consume final-test data.

Visual/browser end-to-end acceptance remains **UNVERIFIED** until real controls and
screenshots have been inspected. Automated component/API passes do not replace it.
