# Virtual controller contract

Educational simulation only. These classes cannot operate physical infrastructure;
they have no hardware, network, paid API or signal-actuation adapter. No RL or deep
learning is used. ML and syllabus status remain **PROVISIONAL / UNVERIFIED**.

## Classes and clock

`simulation/controllers.py` exports `FixedTimeController`,
`RuleOnlyAdaptiveController`, `MLAdaptiveController`, `TimingConfig` and `Phase`.
Each controller owns one new virtual run starting at t=0 in `ns_green` with an
initially clear conflict area. Call `step(t, queues, predictions=None)` for every
consecutive integer second, starting at zero. Skipped, duplicate or backward calls
raise before mutation. This is a simulation clock, not a wall-clock scheduler;
there is no restart/resume or physical failover contract.

```python
from simulation.controllers import RuleOnlyAdaptiveController, TimingConfig

controller = RuleOnlyAdaptiveController(TimingConfig())
for second in range(120):
    # Replace with the current synthetic snapshot each second.
    state = controller.step(second, {
        "north": 15, "south": 12, "east": 4, "west": 3,
    })
controller.write_log("artifacts/controller_demo/example.jsonl")
```

Queues must contain exactly the four named approaches and exact integer counts in
[0,10000]. Invalid demand or clock stops that simulation step without changing
state; the caller must correct it and retry that same second. Public configuration,
returned state, action records and accepted prediction evidence are immutable.
Instances must not be recreated partway through a run to reset fairness timers.

## Shared safety envelope

| Parameter | Default | Meaning |
|---|---:|---|
| min_green | 15s | Minimum vehicle green |
| max_green | 60s | Hard green limit |
| yellow | 3s | Mandatory vehicle clearance; no new departures |
| all_red | 1s | Mandatory clearance with all vehicle movements red |
| fixed_green | 30s | Both axes' fixed baseline duration |
| max_red_wait | 75s | Maximum continuous absence of green for either axis |
| extension_step | 5s | Maximum increase of the current green target per decision |
| pedestrian_walk | 7s | Entry window at the beginning of each green |
| pedestrian_clearance | 8s | Protected clearance after WALK entry closes |
| prediction_max_age | 10s | Accepted age of an optional forecast |
| queue_hysteresis | 1 | Required active-minus-opposing pressure advantage |
| ml_weight | 3 | Bounded supplemental forecast weight |

Timings are illustrative configurable values, **not real-road safety recommendations**.
All durations are exact positive integers, with bounded finite numeric settings.
Let `C=yellow+all_red` and `F=max(min_green, pedestrian_walk+pedestrian_clearance)`.
Configuration requires `F <= fixed_green <= max_green`,
`F+2*C <= max_red_wait`, and `fixed_green+2*C <= max_red_wait`.
Infeasible combinations are rejected, including a pedestrian window longer than
the permitted green. Use a shorter fixed_green explicitly if configuring a tighter
fairness deadline. Zero-length clearances and nonfinite/bool timing inputs are rejected.

Every transition follows this exact cycle:

```text
ns_green -> ns_yellow -> all_red_to_ew -> ew_green
         -> ew_yellow -> all_red_to_ns -> ns_green
```

North/south through movements share green; east/west through movements share green.
There are no turns or overlapping incompatible greens. Green movement sets are
derived from the enum phase, never supplied by an ML prediction. Yellow and all-red
durations are fixed for each phase, even if inputs change during clearance.

Precedence: complete any current vehicle clearance; protect the green/pedestrian
minimum; meet the opposing red deadline; enforce max_green; then consider fixed
expiry or bounded pressure-based extensions. Configuration feasibility ensures the
minimum and fairness deadline cannot conflict. Extensions reserve the entire outgoing
clearance before the opposing deadline and never exceed max_green or extension_step.

### Meaning and limits of fairness

An axis's red clock starts when its green ends, **including yellow and all-red**,
and resets only when that axis becomes green again. At each green decision, switching
begins no later than `opposing_red_age + C == max_red_wait`. The alternating policy
services both axes even with zero reported opposing queues. After an opposing green
starts, the other axis has already spent C seconds without green; feasibility
`F+2*C <= max_red_wait` leaves enough time for its protected minimum and return
clearance. Thus repeated red intervals are bounded even under extreme asymmetric
demand, adversarial forecasts and unoccupied approaches.

This is a bound on **service opportunities**, not every vehicle's time in queue.
Oversaturation, incidents and FIFO backlogs can cause individual delays longer than
max_red_wait. The demo reports queue delay separately; it does not equate the two.

### Pedestrian assumptions

