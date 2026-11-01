import csv
from collections import Counter, defaultdict
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

import pytest

from app.schemas import LabeledTrafficRecord, RunProvenance, TrafficObservation
from simulation.generate_data import (
    APPROACHES, PHASES, SCENARIOS, demand_rate, generate_dataset,
    incident_active, make_run_config, simulate_run,
)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    output = tmp_path_factory.mktemp("synthetic-junction")
    results, summary = generate_dataset(output)
    return output, results, summary


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_record(row, labeled=False):
    integers = {"timestamp_seconds", "vehicle_count", "queue_length_vehicles",
                "incoming_vehicles", "outgoing_vehicles", "gps_sample_count"}
    numbers = {"mean_speed_kmh", "free_flow_speed_kmh", "mean_wait_seconds",
               "seconds_in_phase", "time_of_day", "future_wait_seconds"}
    result = {}
    for key, value in row.items():
        if key in integers:
            result[key] = int(value)
        elif key in numbers:
            result[key] = float(value) if value else None
        else:
            result[key] = value
    return (LabeledTrafficRecord if labeled else TrafficObservation).model_validate(result)


def test_exported_row_counts_class_balance_and_synthetic_provenance(generated):
    output, results, summary = generated
    assert len(results) == 30
    assert summary["labeled_rows"] == 30 * 121 * 4 == 14520
    assert summary["source_snapshot_rows"] == 30 * 127 * 4 == 15240
    assert summary["sample_rows"] == 20
    assert set(summary["class_balance"]) == {"low", "medium", "high"}
    assert sum(summary["class_balance"].values()) == 14520
    assert all(value > 0 for value in summary["class_balance"].values())
    metadata = read_csv(output / "run_metadata.csv")
    assert len(metadata) == 30
    assert len({row["run_seed"] for row in metadata}) == 30
    assert len({row["run_id"] for row in metadata}) == 30
    assert Counter(row["scenario_type"] for row in metadata) == dict.fromkeys(SCENARIOS, 6)
    for row in metadata:
        provenance = {key: row[key] for key in RunProvenance.model_fields}
        for key in ("seed", "observation_interval_seconds", "prediction_horizon_seconds"):
            provenance[key] = int(provenance[key])
        assert RunProvenance.model_validate(provenance).source_kind == "synthetic"
        assert row["data_description"] == "synthetic-not-live-GPS"
        assert json.loads(row["config_json"])["run_seed"] == int(row["run_seed"])
        assert len(row["generator_sha256"]) == 64


def test_all_exported_rows_meet_schema_bounds_and_targets_match_exact_future(generated):
    output, _, _ = generated
    source = [parse_record(row) for row in read_csv(output / "traffic_source_snapshots.csv")]
    lookup = {(row.run_id, row.timestamp_seconds, row.approach_id): row for row in source}
    assert len(lookup) == len(source)
    for row in source:
        assert row.mean_wait_seconds <= row.timestamp_seconds
        assert row.queue_length_vehicles <= row.vehicle_count
        assert row.gps_sample_count <= row.vehicle_count
        assert (row.mean_speed_kmh is None) == (row.gps_sample_count == 0)
    for raw in read_csv(output / "traffic_observations.csv"):
        row = parse_record(raw, labeled=True)
        future = lookup[(row.run_id, row.timestamp_seconds + 60, row.approach_id)]
        assert row.future_wait_seconds == future.mean_wait_seconds
        assert row.timestamp_seconds <= 1200
    sample = read_csv(output / "traffic_sample.csv")
    assert len(sample) == 20
    assert len({row["run_id"] for row in sample}) == 5
    assert all(row["timestamp_seconds"] == "600" for row in sample)


