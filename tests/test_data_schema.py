import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import (
    LabeledRun, LabeledTrafficRecord, RunProvenance, TrafficObservation,
    congestion_level_for, label_observation,
)
from export_schema import build_schema

OBSERVATION = {
    "run_id": "run-57-001",
    "timestamp_seconds": 3600,
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
    "time_of_day": 1.0,
    "gps_sample_count": 10,
}
PROVENANCE = {
    "run_id": "run-57-001",
    "scenario_id": "fixture-scenario-1",
    "source_kind": "synthetic",
    "generator_version": "test-fixture-v1",
    "schema_version": "1.0.0",
    "seed": 57,
    "observation_interval_seconds": 10,
    "prediction_horizon_seconds": 60,
    "label_rule_version": "congestion-v1",
}
NUMERIC_FIELDS = [key for key, value in OBSERVATION.items() if type(value) in (int, float)]


def observation(**updates):
    return TrafficObservation.model_validate({**OBSERVATION, **updates})


def labeled(**updates):
    current = observation()
    future = observation(timestamp_seconds=3660, time_of_day=3660 / 3600, mean_wait_seconds=25.0)
    return LabeledTrafficRecord.model_validate({**label_observation(current, future).model_dump(), **updates})


def envelope(records=None, **metadata):
    return {"provenance": {**PROVENANCE, **metadata}, "records": records or [labeled().model_dump()]}


def test_valid_snapshot_and_labeled_json_round_trip():
    row = labeled()
    assert row.congestion_level == "low"
    assert row.future_wait_seconds == 25
    assert LabeledTrafficRecord.model_validate_json(row.model_dump_json()) == row
    assert LabeledRun.model_validate_json(json.dumps(envelope())).provenance.seed == 57


@pytest.mark.parametrize("field", list(OBSERVATION))
def test_every_observation_field_is_required(field):
    payload = dict(OBSERVATION)
    del payload[field]
    with pytest.raises(ValidationError):
        TrafficObservation.model_validate(payload)


@pytest.mark.parametrize("field", ["congestion_level", "future_wait_seconds"])
def test_both_targets_are_required_for_labeled_rows(field):
    payload = labeled().model_dump()
    del payload[field]
    with pytest.raises(ValidationError):
        LabeledTrafficRecord.model_validate(payload)


@pytest.mark.parametrize("field", list(PROVENANCE))
def test_every_provenance_field_is_required(field):
    payload = dict(PROVENANCE)
    del payload[field]
    with pytest.raises(ValidationError):
        RunProvenance.model_validate(payload)


@pytest.mark.parametrize("field", NUMERIC_FIELDS)
@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), float("-inf"), "1", True])
def test_reject_invalid_numeric_values_and_coercion(field, bad):
    with pytest.raises(ValidationError):
        observation(**{field: bad})


@pytest.mark.parametrize("field,bad", [
    ("timestamp_seconds", 604810), ("timestamp_seconds", 3601),
    ("mean_speed_kmh", 160.1), ("free_flow_speed_kmh", 0),
    ("free_flow_speed_kmh", 160.1), ("vehicle_count", 10001),
    ("queue_length_vehicles", 10001), ("gps_sample_count", 10001),
    ("incoming_vehicles", 10001), ("outgoing_vehicles", 10001),
    ("mean_wait_seconds", 3600.1), ("seconds_in_phase", 3600.1),
    ("time_of_day", 24),
])
def test_reject_upper_bounds_zero_reference_and_off_grid_time(field, bad):
    with pytest.raises(ValidationError):
        observation(**{field: bad})


@pytest.mark.parametrize("field", ["timestamp_seconds", "vehicle_count", "queue_length_vehicles", "incoming_vehicles", "outgoing_vehicles", "gps_sample_count"])
def test_counts_and_timestamps_must_be_integers(field):
    with pytest.raises(ValidationError):
        observation(**{field: 1.5})


