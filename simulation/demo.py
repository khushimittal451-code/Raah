"""Bounded, deterministic, in-memory VIRTUAL demo physics. No hardware or I/O."""
from collections import deque
import copy
from dataclasses import asdict, dataclass
import hashlib
import json
from types import SimpleNamespace

import numpy as np

from app.models import Unavailable
from app.schemas import congestion_level_for
from simulation.compare_controllers import forecast
from simulation.controllers import (
    APPROACHES, FixedTimeController, MLAdaptiveController, Phase,
    RuleOnlyAdaptiveController,
)

SCENARIOS = ("low", "medium", "high", "asymmetric_rush_hour", "incident")
CONTROLLERS = {"fixed_time": FixedTimeController, "rule_only": RuleOnlyAdaptiveController,
               "ml_assisted": MLAdaptiveController}


def make_trace(scenario, seconds, replicate=0, warmup=0):
    """Same seed tree/exogenous dynamics as benchmark v1, without filesystem exports."""
    sequence = np.random.SeedSequence([57, SCENARIOS.index(scenario), replicate])
    run_seed = int(sequence.generate_state(1, dtype=np.uint64)[0])
    cfg_rng, arrivals_rng, noise_rng = (np.random.default_rng(s) for s in sequence.spawn(3))
    base = {"low": .04, "medium": .20, "high": .48, "asymmetric_rush_hour": .08, "incident": .24}[scenario]
    rates = np.full((seconds, 4), base) * cfg_rng.uniform(.85, 1.15, 4)
    measured = seconds - warmup
    if scenario == "asymmetric_rush_hour":
        fraction = (np.arange(seconds) - warmup) / measured
        pulse = .48 * np.exp(-.5 * ((fraction - .5) / .18) ** 2)
        pulse[:warmup] = 0
        rates[:, :2] += pulse[:, None]
    arrivals = arrivals_rng.poisson(rates).astype(np.int64)
    arrivals[0] = 0
    noise = noise_rng.normal(0, .12, (seconds, 4))
    capacity = np.full((seconds, 4), .65)
    if scenario == "incident":
        capacity[warmup + int(.35 * measured):warmup + int(.70 * measured), 0] *= .20
    arrays = (arrivals, noise, capacity)
    digest = hashlib.sha256(json.dumps(dict(version="demo-trace-v1", scenario=scenario,
        seconds=seconds, replicate=replicate, warmup=warmup, seed=57), sort_keys=True).encode())
    for i, array in enumerate(arrays):
        digest.update(array.astype("<i8" if i == 0 else "<f8").tobytes())
        array.setflags(write=False)
    return arrays, run_seed, digest.hexdigest()


@dataclass(frozen=True)
class DemoConfig:
    scenario: str
    controller: str
    duration_seconds: int
    replicate: int
    model_fallback: str


