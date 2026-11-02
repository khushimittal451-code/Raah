"""Paired multi-seed virtual benchmark. Never trains or reads ML evaluation data."""
from __future__ import annotations

import argparse
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import csv
import gzip
import hashlib
import io
from importlib.metadata import version as package_version
import json
from pathlib import Path
import platform
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml-service"))
from app.models import ModelBundle, Unavailable  # noqa: E402
from simulation.compare_controllers import audit, forecast  # noqa: E402
from simulation.controllers import (  # noqa: E402
    APPROACHES, AXES, FixedTimeController, MLAdaptiveController,
    RuleOnlyAdaptiveController, TimingConfig, integer,
)

VERSION = "paired-virtual-benchmark-v1"
SCENARIOS = ("low", "medium", "high", "asymmetric_rush_hour", "incident")
POLICIES = (FixedTimeController, RuleOnlyAdaptiveController, MLAdaptiveController)
NAMES = tuple(kind.__name__ for kind in POLICIES)
METRICS = (
    "mean_wait_seconds", "p95_wait_seconds", "max_wait_seconds",
    "completed_mean_wait_seconds", "completed_p95_wait_seconds",
    "mean_total_queue_vehicles", "p95_total_queue_vehicles", "max_total_queue_vehicles",
    "throughput_vehicles", "throughput_vehicles_per_hour", "completion_fraction", "censored_fraction",
    "fairness_jain_service_fraction", "min_approach_service_fraction", "approach_mean_wait_gap_seconds",
    "max_red_seconds", "phase_changes", "ml_fallback_fraction", "constraint_violations",
)


@dataclass(frozen=True)
class BenchmarkConfig:
    warmup_seconds: int = 180
    measurement_seconds: int = 600
    runs_per_scenario: int = 5
    bootstrap_resamples: int = 2000
    master_seed: int = 57

    def __post_init__(self):
        integer(self.warmup_seconds, "warmup_seconds", 1, 1000)
        integer(self.measurement_seconds, "measurement_seconds", 1, 2000)
        integer(self.runs_per_scenario, "runs_per_scenario", 2, 100)
        integer(self.bootstrap_resamples, "bootstrap_resamples", 100, 100000)
        if self.master_seed != 57 or type(self.master_seed) is not int:
            raise ValueError("master seed must be exactly 57")

    @property
    def total_seconds(self):
        return self.warmup_seconds + self.measurement_seconds


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def save_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


@contextmanager
def compressed_text(path):
    # An empty embedded filename and fixed mtime prevent path/time-dependent gzip bytes.
    with Path(path).open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
                yield text


def generate_traces(output, config):
    """Persist ALL exogenous traces before any policy rollout or model inference."""
    folder = Path(output) / "traces"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = []
    for scenario_index, scenario in enumerate(SCENARIOS):
        for replicate in range(config.runs_per_scenario):
            seed = np.random.SeedSequence([57, scenario_index, replicate])
            run_seed = int(seed.generate_state(1, dtype=np.uint64)[0])
            cfg_rng, arrival_rng, gps_rng = (np.random.default_rng(s) for s in seed.spawn(3))
            total = config.total_seconds
            base = {"low": .04, "medium": .20, "high": .48,
                    "asymmetric_rush_hour": .08, "incident": .24}[scenario]
            rates = np.full((total, 4), base) * cfg_rng.uniform(.85, 1.15, 4)
            if scenario == "asymmetric_rush_hour":
                fraction = (np.arange(total) - config.warmup_seconds) / config.measurement_seconds
                pulse = .48 * np.exp(-.5 * ((fraction - .5) / .18) ** 2)
                pulse[:config.warmup_seconds] = 0
                rates[:, :2] += pulse[:, None]
            arrivals = arrival_rng.poisson(rates)
            arrivals[0] = 0
            noise = gps_rng.normal(0, .12, (total, 4))
            capacity = np.full((total, 4), .65)
            if scenario == "incident":
                start = config.warmup_seconds + int(.35 * config.measurement_seconds)
                end = config.warmup_seconds + int(.70 * config.measurement_seconds)
                capacity[start:end, 0] *= .20
            trace_id = f"{scenario}-r{replicate + 1:02d}"
            path = folder / (trace_id + ".csv")
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(["second"] + [f"{a}_{kind}" for kind in ("arrivals", "noise", "capacity") for a in APPROACHES])
                for second in range(total):
                    writer.writerow([second, *map(int, arrivals[second]),
                                     *(format(float(x), ".17g") for x in noise[second]),
                                     *(format(float(x), ".17g") for x in capacity[second])])
            manifest.append(dict(trace_id=trace_id, scenario=scenario, replicate=replicate,
                run_seed=run_seed, file="traces/" + path.name, sha256=digest(path), seconds=total))
    save_json(Path(output) / "trace_manifest.json", {"config": asdict(config), "traces": manifest})
    return manifest


