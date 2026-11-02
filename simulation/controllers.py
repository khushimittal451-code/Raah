"""Deterministic VIRTUAL controllers. No network, hardware, or actuation adapters.

Call step once per integer second, starting at zero. Opposing through movements
share green; turns are excluded. All decisions pass through the same state machine.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import Enum
import json
import math
from pathlib import Path

APPROACHES = ("north", "south", "east", "west")
AXES = {"ns": APPROACHES[:2], "ew": APPROACHES[2:]}


class Phase(str, Enum):
    NS_GREEN = "ns_green"
    NS_YELLOW = "ns_yellow"
    ALL_RED_TO_EW = "all_red_to_ew"
    EW_GREEN = "ew_green"
    EW_YELLOW = "ew_yellow"
    ALL_RED_TO_NS = "all_red_to_ns"


PHASE_SEQUENCE = tuple(Phase)
NEXT_PHASE = dict(zip(PHASE_SEQUENCE, PHASE_SEQUENCE[1:] + PHASE_SEQUENCE[:1]))


def integer(value, name, low=0, high=604800):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an exact integer in [{low},{high}]")
    return value


def finite(value, name, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError(f"{name} must be finite in [{low},{high}]")
    return float(value)


@dataclass(frozen=True)
class TimingConfig:
    """Illustrative simulation timings, never certified real-road timings."""
    min_green: int = 15
    max_green: int = 60
    yellow: int = 3
    all_red: int = 1
    fixed_green: int = 30
    max_red_wait: int = 75
    extension_step: int = 5
    pedestrian_walk: int = 7
    pedestrian_clearance: int = 8
    prediction_max_age: int = 10
    queue_hysteresis: float = 1.0
    ml_weight: float = 3.0

    def __post_init__(self):
        for name in ("min_green", "max_green", "yellow", "all_red", "fixed_green",
                     "max_red_wait", "extension_step", "pedestrian_walk", "pedestrian_clearance"):
            integer(getattr(self, name), name, 1, 3600)
        integer(self.prediction_max_age, "prediction_max_age", 0, 3600)
        finite(self.queue_hysteresis, "queue_hysteresis", 0, 100)
        finite(self.ml_weight, "ml_weight", 0, 10)
        if not self.green_floor <= self.fixed_green <= self.max_green:
            raise ValueError("require max(min_green, walk+pedestrian clearance) <= fixed_green <= max_green")
        if self.max_red_wait < self.green_floor + 2 * self.clearance:
            raise ValueError("infeasible fairness: max_red_wait < green floor + two vehicle clearances")
        if self.fixed_green + 2 * self.clearance > self.max_red_wait:
            raise ValueError("fixed green violates maximum red bound")
        if self.extension_step > self.max_green:
            raise ValueError("extension_step cannot exceed max_green")

    @property
    def clearance(self):
        return self.yellow + self.all_red

    @property
    def green_floor(self):
        return max(self.min_green, self.pedestrian_walk + self.pedestrian_clearance)


@dataclass(frozen=True)
class ControllerState:
    timestamp_seconds: int
    phase: Phase
    seconds_in_phase: int
    vehicle_greens: tuple[str, ...]
    pedestrian_state: str
    pedestrian_axis: str | None
    ns_red_seconds: int
    ew_red_seconds: int
    planned_green_seconds: int


@dataclass(frozen=True)
class PredictionEvidence:
    approach: str
    generated_at_seconds: int
    congestion_level: str
    future_wait_seconds: float
    prediction_horizon_seconds: int = 60


@dataclass(frozen=True)
class Action:
    timestamp_seconds: int
    controller: str
    action: str
    previous_phase: str | None
    phase: str
    seconds_in_phase: int
    planned_green_seconds: int
    reason: str
    queues: tuple[int, ...]
    ns_pressure: float
    ew_pressure: float
    prediction_status: str
    prediction_model_version: str | None
    prediction_inputs: tuple[PredictionEvidence, ...]
    red_seconds: tuple[int, int]
    pedestrian_state: str
    pedestrian_axis: str | None
    virtual_only: bool = True


class FixedTimeController:
    """Alternating fixed schedule with the same mandatory safety checks."""
    adaptive = False

    def __init__(self, config: TimingConfig | None = None):
        self._config = TimingConfig() if config is None else config
        if not isinstance(self._config, TimingConfig):
            raise TypeError("config must be TimingConfig")
        self._phase = Phase.NS_GREEN
        self._phase_start = 0
        self._last_second = -1
        self._red_since = {"ns": None, "ew": 0}
        self._target = self._initial_target()
        self._actions = []

    @property
    def config(self):
        return self._config

    @property
    def phase(self):
        return self._phase

    @property
    def action_log(self):
        return tuple(self._actions)

    def _initial_target(self):
        return self.config.green_floor if self.adaptive else self.config.fixed_green

    def _pressures(self, queues, predictions, second):
        return ({axis: float(sum(queues[a] for a in approaches)) for axis, approaches in AXES.items()},
                "not_used", None, ())

    def _snapshot(self, second):
        elapsed = second - self._phase_start
        axis = "ns" if self.phase == Phase.NS_GREEN else "ew" if self.phase == Phase.EW_GREEN else None
        ped = "dont_walk"
        if axis and elapsed < self.config.pedestrian_walk:
            ped = "walk"
        elif axis and elapsed < self.config.pedestrian_walk + self.config.pedestrian_clearance:
            ped = "clearance"
        ages = {key: 0 if start is None else second - start for key, start in self._red_since.items()}
        return ControllerState(second, self.phase, elapsed, AXES[axis] if axis else (), ped,
                               axis if ped != "dont_walk" else None, ages["ns"], ages["ew"], self._target)

    def _transition(self, second):
        previous = self.phase
        self._phase = NEXT_PHASE[previous]
        self._phase_start = second
        if previous in (Phase.NS_GREEN, Phase.EW_GREEN):
            self._red_since["ns" if previous == Phase.NS_GREEN else "ew"] = second
        if self.phase in (Phase.NS_GREEN, Phase.EW_GREEN):
            self._red_since["ns" if self.phase == Phase.NS_GREEN else "ew"] = None
            self._target = self._initial_target()

    def step(self, timestamp_seconds: int, queues: Mapping[str, int], predictions=None) -> ControllerState:
        """Process one second. Invalid demand/clock raises before any state changes.

        predictions are optional timestamped ML estimates for all four approaches.
        Invalid ML estimates fall back atomically to current-queue rules.
        """
        second = integer(timestamp_seconds, "timestamp_seconds")
        if second != self._last_second + 1:
            raise ValueError("call every consecutive second, starting at zero; skipped/duplicate clocks are forbidden")
        if not isinstance(queues, Mapping) or set(queues) != set(APPROACHES):
            raise ValueError("queues must contain exactly north, south, east, west")
        observed = {a: integer(queues[a], f"queue[{a}]", 0, 10000) for a in APPROACHES}
        pressure, prediction_status, version, evidence = self._pressures(observed, predictions, second)
        previous = self.phase
        elapsed = second - self._phase_start
        action, reason = "HOLD", "holding_planned_green"
        if self._last_second == -1:
            action, reason = "INITIALIZE", "virtual_start_ns_green"
        elif previous in (Phase.NS_YELLOW, Phase.EW_YELLOW):
            if elapsed >= self.config.yellow:
                self._transition(second)
                action, reason = "TRANSITION", "yellow_complete_enter_all_red"
            else:
                reason = "mandatory_yellow_clearance"
        elif previous in (Phase.ALL_RED_TO_EW, Phase.ALL_RED_TO_NS):
            if elapsed >= self.config.all_red:
                self._transition(second)
                action, reason = "TRANSITION", "all_red_complete_opposing_green"
            else:
                reason = "mandatory_all_red_clearance"
        else:
            axis = "ns" if previous == Phase.NS_GREEN else "ew"
            other = "ew" if axis == "ns" else "ns"
            red_age = second - self._red_since[other]
            if elapsed < self.config.green_floor:
                reason = "minimum_green_and_pedestrian_clearance"
            elif red_age + self.config.clearance >= self.config.max_red_wait:
                self._transition(second)
                action, reason = "TRANSITION", "maximum_red_fairness_deadline"
            elif elapsed >= self.config.max_green:
                self._transition(second)
                action, reason = "TRANSITION", "maximum_green_reached"
            elif elapsed >= self._target:
                if self.adaptive and pressure[axis] > pressure[other] + self.config.queue_hysteresis:
                    # Reserve time for the full outgoing clearance before the red deadline.
                    extension = min(self.config.extension_step, self.config.max_green - elapsed,
                                    self.config.max_red_wait - red_age - self.config.clearance)
                    self._target = elapsed + extension
                    action, reason = "EXTEND", "active_pressure_higher_bounded_extension"
                else:
                    self._transition(second)
                    action = "TRANSITION"
                    reason = "fixed_green_complete" if not self.adaptive else "opposing_pressure_or_no_extension_benefit"
        self._last_second = second
        state = self._snapshot(second)
        assert max(state.ns_red_seconds, state.ew_red_seconds) <= self.config.max_red_wait
        assert not (set(state.vehicle_greens) & set(AXES["ns"]) and set(state.vehicle_greens) & set(AXES["ew"]))
        self._actions.append(Action(second, type(self).__name__, action,
            previous.value if second else None, self.phase.value, state.seconds_in_phase, self._target,
            reason, tuple(observed[a] for a in APPROACHES), pressure["ns"], pressure["ew"],
            prediction_status, version, evidence, (state.ns_red_seconds, state.ew_red_seconds),
            state.pedestrian_state, state.pedestrian_axis))
        return state

    def write_log(self, path):
        """Explicitly export this controller's immutable action history as JSONL."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(asdict(row), sort_keys=True, allow_nan=False) + "\n"
                                for row in self._actions), encoding="utf-8")


