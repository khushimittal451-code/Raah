# Raah

Raah is a planned educational simulation that estimates traffic congestion from **synthetic GPS-like aggregate speed, vehicle counts, and queue lengths**, compares permitted semester ML models, and adjusts **VIRTUAL signals** using a constrained rule-based controller.

## Status

Documentation and local setup only. No data generator, models, simulator, application, or automated test suite is implemented yet. The official syllabus is pending; all proposed topics are **UNVERIFIED**, and complete coverage is not claimed. See [the checklist](docs/SYLLABUS_CHECKLIST.md) and [implementation guidance](AGENTS.md).

## Boundaries

- Synthetic data only: no real private GPS, paid traffic APIs, or physical traffic signal control.
- No reinforcement learning or deep learning.
- Seed **57**, group-separated train/validation/test splits, and training-only preprocessing.
- Transparent model metrics and reproducible experiments; virtual control must enforce safe phase transitions and timing constraints.

## Local setup

See [setup status and command history](docs/SETUP_STATUS.md). A local `.venv` exists; npm/npx are workspace-local tools under ignored `work/`. No application dependency manifests exist yet.

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
# Available only after the workspace-local npm setup described in SETUP_STATUS:
.\npm.cmd --version
```

These commands inspect tooling; there is no application run command yet. Generated tools and the venv are not included in Git and require setup in a fresh checkout.

## Planned implementation

1. Confirm the official syllabus and permitted model comparisons.
2. Define synthetic scenarios, aggregate units, congestion targets, and independent split groups.
3. Build reproducible generation, train-only pipelines, baselines, and evaluation.
4. Implement and test the constrained virtual controller against a fixed-time baseline.

## Results

Pending implementation. Report prediction metrics, scenario variation, queue length, throughput, waiting time, and controller constraint violations with limitations once measured.