def load_trace(output, metadata):
    path = Path(output) / metadata["file"]
    if digest(path) != metadata["sha256"]:
        raise ValueError("arrival trace hash mismatch")
    expected = ["second"] + [f"{a}_{kind}" for kind in ("arrivals", "noise", "capacity") for a in APPROACHES]
    with path.open(encoding='utf-8',newline='') as handle:
        reader=csv.reader(handle)
        if next(reader,None)!=expected:
            raise ValueError('invalid trace columns')
        records=list(reader)
    if len(records)!=metadata['seconds'] or any(len(row)!=13 or int(row[0])!=t for t,row in enumerate(records)):
        raise ValueError('invalid trace shape or clock')
    try:
        arrays=[np.array([[int(x) for x in row[1:5]] for row in records],dtype=np.int64),
                np.array([[float(x) for x in row[5:9]] for row in records]),
                np.array([[float(x) for x in row[9:13]] for row in records])]
    except (ValueError,OverflowError) as exc:
        raise ValueError('invalid trace numeric fields') from exc
    arrivals, noise, capacity = arrays
    if not all(np.isfinite(a).all() for a in arrays) or (arrivals < 0).any() or (arrivals != np.floor(arrivals)).any():
        raise ValueError("invalid trace arrivals or nonfinite values")
    if (capacity < 0).any() or (capacity > 1).any():
        raise ValueError("invalid trace capacity")
    arrays[0] = arrivals.astype(np.int64)
    for array in arrays:
        array.setflags(write=False)
    return tuple(arrays)


def distribution(values):
    if not values:
        return {"mean": None, "p95": None, "max": None}
    return {"mean": float(np.mean(values)), "p95": float(np.percentile(values, 95, method="linear")),
            "max": float(max(values))}


def fairness(fractions):
    values = np.asarray([v for v in fractions if v is not None], dtype=float)
    if not len(values) or not np.square(values).sum():
        return None
    return float(values.sum() ** 2 / (len(values) * np.square(values).sum()))


def red_intervals(states, warmup, end):
    starts = {"ns": None, "ew": 0}
    rows = []
    for second, state in enumerate(states):
        for axis in AXES:
            active = state.vehicle_greens == AXES[axis]
            if not active and starts[axis] is None:
                starts[axis] = second
            elif active and starts[axis] is not None:
                rows.append(dict(axis=axis, start=starts[axis], end=second, duration=second-starts[axis],
                                 right_censored=False, measured=second > warmup and starts[axis] < end))
                starts[axis] = None
    for axis, start in starts.items():
        if start is not None:
            rows.append(dict(axis=axis, start=start, end=end, duration=end-start,
                             right_censored=True, measured=end > warmup and start < end))
    return rows