@pytest.mark.parametrize("field,bad", [
    ("run_id", ""), ("run_id", "with space"), ("intersection_id", "_bad"),
    ("intersection_id", "x" * 65), ("approach_id", "northeast"),
    ("current_phase", "conflicting_green"),
])
def test_identifiers_and_phase_vocabulary(field, bad):
    with pytest.raises(ValidationError):
        observation(**{field: bad})


@pytest.mark.parametrize("updates", [
    {"queue_length_vehicles": 21}, {"gps_sample_count": 21},
    {"gps_sample_count": 0}, {"mean_speed_kmh": None},
    {"queue_length_vehicles": 0, "mean_wait_seconds": 1},
    {"timestamp_seconds": 10, "time_of_day": 10 / 3600, "seconds_in_phase": 11},
    {"time_of_day": 2.0},
    {"timestamp_seconds": 0, "time_of_day": 0, "seconds_in_phase": 0},
])
def test_snapshot_cross_field_invariants(updates):
    with pytest.raises(ValidationError):
        observation(**updates)


def test_empty_and_unsampled_observations_preserve_missing_speed():
    empty = observation(vehicle_count=0, queue_length_vehicles=0, mean_wait_seconds=0,
                        gps_sample_count=0, mean_speed_kmh=None)
    assert congestion_level_for(empty) == "low"
    assert observation(gps_sample_count=0, mean_speed_kmh=None).mean_speed_kmh is None
    with pytest.raises(ValidationError):
        observation(gps_sample_count=0, mean_speed_kmh=0)


def test_initialization_and_synthetic_clock_rollover():
    assert observation(timestamp_seconds=0, time_of_day=0, seconds_in_phase=0,
                       incoming_vehicles=0, outgoing_vehicles=0).timestamp_seconds == 0
    assert observation(timestamp_seconds=86400, time_of_day=0).time_of_day == 0
    assert observation(timestamp_seconds=604800, time_of_day=0).timestamp_seconds == 604800


@pytest.mark.parametrize("updates,expected", [
    ({"queue_length_vehicles": 4}, "low"),
    ({"queue_length_vehicles": 5}, "medium"),
    ({"queue_length_vehicles": 9}, "medium"),
    ({"queue_length_vehicles": 10}, "high"),
    ({"mean_wait_seconds": 29.999}, "low"),
    ({"mean_wait_seconds": 30}, "medium"),
    ({"mean_wait_seconds": 59.999}, "medium"),
    ({"mean_wait_seconds": 60}, "high"),
    ({"mean_speed_kmh": 21}, "high"),
    ({"mean_speed_kmh": 21.0001}, "medium"),
    ({"mean_speed_kmh": 42}, "medium"),
    ({"mean_speed_kmh": 42.0001}, "low"),
    ({"vehicle_count": 4, "queue_length_vehicles": 0, "mean_wait_seconds": 0,
      "gps_sample_count": 4, "mean_speed_kmh": 0}, "low"),
    ({"vehicle_count": 5, "gps_sample_count": 5, "mean_speed_kmh": 0}, "high"),
    ({"gps_sample_count": 0, "mean_speed_kmh": None}, "low"),
    ({"gps_sample_count": 0, "mean_speed_kmh": None, "mean_wait_seconds": 60}, "high"),
])
def test_congestion_thresholds_precedence_missingness_and_sparse_count_gate(updates, expected):
    assert congestion_level_for(observation(**updates)) == expected


@pytest.mark.parametrize("updates", [
    {"congestion_level": "unknown"}, {"congestion_level": "high"},
    {"future_wait_seconds": -1}, {"future_wait_seconds": 3600.1},
    {"future_wait_seconds": None}, {"future_wait_seconds": float("inf")},
    {"future_wait_seconds": float("nan")}, {"future_wait_seconds": "20"},
])
def test_targets_reject_wrong_labels_and_invalid_future_wait(updates):
    with pytest.raises(ValidationError):
        labeled(**updates)