def test_time_order_flow_conservation_and_initial_empty_state(generated):
    _, results, _ = generated
    for result in results:
        per_approach = defaultdict(list)
        for row in result.observations:
            per_approach[row.approach_id].append(row)
        assert set(per_approach) == set(APPROACHES)
        for index, approach in enumerate(APPROACHES):
            rows = per_approach[approach]
            assert [row.timestamp_seconds for row in rows] == list(range(0, 1261, 10))
            first = rows[0]
            assert first.vehicle_count == first.incoming_vehicles == first.outgoing_vehicles == 0
            for before, after in zip(rows, rows[1:]):
                assert after.vehicle_count == before.vehicle_count + after.incoming_vehicles - after.outgoing_vehicles
            arrivals = sum(step["arrivals"][index] for step in result.step_audit)
            departures = sum(step["departures"][index] for step in result.step_audit)
            assert arrivals - departures == rows[-1].vehicle_count
            assert arrivals == sum(row.incoming_vehicles for row in rows)
            assert departures == sum(row.outgoing_vehicles for row in rows)


def test_every_phase_transition_clearance_and_departure_is_safe(generated):
    _, results, _ = generated
    for result in results:
        events = result.phase_events
        assert events[0]["timestamp_seconds"] == 0 and events[0]["current_phase"] == "ns_green"
        for previous, event in zip(events, events[1:]):
            previous_index = PHASES.index(previous["current_phase"])
            assert event["current_phase"] == PHASES[(previous_index + 1) % 6]
            assert event["timestamp_seconds"] - previous["timestamp_seconds"] == previous["planned_duration_seconds"]
        for event in events:
            if "green" in event["current_phase"]:
                assert 20 <= event["planned_duration_seconds"] <= 45
            elif "yellow" in event["current_phase"]:
                assert event["planned_duration_seconds"] == 3
            else:
                assert event["planned_duration_seconds"] == 2
        current_event = 0
        for step in result.step_audit:
            while current_event + 1 < len(events) and events[current_event + 1]["timestamp_seconds"] <= step["timestamp_seconds"]:
                current_event += 1
            event = events[current_event]
            assert step["current_phase"] == event["current_phase"]
            assert step["seconds_in_phase"] == step["timestamp_seconds"] - event["timestamp_seconds"]
            north_south, east_west = sum(step["departures"][:2]), sum(step["departures"][2:])
            assert not (north_south and east_west)
            if north_south:
                assert step["current_phase"] == "ns_green" and step["seconds_in_phase"] >= 2
            if east_west:
                assert step["current_phase"] == "ew_green" and step["seconds_in_phase"] >= 2
            if "green" not in step["current_phase"]:
                assert sum(step["departures"]) == 0
        # Both axes receive regular service opportunities; no adaptive phase starvation.
        cycle = sum(result.config.phase_durations)
        for green in ("ns_green", "ew_green"):
            starts = [event["timestamp_seconds"] for event in events if event["current_phase"] == green]
            assert all(after - before == cycle for before, after in zip(starts, starts[1:]))
        # Fractional capacity must be conserved, never rounded up to extra departures.
        for index in range(4):
            budget = sum(result.config.saturation_rates[index] *
                         (result.config.incident_capacity_factor if incident_active(result.config, step["timestamp_seconds"])
                          and index == result.config.incident_index else 1)
                         for step in result.step_audit
                         if ((step["current_phase"] == "ns_green" and index < 2) or
                             (step["current_phase"] == "ew_green" and index >= 2)) and step["seconds_in_phase"] >= 2)
            assert sum(step["departures"][index] for step in result.step_audit) <= budget + 1e-8


def test_demand_scenario_diversity_is_real_not_just_different_names(generated):
    _, results, _ = generated
    totals = defaultdict(list)
    queues = defaultdict(list)
    for result in results:
        totals[result.config.scenario_type].append(sum(sum(step["arrivals"]) for step in result.step_audit))
        queues[result.config.scenario_type].extend(row.queue_length_vehicles for row in result.records)
        if result.config.scenario_type == "asymmetric_rush_hour":
            dominant = result.config.dominant_index
            cross = (dominant + 2) % 4
            midpoint = result.config.duration_seconds // 2
            assert demand_rate(result.config, dominant, midpoint) > 3 * demand_rate(result.config, cross, midpoint)
            assert demand_rate(result.config, dominant, midpoint) > 3 * demand_rate(result.config, dominant, 0)
    assert sum(totals["high"]) > 5 * sum(totals["low"])
    assert sum(queues["high"]) / len(queues["high"]) > 5 * sum(queues["low"]) / len(queues["low"])
    assert sum(totals["medium"]) > 2 * sum(totals["low"])