def simulate(controller, arrays, config, bundle=None):
    """FIFO queue-only dynamics; all external arrivals, noise and capacity are replayed."""
    arrivals, noise, capacity = arrays
    if arrivals.shape != (config.total_seconds, 4) or any(a.shape != arrivals.shape for a in arrays):
        raise ValueError("trace shape disagrees with benchmark configuration")
    queues, credits = [deque() for _ in APPROACHES], [0.] * 4
    incoming, outgoing = np.zeros(4, dtype=int), np.zeros(4, dtype=int)
    states, trajectory, vehicle_rows, failures = [], [], [], []
    completed = [[] for _ in APPROACHES]
    measured_departures = np.zeros(4, dtype=int)
    all_departures = np.zeros(4, dtype=int)
    cohort_counts = np.zeros(4, dtype=int)
    cohort_pending, cohort_area = 0, 0
    previous, predictions = None, None
    phase_changes = 0
    for second in range(config.total_seconds):
        measured = second >= config.warmup_seconds
        for i in range(4):
            queues[i].extend([second] * int(arrivals[second, i]))
        if measured:
            cohort_counts += arrivals[second]
            cohort_pending += int(arrivals[second].sum())
        incoming += arrivals[second]
        if isinstance(controller, MLAdaptiveController) and second % 10 == 0:
            try:
                if bundle is None:
                    raise Unavailable("no inference bundle supplied")
                predictions = forecast(bundle, queues, second, previous, incoming, outgoing, noise[second])
            except (Unavailable, ValueError) as exc:
                predictions = None
                failures.append(dict(second=second, reason=str(exc)))
        if second % 10 == 0:
            incoming[:], outgoing[:] = 0, 0
        state = controller.step(second, {a: len(queues[i]) for i, a in enumerate(APPROACHES)}, predictions)
        if measured and previous is not None and state.phase != previous.phase:
            phase_changes += 1
        states.append(state)
        for i, approach in enumerate(APPROACHES):
            if approach in state.vehicle_greens and state.seconds_in_phase >= 2:
                credits[i] += float(capacity[second, i])
                while credits[i] >= 1 and queues[i]:
                    arrival = queues[i].popleft()
                    wait = second - arrival
                    outgoing[i] += 1
                    all_departures[i] += 1
                    credits[i] -= 1
                    if measured:
                        measured_departures[i] += 1
                    if arrival >= config.warmup_seconds:
                        cohort_pending -= 1
                        completed[i].append(wait)
                        vehicle_rows.append(dict(approach=approach, arrival_second=arrival,
                            departure_second=second, observed_wait_seconds=wait, censored=False))
                if not queues[i]:
                    credits[i] = 0.
            else:
                credits[i] = 0.
        counts = [len(q) for q in queues]
        cohort_area += cohort_pending if measured else 0
        trajectory.append(dict(second=second, measured=measured, phase=state.phase.value,
            total_queue_vehicles=sum(counts), oldest_queue_wait_seconds=max(
                [second + 1 - q[0] for q in queues if q] or [0]),
            **{f"{a}_queue": counts[i] for i, a in enumerate(APPROACHES)},
            ml_fallback=controller.action_log[-1].prediction_status.startswith("fallback_queue_only")))
        previous = state
    observed = [list(waits) for waits in completed]
    approach_rows = []
    for i, approach in enumerate(APPROACHES):
        pending = [config.total_seconds - arrival for arrival in queues[i] if arrival >= config.warmup_seconds]
        for arrival in queues[i]:
            if arrival >= config.warmup_seconds:
                vehicle_rows.append(dict(approach=approach, arrival_second=arrival, departure_second=None,
                    observed_wait_seconds=config.total_seconds-arrival, censored=True))
        observed[i].extend(pending)
        stats = distribution(observed[i])
        approach_rows.append(dict(approach=approach, cohort_arrivals=int(cohort_counts[i]),
            cohort_completed=len(completed[i]), cohort_censored=len(pending),
            service_fraction=len(completed[i])/int(cohort_counts[i]) if cohort_counts[i] else None,
            throughput_vehicles=int(measured_departures[i]), ending_queue_vehicles=len(queues[i]),
            mean_wait_seconds=stats["mean"], p95_wait_seconds=stats["p95"], max_wait_seconds=stats["max"]))
    all_observed = [wait for values in observed for wait in values]
    all_completed = [wait for values in completed for wait in values]
    observed_stats, completed_stats = distribution(all_observed), distribution(all_completed)
    measured_trace = trajectory[config.warmup_seconds:]
    queue_values = [row["total_queue_vehicles"] for row in measured_trace]
    reds = red_intervals(states, config.warmup_seconds, config.total_seconds)
    violations, _ = audit(states, controller.config)
    if len(vehicle_rows) != int(cohort_counts.sum()) or sum(all_observed) != cohort_area:
        violations.append("cohort_conservation_or_wait_area")
    # Each deque contains all not-yet-served arrivals; throughput accounting is checked per approach.
    for i in range(4):
        expected_cohort = len(completed[i]) + sum(t >= config.warmup_seconds for t in queues[i])
        if expected_cohort != cohort_counts[i]:
            violations.append("approach_cohort_conservation")
        if all_departures[i] + len(queues[i]) != arrivals[:,i].sum():
            violations.append("full_run_inventory_conservation")
    if violations:
        raise AssertionError(violations)
    count = int(cohort_counts.sum())
    fractions = [row["service_fraction"] for row in approach_rows]
    means = [row["mean_wait_seconds"] for row in approach_rows if row["mean_wait_seconds"] is not None]
    row = dict(cohort_arrivals=count, cohort_completed=len(all_completed),
        cohort_censored=count-len(all_completed),
        completion_fraction=len(all_completed)/count if count else None,
        censored_fraction=1-len(all_completed)/count if count else None,
        mean_wait_seconds=observed_stats["mean"], p95_wait_seconds=observed_stats["p95"],
        max_wait_seconds=observed_stats["max"], completed_mean_wait_seconds=completed_stats["mean"],
        completed_p95_wait_seconds=completed_stats["p95"],
        mean_total_queue_vehicles=float(np.mean(queue_values)),
        p95_total_queue_vehicles=float(np.percentile(queue_values,95,method="linear")),
        max_total_queue_vehicles=max(queue_values), ending_total_queue_vehicles=sum(map(len,queues)),
        throughput_vehicles=int(measured_departures.sum()),
        throughput_vehicles_per_hour=float(measured_departures.sum())*3600/config.measurement_seconds,
        fairness_jain_service_fraction=fairness(fractions),
        min_approach_service_fraction=min((v for v in fractions if v is not None),default=None),
        approach_mean_wait_gap_seconds=max(means)-min(means) if means else None,
        max_red_seconds=max((r["duration"] for r in reds if r["measured"]),default=0),
        phase_changes=phase_changes, constraint_violations=len(violations),
        ml_fallback_fraction=sum(r["ml_fallback"] for r in measured_trace)/config.measurement_seconds,
        prediction_call_failures=len(failures), measured_prediction_call_failures=sum(
            item["second"] >= config.warmup_seconds for item in failures))
    return row, approach_rows, vehicle_rows, trajectory, reds, failures


