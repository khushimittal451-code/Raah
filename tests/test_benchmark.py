"""Benchmark accounting, pairing, warm-up, censoring and seed-isolation checks."""
from dataclasses import replace
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import simulation.benchmark as benchmark
from simulation.benchmark import (BenchmarkConfig, NAMES, SCENARIOS, distribution, fairness,
    generate_traces, load_trace, run, simulate, summarize, uncertainty, verify_reproducibility)
from simulation.controllers import FixedTimeController, MLAdaptiveController, RuleOnlyAdaptiveController


def tiny_config(**kwargs):
    return replace(BenchmarkConfig(),warmup_seconds=2,measurement_seconds=4,
                   runs_per_scenario=2,bootstrap_resamples=100,**kwargs)


def arrays(arrivals):
    arrivals=np.asarray(arrivals,dtype=np.int64)
    return arrivals,np.zeros_like(arrivals,dtype=float),np.full_like(arrivals,.65,dtype=float)


def test_exact_warmup_cohort_censoring_and_queue_integral():
    arrivals=np.zeros((6,4),dtype=int)
    arrivals[[1,2,5],0]=1
    controller=FixedTimeController()
    row,parts,waits,trajectory,_,_=simulate(controller,arrays(arrivals),tiny_config())
    assert row['cohort_arrivals']==2 and row['cohort_completed']==row['cohort_censored']==1
    assert row['mean_wait_seconds']==2
    assert row['p95_wait_seconds']==pytest.approx(2.9)
    assert row['max_wait_seconds']==3
    assert row['completed_mean_wait_seconds']==3
    assert row['mean_total_queue_vehicles']==1.25
    assert row['throughput_vehicles']==2  # Includes the warm-up arrival departed during measurement.
    assert row['censored_fraction']==.5
    assert all(r['arrival_second']>=2 for r in waits)
    assert [r['measured'] for r in trajectory]==[False,False,True,True,True,True]
    assert parts[0]['service_fraction']==.5
    assert row['fairness_jain_service_fraction']==1  # One active demand approach, not all approaches.
    assert row['constraint_violations']==0


def test_warmup_does_not_reset_clock_phase_or_queues():
    config=replace(tiny_config(),warmup_seconds=30,measurement_seconds=8)
    arrivals=np.zeros((38,4),dtype=int);arrivals[1,2]=10
    row,_,waits,trajectory,reds,_=simulate(FixedTimeController(),arrays(arrivals),config)
    assert trajectory[30]['phase']=='ns_yellow'
    assert trajectory[30]['east_queue']==10
    assert row['throughput_vehicles']>0
    assert row['mean_wait_seconds'] is None and waits==[]  # No new measurement arrivals.
    assert row['phase_changes']==3
    assert any(r['start']==0 and r['end']==34 and r['measured'] for r in reds)
    assert row['max_red_seconds']==34


@pytest.mark.parametrize('kind',[FixedTimeController,RuleOnlyAdaptiveController,MLAdaptiveController])
def test_empty_trace_never_fabricates_wait_or_fairness(kind):
    row,parts,waits,_,_,_=simulate(kind(),arrays(np.zeros((6,4))),tiny_config())
    assert row['mean_wait_seconds'] is row['p95_wait_seconds'] is row['max_wait_seconds'] is None
    assert row['fairness_jain_service_fraction'] is None
    assert row['completion_fraction'] is row['censored_fraction'] is None
    assert row['mean_total_queue_vehicles']==row['throughput_vehicles']==0
    assert waits==[]


def test_all_censored_is_not_zero_delay_or_perfect_service():
    arrivals=np.zeros((6,4),dtype=int);arrivals[2,2]=2
    row,_,waits,_,_,_=simulate(FixedTimeController(),arrays(arrivals),tiny_config())
    assert row['cohort_completed']==0 and row['cohort_censored']==2
    assert row['mean_wait_seconds']==row['p95_wait_seconds']==row['max_wait_seconds']==4
    assert row['completed_mean_wait_seconds'] is None
    assert row['fairness_jain_service_fraction'] is None
    assert all(w['censored'] for w in waits)


def test_distribution_and_jain_definitions():
    assert distribution([])==dict(mean=None,p95=None,max=None)
    assert distribution([0,10])['p95']==9.5
    assert fairness([None,1,1])==1
    assert fairness([1,0])==.5
    assert fairness([0,0]) is None


@pytest.mark.parametrize('field,value',[('warmup_seconds',0),('warmup_seconds',True),
    ('measurement_seconds',0),('measurement_seconds',2001),('runs_per_scenario',1),
    ('bootstrap_resamples',99),('master_seed',58),('master_seed',57.0)])
def test_invalid_config(field,value):
    with pytest.raises(ValueError):replace(BenchmarkConfig(),**{field:value})


