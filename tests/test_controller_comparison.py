"""New virtual rollouts only; no saved held-out source observations are accessed."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from simulation.compare_controllers import audit, demand, rollout, run
from simulation.controllers import APPROACHES, FixedTimeController, MLAdaptiveController, Phase, RuleOnlyAdaptiveController


class SyntheticBundle:
    version = 'unit-estimator-not-a-trained-model'

    def __init__(self, wait=10):
        self.wait = wait
        self.timestamps = []

    def predict(self, task, observations):
        self.timestamps.append((task,observations[0].timestamp_seconds))
        assert [row.approach_id for row in observations] == list(APPROACHES)
        assert all(row.run_id == 'controller-demo-57' for row in observations)
        return ['HIGH']*4 if task=='classification' else [self.wait]*4


@pytest.mark.parametrize('index',range(5))
def test_paired_demand_is_seeded_independent_and_new(index):
    a,noise=demand(index,150)
    b,other=demand(index,150)
    np.testing.assert_array_equal(a,b)
    np.testing.assert_array_equal(noise,other)
    assert not a[0].any()
    assert (a>=0).all()
    assert not np.array_equal(a,demand((index+1)%5,150)[0])


@pytest.mark.parametrize('kind',[FixedTimeController,RuleOnlyAdaptiveController,MLAdaptiveController])
@pytest.mark.parametrize('scenario,index',[('low',0),('medium',1),('high',2),('asymmetric_rush_hour',3),('incident',4)])
def test_conservation_safety_and_metrics(kind,scenario,index):
    arrivals,noise=demand(index,150)
    controller=kind()
    row,failures=rollout(controller,arrivals,noise,scenario,SyntheticBundle())
    assert row['throughput_vehicles']+row['ending_queue_vehicles']==row['arrivals']==arrivals.sum()
    assert row['constraint_violations']==0
    assert row['maximum_red_seconds']<=controller.config.max_red_wait
    assert row['mean_queue_vehicles']>=0 and row['restricted_mean_wait_seconds']>=0
    assert not failures
    assert len(controller.action_log)==150


def test_negative_ml_output_is_not_clipped_or_used_as_safe_estimate():
    arrivals,noise=demand(0,150)
    bundle=SyntheticBundle(wait=-1)
    ml,rule=MLAdaptiveController(),RuleOnlyAdaptiveController()
    a,_=rollout(ml,arrivals,noise,'low',bundle)
    b,_=rollout(rule,arrivals,noise,'low')
    assert a['ml_fallback_steps']==150
    assert a['throughput_vehicles']==b['throughput_vehicles']
    assert a['restricted_mean_wait_seconds']==b['restricted_mean_wait_seconds']
    assert bundle.timestamps==[(task,t) for t in range(0,150,10) for task in ['classification','regression']]
    assert all('future_wait_seconds' in row.prediction_status for row in ml.action_log)


def test_zero_demand_metrics_do_not_invent_waits():
    row,_=rollout(FixedTimeController(),np.zeros((120,4),dtype=int),np.zeros((120,4)),'low')
    assert row['arrivals']==row['throughput_vehicles']==row['mean_queue_vehicles']==0
    assert row['completed_vehicle_mean_wait_seconds'] is row['restricted_mean_wait_seconds'] is None


def test_independent_auditor_detects_conflicting_and_illegal_trace():
    controller=FixedTimeController()
    states=[controller.step(t,dict.fromkeys(APPROACHES,0)) for t in range(100)]
    assert audit(states,controller.config)[0]==[]
    wrong=list(states)
    wrong[1]=replace(wrong[1],phase=Phase.EW_GREEN,vehicle_greens=('east','west'),seconds_in_phase=0,pedestrian_axis='ew')
    assert 'illegal_phase_transition' in audit(wrong,controller.config)[0]
    wrong=list(states)
    wrong[1]=replace(wrong[1],vehicle_greens=('north','east'))
    issues=audit(wrong,controller.config)[0]
    assert 'conflicting_or_unknown_green' in issues and 'phase_movement_mismatch' in issues
    wrong=list(states)
    wrong[-1]=replace(wrong[-1],seconds_in_phase=10000)
    assert 'phase_overrun' in audit(wrong,controller.config)[0]


def test_missing_models_run_reproducibly_without_any_offline_data_access(tmp_path,monkeypatch,capsys):
    original=Path.open
    def guard(self,*args,**kwargs):
        if self.name in ('train.csv','validation.csv','test.csv','test_predictions.csv','test_snapshot.csv'):
            raise AssertionError('offline data opened')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guard)
    first=run(tmp_path/'first',120,tmp_path/'no-models')
    second=run(tmp_path/'second',120,tmp_path/'no-models')
    assert first==second
    assert len(first['comparison'])==15
    assert all(not row['available'] for row in first['model_info']['tasks'].values())
    assert all(row['constraint_violations']==0 for row in first['comparison'])
    for path in (tmp_path/'first').iterdir():
        assert path.read_bytes()==(tmp_path/'second'/path.name).read_bytes()