def uncertainty(values, resamples, seed_key):
    values = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    n = len(values)
    if not n:
        return dict(n=0, mean=None, std=None, minimum=None, maximum=None, ci95_low=None, ci95_high=None)
    result = dict(n=n, mean=float(values.mean()), std=float(values.std(ddof=1)) if n > 1 else None,
                  minimum=float(values.min()), maximum=float(values.max()), ci95_low=None, ci95_high=None)
    if n > 1:
        rng = np.random.default_rng(np.random.SeedSequence([57, 9101, *seed_key]))
        means = values[rng.integers(0,n,(resamples,n))].mean(axis=1)
        result.update(ci95_low=float(np.percentile(means,2.5)), ci95_high=float(np.percentile(means,97.5)))
    return result


def summarize(rows, config):
    keys = [(r["scenario"],r["controller"],r["replicate"]) for r in rows]
    expected = {(s,c,r) for s in SCENARIOS for c in NAMES for r in range(config.runs_per_scenario)}
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError("missing or duplicate paired runs")
    summary, paired = [], []
    for si, scenario in enumerate(SCENARIOS):
        group = [r for r in rows if r["scenario"] == scenario]
        baseline = {r["replicate"]: r for r in group if r["controller"] == NAMES[0]}
        for ci, controller in enumerate(NAMES):
            selected = sorted((r for r in group if r["controller"] == controller),key=lambda r:r["replicate"])
            for mi, metric in enumerate(METRICS):
                summary.append(dict(scenario=scenario,controller=controller,metric=metric,
                    **uncertainty([r[metric] for r in selected],config.bootstrap_resamples,[si,ci,mi])))
            if ci:
                for row in selected:
                    base = baseline[row["replicate"]]
                    if row["trace_sha256"] != base["trace_sha256"]:
                        raise AssertionError("unpaired arrival traces")
                    deltas = {metric+"_delta": row[metric]-base[metric] if row[metric] is not None and base[metric] is not None else None for metric in METRICS}
                    paired.append(dict(scenario=scenario,controller=controller,replicate=row["replicate"],
                        trace_id=row["trace_id"],trace_sha256=row["trace_sha256"],**deltas,
                        adverse_mean_wait=deltas["mean_wait_seconds_delta"] is not None and deltas["mean_wait_seconds_delta"]>0,
                        adverse_throughput=deltas["throughput_vehicles_delta"]<0))
    paired_summary = []
    for si, scenario in enumerate(SCENARIOS):
        for ci, controller in enumerate(NAMES[1:]):
            group = [r for r in paired if r["scenario"] == scenario and r["controller"] == controller]
            for mi, metric in enumerate(METRICS):
                values = [r[metric+"_delta"] for r in group]
                paired_summary.append(dict(scenario=scenario,controller=controller,metric=metric,
                    adverse_wait_runs=sum(r["adverse_mean_wait"] for r in group),
                    adverse_throughput_runs=sum(r["adverse_throughput"] for r in group),
                    **uncertainty(values,config.bootstrap_resamples,[si,ci+10,mi])))
    return summary, paired, paired_summary


