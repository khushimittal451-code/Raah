"""Safety tests use new synthetic inputs; never open training or held-out records."""
from dataclasses import FrozenInstanceError, asdict, replace
import json
import math
from itertools import product
import random

import pytest

from simulation.controllers import (
    APPROACHES, AXES, NEXT_PHASE, PHASE_SEQUENCE, FixedTimeController,
    MLAdaptiveController, Phase, RuleOnlyAdaptiveController, TimingConfig,
)

CONTROLLERS = (FixedTimeController, RuleOnlyAdaptiveController, MLAdaptiveController)
ZERO = dict.fromkeys(APPROACHES, 0)


def predictions(second, label="HIGH", wait=120):
    return {a: dict(congestion_level=label, future_wait_seconds=wait,
        generated_at_seconds=second, prediction_horizon_seconds=60, model_version="synthetic-unit-57")
        for a in APPROACHES}


def advance(controller, end, queues=None, estimates=None):
    return [controller.step(t, ZERO if queues is None else queues,
                            estimates(t) if estimates else None) for t in range(end + 1)]


def assert_invariants(states, config):
    entries = []
    for i, state in enumerate(states):
        assert state.timestamp_seconds == i
        assert state.phase in PHASE_SEQUENCE
        assert state.seconds_in_phase >= 0
        assert max(state.ns_red_seconds, state.ew_red_seconds) <= config.max_red_wait
        if state.phase == Phase.NS_GREEN:
            assert state.vehicle_greens == AXES["ns"]
            assert state.ns_red_seconds == 0
        elif state.phase == Phase.EW_GREEN:
            assert state.vehicle_greens == AXES["ew"]
            assert state.ew_red_seconds == 0
        else:
            assert not state.vehicle_greens
            assert state.pedestrian_state == "dont_walk" and state.pedestrian_axis is None
        if state.pedestrian_state != "dont_walk":
            axis = "ns" if state.phase == Phase.NS_GREEN else "ew"
            assert state.pedestrian_axis == axis
            assert state.vehicle_greens == AXES[axis]
        if i and state.phase != states[i-1].phase:
            before = states[i-1]
            assert state.phase == NEXT_PHASE[before.phase]
            duration = before.seconds_in_phase + 1
            if before.phase in (Phase.NS_GREEN, Phase.EW_GREEN):
                assert config.green_floor <= duration <= config.max_green
                assert before.pedestrian_state == "dont_walk" or duration == config.green_floor
                # At transition the protected crossing has finished, even at the exact floor.
                assert duration >= config.pedestrian_walk + config.pedestrian_clearance
            elif before.phase in (Phase.NS_YELLOW, Phase.EW_YELLOW):
                assert duration == config.yellow
            else:
                assert duration == config.all_red
            assert state.seconds_in_phase == 0
            entries.append((i,state.phase))
        elif i:
            assert state.seconds_in_phase == states[i-1].seconds_in_phase + 1
    assert len({s.phase for s in states}) == 6
    # Reconstruct full no-green intervals, including the initialization red interval.
    for axis in AXES:
        start = 0 if not states[0].vehicle_greens == AXES[axis] else None
        for state in states[1:]:
            is_green = state.vehicle_greens == AXES[axis]
            if not is_green and start is None:
                start = state.timestamp_seconds
            elif is_green and start is not None:
                assert state.timestamp_seconds - start <= config.max_red_wait
                start = None
        if start is not None:
            assert states[-1].timestamp_seconds - start <= config.max_red_wait


