"""Small paired virtual demonstration, separate from the frozen training generator.

New seed-57 demand only. Not a traffic calibration or a held-out ML assessment.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import asdict
import csv
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml-service"))
from app.models import ModelBundle, Unavailable  # noqa: E402
from app.schemas import TrafficObservation  # noqa: E402
from simulation.controllers import (  # noqa: E402
    APPROACHES, AXES, NEXT_PHASE, FixedTimeController, MLAdaptiveController,
    Phase, RuleOnlyAdaptiveController, TimingConfig, integer,
)

SCENARIOS = ("low", "medium", "high", "asymmetric_rush_hour", "incident")
CONTROLLERS = (FixedTimeController, RuleOnlyAdaptiveController, MLAdaptiveController)


def demand(index, duration):
    streams = np.random.SeedSequence([57, index]).spawn(2)
    rng, gps = (np.random.default_rng(stream) for stream in streams)
    scenario = SCENARIOS[index]
    base = {"low": .04, "medium": .20, "high": .48,
            "asymmetric_rush_hour": .08, "incident": .24}[scenario]
    rates = np.full((duration, 4), base)
    if scenario == "asymmetric_rush_hour":
        pulse = .48 * np.exp(-.5 * ((np.arange(duration) / duration - .5) / .18) ** 2)
        rates[:, :2] += pulse[:, None]
    arrivals = rng.poisson(rates)
    arrivals[0] = 0
    return arrivals, gps.normal(0, .12, (duration, 4))


def audit(states, config):
    """Independent trace check, including full red intervals at green entry."""
    violations = []
    red_since = {"ns": None, "ew": 0}
    max_red = 0
    for i, state in enumerate(states):
        if state.timestamp_seconds != i:
            violations.append("nonconsecutive_clock")
        if state.vehicle_greens not in ((), AXES["ns"], AXES["ew"]):
            violations.append("conflicting_or_unknown_green")
        expected_greens = AXES["ns"] if state.phase == Phase.NS_GREEN else AXES["ew"] if state.phase == Phase.EW_GREEN else ()
        if state.vehicle_greens != expected_greens:
            violations.append("phase_movement_mismatch")
        ceiling = config.max_green if expected_greens else config.yellow if state.phase in (Phase.NS_YELLOW, Phase.EW_YELLOW) else config.all_red
        if not 0 <= state.seconds_in_phase < ceiling:
            violations.append("phase_overrun")
        for axis in AXES:
            active = state.vehicle_greens == AXES[axis]
            if not active and red_since[axis] is None:
                red_since[axis] = i
            elif active and red_since[axis] is not None:
                interval = i - red_since[axis]
                max_red = max(max_red, interval)
                if interval > config.max_red_wait:
                    violations.append("maximum_red_wait")
                red_since[axis] = None
            if red_since[axis] is not None:
                max_red = max(max_red, i - red_since[axis])
                if i - red_since[axis] > config.max_red_wait:
                    violations.append("maximum_red_wait")
        if state.pedestrian_state != "dont_walk" and (
                not state.vehicle_greens or state.vehicle_greens != AXES[state.pedestrian_axis]):
            violations.append("pedestrian_conflict")
        if i and state.phase != states[i - 1].phase:
            previous = states[i - 1]
            if state.phase != NEXT_PHASE[previous.phase]:
                violations.append("illegal_phase_transition")
            duration = previous.seconds_in_phase + 1
            if previous.phase in (Phase.NS_GREEN, Phase.EW_GREEN):
                if not config.green_floor <= duration <= config.max_green:
                    violations.append("green_duration")
            elif previous.phase in (Phase.NS_YELLOW, Phase.EW_YELLOW):
                if duration != config.yellow:
                    violations.append("yellow_duration")
            elif duration != config.all_red:
                violations.append("all_red_duration")
    return violations, max_red


def forecast(bundle, queues, second, previous, incoming, outgoing, noise):
    observations = []
    phase = previous.phase.value if previous else "ns_green"
    elapsed = previous.seconds_in_phase + 1 if previous else 0
    for i, approach in enumerate(APPROACHES):
        count = len(queues[i])
        wait = sum(second - arrival for arrival in queues[i]) / count if count else 0.
        observations.append(TrafficObservation(
            run_id="controller-demo-57", timestamp_seconds=second, intersection_id="virtual-junction",
            approach_id=approach, mean_speed_kmh=float(np.clip(.2 + noise[i], 0, .9)) if count else None,
            free_flow_speed_kmh=60., vehicle_count=count, queue_length_vehicles=count,
            mean_wait_seconds=wait, incoming_vehicles=int(incoming[i]), outgoing_vehicles=int(outgoing[i]),
            current_phase=phase, seconds_in_phase=float(elapsed), time_of_day=second / 3600,
            gps_sample_count=min(count, 20)))
    levels = bundle.predict("classification", observations)
    waits = bundle.predict("regression", observations)
    return {a: dict(congestion_level=levels[i], future_wait_seconds=waits[i],
                    generated_at_seconds=second, prediction_horizon_seconds=60, model_version=bundle.version)
            for i, a in enumerate(APPROACHES)}


def rollout(controller, arrivals, noise, scenario, bundle=None):
    """Identical arrivals per policy; FIFO point queues with 0.65 veh/s discharge."""
    duration = len(arrivals)
    queues = [deque() for _ in APPROACHES]
    credits = [0.] * 4
    incoming, outgoing = np.zeros(4, dtype=int), np.zeros(4, dtype=int)
    departed_waits, states = [], []
    previous, predictions = None, None
    total_queue, maximum_queue, failures = 0, 0, []
    for second in range(duration):
        for i in range(4):
            queues[i].extend([second] * int(arrivals[second, i]))
        incoming += arrivals[second]
        if isinstance(controller, MLAdaptiveController) and second % 10 == 0 and bundle is not None:
            try:
                predictions = forecast(bundle, queues, second, previous, incoming, outgoing, noise[second])
            except (Unavailable, ValueError) as exc:
                predictions = None
                failures.append({"second": second, "reason": str(exc)})
        if second % 10 == 0:
            incoming[:], outgoing[:] = 0, 0
        state = controller.step(second, {a: len(queues[i]) for i, a in enumerate(APPROACHES)}, predictions)
        states.append(state)
        for i, approach in enumerate(APPROACHES):
            if approach in state.vehicle_greens and state.seconds_in_phase >= 2:
                factor = .20 if scenario == "incident" and i == 0 and .35 * duration <= second < .70 * duration else 1.
                credits[i] += .65 * factor
                while credits[i] >= 1 and queues[i]:
                    departed_waits.append(second - queues[i].popleft())
                    outgoing[i] += 1
                    credits[i] -= 1
                if not queues[i]:
                    credits[i] = 0.
            else:
                credits[i] = 0.
        count = sum(map(len, queues))
        total_queue += count
        maximum_queue = max(maximum_queue, count)
        previous = state
    violations, max_red = audit(states, controller.config)
    arrivals_total = int(arrivals.sum())
    ending = sum(map(len, queues))
    if len(departed_waits) + ending != arrivals_total:
        violations.append("inventory_conservation")
    row = dict(seed=57, scenario=scenario, controller=type(controller).__name__, duration_seconds=duration,
        arrivals=arrivals_total, throughput_vehicles=len(departed_waits), ending_queue_vehicles=ending,
        mean_queue_vehicles=total_queue / duration, maximum_queue_vehicles=maximum_queue,
        completed_vehicle_mean_wait_seconds=float(np.mean(departed_waits)) if departed_waits else None,
        restricted_mean_wait_seconds=total_queue / arrivals_total if arrivals_total else None,
        maximum_red_seconds=max_red, constraint_violations=len(violations),
        ml_fallback_steps=sum(a.prediction_status.startswith("fallback_queue_only") for a in controller.action_log),
        prediction_call_failures=len(failures))
    if violations:
        raise AssertionError(violations)
    return row, failures


def run(output=ROOT / "artifacts/controller_demo", duration=600, model_dir=ROOT / "artifacts/final"):
    integer(duration, "duration", 120, 3000)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    bundle = ModelBundle(model_dir)
    bundle.load()
    rows, errors = [], {}
    for index, scenario in enumerate(SCENARIOS):
        arrivals, noise = demand(index, duration)
        for kind in CONTROLLERS:
            controller = kind()
            row, failures = rollout(controller, arrivals, noise, scenario, bundle)
            controller.write_log(output / f"{scenario}_{kind.__name__}.jsonl")
            rows.append(row)
            errors[f"{scenario}/{kind.__name__}"] = failures
    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {"seed": 57, "timings": asdict(TimingConfig()), "model_info": bundle.describe(),
        "data_source": "new paired synthetic FIFO point queues; not held-out data",
        "pedestrian_assumption": "parallel protected crossing, no turns, no late WALK entry",
        "prediction_call_errors": errors, "comparison": rows,
        "limitations": "not calibrated; distribution shift from training generator; no benefit guarantee; "
            "fairness bounds red time, not individual delay; polynomial negative estimates use queue-only fallback"}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, allow_nan=False))
    print("Output:", output.resolve())
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/controller_demo")
    parser.add_argument("--duration-seconds", type=int, default=600)
    args = parser.parse_args()
    run(args.output_dir, args.duration_seconds)