def plot_results(output, summary, paired_summary, paired):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    plt.rcParams.update({"font.family":"DejaVu Sans", "font.size":9})
    folder = Path(output)/"plots"
    folder.mkdir(exist_ok=True)
    labels = ["Low", "Medium", "High", "Rush", "Incident"]
    policy_labels = ["Fixed", "Rule-only", "ML-assisted"]
    colors = ["#64748b", "#d69521", "#087f8c"]
    def bars(ax, records, metric, policies, title, ylabel):
        x = np.arange(5)
        width = .75/len(policies)
        for i,controller in enumerate(policies):
            series = [next(row for row in records if row['scenario']==s and row['controller']==controller and row['metric']==metric) for s in SCENARIOS]
            means = np.array([r['mean'] if r['mean'] is not None else np.nan for r in series])
            lower = np.array([r['ci95_low'] if r['ci95_low'] is not None else np.nan for r in series])
            upper = np.array([r['ci95_high'] if r['ci95_high'] is not None else np.nan for r in series])
            index=NAMES.index(controller)
            ax.bar(x+(i-(len(policies)-1)/2)*width, means, width,
                   yerr=np.vstack([np.maximum(0,means-lower),np.maximum(0,upper-means)]),
                   capsize=3,color=colors[index],label=policy_labels[index])
        ax.set_xticks(x,labels)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis='y',alpha=.2)
        ax.set_axisbelow(True)
        ax.yaxis.set_major_locator(MaxNLocator(6))
    fig,axes=plt.subplots(2,3,figsize=(15,8),layout='constrained')
    for ax,(metric,title,ylabel) in zip(axes.flat,[
        ('mean_wait_seconds','Mean observed cohort wait','seconds; right-censored'),
        ('p95_wait_seconds','p95 observed cohort wait','seconds; right-censored'),
        ('max_wait_seconds','Maximum observed cohort wait','seconds; right-censored'),
        ('mean_total_queue_vehicles','Mean total queue','vehicles'),
        ('throughput_vehicles','Measurement-window throughput','departed vehicles'),
        ('phase_changes','Measurement-window phase changes','all phase transitions')]):
        bars(ax,summary,metric,NAMES,title,ylabel)
    axes[0,0].legend(loc='upper left',fontsize=8)
    fig.suptitle('Paired synthetic benchmark: run means and 95% bootstrap intervals',fontsize=14)
    fig.savefig(folder/'comparisons.png',dpi=140)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,4.5),layout='constrained')
    for ax,metric,title,ylabel in [
        (axes[0],'mean_wait_seconds','Paired wait difference from fixed','seconds; positive is worse'),
        (axes[1],'throughput_vehicles','Paired throughput difference from fixed','vehicles; negative is worse')]:
        bars(ax,paired_summary,metric,NAMES[1:],title,ylabel)
        ax.axhline(0,color='black',linewidth=.8)
    axes[0].legend(fontsize=8)
    fig.suptitle('Paired differences: resample independent trace groups, not vehicles',fontsize=12)
    fig.savefig(folder/'paired_differences.png',dpi=140)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,4.5),layout='constrained')
    bars(axes[0],summary,'censored_fraction',NAMES,'Unfinished measurement-cohort vehicles','fraction at horizon')
    bars(axes[1],summary,'fairness_jain_service_fraction',NAMES,'Jain index of approach service fractions','1 = equal fractions; not a delay guarantee')
    axes[0].legend(fontsize=8)
    axes[1].set_ylim(0,1.05)
    fig.suptitle('Censoring and fairness: read alongside queue delays and red-time limits',fontsize=12)
    fig.savefig(folder/'censoring_fairness.png',dpi=140)
    plt.close(fig)
    worst=max((r for r in paired if r['mean_wait_seconds_delta'] is not None),
              key=lambda r:r['mean_wait_seconds_delta'],default=None)
    if worst:
        series=pd.read_csv(Path(output)/'trajectories.csv')
        series=series[series.trace_id.eq(worst['trace_id'])]
        fig,axes=plt.subplots(2,1,figsize=(12,7),layout='constrained',sharex=True)
        warmup=int(series.loc[series.measured.eq(True),'second'].min())
        for i,controller in enumerate(NAMES):
            part=series[series.controller.eq(controller)]
            axes[0].plot(part.second,part.total_queue_vehicles,label=policy_labels[i],color=colors[i])
            axes[1].plot(part.second,part.oldest_queue_wait_seconds,label=policy_labels[i],color=colors[i])
        for ax in axes:
            ax.axvspan(0,warmup,color='#cccccc',alpha=.25,label='Warm-up')
            ax.axvline(warmup,color='black',linestyle='--',linewidth=.8)
            ax.grid(alpha=.2)
        axes[0].set_ylabel('total queued vehicles')
        axes[1].set_ylabel('oldest remaining wait (s)')
        axes[1].set_xlabel('simulation second; queue/oldest sampled after discharge')
        axes[0].legend(ncol=4,fontsize=8)
        fig.suptitle(f"Largest paired mean-wait difference: {worst['trace_id']} / "
                     f"{policy_labels[NAMES.index(worst['controller'])]} ({worst['mean_wait_seconds_delta']:+.2f}s)",fontsize=12)
        fig.savefig(folder/'adverse_case.png',dpi=140)
        plt.close(fig)


