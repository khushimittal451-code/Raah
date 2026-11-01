"""Versioned synthetic traffic contract; no private GPS ingestion is supported."""
from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"
SEED = 57
OBSERVATION_INTERVAL_SECONDS = 10
PREDICTION_HORIZON_SECONDS = 60
LABEL_RULE_VERSION = "congestion-v1"

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
Count = Annotated[int, Field(ge=0, le=10000)]
Seconds = Annotated[float, Field(ge=0, le=3600)]
Phase = Literal[
    "ns_green", "ns_yellow", "all_red_to_ew",
    "ew_green", "ew_yellow", "all_red_to_ns",
]
CongestionLevel = Literal["low", "medium", "high"]


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class TrafficObservation(StrictRecord):
    """Required fields available at synthetic snapshot time t; no future data."""

    run_id: Identifier = Field(description="Independent synthetic run; split by this group.")
    timestamp_seconds: Annotated[int, Field(ge=0, le=604800, multiple_of=10)] = Field(
        description="Elapsed run seconds from synthetic midnight, on a 10-second grid."
    )
    intersection_id: Identifier = Field(description="Synthetic junction identifier, not GPS.")
    approach_id: Literal["north", "south", "east", "west"] = Field(
        description="Inbound approach relative to the abstract junction."
    )
    mean_speed_kmh: Annotated[float, Field(ge=0, le=160)] | None = Field(
        description="Mean GPS-like sampled speed of vehicles present at t; null iff no samples."
    )
    free_flow_speed_kmh: Annotated[float, Field(gt=0, le=160)] = Field(
        description="Run/approach configuration speed; not estimated using held-out traffic."
    )
    vehicle_count: Count = Field(description="Vehicles present on the approach at snapshot t.")
    queue_length_vehicles: Count = Field(description="Queued subset of present vehicles at t.")
    mean_wait_seconds: Seconds = Field(description="Mean elapsed waiting of currently queued vehicles; zero for no queue.")
    incoming_vehicles: Count = Field(description="Approach entries during (t-10,t]; zero at initialization t=0.")
    outgoing_vehicles: Count = Field(description="Approach exits during (t-10,t]; zero at initialization t=0.")
    current_phase: Phase = Field(description="Intersection-wide virtual phase at t; not a physical signal.")
    seconds_in_phase: Seconds = Field(description="Elapsed seconds in the current virtual phase at t.")
    time_of_day: Annotated[float, Field(ge=0, lt=24)] = Field(
        description="Fractional synthetic hour: (timestamp_seconds / 3600) modulo 24."
    )
    gps_sample_count: Count = Field(
        description="Distinct currently present vehicles with a valid synthetic speed sample; one per vehicle."
    )

    @model_validator(mode="after")
    def consistent_snapshot(self) -> TrafficObservation:
        if self.timestamp_seconds % OBSERVATION_INTERVAL_SECONDS:
            raise ValueError("timestamp_seconds must lie on the 10-second grid")
        if self.queue_length_vehicles > self.vehicle_count:
            raise ValueError("queue_length_vehicles cannot exceed vehicle_count")
        if self.gps_sample_count > self.vehicle_count:
            raise ValueError("gps_sample_count cannot exceed vehicle_count")
        if (self.gps_sample_count == 0) != (self.mean_speed_kmh is None):
            raise ValueError("mean_speed_kmh must be null exactly when gps_sample_count is zero")
        if self.queue_length_vehicles == 0 and self.mean_wait_seconds != 0:
            raise ValueError("mean_wait_seconds must be zero when there is no queue")
        if self.seconds_in_phase > self.timestamp_seconds:
            raise ValueError("seconds_in_phase cannot exceed elapsed run time")
        if self.timestamp_seconds == 0 and (self.incoming_vehicles or self.outgoing_vehicles):
            raise ValueError("initialization has no previous flow interval")
        expected_hour = (self.timestamp_seconds / 3600) % 24
        if not math.isclose(self.time_of_day, expected_hour, rel_tol=0, abs_tol=1e-6):
            raise ValueError("time_of_day must match the synthetic timestamp within 1e-6 hours")
        return self


