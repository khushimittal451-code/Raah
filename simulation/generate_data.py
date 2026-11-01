"""Reproducible synthetic junction rollouts. No live GPS or physical signals.

Run from repository root using ml-service/.venv/Scripts/python.exe simulation/generate_data.py.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml-service"))
from app.schemas import (  # noqa: E402
    LabeledRun, LabeledTrafficRecord, RunProvenance, TrafficObservation,
    PREDICTION_HORIZON_SECONDS, label_observation,
)

VERSION = "point-queue-v1"
APPROACHES = ("north", "south", "east", "west")
SCENARIOS = ("low", "medium", "high", "asymmetric_rush_hour", "incident")
PHASES = ("ns_green", "ns_yellow", "all_red_to_ew", "ew_green", "ew_yellow", "all_red_to_ns")


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    run_seed: int
    scenario_type: str
    free_flow_speeds: tuple[float, ...]
    approach_lengths_m: tuple[float, ...]
    base_arrival_rates: tuple[float, ...]
    saturation_rates: tuple[float, ...]
    gps_coverage: float
    ns_green_seconds: int
    ew_green_seconds: int
    dominant_index: int
    incident_index: int
    duration_seconds: int = 1200
    yellow_seconds: int = 3
    all_red_seconds: int = 2
    startup_lost_seconds: int = 2
    incident_capacity_factor: float = 0.12

    def __post_init__(self):
        if self.scenario_type not in SCENARIOS:
            raise ValueError("unknown scenario")
        if type(self.duration_seconds) is not int or not 120 <= self.duration_seconds <= 3000 or self.duration_seconds % 10:
            raise ValueError("duration must be an integer 10-second multiple in [120,3000]")
        if any(type(v) is not int or not 20 <= v <= 45 for v in (self.ns_green_seconds, self.ew_green_seconds)):
            raise ValueError("virtual green duration must be an integer in [20,45]")
        if any(type(value) is not int for value in (self.yellow_seconds, self.all_red_seconds, self.startup_lost_seconds)):
            raise ValueError("clearance and startup durations must be exact integers")
        if self.yellow_seconds != 3 or self.all_red_seconds != 2 or self.startup_lost_seconds != 2:
            raise ValueError("this baseline requires 3s yellow, 2s all-red and 2s startup")
        for values, lower, upper in (
            (self.free_flow_speeds, 20, 80), (self.approach_lengths_m, 50, 500),
            (self.base_arrival_rates, 0.001, 0.8), (self.saturation_rates, 0.4, 0.9),
        ):
            if len(values) != 4 or any(not math.isfinite(v) or not lower <= v <= upper for v in values):
                raise ValueError("invalid per-approach configuration")
        if not 0 < self.gps_coverage <= 1 or not 0 < self.incident_capacity_factor <= 1:
            raise ValueError("coverage and capacity factor must lie in (0,1]")
        if self.dominant_index not in range(4) or self.incident_index not in range(4):
            raise ValueError("invalid approach index")

    @property
    def phase_durations(self):
        return (self.ns_green_seconds, self.yellow_seconds, self.all_red_seconds,
                self.ew_green_seconds, self.yellow_seconds, self.all_red_seconds)


@dataclass
class RunResult:
    config: RunConfig
    observations: list[TrafficObservation]
    records: list[LabeledTrafficRecord]
    phase_events: list[dict]
    step_audit: list[dict]


def make_run_config(index: int, duration_seconds: int = 1200) -> RunConfig:
    if type(index) is not int or index < 0:
        raise ValueError("run index must be a nonnegative integer")
    run_seed = int(np.random.SeedSequence([57, index]).generate_state(1, dtype=np.uint64)[0])
    config_stream = np.random.SeedSequence(run_seed).spawn(3)[0]
    rng = np.random.default_rng(config_stream)
    scenario = SCENARIOS[index % len(SCENARIOS)]
    base = {"low": 0.035, "medium": 0.17, "high": 0.43,
            "asymmetric_rush_hour": 0.075, "incident": 0.20}[scenario]
    return RunConfig(
        run_id=f"run-57-{index + 1:04d}", run_seed=run_seed, scenario_type=scenario,
        free_flow_speeds=tuple(round(float(v), 3) for v in rng.uniform(40, 65, 4)),
        approach_lengths_m=tuple(round(float(v), 1) for v in rng.uniform(150, 280, 4)),
        base_arrival_rates=tuple(round(float(v), 6) for v in base * rng.uniform(0.85, 1.15, 4)),
        saturation_rates=tuple(round(float(v), 6) for v in rng.uniform(0.55, 0.75, 4)),
        gps_coverage=round(float(rng.uniform(0.35, 0.85)), 6),
        ns_green_seconds=int(rng.integers(25, 41)), ew_green_seconds=int(rng.integers(25, 41)),
        dominant_index=int(rng.integers(0, 4)), incident_index=int(rng.integers(0, 4)),
        duration_seconds=duration_seconds,
    )


def phase_at(config: RunConfig, second: int):
    if type(second) is not int or second < 0:
        raise ValueError("phase time must be a nonnegative integer")
    cycle = sum(config.phase_durations)
    cycle_start = (second // cycle) * cycle
    offset = second % cycle
    start = 0
    for name, duration in zip(PHASES, config.phase_durations):
        if offset < start + duration:
            return name, offset - start
        start += duration
    raise AssertionError("unreachable phase")


def incident_active(config: RunConfig, second: int):
    return config.scenario_type == "incident" and 0.35 * config.duration_seconds <= second < 0.70 * config.duration_seconds


def demand_rate(config: RunConfig, approach_index: int, second: int):
    # A compressed rush-hour-like profile, not a claim about actual midnight traffic.
    fraction = min(second / config.duration_seconds, 1.0)
    rate = config.base_arrival_rates[approach_index] * (0.9 + 0.2 * math.sin(math.pi * fraction) ** 2)
    if config.scenario_type == "asymmetric_rush_hour":
        pulse = math.exp(-0.5 * ((fraction - 0.5) / 0.18) ** 2)
        opposite = config.dominant_index ^ 1
        if approach_index == config.dominant_index:
            rate += 0.43 * pulse
        elif approach_index == opposite:
            rate += 0.30 * pulse
    if incident_active(config, second) and approach_index == config.incident_index:
        rate *= 1.3
    return rate


def can_depart(phase: str, approach_index: int):
    return (phase == "ns_green" and approach_index < 2) or (phase == "ew_green" and approach_index >= 2)


def simulate_run(config: RunConfig) -> RunResult:
    streams = np.random.SeedSequence(config.run_seed).spawn(3)
    traffic_rng, gps_rng = (np.random.default_rng(stream) for stream in streams[1:])
    # Each tuple is (earliest stop-line arrival second, moving speed). Internal only;
    # no per-person identifiers, real coordinates or raw GPS records are generated.
    vehicles = [deque() for _ in APPROACHES]
    credit = [0.0] * 4
    incoming, outgoing = [0] * 4, [0] * 4
    observations, events, audit = [], [], []
    end = config.duration_seconds + PREDICTION_HORIZON_SECONDS
    previous_phase = None
    for second in range(end + 1):
        phase, elapsed = phase_at(config, second)
        if phase != previous_phase:
            events.append(dict(run_id=config.run_id, timestamp_seconds=second,
                               current_phase=phase, planned_duration_seconds=config.phase_durations[PHASES.index(phase)]))
            previous_phase = phase
        step_arrivals, step_departures = [], []
        for index in range(4):
            arrivals = int(traffic_rng.poisson(demand_rate(config, index, second))) if second else 0
            for _ in range(arrivals):
                factor = 1.8 if incident_active(config, second) and index == config.incident_index else 1.0
                travel = max(3, int(math.ceil(config.approach_lengths_m[index] / (config.free_flow_speeds[index] / 3.6)
                                              * float(traffic_rng.uniform(0.9, 1.1)) * factor)))
                ready = second + travel
                if vehicles[index]:
                    ready = max(ready, vehicles[index][-1][0])  # FIFO, no overtaking.
                speed = config.approach_lengths_m[index] / (ready - second) * 3.6
                vehicles[index].append((ready, speed))
            incoming[index] += arrivals
            departed = 0
            if can_depart(phase, index) and elapsed >= config.startup_lost_seconds:
                factor = config.incident_capacity_factor if incident_active(config, second) and index == config.incident_index else 1.0
                # Keep fractional service credit; clipping at one would erase the
                # remainder and incorrectly quantize every 0.55-0.75 rate to 0.5.
                credit[index] += config.saturation_rates[index] * factor
                if vehicles[index] and vehicles[index][0][0] <= second and credit[index] >= 1.0:
                    vehicles[index].popleft()
                    departed = 1
                    credit[index] -= 1.0
                elif not vehicles[index] or vehicles[index][0][0] > second:
                    credit[index] = 0.0
            else:
                credit[index] = 0.0
            outgoing[index] += departed
            step_arrivals.append(arrivals)
            step_departures.append(departed)
        audit.append(dict(timestamp_seconds=second, current_phase=phase,
                          seconds_in_phase=elapsed, arrivals=tuple(step_arrivals), departures=tuple(step_departures)))
        if second % 10:
            continue
        for index, approach in enumerate(APPROACHES):
            stopped = [second - ready - 5 for ready, _ in vehicles[index] if second - ready >= 5]
            sample_speeds = []
            for ready, moving_speed in vehicles[index]:
                if float(gps_rng.random()) <= config.gps_coverage:
                    # Stopped samples stay below the queue-definition speed threshold.
                    speed = float(np.clip(gps_rng.normal(0.1, 0.15), 0, 0.9)) if ready <= second else float(
                        np.clip(gps_rng.normal(moving_speed, config.free_flow_speeds[index] * 0.06), 1.0, 160))
                    sample_speeds.append(speed)
            observations.append(TrafficObservation(
                run_id=config.run_id, timestamp_seconds=second, intersection_id="junction-1", approach_id=approach,
                mean_speed_kmh=round(float(np.mean(sample_speeds)), 3) if sample_speeds else None,
                free_flow_speed_kmh=config.free_flow_speeds[index], vehicle_count=len(vehicles[index]),
                queue_length_vehicles=len(stopped), mean_wait_seconds=round(float(np.mean(stopped)), 3) if stopped else 0.0,
                incoming_vehicles=incoming[index], outgoing_vehicles=outgoing[index], current_phase=phase,
                seconds_in_phase=float(elapsed), time_of_day=round((second / 3600) % 24, 9),
                gps_sample_count=len(sample_speeds),
            ))
        incoming, outgoing = [0] * 4, [0] * 4
    lookup = {(row.timestamp_seconds, row.approach_id): row for row in observations}
    records = [label_observation(row, lookup[(row.timestamp_seconds + 60, row.approach_id)])
               for row in observations if row.timestamp_seconds <= config.duration_seconds]
    # Validate required metadata, group binding, phase consistency and configuration.
    LabeledRun(provenance=provenance_for(config), records=records)
    return RunResult(config, observations, records, events, audit)


def provenance_for(config: RunConfig):
    return RunProvenance(
        run_id=config.run_id, scenario_id=f"{config.scenario_type}-{config.run_id}",
        source_kind="synthetic", generator_version=VERSION, schema_version="1.0.0", seed=57,
        observation_interval_seconds=10, prediction_horizon_seconds=60, label_rule_version="congestion-v1",
    )


def metadata_for(result: RunResult):
    config = result.config
    return {
        **provenance_for(config).model_dump(), "run_seed": config.run_seed,
        "scenario_type": config.scenario_type, "duration_seconds": config.duration_seconds,
        "source_end_seconds": config.duration_seconds + 60, "internal_step_seconds": 1,
        "labeled_rows": len(result.records), "source_rows": len(result.observations),
        "config_json": json.dumps(asdict(config), sort_keys=True, separators=(",", ":")),
        "arrivals_total": sum(sum(step["arrivals"]) for step in result.step_audit),
        "departures_total": sum(sum(step["departures"]) for step in result.step_audit),
        "python_version": platform.python_version(), "numpy_version": np.__version__,
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "signal_policy": "fixed-time-virtual-baseline", "data_description": "synthetic-not-live-GPS",
    }


def write_csv(path: Path, rows: list[dict], fields=None):
    if not rows:
        raise ValueError("cannot export empty CSV")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate_dataset(output_dir: Path, num_runs: int = 30, duration_seconds: int = 1200, seed: int = 57):
    if type(seed) is not int or seed != 57:
        raise ValueError("master seed must be 57; independent run seeds are derived from it")
    if type(num_runs) is not int or not 30 <= num_runs <= 1000:
        raise ValueError("generate at least 30 runs (maximum 1000)")
    # Validate configuration before creating/writing any output.
    configs = [make_run_config(index, duration_seconds) for index in range(num_runs)]
    results = [simulate_run(config) for config in configs]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [row.model_dump() for result in results for row in result.records]
    sources = [row.model_dump() for result in results for row in result.observations]
    metadata = [metadata_for(result) for result in results]
    events = [event for result in results for event in result.phase_events]
    sample_time = (duration_seconds // 20) * 10
    sample = [row.model_dump() for result in results[:5] for row in result.records if row.timestamp_seconds == sample_time]
    outputs = {
        "traffic_observations.csv": records, "run_metadata.csv": metadata,
        "traffic_sample.csv": sample, "traffic_source_snapshots.csv": sources,
        "phase_events.csv": events,
    }
    for name, rows in outputs.items():
        write_csv(output_dir / name, rows)
    summary = {
        "master_seed": 57, "independent_runs": num_runs, "labeled_rows": len(records),
        "source_snapshot_rows": len(sources), "sample_rows": len(sample),
        "phase_event_rows": len(events), "class_balance": dict(sorted(Counter(row["congestion_level"] for row in records).items())),
        "scenario_runs": dict(sorted(Counter(config.scenario_type for config in configs).items())),
        "files": {name: str((output_dir / name).resolve()) for name in outputs},
    }
    return results, summary


def main():
    parser = argparse.ArgumentParser(description="Synthetic traffic only: no live GPS or physical signals.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "ml-service" / "data")
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--duration-seconds", type=int, default=1200)
    parser.add_argument("--seed", type=int, choices=[57], default=57)
    args = parser.parse_args()
    _, summary = generate_dataset(args.output_dir, args.runs, args.duration_seconds, args.seed)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
