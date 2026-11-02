"""Single-user, single-worker local simulation API; bounded, atomic mutations."""
import copy
from dataclasses import asdict
import sys
from threading import Lock, RLock
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, model_validator

from app.models import ROOT, Unavailable
from app.schemas import StrictRecord

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from simulation.demo import CONTROLLERS, SCENARIOS, DemoConfig, DemoSession, make_trace
from simulation.benchmark import BenchmarkConfig, METRICS, simulate, uncertainty

Scenario = Literal["low", "medium", "high", "asymmetric_rush_hour", "incident"]
Fallback = Literal["error", "rule_only"]


class ResetRequest(StrictRecord):
    scenario: Scenario = "medium"
    controller: Literal["fixed_time", "rule_only", "ml_assisted"] = "fixed_time"
    seed: int = Field(default=57, ge=57, le=57)
    replicate: int = Field(default=0, ge=0, le=99)
    duration_seconds: int = Field(default=600, ge=60, le=1800)
    model_fallback: Fallback = "error"


class StepRequest(StrictRecord):
    generation: int = Field(ge=1)
    expected_tick: int = Field(ge=0, le=1800)
    steps: int = Field(default=1, ge=1, le=100)


class BenchmarkRequest(StrictRecord):
    scenarios: list[Scenario] = Field(default_factory=lambda: list(SCENARIOS), min_length=1, max_length=5)
    seed: int = Field(default=57, ge=57, le=57)
    runs_per_scenario: int = Field(default=2, ge=2, le=3)
    warmup_seconds: int = Field(default=30, ge=1, le=120)
    measurement_seconds: int = Field(default=120, ge=1, le=300)
    model_fallback: Fallback = "error"

    @model_validator(mode="after")
    def bounded_work(self):
        if len(set(self.scenarios)) != len(self.scenarios):
            raise ValueError("duplicate scenarios are forbidden")
        if self.total_ticks > 6000:
            raise ValueError("benchmark budget exceeds 6000 controller-ticks; reduce scenarios, runs or duration")
        return self

    @property
    def total_ticks(self):
        return len(self.scenarios) * self.runs_per_scenario * 3 * (self.warmup_seconds + self.measurement_seconds)


def conflict(code, message):
    raise HTTPException(status_code=409, detail=dict(code=code, reason=message))