@pytest.mark.parametrize("field,value", [
    ("run_id", "different-run"), ("intersection_id", "different-junction"),
    ("approach_id", "east"), ("free_flow_speed_kmh", 65),
])
def test_future_join_rejects_wrong_group_or_configuration(field, value):
    future = observation(timestamp_seconds=3660, time_of_day=3660 / 3600, **{field: value})
    with pytest.raises(ValueError):
        label_observation(observation(), future)


@pytest.mark.parametrize("future_time", [3600, 3650, 3670])
def test_future_join_requires_exact_horizon_no_nearest_or_cross_run_shift(future_time):
    future = observation(timestamp_seconds=future_time, time_of_day=future_time / 3600)
    with pytest.raises(ValueError, match="exactly 60"):
        label_observation(observation(), future)


def test_no_future_target_is_accepted_as_current_inference_feature():
    with pytest.raises(ValidationError):
        TrafficObservation.model_validate(labeled().model_dump())
    with pytest.raises(ValidationError):
        observation(latitude=28.6)


@pytest.mark.parametrize("updates", [
    {"source_kind": "measured"}, {"seed": 58}, {"seed": 57.0},
    {"observation_interval_seconds": 5}, {"observation_interval_seconds": 10.0},
    {"prediction_horizon_seconds": 30}, {"prediction_horizon_seconds": 60.0},
    {"label_rule_version": "unknown"}, {"schema_version": "2.0.0"},
    {"generator_version": ""},
])
def test_provenance_rejects_unknown_sources_versions_or_contract_values(updates):
    with pytest.raises(ValidationError):
        RunProvenance.model_validate({**PROVENANCE, **updates})


def test_run_envelope_rejects_missing_provenance_or_empty_records():
    with pytest.raises(ValidationError):
        LabeledRun.model_validate({"records": [labeled().model_dump()]})
    with pytest.raises(ValidationError):
        LabeledRun.model_validate({"provenance": PROVENANCE, "records": []})


def test_run_envelope_rejects_wrong_run_and_duplicate_keys():
    with pytest.raises(ValidationError, match="provenance.run_id"):
        LabeledRun.model_validate(envelope(run_id="other-run"))
    row = labeled().model_dump()
    with pytest.raises(ValidationError, match="duplicate"):
        LabeledRun.model_validate(envelope(records=[row, row]))


def test_run_envelope_rejects_inconsistent_intersection_phase():
    row = labeled().model_dump()
    second = {**row, "approach_id": "east", "current_phase": "ew_green"}
    with pytest.raises(ValidationError, match="same phase"):
        LabeledRun.model_validate(envelope(records=[row, second]))


def test_run_envelope_rejects_changing_free_flow_speed():
    row = labeled().model_dump()
    second = {**row, "timestamp_seconds": 3660, "time_of_day": 3660 / 3600,
              "free_flow_speed_kmh": 65}
    with pytest.raises(ValidationError, match="constant"):
        LabeledRun.model_validate(envelope(records=[row, second]))


def test_exported_json_schema_matches_canonical_pydantic_models():
    path = Path(__file__).resolve().parents[1] / "ml-service" / "data" / "schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert schema == build_schema()
    assert schema["$ref"] == "#/$defs/LabeledRun"
    defs = schema["$defs"]
    assert set(defs["TrafficObservation"]["required"]) == set(OBSERVATION)
    assert set(defs["LabeledTrafficRecord"]["required"]) == set(labeled().model_dump())
    assert set(defs["RunProvenance"]["required"]) == set(PROVENANCE)
    assert defs["TrafficObservation"]["additionalProperties"] is False
    assert defs["TrafficObservation"]["properties"]["timestamp_seconds"]["multipleOf"] == 10
    assert "future_wait_seconds" not in defs["TrafficObservation"]["properties"]


@pytest.mark.parametrize("field", list(OBSERVATION))
def test_required_observation_fields_reject_null_in_an_otherwise_sampled_row(field):
    with pytest.raises(ValidationError):
        observation(**{field: None})