def write_findings(path, output, config, rows, summary, paired, paired_summary, bundle_info):
    def metric(scenario,controller,name):
        return next(r for r in summary if r['scenario']==scenario and r['controller']==controller and r['metric']==name)
    lines=["# Paired virtual benchmark findings", "", "Status: executed. All models remain PROVISIONAL / UNVERIFIED.", "",
        f"Master seed 57; {config.runs_per_scenario} independent derived run seeds per scenario, five scenarios, "
        f"{len(rows)} policy rollouts. Every run has {config.warmup_seconds}s warm-up and "
        f"{config.measurement_seconds}s measurement. Queues, phase state and fairness clocks continue through warm-up.", "",
        "All arrival counts, capacity and synthetic aggregate-speed noise were generated and saved before any "
        "policy was run. Every policy replays the same hash-verified, read-only arrays for a trace. "
        "These are new FIFO point queues, not live GPS or held-out ML observations. No retraining, "
        "parameter tuning, physical control, RL, deep learning or paid APIs were used.", "",
        "## Metrics and uncertainty", "",
        "Primary mean/p95/max waits use vehicles arriving during measurement. Completed vehicles contribute "
        "their complete queue delay; unfinished vehicles contribute only waiting accumulated to the horizon "
        "and are explicitly right-censored. These are observed finite-horizon waits, not estimates of eventual "
        "completed delay. Completed-only mean/p95 are saved separately and have selection bias. "
        "The cohort wait sum equals the integral of that cohort's queue exactly (asserted). "
        "Mean/p95/max queues include warm-up backlog. Throughput counts all departures within measurement, "
        "including vehicles that arrived during warm-up; cohort completions are also saved separately.", "",
        "Fairness includes maximum continuous axis red (yellow/all-red included), Jain's index of per-approach "
        "cohort completion fractions, minimum completion fraction and the approach mean-wait gap. Empty-demand "
        "approaches are omitted from Jain's index; no service or no demand produces an undefined index, never "
        "a fabricated perfect score. Red intervals overlapping measurement retain pre-warm-up ages; terminal "
        "red intervals are flagged as censored. Phase changes count every enum transition in measurement.", "",
        f"Each scenario/policy metric has run mean, sample standard deviation, min/max and a 95% percentile "
        f"bootstrap interval ({config.bootstrap_resamples} resamples, seed 57). The resampling unit is an "
        "independent trace/run, not correlated vehicles or time rows. Paired deltas subtract the same-trace "
        f"fixed baseline before resampling. Runs receive equal weight. {config.runs_per_scenario} runs per scenario is a small "
        "exploratory sample: intervals do not establish general superiority, and no multiple-comparison "
        "correction or real-world validity is claimed.", "",
        "## Results", "", "Entries below are means across independent runs. Complete uncertainty is in summary.csv and paired_summary.csv.", "",
        "| Scenario | Policy | Mean wait (s) | p95 wait (s) | Mean queue | Throughput | Censored fraction | Max red (s, worst run) |",
        "|---|---|---:|---:|---:|---:|---:|---:|"]
    for s in SCENARIOS:
        for c in NAMES:
            vals=[metric(s,c,m)['mean'] for m in ('mean_wait_seconds','p95_wait_seconds','mean_total_queue_vehicles','throughput_vehicles','censored_fraction')]
            rendered=[f'{v:.3f}' if v is not None else 'undefined' for v in vals]
            max_red=metric(s,c,'max_red_seconds')['maximum']
            lines.append('| '+ ' | '.join([s,c,*rendered,f'{max_red:.0f}'])+' |')
    violations=sum(r['constraint_violations'] for r in rows)
    lines += ["", f"Independent trace/inventory audits recorded **{violations} constraint violations**. "
        f"Maximum observed red was {max(r['max_red_seconds'] for r in rows):.0f}s; configured bound is 75s. "
        "This bounds service opportunities, not individual queue delays under overload.", "", "## Paired adverse cases", "",
        "Every paired delta is published; positive wait differences and negative throughput differences "
        "are adverse. The following rows are selected mechanically by descending mean-wait delta "
        "(up to ten), rather than picking favorable seeds. The adverse-case plot uses the largest delta.", "",
        "| Trace | Policy | Mean wait delta (s) | p95 wait delta (s) | Throughput delta |",
        "|---|---|---:|---:|---:|"]
    worst=sorted((r for r in paired if r['mean_wait_seconds_delta'] is not None),
                 key=lambda r:r['mean_wait_seconds_delta'],reverse=True)[:10]
    for r in worst:
        lines.append(f"| {r['trace_id']} | {r['controller']} | {r['mean_wait_seconds_delta']:+.3f} | "
                     f"{r['p95_wait_seconds_delta']:+.3f} | {r['throughput_vehicles_delta']:+.0f} |")
    lines += ["", f"Of {len(paired)} paired adaptive-versus-fixed runs, "
        f"{sum(r['adverse_mean_wait'] for r in paired)} had higher mean observed wait and "
        f"{sum(r['adverse_throughput'] for r in paired)} had lower throughput. "
        "Different metrics can disagree. This benchmark does not manufacture improvements or "
        "assume that ML-assisted control is best.", "", "Scenario-level paired mean-wait differences with 95% bootstrap intervals:", "",
        "| Scenario | Policy | Mean delta (s) | 95% interval (s) | Worse-wait runs |", "|---|---|---:|---|---:|"]
    for r in paired_summary:
        if r['metric']=='mean_wait_seconds':
            point=f"{r['mean']:+.3f}" if r['mean'] is not None else 'undefined'
            interval=f"[{r['ci95_low']:+.3f}, {r['ci95_high']:+.3f}]" if r['ci95_low'] is not None else 'undefined'
            lines.append(f"| {r['scenario']} | {r['controller']} | {point} | "
                         f"{interval} | {r['adverse_wait_runs']}/{config.runs_per_scenario} |")
    ml=[r for r in rows if r['controller']==NAMES[2]]
    lines += ["", "## ML provenance and limitations", "", f"Model availability: "
        f"{json.dumps({k:v['available'] for k,v in bundle_info['tasks'].items()})}. "
        f"Frozen selection version: `{bundle_info['model_version']}`. "
        "Only current inputs are supplied to the existing hash-checked pipelines every 10s. "
        "Predictions are used by constrained rules; no future source data or test scores are consulted.", "",
        f"Mean ML queue-only fallback fraction during measurement: {np.mean([r['ml_fallback_fraction'] for r in ml]):.3f}. "
        f"Forecast-call failures over all warm-up and measured ML steps: {sum(r['prediction_call_failures'] for r in ml)}. "
        "Negative, stale, missing or invalid estimates are logged and rejected rather than clipped or invented. "
        "If models are unavailable, the ML-labelled policy is explicitly queue-only fallback; such a run "
        "does not demonstrate ML-assisted performance.", "",
        "This simulator starts all vehicles at point queues (no travel/spillback), uses 0.65 veh/s nominal "
        "discharge with 2s green startup loss, and multiplies north capacity by 0.20 for the incident's "
        "middle measurement interval. Poisson demand and near-zero stopped aggregate speeds differ from "
        "the training generator. Derived congestion labels, weak class recall, polynomial extrapolation "
        "and model/controller distribution shift limit interpretation. The 180s default warm-up is "
        "predeclared, not evidence of equilibrium: overloaded and incident queues can grow indefinitely. "
        "Pedestrian safety is limited to the documented parallel, no-turns, no-late-entry assumptions. "
        "The fixed baseline is one predeclared 30s schedule, not an optimized timing plan.", "",
        "## Outputs and execution", "", f"Artifacts: `{Path(output).as_posix()}`.", "",
        "- trace_manifest.json and traces/: seeds, capacities, arrivals, noise and SHA-256 provenance.",
        "- run_metrics.csv, approach_metrics.csv, vehicle_waits.csv.gz, red_intervals.csv and trajectories.csv.",
        "- summary.csv, paired_runs.csv, paired_summary.csv and adverse_cases.csv.",
        "- action_logs/*.jsonl.gz: every action and its reason, including warm-up and model evidence.",
        "- plots/: comparisons, paired differences, censoring/fairness and worst paired trajectory.",
        "- run_manifest.json and artifact_hashes.json: config, versions, source/model provenance and reproducibility hashes.", "",
        "```powershell", ".\\ml-service\\.venv\\Scripts\\python.exe simulation/benchmark.py",
        ".\\ml-service\\.venv\\Scripts\\python.exe simulation/benchmark.py --output-dir work/benchmark-repro --findings work/benchmark-repro-findings.md --verify-against artifacts/benchmark",
        "```", "", "No training data, validation data, held-out observations or final evaluation ledger is modified.", ""]
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text('\n'.join(lines),encoding='utf-8')