class RuleOnlyAdaptiveController(FixedTimeController):
    """Extend green in bounded increments based only on current queue pressure."""
    adaptive = True


class MLAdaptiveController(RuleOnlyAdaptiveController):
    """Bounded ML pressure supplement; safety and fairness never depend on ML."""
    def _pressures(self, queues, predictions, second):
        pressures, _, _, _ = super()._pressures(queues, predictions, second)
        try:
            if not isinstance(predictions, Mapping) or set(predictions) != set(APPROACHES):
                raise ValueError("missing_or_incomplete_predictions")
            additions, versions, evidence = {}, set(), []
            for approach in APPROACHES:
                item = predictions[approach]
                if not isinstance(item, Mapping):
                    raise ValueError("invalid_prediction_record")
                if set(item) != {"congestion_level", "future_wait_seconds", "generated_at_seconds",
                                 "prediction_horizon_seconds", "model_version"}:
                    raise ValueError("invalid_prediction_fields")
                generated = integer(item["generated_at_seconds"], "generated_at_seconds")
                horizon = integer(item["prediction_horizon_seconds"], "prediction_horizon_seconds")
                if generated > second or second - generated > self.config.prediction_max_age:
                    raise ValueError("stale_or_future_prediction")
                if horizon != 60:
                    raise ValueError("unsupported_prediction_horizon")
                label = item["congestion_level"]
                if not isinstance(label, str) or label not in ("LOW", "MEDIUM", "HIGH"):
                    raise ValueError("invalid_congestion_label")
                raw_wait = item["future_wait_seconds"]
                if type(raw_wait) in (int, float) and raw_wait < 0:
                    raise ValueError("negative_future_wait_seconds")
                wait = finite(raw_wait, "future_wait_seconds", 0, 3600)
                version = item["model_version"]
                if not isinstance(version, str) or not version or len(version) > 128:
                    raise ValueError("missing_or_invalid_model_version")
                versions.add(version)
                evidence.append(PredictionEvidence(approach, generated, label, wait))
                additions[approach] = ("LOW", "MEDIUM", "HIGH").index(label) + min(wait, 120) / 120
            if len(versions) != 1:
                raise ValueError("mixed_model_versions")
            for axis, approaches in AXES.items():
                pressures[axis] += self.config.ml_weight * sum(additions[a] for a in approaches) / 2
            return pressures, "valid_bounded_ml_supplement", versions.pop(), tuple(evidence)
        except (ValueError, TypeError, KeyError) as exc:
            # Invalid model output cannot create a phase command or substitute made-up estimates.
            return pressures, f"fallback_queue_only: {exc}", None, ()