class DemoSession:
    def __init__(self, config, bundle):
        self.config = config
        self.arrays, self.run_seed, self.trace_sha256 = make_trace(
            config.scenario, config.duration_seconds + 1, config.replicate)
        self.controller = CONTROLLERS[config.controller]()
        self.queues = [deque() for _ in APPROACHES]
        self.credits = [0.] * 4
        self.incoming, self.outgoing = deque(maxlen=10), deque(maxlen=10)
        self.arrivals_total, self.departures_total = 0, 0
        self.snapshot = None
        self.predictions = None
        self.forecast_error = None
        self.forecast_second = None
        self.prediction_display = None
        self.last_interval = None
        self.tick(0, bundle)

    def clone(self):
        # Read-only exogenous arrays are shared; every mutable traffic/controller object is copied.
        return copy.deepcopy(self, {id(array): array for array in self.arrays})

    def tick(self, second, bundle):
        arrivals, noise, capacity = self.arrays
        previous = self.snapshot
        inputs, outputs = list(map(int, arrivals[second])), [0] * 4
        for i in range(4):
            self.queues[i].extend([second] * inputs[i])
        # Events in (t-1,t] use the signal that governed that completed interval.
        for i, approach in enumerate(APPROACHES):
            if previous and approach in previous.vehicle_greens and previous.seconds_in_phase >= 2:
                self.credits[i] += float(capacity[second, i])
                while self.credits[i] >= 1 and self.queues[i]:
                    self.queues[i].popleft()
                    self.credits[i] -= 1
                    outputs[i] += 1
                if not self.queues[i]:
                    self.credits[i] = 0.
            else:
                self.credits[i] = 0.
        self.incoming.append(inputs)
        self.outgoing.append(outputs)
        self.arrivals_total += sum(inputs)
        self.departures_total += sum(outputs)
        incoming = np.sum(self.incoming, axis=0)
        outgoing = np.sum(self.outgoing, axis=0)
        if second % 10 == 0:
            if self.config.controller == 'ml_assisted':
                self.forecast_second = second
            try:
                self.predictions = forecast(bundle, self.queues, second, previous, incoming, outgoing, noise[second])
                self.forecast_error = None
                self.prediction_display = dict(available=True, generated_at_seconds=second,
                    model_version=bundle.version, prediction_horizon_seconds=60,
                    approaches=[dict(approach_id=a, congestion_level=row['congestion_level'],
                        future_wait_seconds=row['future_wait_seconds'],
                        nonphysical_wait=row['future_wait_seconds'] < 0) for a,row in self.predictions.items()])
            except (Unavailable, ValueError) as exc:
                self.predictions = None
                self.forecast_error = str(exc)
                self.prediction_display = dict(available=False, generated_at_seconds=second,
                    model_version=bundle.version, reason=str(exc), approaches=None)
                if self.config.controller == 'ml_assisted' and self.config.model_fallback == "error":
                    raise Unavailable("simulation ML estimates unavailable; explicitly choose model_fallback=rule_only: " + str(exc)) from exc
        state = self.controller.step(second, {a: len(self.queues[i]) for i, a in enumerate(APPROACHES)},
                                     self.predictions if self.config.controller == 'ml_assisted' else None)
        action = self.controller.action_log[-1]
        if action.prediction_status.startswith("fallback") and self.config.model_fallback == "error":
            raise Unavailable("simulation prediction rejected; explicitly choose model_fallback=rule_only: " + action.prediction_status)
        self.snapshot = state
        self.last_interval = dict(from_seconds=max(0, second - 1), to_seconds=second,
            service_phase=previous.phase.value if previous else None, arrivals=inputs, departures=outputs)
        if self.arrivals_total - self.departures_total != sum(map(len, self.queues)):
            raise AssertionError("demo inventory conservation violation")

    def serialize(self):
        state = self.snapshot
        second = state.timestamp_seconds
        action = self.controller.action_log[-1]
        fallback = action.prediction_status.startswith("fallback")
        rows = []
        for i, approach in enumerate(APPROACHES):
            count = len(self.queues[i])
            rows.append(dict(approach_id=approach, vehicle_count=count, queue_length_vehicles=count,
                mean_speed_kmh=float(np.clip(.2 + self.arrays[1][second, i], 0, .9)) if count else None,
                free_flow_speed_kmh=60., gps_sample_count=min(count, 20),
                mean_wait_seconds=sum(second - t for t in self.queues[i]) / count if count else 0.,
                incoming_vehicles=sum(row[i] for row in self.incoming),
                outgoing_vehicles=sum(row[i] for row in self.outgoing)))
            rows[-1]['congestion_level'] = congestion_level_for(SimpleNamespace(**rows[-1])).upper()
            rows[-1].update(self.countdown(approach))
        is_green = state.phase in (Phase.NS_GREEN, Phase.EW_GREEN)
        boundary = state.planned_green_seconds if is_green else (
            self.controller.config.yellow if state.phase in (Phase.NS_YELLOW, Phase.EW_YELLOW) else self.controller.config.all_red)
        return dict(schema_version="simulation-state-v1", engine="demo-interval-end-v1",
            data_mode="synthetic-only", virtual_only=True,
            state_scope="single-user-per-process", seed=57, scenario=self.config.scenario,
            replicate=self.config.replicate, run_seed=str(self.run_seed), trace_sha256=self.trace_sha256,
            requested_controller=self.config.controller,
            effective_controller="rule_only" if fallback else self.config.controller,
            tick=second, duration_seconds=self.config.duration_seconds,
            completed=second == self.config.duration_seconds, approaches=rows,
            current_phase=state.phase.value, vehicle_greens=list(state.vehicle_greens),
            timers=dict(seconds_in_phase=state.seconds_in_phase,
                planned_green_seconds=state.planned_green_seconds if is_green else None,
                seconds_to_planned_boundary=max(0, boundary - state.seconds_in_phase),
                timer_kind="green_plan" if is_green else "mandatory_clearance",
                ns_red_seconds=state.ns_red_seconds, ew_red_seconds=state.ew_red_seconds,
                maximum_red_seconds=self.controller.config.max_red_wait),
            pedestrian=dict(state=state.pedestrian_state, axis=state.pedestrian_axis,
                assumption="parallel crossings, no turns or late WALK entry"),
            timings=asdict(self.controller.config), flow_window_seconds=min(10, second),
            totals=dict(arrivals=self.arrivals_total, departures=self.departures_total,
                        vehicle_count=sum(map(len, self.queues)),
                        mean_speed_kmh=sum(r['mean_speed_kmh']*r['gps_sample_count'] for r in rows if r['mean_speed_kmh'] is not None)/sum(r['gps_sample_count'] for r in rows) if any(r['gps_sample_count'] for r in rows) else None),
            prediction_display=copy.deepcopy(self.prediction_display),
            congestion_source='congestion-v1 rule on current simulated observations',
            ml=dict(fallback_policy=self.config.model_fallback, fallback_active=fallback,
                    status=action.prediction_status,
                    fallback_reason=(self.forecast_error or action.prediction_status) if fallback else None,
                    generated_at_seconds=self.forecast_second,
                    model_version=action.prediction_model_version,
                    predictions=[asdict(item) for item in action.prediction_inputs] or None),
            last_interval=copy.deepcopy(self.last_interval), last_action=asdict(action))

    def countdown(self, approach):
        state, config = self.snapshot, self.controller.config
        axis = 'ns' if approach in ('north','south') else 'ew'
        phase = state.phase.value
        red_age = state.ns_red_seconds if axis=='ns' else state.ew_red_seconds
        if phase == axis+'_green':
            return dict(signal_color='GREEN', countdown_seconds=max(0,state.planned_green_seconds-state.seconds_in_phase),
                        countdown_kind='green_end' if self.config.controller=='fixed_time' else 'green_review', red_wait_seconds=0)
        if phase == axis+'_yellow':
            return dict(signal_color='YELLOW',countdown_seconds=config.yellow-state.seconds_in_phase,
                        countdown_kind='yellow_end',red_wait_seconds=red_age)
        seconds=None
        if self.config.controller=='fixed_time':
            phases=['ns_green','ns_yellow','all_red_to_ew','ew_green','ew_yellow','all_red_to_ns']
            durations=[config.fixed_green,config.yellow,config.all_red]*2
            index=phases.index(phase)
            seconds=durations[index]-state.seconds_in_phase
            index=(index+1)%6
            while phases[index] != axis+'_green':
                seconds+=durations[index];index=(index+1)%6
        elif phase == ('ns_yellow' if axis=='ew' else 'ew_yellow'):
            seconds=config.yellow-state.seconds_in_phase+config.all_red
        elif phase == ('all_red_to_ew' if axis=='ew' else 'all_red_to_ns'):
            seconds=config.all_red-state.seconds_in_phase
        return dict(signal_color='RED',countdown_seconds=seconds,
                    countdown_kind='next_green' if seconds is not None else 'not_scheduled',red_wait_seconds=red_age)