def run(output=ROOT/'artifacts/benchmark', config=None, model_dir=ROOT/'artifacts/final', findings=None, plots=True):
    config=BenchmarkConfig() if config is None else config
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    existing=output/'trace_manifest.json'
    if existing.exists() and json.loads(existing.read_text(encoding='utf-8'))['config'] != asdict(config):
        raise ValueError('use a fresh output directory for a different benchmark configuration')
    metadata=generate_traces(output,config)
    print(f'PREGENERATED {len(metadata)} traces; all files persisted before rollouts',flush=True)
    bundle=ModelBundle(model_dir)
    bundle.load()
    info=bundle.describe()
    rows,approaches,reds,failures=[],[],[],[]
    logs=output/'action_logs'
    logs.mkdir(exist_ok=True)
    with compressed_text(output/'vehicle_waits.csv.gz') as wait_file, (output/'trajectories.csv').open('w',encoding='utf-8',newline='') as trajectory_file:
        wait_writer=trajectory_writer=None
        for meta in metadata:
            arrays=load_trace(output,meta)
            for kind in POLICIES:
                controller=kind()
                metrics,parts,waits,trajectory,intervals,errors=simulate(controller,arrays,config,bundle)
                identity={k:meta[k] for k in ('trace_id','scenario','replicate','run_seed')}
                identity['controller']=kind.__name__
                rows.append(dict(**identity,trace_sha256=meta['sha256'],**metrics))
                approaches.extend(dict(**identity,**part) for part in parts)
                reds.extend(dict(**identity,**interval) for interval in intervals)
                failures.extend(dict(**identity,**error) for error in errors)
                for item in waits:
                    record=dict(**identity,**item)
                    if wait_writer is None:
                        wait_writer=csv.DictWriter(wait_file,fieldnames=list(record),lineterminator='\n')
                        wait_writer.writeheader()
                    wait_writer.writerow(record)
                for item in trajectory:
                    record=dict(**identity,**item)
                    if trajectory_writer is None:
                        trajectory_writer=csv.DictWriter(trajectory_file,fieldnames=list(record),lineterminator='\n')
                        trajectory_writer.writeheader()
                    trajectory_writer.writerow(record)
                with compressed_text(logs/f"{meta['trace_id']}_{kind.__name__}.jsonl.gz") as handle:
                    for action in controller.action_log:
                        handle.write(json.dumps(asdict(action),sort_keys=True,allow_nan=False)+'\n')
            if digest(output/meta['file']) != meta['sha256']:
                raise AssertionError('input trace changed during rollout')
            print('DONE',meta['trace_id'],'3 paired policies',flush=True)
    summary,paired,paired_summary=summarize(rows,config)
    for filename,items in [('run_metrics.csv',rows),('approach_metrics.csv',approaches),('red_intervals.csv',reds),
                           ('summary.csv',summary),('paired_runs.csv',paired),('paired_summary.csv',paired_summary),
                           ('adverse_cases.csv',[r for r in paired if r['adverse_mean_wait'] or r['adverse_throughput']])]:
        save_csv(output/filename,items)
    save_json(output/'prediction_failures.json',failures)
    sources=['simulation/benchmark.py','simulation/controllers.py','simulation/compare_controllers.py','ml-service/app/models.py']
    manifest=dict(version=VERSION,config=asdict(config),timings=asdict(TimingConfig()),
        scenarios=list(SCENARIOS),policies=list(NAMES),trace_count=len(metadata),rollouts=len(rows),
        model_info=info,syllabus_status='UNVERIFIED',offline_evaluation_data_opened=False,
        uncertainty_unit='independent same-trace run groups',source_hashes={name:digest(ROOT/name) for name in sources},
        versions=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,
                      **{name:package_version(name) for name in ('matplotlib','scikit-learn','joblib')}))
    save_json(output/'run_manifest.json',manifest)
    if plots:
        plot_results(output,summary,paired_summary,paired)
    if findings is not None:
        write_findings(findings,output,config,rows,summary,paired,paired_summary,info)
    files=[p for p in sorted(output.rglob('*')) if p.is_file() and p.name!='artifact_hashes.json']
    hashes={p.relative_to(output).as_posix():digest(p) for p in files}
    save_json(output/'artifact_hashes.json',hashes)
    print('PASS',len(rows),'rollouts;',sum(r['constraint_violations'] for r in rows),'constraint violations;',
          sum(r['adverse_mean_wait'] for r in paired),'adverse wait pairs;',len(hashes),'hashed artifacts',flush=True)
    return rows,summary,paired