Only parallel protected crossings are modeled: during ns_green, pedestrians travel
parallel to north/south traffic across the east/west road, and vice versa. Turning
vehicles and right-on-red are forbidden. WALK is open for pedestrian_walk seconds,
then entry closes and pedestrian_clearance must finish while the parallel vehicle
green remains active. Yellow cannot begin until that whole window completes.
All crossings show DONT_WALK during vehicle clearance. Late pedestrian entry is
excluded; later arrivals wait for the next WALK on their axis. Each axis receives
WALK once per cycle, with cycle length at most `2*max_green+2*C` (128s by default).
No pedestrian occupancy sensors, request prioritization, accessible timing design,
turning conflict model or real crossing-distance/walking-speed calibration is claimed.

## Policy and ML input contract

FixedTimeController ignores queues and forecasts for timing after validating demand.
RuleOnlyAdaptiveController uses the sum of current queues on each axis. At its green
target, it extends only if active pressure exceeds opposing pressure plus hysteresis;
otherwise it begins yellow. It starts each green at F and extends incrementally.

MLAdaptiveController uses those same queues and adds, per axis:

```text
ml_weight * mean(class_severity + min(future_wait_seconds,120)/120)
class_severity: LOW=0, MEDIUM=1, HIGH=2
```

The extra pressure is bounded by `3*ml_weight` (9 by default). Both class and predicted
future waiting time influence this transparent rule; neither can override a safety
constraint. At ml_weight=0 it reproduces the queue-only controller exactly.

Supply all four current-approach estimates together, for example:

```python
prediction = {
    "congestion_level": "HIGH",
    "future_wait_seconds": 35.0,
    "generated_at_seconds": 10,
    "prediction_horizon_seconds": 60,
    "model_version": "<version of the frozen inference bundle>",
}
predictions = {name: dict(prediction) for name in ("north", "south", "east", "west")}
# controller.step(10, queues, predictions) after processing seconds 0 through 9.
```

No additional or missing prediction fields are accepted. All estimates must have
the same nonempty model version, uppercase class, exact +60s horizon, a generated
timestamp no later than now and age <= prediction_max_age. Waiting estimates must
be finite numbers in [0,3600]; negative polynomial outputs are rejected, not clipped.
Invalid, stale, missing, mixed-version or malformed estimates trigger **atomic
queue-only fallback for all four approaches**, with the reason logged. They never
create fabricated forecasts. A version label is provenance supplied by the caller;
the controller does not authenticate an arbitrary caller's model. The demo uses the
existing hash-checked frozen local model loader. With cached estimates the forecast
is still for +60s from its generation timestamp, not a newly shifted horizon.

Every accepted second produces an action (INITIALIZE/HOLD/EXTEND/TRANSITION) with its
reason, before/after phase, elapsed/target timing, all queue counts, pressures, red
ages, pedestrian state, model status/version and exact validated forecast evidence.
Fallback records omit invalid numeric evidence so JSON logs never contain NaN/Inf.
`write_log(path)` exports deterministic JSONL; logging has no external side effects.

## Paired demonstration and isolation

```powershell
.\ml-service\.venv\Scripts\python.exe -m pytest tests/test_controllers.py tests/test_controller_comparison.py -q
.\ml-service\.venv\Scripts\python.exe simulation/compare_controllers.py
```

The demo saves comparison.csv, summary.json and 15 per-run JSONL logs under ignored
`artifacts/controller_demo/`. Five new 600-second scenarios share exactly the same
seed-57 arrivals and noise across the three policies. These are separate FIFO
point queues with Poisson arrivals, 0.65 veh/s discharge, 2s startup loss and a
temporary 20% north capacity during the incident. All vehicles start at the queue;
there is no approach travel, spillback or geographic GPS. Samples are synthetic
near-zero stopped speeds. This simplified rollout differs from the training generator.

Every 10s the ML demo builds validated current-only TrafficObservation records
before the controller's current decision, calls the saved pipelines in exact feature
order, and stamps their outputs. It records model unavailability and falls back;
it never retrains, creates future ground-truth labels, or opens offline split/test
observations. The controller cannot tune from held-out metrics. This is an inference
demonstration with distribution shift, not a new test-set accuracy assessment.

Throughput counts departed vehicles; mean queue is the time-average total queue.
Completed-vehicle mean wait excludes vehicles remaining at the horizon and is biased
by censoring. Restricted mean wait is total queued vehicle-seconds divided by all
arrivals, including waiting accumulated by unfinished vehicles up to the horizon.
It is not their eventual completed delay. An independent trace audit checks phases,
green/clearance durations, conflicts, pedestrian compatibility, maximum red and inventory.

See CONTROLLER_TEST_REPORT.md for executed checks and honest results. Existing
generate_data.py, its original 3s yellow/2s all-red baseline, raw data, frozen model
artifacts and final-test ledger are unchanged. These standalone modules are not
connected to frontend controls or a signal-command API. `/health` still describes
the API's lack of a running controller, not the availability of these Python classes.