class SimulationService:
    def __init__(self, bundle):
        self.bundle = bundle
        self.lock = RLock()
        self.benchmark_lock = Lock()
        self.session = None
        self.generation = 0
        self.last_benchmark = None

    def state(self):
        with self.lock:
            if self.session is None:
                conflict("simulation_not_initialized", "POST /simulation/reset first")
            return dict(generation=self.generation,
                        loaded_model_version=self.bundle.version,
                        model_availability={task: state['available'] for task, state in self.bundle.describe()['tasks'].items()},
                        **self.session.serialize())

    def reset(self, body):
        with self.lock:
            if body.controller == "ml_assisted" and body.model_fallback == "error":
                self.bundle.require(["classification", "regression"])
            candidate = DemoSession(DemoConfig(body.scenario, body.controller, body.duration_seconds,
                                              body.replicate, body.model_fallback), self.bundle)
            self.session = candidate
            self.generation += 1
            return self.state()

    def step(self, body):
        with self.lock:
            if self.session is None:
                conflict("simulation_not_initialized", "POST /simulation/reset first")
            if body.generation != self.generation:
                conflict("generation_mismatch", "The demo was reset; fetch /simulation/state")
            current = self.session.snapshot.timestamp_seconds
            if body.expected_tick != current:
                conflict("tick_mismatch", "Stale/retried step; fetch /simulation/state")
            if current + body.steps > self.session.config.duration_seconds:
                conflict("step_exceeds_duration", "Requested steps exceed the remaining demo duration")
            candidate = self.session.clone()
            before = len(candidate.controller.action_log)
            for second in range(current + 1, current + body.steps + 1):
                candidate.tick(second, self.bundle)
            self.session = candidate
            return dict(executed_steps=body.steps, state=self.state(),
                        actions=[asdict(a) for a in candidate.controller.action_log[before:]])

    def benchmark(self, body):
        if not self.benchmark_lock.acquire(blocking=False):
            conflict("benchmark_busy", "One benchmark is already running in this process")
        try:
            if body.model_fallback == "error":
                self.bundle.require(["classification", "regression"])
            config = BenchmarkConfig(body.warmup_seconds, body.measurement_seconds,
                                     body.runs_per_scenario, 500)
            traces = [(scenario, replicate, *make_trace(scenario, config.total_seconds, replicate,
                      config.warmup_seconds)) for scenario in body.scenarios for replicate in range(body.runs_per_scenario)]
            rows = []
            for scenario, replicate, arrays, run_seed, trace_hash in traces:
                for name, kind in CONTROLLERS.items():
                    controller = kind()
                    metrics, *_ = simulate(controller, arrays, config, self.bundle)
                    fallback_steps = sum(action.prediction_status.startswith('fallback') for action in controller.action_log)
                    if name == "ml_assisted" and body.model_fallback == "error" and fallback_steps:
                        raise Unavailable("benchmark rejected ML estimates; explicitly choose model_fallback=rule_only")
                    rows.append(dict(scenario=scenario, replicate=replicate, run_seed=str(run_seed),
                                     controller=name, trace_sha256=trace_hash,
                                     effective_controller=('rule_only' if fallback_steps == config.total_seconds else
                                         'ml_assisted_with_rule_fallback') if name == 'ml_assisted' and fallback_steps else name,
                                     fallback_steps_including_warmup=fallback_steps, **metrics))
            summaries, deltas = [], []
            for scenario in body.scenarios:
                baseline = {r["replicate"]: r for r in rows if r["scenario"] == scenario and r["controller"] == "fixed_time"}
                for ci, name in enumerate(CONTROLLERS):
                    group = [r for r in rows if r["scenario"] == scenario and r["controller"] == name]
                    for mi, metric in enumerate(METRICS):
                        summaries.append(dict(scenario=scenario, controller=name, metric=metric,
                            **uncertainty([r[metric] for r in group], 500, [SCENARIOS.index(scenario), ci, mi])))
                    if name != "fixed_time":
                        for row in group:
                            base = baseline[row["replicate"]]
                            assert row["trace_sha256"] == base["trace_sha256"]
                            deltas.append(dict(scenario=scenario, replicate=row["replicate"], controller=name,
                                **{key + "_delta": row[key] - base[key] if row[key] is not None and base[key] is not None else None for key in METRICS}))
            result = dict(schema_version="simulation-benchmark-v1", virtual_only=True, seed=57,
                engine="paired-virtual-benchmark-v1", state_scope="single-user-per-process",
                config=body.model_dump(), total_controller_ticks=body.total_ticks,
                models=copy.deepcopy(self.bundle.describe()), run_metrics=rows, uncertainty=summaries,
                paired_differences=deltas, constraint_violations=sum(r["constraint_violations"] for r in rows),
                limitations="right-censored waits; run-level bootstrap; simplified point queues; no superiority claim",
                fallback_used=any(r["fallback_steps_including_warmup"] for r in rows), active_demo_unchanged=True)
            with self.lock:
                self.last_benchmark = copy.deepcopy(result)
            return result
        finally:
            self.benchmark_lock.release()


router = APIRouter(prefix="/simulation", tags=["virtual simulation"])


@router.get('/config')
def configuration():
    return dict(seed=57,scenarios=list(SCENARIOS),controllers=list(CONTROLLERS),
                default_scenario='medium',default_controller='fixed_time',
                duration_seconds=600,steps_per_request=100,state_scope='single-user-per-process',
                syllabus_status='UNVERIFIED',virtual_only=True)


def service(request):
    instance = getattr(request.app.state, "simulation", None)
    if instance is None:
        raise HTTPException(status_code=503, detail=dict(code="simulation_unavailable", reason="application startup incomplete"))
    return instance


@router.post("/reset")
def reset(body: ResetRequest, request: Request):
    return service(request).reset(body)


@router.post("/step")
def step(body: StepRequest, request: Request):
    return service(request).step(body)


@router.get("/state")
def state(request: Request):
    return service(request).state()


@router.post("/benchmark")
def benchmark(body: BenchmarkRequest, request: Request):
    return service(request).benchmark(body)


@router.get("/benchmark")
def benchmark_result(request: Request):
    instance = service(request)
    with instance.lock:
        if instance.last_benchmark is None:
            conflict("benchmark_not_run", "POST /simulation/benchmark first")
        return copy.deepcopy(instance.last_benchmark)