@pytest.mark.parametrize("kind",CONTROLLERS)
@pytest.mark.parametrize("config",[
    TimingConfig(), TimingConfig(max_red_wait=23,fixed_green=15),
    TimingConfig(min_green=4,max_green=12,fixed_green=7,yellow=2,all_red=2,
                 pedestrian_walk=2,pedestrian_clearance=3,max_red_wait=15,extension_step=2),
    TimingConfig(pedestrian_walk=8,pedestrian_clearance=14),
])
@pytest.mark.parametrize("pattern",["empty","ns_heavy","ew_heavy","changing","seeded"])
def test_exhaustive_phase_safety_and_fairness(kind,config,pattern):
    controller=kind(config)
    rng=random.Random(57)
    states=[]
    for second in range(700):
        queues = ({"empty":[0]*4,"ns_heavy":[10000,10000,1,1],
                   "ew_heavy":[1,1,10000,10000],
                   "changing":[100 if ((second//11+i)%2) else 0 for i in range(4)],
                   "seeded":[rng.randrange(10001) for _ in range(4)]})[pattern]
        forecast=predictions(second)
        # ML can oppose observed demand, but cannot override any hard constraint.
        for i,a in enumerate(APPROACHES):
            forecast[a].update(congestion_level="HIGH" if second%2==i%2 else "LOW",
                               future_wait_seconds=3600 if second%3 else 0)
        states.append(controller.step(second,dict(zip(APPROACHES,queues)),forecast))
    assert_invariants(states,config)
    assert len(controller.action_log)==len(states)
    for index,action in enumerate(controller.action_log):
        assert action.timestamp_seconds == index and action.reason and action.virtual_only
        assert action.phase == states[index].phase.value
        if action.action=="EXTEND":
            assert 0 < action.planned_green_seconds - states[index].seconds_in_phase <= config.extension_step
            assert action.planned_green_seconds <= config.max_green


def test_exact_default_fixed_time_boundaries():
    states=advance(FixedTimeController(),75)
    expected={0:Phase.NS_GREEN,29:Phase.NS_GREEN,30:Phase.NS_YELLOW,32:Phase.NS_YELLOW,
              33:Phase.ALL_RED_TO_EW,34:Phase.EW_GREEN,64:Phase.EW_YELLOW,
              67:Phase.ALL_RED_TO_NS,68:Phase.NS_GREEN}
    for second,phase in expected.items():
        assert states[second].phase==phase


@pytest.mark.parametrize("kind",CONTROLLERS)
def test_pedestrian_walk_clearance_and_no_late_entry(kind):
    config=TimingConfig(pedestrian_walk=8,pedestrian_clearance=14)
    states=advance(kind(config),120)
    for state in states:
        if state.vehicle_greens:
            expected="walk" if state.seconds_in_phase<8 else "clearance" if state.seconds_in_phase<22 else "dont_walk"
            assert state.pedestrian_state==expected
    assert states[21].phase==Phase.NS_GREEN
    if kind is not FixedTimeController:
        assert states[22].phase==Phase.NS_YELLOW


def test_rule_extension_and_max_green_are_hard_bounded():
    controller=RuleOnlyAdaptiveController()
    states=advance(controller,100,{"north":10000,"south":10000,"east":1,"west":1})
    assert states[14].phase==Phase.NS_GREEN
    assert controller.action_log[15].action=="EXTEND"
    assert states[59].phase==Phase.NS_GREEN and states[60].phase==Phase.NS_YELLOW
    assert controller.action_log[60].reason=="maximum_green_reached"


@pytest.mark.parametrize("kind",[RuleOnlyAdaptiveController,MLAdaptiveController])
def test_fairness_wins_over_unlimited_active_pressure(kind):
    config=TimingConfig(max_red_wait=23,fixed_green=15)
    controller=kind(config)
    states=advance(controller,100,{"north":10000,"south":10000,"east":0,"west":0},predictions)
    assert states[19].phase==Phase.NS_YELLOW
    assert controller.action_log[19].reason=="maximum_red_fairness_deadline"
    assert states[23].phase==Phase.EW_GREEN


def test_ml_uses_both_class_and_wait_without_overriding_queues():
    q=dict.fromkeys(APPROACHES,1)
    def estimates(second):
        result=predictions(second,"LOW",0)
        for a in AXES['ns']:
            result[a].update(congestion_level="HIGH",future_wait_seconds=120)
        return result
    rule=advance(RuleOnlyAdaptiveController(),15,q)
    ml=MLAdaptiveController()
    states=advance(ml,15,q,estimates)
    assert rule[15].phase==Phase.NS_YELLOW and states[15].phase==Phase.NS_GREEN
    assert ml.action_log[-1].ns_pressure==11 and ml.action_log[-1].ew_pressure==2
    huge_opposing={"north":1,"south":1,"east":1000,"west":1000}
    assert advance(MLAdaptiveController(),15,huge_opposing,estimates)[15].phase==Phase.NS_YELLOW


@pytest.mark.parametrize("field,bad",[
    ("min_green",0),("min_green",True),("min_green",15.0),("min_green",61),
    ("max_green",14),("max_green",math.inf),("max_green",math.nan),
    ("yellow",0),("yellow",-1),("all_red",0),("all_red",1.0),
    ("fixed_green",14),("fixed_green",61),("max_red_wait",22),
    ("max_red_wait",37),("extension_step",0),("extension_step",61),
    ("pedestrian_walk",0),("pedestrian_clearance",100),
    ("prediction_max_age",-1),("prediction_max_age",True),
    ("queue_hysteresis",math.nan),("queue_hysteresis",-1),
    ("ml_weight",math.inf),("ml_weight",-1),("ml_weight",True),("ml_weight",10**1000),
])
def test_invalid_or_infeasible_config_rejected(field,bad):
    with pytest.raises(ValueError):replace(TimingConfig(),**{field:bad})


@pytest.mark.parametrize("kind",CONTROLLERS)
@pytest.mark.parametrize("bad",[None,{},[0]*4,{**ZERO,"extra":0},{**ZERO,"north":-1},
    {**ZERO,"north":10001},{**ZERO,"north":1.0},{**ZERO,"north":True},
    {**ZERO,"north":math.nan},{**ZERO,"north":math.inf}])
def test_bad_demand_rejected_transactionally(kind,bad):
    controller=kind()
    with pytest.raises(ValueError):controller.step(0,bad)
    assert controller.action_log==() and controller.phase==Phase.NS_GREEN
    controller.step(0,ZERO)


@pytest.mark.parametrize("bad",[-1,1,True,0.0,math.nan,math.inf])
def test_invalid_first_clock_rejected(bad):
    with pytest.raises(ValueError):FixedTimeController().step(bad,ZERO)


def test_no_duplicate_backwards_or_skipped_ticks():
    controller=FixedTimeController()
    advance(controller,10)
    for second in [10,9,12,10000]:
        before=controller.action_log
        with pytest.raises(ValueError):controller.step(second,ZERO)
        assert controller.action_log==before
    controller.step(11,ZERO)


@pytest.mark.parametrize("field,bad",[
    ("congestion_level","extreme"),("congestion_level",None),("congestion_level",[]),
    ("future_wait_seconds",-1),("future_wait_seconds",math.nan),("future_wait_seconds",math.inf),
    ("future_wait_seconds",True),("future_wait_seconds","5"),("future_wait_seconds",3601),
    ("future_wait_seconds",10**1000),("future_wait_seconds",-(10**1000)),
    ("generated_at_seconds",-1),("generated_at_seconds",True),("generated_at_seconds",1.0),
    ("generated_at_seconds",1000),("prediction_horizon_seconds",30),
    ("model_version",None),("model_version",""),("model_version",["x"]),
])
def test_malformed_ml_forecasts_fall_back_to_identical_rule_actions(field,bad):
    ml,rule=MLAdaptiveController(),RuleOnlyAdaptiveController()
    for second in range(130):
        p=predictions(second);p['west'][field]=bad
        q=dict(zip(APPROACHES,[100 if (second//9)%2 else 1,20,10,30]))
        assert ml.step(second,q,p)==rule.step(second,q)
        assert ml.action_log[-1].prediction_status.startswith('fallback_queue_only')


@pytest.mark.parametrize("case",['missing','partial','bad_record','extra','mixed_version','stale'])
def test_incomplete_stale_or_mixed_predictions_atomic_fallback(case):
    ml,rule=MLAdaptiveController(),RuleOnlyAdaptiveController()
    for second in range(150):
        p=predictions(second)
        if case=='missing':p=None
        elif case=='partial':del p['west']
        elif case=='bad_record':p['west']=None
        elif case=='extra':p['west']['future_target']=999
        elif case=='mixed_version':p['west']['model_version']='other'
        elif case=='stale':
            for row in p.values():row['generated_at_seconds']=max(0,second-11)
        q=dict.fromkeys(APPROACHES,20)
        assert ml.step(second,q,p)==rule.step(second,q)
        if case!='stale' or second>10:
            assert ml.action_log[-1].prediction_status.startswith('fallback_queue_only')


def test_prediction_age_boundary_and_wait_bonus_cap():
    ml=MLAdaptiveController()
    for second in range(12):ml.step(second,ZERO,predictions(0,wait=3600))
    assert ml.action_log[10].prediction_status=='valid_bounded_ml_supplement'
    assert ml.action_log[10].ns_pressure==9
    assert ml.action_log[11].prediction_status.startswith('fallback_queue_only')


def test_ml_weight_zero_reproduces_rule_policy():
    config=TimingConfig(ml_weight=0)
    ml,rule=MLAdaptiveController(config),RuleOnlyAdaptiveController(config)
    for second in range(300):
        q=dict(zip(APPROACHES,[second%27,2,3,second%12]))
        assert ml.step(second,q,predictions(second))==rule.step(second,q)


@pytest.mark.parametrize("kind",CONTROLLERS)
def test_immutable_public_state_and_complete_reproducible_logs(kind,tmp_path):
    first,second=kind(),kind()
    a=advance(first,150,estimates=predictions)
    b=advance(second,150,estimates=predictions)
    assert a==b and first.action_log==second.action_log
    with pytest.raises(FrozenInstanceError):a[0].phase=Phase.EW_GREEN
    with pytest.raises(FrozenInstanceError):first.config.max_green=1
    with pytest.raises(AttributeError):first.phase=Phase.EW_GREEN
    with pytest.raises(FrozenInstanceError):first.action_log[0].reason='tampered'
    first.write_log(tmp_path/'a.jsonl');second.write_log(tmp_path/'b.jsonl')
    assert (tmp_path/'a.jsonl').read_bytes()==(tmp_path/'b.jsonl').read_bytes()
    rows=[json.loads(line) for line in (tmp_path/'a.jsonl').read_text().splitlines()]
    assert len(rows)==151 and rows[0]['action']=='INITIALIZE'
    assert all(row['reason'] and row['virtual_only'] for row in rows)


def test_controller_rejects_wrong_config_type():
    for bad in (0,{},'config'):
        with pytest.raises(TypeError):FixedTimeController(bad)


def test_exhaustive_small_timing_grid():
    """Enumerate every feasible combination in this explicitly bounded timing grid."""
    count=0
    for kind,minimum,extra,yellow,red,ped_clear,slack,extension in product(
            CONTROLLERS,(2,3,5),(0,2),(1,2),(1,2),(1,4),(0,3),(1,2)):
        floor=max(minimum,1+ped_clear)
        config=TimingConfig(min_green=minimum,max_green=floor+extra,fixed_green=floor,
            yellow=yellow,all_red=red,pedestrian_walk=1,pedestrian_clearance=ped_clear,
            max_red_wait=floor+2*(yellow+red)+slack,extension_step=extension)
        controller=kind(config)
        states=[]
        for second in range(100):
            q=dict(zip(APPROACHES,([10000,10000,0,0] if (second//7)%2 else [0,0,10000,10000])))
            states.append(controller.step(second,q,predictions(second)))
        assert_invariants(states,config)
        count+=1
    assert count==576


def test_ml_log_contains_exact_validated_forecast_evidence():
    controller=MLAdaptiveController()
    controller.step(0,ZERO,predictions(0))
    entry=controller.action_log[0]
    assert len(entry.prediction_inputs)==4
    assert [x.approach for x in entry.prediction_inputs]==list(APPROACHES)
    assert all(x.generated_at_seconds==0 and x.future_wait_seconds==120 for x in entry.prediction_inputs)
    with pytest.raises(FrozenInstanceError):entry.prediction_inputs[0].future_wait_seconds=0