def verify_reproducibility(first,second):
    left=json.loads((Path(first)/'artifact_hashes.json').read_text(encoding='utf-8'))
    right=json.loads((Path(second)/'artifact_hashes.json').read_text(encoding='utf-8'))
    for folder,expected in ((Path(first),left),(Path(second),right)):
        for name,sha in expected.items():
            if digest(folder/name)!=sha:
                raise AssertionError('artifact changed since hash manifest: '+name)
    if left!=right:
        differing=[name for name in sorted(set(left)|set(right)) if left.get(name)!=right.get(name)]
        raise AssertionError('reproducibility mismatch: '+str(differing))
    print(f'REPRODUCIBILITY PASS: {len(left)} artifacts byte-identical, including plots, traces and compressed logs',flush=True)
    return len(left)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'artifacts/benchmark')
    parser.add_argument('--findings',type=Path,default=ROOT/'docs/BENCHMARK_FINDINGS.md')
    parser.add_argument('--warmup-seconds',type=int,default=180)
    parser.add_argument('--measurement-seconds',type=int,default=600)
    parser.add_argument('--runs-per-scenario',type=int,default=5)
    parser.add_argument('--bootstrap-resamples',type=int,default=2000)
    parser.add_argument('--verify-against',type=Path)
    args=parser.parse_args()
    config=BenchmarkConfig(args.warmup_seconds,args.measurement_seconds,args.runs_per_scenario,args.bootstrap_resamples)
    run(args.output_dir,config,findings=args.findings)
    if args.verify_against:
        verify_reproducibility(args.verify_against,args.output_dir)