def test_traces_are_pregenerated_distinct_readonly_and_replayable(tmp_path):
    config=replace(tiny_config(),measurement_seconds=50)
    first=generate_traces(tmp_path/'a',config)
    second=generate_traces(tmp_path/'b',config)
    assert first==second and len(first)==10
    assert len({m['run_seed'] for m in first})==10
    for a,b in zip(first,second):
        assert (tmp_path/'a'/a['file']).read_bytes()==(tmp_path/'b'/b['file']).read_bytes()
        trace=load_trace(tmp_path/'a',a)
        assert not any(x.flags.writeable for x in trace)
        with pytest.raises(ValueError):trace[0][0,0]=999
    incident=next(m for m in first if m['scenario']=='incident')
    assert (load_trace(tmp_path/'a',incident)[2][:,0]<.65).any()
    path=tmp_path/'a'/first[0]['file']
    path.write_text(path.read_text()+'\n',encoding='utf-8')
    with pytest.raises(ValueError,match='hash mismatch'):load_trace(tmp_path/'a',first[0])


def test_bootstrap_resamples_runs_and_is_seeded():
    a=uncertainty([1,2,5],500,[1,2])
    assert a==uncertainty([1,2,5],500,[1,2])
    assert a['n']==3 and a['mean']==pytest.approx(8/3)
    assert a['std']==pytest.approx(np.std([1,2,5],ddof=1))
    assert a['ci95_low']<=a['mean']<=a['ci95_high']
    assert uncertainty([None,np.nan],100,[0])['n']==0
    assert uncertainty([1],100,[0])['ci95_low'] is None


def synthetic_run_rows(config):
    rows=[]
    for scenario in SCENARIOS:
        for controller in NAMES:
            for replicate in range(config.runs_per_scenario):
                delta=0 if controller==NAMES[0] else (-2 if replicate==0 else 2)
                rows.append(dict(scenario=scenario,controller=controller,replicate=replicate,
                    trace_id=scenario+str(replicate),trace_sha256=scenario+str(replicate),
                    **{m:10+delta for m in benchmark.METRICS}))
    return rows


def test_paired_differences_and_adverse_counts():
    config=tiny_config()
    rows=synthetic_run_rows(config)
    summary,paired,stats=summarize(rows,config)
    assert len(paired)==20
    assert sum(r['adverse_mean_wait'] for r in paired)==10
    assert all(r['mean']==0 for r in stats)
    assert all(r['n']==2 for r in stats)
    altered=[dict(r) for r in rows];altered[-1]['trace_sha256']='other-arrivals'
    with pytest.raises(AssertionError,match='unpaired'):summarize(altered,config)
    with pytest.raises(ValueError,match='duplicate'):summarize(rows[:-1]+[rows[0]],config)


def test_full_small_run_persists_all_traces_before_policy_and_reproduces(tmp_path,monkeypatch):
    config=replace(tiny_config(),measurement_seconds=40)
    original=benchmark.simulate
    calls=[]
    def wrapper(controller,arrays,conf,bundle):
        manifests=list(tmp_path.glob('*/trace_manifest.json'))
        assert manifests
        for path in manifests:
            metadata=json.loads(path.read_text(encoding='utf-8'))
            assert len(metadata['traces'])==10
            assert all((path.parent/m['file']).exists() for m in metadata['traces'])
        calls.append(type(controller).__name__)
        return original(controller,arrays,conf,bundle)
    monkeypatch.setattr(benchmark,'simulate',wrapper)
    path_open=Path.open
    def deny_offline(self,*args,**kwargs):
        if self.name in {'train.csv','validation.csv','test.csv','test_predictions.csv','test_snapshot.csv'}:
            raise AssertionError('offline evaluation data accessed')
        return path_open(self,*args,**kwargs)
    monkeypatch.setattr(Path,'open',deny_offline)
    first=run(tmp_path/'first',config,tmp_path/'missing-models',plots=False)
    second=run(tmp_path/'second',config,tmp_path/'missing-models',plots=False)
    assert first==second and len(calls)==60
    assert verify_reproducibility(tmp_path/'first',tmp_path/'second')>40
    frame=pd.read_csv(tmp_path/'first/run_metrics.csv')
    assert len(frame)==30
    assert frame.groupby('trace_id').trace_sha256.nunique().eq(1).all()
    assert frame.constraint_violations.eq(0).all()
    ml=frame[frame.controller.eq(NAMES[2])]
    assert ml.ml_fallback_fraction.eq(1).all()
    with gzip.open(next((tmp_path/'first/action_logs').glob('*.gz')),'rt',encoding='utf-8') as handle:
        assert len(handle.readlines())==config.total_seconds
    # Verification checks live contents, not just two stale hash manifests.
    target=tmp_path/'second/run_metrics.csv'
    target.write_text(target.read_text()+'\n',encoding='utf-8')
    with pytest.raises(AssertionError,match='changed since'):verify_reproducibility(tmp_path/'first',tmp_path/'second')
    with pytest.raises(ValueError,match='fresh output'):run(tmp_path/'first',replace(config,measurement_seconds=41),plots=False)