def test_incident_reduces_actual_discharge_not_only_metadata():
    config = make_run_config(4)
    restricted = simulate_run(config)
    full_capacity = simulate_run(replace(config, incident_capacity_factor=1.0))
    index = config.incident_index
    assert not incident_active(config, 0)
    assert incident_active(config, 600)
    assert not incident_active(config, 1200)
    assert [step["arrivals"] for step in restricted.step_audit] == [step["arrivals"] for step in full_capacity.step_audit]
    affected = [step for step in restricted.step_audit if incident_active(config, step["timestamp_seconds"])]
    reference = [step for step in full_capacity.step_audit if incident_active(config, step["timestamp_seconds"])]
    assert sum(step["departures"][index] for step in affected) < sum(step["departures"][index] for step in reference)


def test_gps_sampling_does_not_change_simulated_traffic():
    config = make_run_config(7, duration_seconds=120)
    sparse = simulate_run(replace(config, gps_coverage=0.1))
    dense = simulate_run(replace(config, gps_coverage=1.0))
    assert sparse.step_audit == dense.step_audit
    for left, right in zip(sparse.observations, dense.observations):
        excluded = {"mean_speed_kmh", "gps_sample_count"}
        assert left.model_dump(exclude=excluded) == right.model_dump(exclude=excluded)
    assert sum(row.gps_sample_count for row in sparse.observations) < sum(row.gps_sample_count for row in dense.observations)


def test_seed_57_is_byte_reproducible_for_every_export(generated, tmp_path):
    first, _, _ = generated
    second = tmp_path / "repeat"
    _, summary = generate_dataset(second)
    assert summary["master_seed"] == 57
    for name in summary["files"]:
        assert hashlib.sha256((first / name).read_bytes()).digest() == hashlib.sha256((second / name).read_bytes()).digest(), name


@pytest.mark.parametrize("updates", [
    {"duration_seconds": 0}, {"duration_seconds": 121}, {"duration_seconds": 3010},
    {"ns_green_seconds": 0}, {"ew_green_seconds": 46}, {"yellow_seconds": 0},
    {"all_red_seconds": 0}, {"yellow_seconds": 3.0}, {"gps_coverage": 0},
    {"incident_capacity_factor": 0}, {"scenario_type": "live_gps"},
])
def test_invalid_or_unsafe_simulation_configuration_is_rejected(updates):
    with pytest.raises(ValueError):
        replace(make_run_config(0), **updates)


@pytest.mark.parametrize("updates", [{"num_runs": 29}, {"num_runs": 0}, {"seed": 58}])
def test_dataset_rejects_too_few_runs_or_wrong_master_seed(tmp_path, updates):
    with pytest.raises(ValueError):
        generate_dataset(tmp_path / "should-not-be-created", **updates)
    assert not (tmp_path / "should-not-be-created").exists()


def test_run_seed_is_stable_and_not_reused_across_scenarios():
    assert make_run_config(17) == make_run_config(17)
    assert len({make_run_config(index).run_seed for index in range(30)}) == 30
    with pytest.raises(ValueError):
        make_run_config(-1)


def test_fractional_saturation_capacity_is_realized_when_backlogged(generated):
    _, results, _ = generated
    result = results[2]  # High demand, with persistent backlog after warm-up.
    for event in result.phase_events:
        start = event["timestamp_seconds"]
        duration = event["planned_duration_seconds"]
        phase = event["current_phase"]
        if start < 600 or start + duration > 1261 or "green" not in phase:
            continue
        active = (0, 1) if phase == "ns_green" else (2, 3)
        steps = result.step_audit[start:start + duration]
        for index in active:
            expected = math.floor((duration - 2) * result.config.saturation_rates[index])
            assert sum(step["departures"][index] for step in steps) == expected