def congestion_level_for(observation: TrafficObservation) -> CongestionLevel:
    """An operational synthetic index, not independent empirical ground truth."""
    ratio = (
        observation.mean_speed_kmh / observation.free_flow_speed_kmh
        if observation.mean_speed_kmh is not None else None
    )
    enough_vehicles = observation.vehicle_count >= 5
    if (
        observation.queue_length_vehicles >= 10
        or observation.mean_wait_seconds >= 60
        or (enough_vehicles and ratio is not None and ratio <= 0.35)
    ):
        return "high"
    if (
        observation.queue_length_vehicles >= 5
        or observation.mean_wait_seconds >= 30
        or (enough_vehicles and ratio is not None and ratio <= 0.70)
    ):
        return "medium"
    return "low"


class LabeledTrafficRecord(TrafficObservation):
    """Offline training/evaluation row; target fields must never be inference inputs."""

    congestion_level: CongestionLevel = Field(description="Current rule-derived congestion-v1 index; horizon zero.")
    future_wait_seconds: Seconds = Field(description="Mean queue wait at the exact same run/junction/approach snapshot t+60s.")

    @model_validator(mode="after")
    def consistent_current_label(self) -> LabeledTrafficRecord:
        if self.congestion_level != congestion_level_for(self):
            raise ValueError("congestion_level does not match congestion-v1")
        return self


def label_observation(
    current: TrafficObservation, future: TrafficObservation,
) -> LabeledTrafficRecord:
    """Join an exact future snapshot; reject wrong groups, horizons, or configuration."""
    keys = ("run_id", "intersection_id", "approach_id")
    if any(getattr(current, key) != getattr(future, key) for key in keys):
        raise ValueError("future snapshot must match run, intersection and approach")
    if future.timestamp_seconds != current.timestamp_seconds + PREDICTION_HORIZON_SECONDS:
        raise ValueError("future snapshot must be exactly 60 seconds ahead")
    if current.free_flow_speed_kmh != future.free_flow_speed_kmh:
        raise ValueError("free-flow configuration must be constant within a run/approach")
    return LabeledTrafficRecord(
        **current.model_dump(),
        congestion_level=congestion_level_for(current),
        future_wait_seconds=future.mean_wait_seconds,
    )


class RunProvenance(StrictRecord):
    """Required companion metadata for each generated run, not model features."""

    run_id: Identifier
    scenario_id: Identifier
    source_kind: Literal["synthetic"]
    generator_version: Annotated[str, Field(min_length=1, max_length=128)]
    schema_version: Literal["1.0.0"]
    seed: Literal[57]
    observation_interval_seconds: Literal[10]
    prediction_horizon_seconds: Literal[60]
    label_rule_version: Literal["congestion-v1"]

    @field_validator("seed", "observation_interval_seconds", "prediction_horizon_seconds", mode="before")
    @classmethod
    def exact_integer_constants(cls, value):
        # Literal equality otherwise treats 57.0 as the same value as 57.
        if type(value) is not int:
            raise ValueError("provenance numeric constants must be exact integers")
        return value


class LabeledRun(StrictRecord):
    """Storage envelope binding every row to its required synthetic provenance."""

    provenance: RunProvenance
    records: Annotated[list[LabeledTrafficRecord], Field(min_length=1)]

    @model_validator(mode="after")
    def consistent_run(self) -> LabeledRun:
        seen = set()
        free_flow = {}
        phases = {}
        for row in self.records:
            if row.run_id != self.provenance.run_id:
                raise ValueError("every record must match provenance.run_id")
            key = (row.timestamp_seconds, row.intersection_id, row.approach_id)
            if key in seen:
                raise ValueError("duplicate snapshot key within run")
            seen.add(key)
            phase_key = (row.timestamp_seconds, row.intersection_id)
            phase_state = (row.current_phase, row.seconds_in_phase)
            if phases.setdefault(phase_key, phase_state) != phase_state:
                raise ValueError("intersection approaches must share the same phase state at t")
            approach = (row.intersection_id, row.approach_id)
            previous = free_flow.setdefault(approach, row.free_flow_speed_kmh)
            if previous != row.free_flow_speed_kmh:
                raise ValueError("free-flow configuration must be constant within a run/approach")
        return self
