"""ASGI integration tests: deterministic new demo traffic, no offline evaluation data."""
import asyncio
import copy
from pathlib import Path

import httpx
import numpy as np
import pytest

from app.main import create_app
from app.models import Unavailable
from simulation.controllers import APPROACHES, NEXT_PHASE, Phase
from simulation.demo import make_trace


class SyntheticModels:
    """Explicit test double, never used to report actual model performance."""
    version = 'unit-models-only'

    def __init__(self, fail_at=None, negative_at=None):
        self.fail_at = fail_at
        self.negative_at = negative_at
        self.calls = []

    def require(self, tasks):
        pass

    def describe(self):
        return dict(model_version=self.version, tasks={task: {'available':True} for task in ('classification','regression')})

    def predict(self, task, observations):
        second = observations[0].timestamp_seconds
        self.calls.append((task, second, [row.model_dump() for row in observations]))
        if self.fail_at is not None and second >= self.fail_at:
            raise Unavailable('deliberate inference failure')
        if task == 'classification':
            return ['HIGH']*len(observations)
        return [-1.0 if self.negative_at is not None and second >= self.negative_at else 10.0]*len(observations)


def exercise(tmp_path, workflow, models=None):
    async def perform():
        app=create_app(tmp_path/'missing-models')
        async with app.router.lifespan_context(app):
            if models is not None:
                app.state.bundle=models
                app.state.simulation.bundle=models
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
                return await workflow(client, app)
    return asyncio.run(perform())


async def reset(client, **kwargs):
    response=await client.post('/simulation/reset',json=kwargs)
    assert response.status_code==200,response.text
    return response.json()


async def step(client, state, steps=1):
    return await client.post('/simulation/step',json=dict(generation=state['generation'],expected_tick=state['tick'],steps=steps))


def test_uninitialized_and_reset_serialization(tmp_path):
    async def run(client,app):
        for path in ('/simulation/state','/simulation/benchmark'):
            assert (await client.get(path)).status_code==409
        state=await reset(client)
        assert state['tick']==0 and state['generation']==1
        assert state['state_scope']=='single-user-per-process' and state['virtual_only']
        assert state['seed']==57 and state['current_phase']=='ns_green'
        assert isinstance(state['run_seed'],str) and state['run_seed'].isdigit()
        assert state['totals']==dict(arrivals=0,departures=0,vehicle_count=0,mean_speed_kmh=None)
        assert all(r['mean_speed_kmh'] is None and r['vehicle_count']==r['queue_length_vehicles']==0 for r in state['approaches'])
        assert state['ml']['predictions'] is None and not state['ml']['fallback_active']
        assert state==(await client.get('/simulation/state')).json()
        assert (await client.get('/health')).json()['controller']=='virtual-demo'
    exercise(tmp_path,run)


@pytest.mark.parametrize('scenario',['low','medium','high','asymmetric_rush_hour','incident'])
@pytest.mark.parametrize('controller',['fixed_time','rule_only','ml_assisted'])
def test_safe_deterministic_ticks_and_conservation(tmp_path,scenario,controller):
    async def run(client,app):
        initial=await reset(client,scenario=scenario,controller=controller,duration_seconds=120)
        states=[]
        for _ in range(100):
            response=await step(client,initial)
            assert response.status_code==200,response.text
            new=response.json()['state']
            assert new['tick']==initial['tick']+1
            assert new['timers']['maximum_red_seconds']==75
            assert max(new['timers']['ns_red_seconds'],new['timers']['ew_red_seconds'])<=75
            if new['current_phase']!=initial['current_phase']:
                assert Phase(new['current_phase'])==NEXT_PHASE[Phase(initial['current_phase'])]
            assert new['totals']['arrivals']-new['totals']['departures']==new['totals']['vehicle_count']
            for row in new['approaches']:
                assert 0<=row['queue_length_vehicles']==row['vehicle_count']
                assert row['mean_wait_seconds']>=0
                assert (row['mean_speed_kmh'] is None)==(row['gps_sample_count']==0)
            greens=set(new['vehicle_greens'])
            assert not (greens & {'north','south'} and greens & {'east','west'})
            interval=new['last_interval']
            if not interval['service_phase'].endswith('_green'):
                assert not any(interval['departures'])
            else:
                allowed={'north','south'} if interval['service_phase']=='ns_green' else {'east','west'}
                assert all(not value or approach in allowed for approach,value in zip(APPROACHES,interval['departures']))
            states.append(new)
            initial=new
        repeated=await reset(client,scenario=scenario,controller=controller,duration_seconds=120)
        result=await step(client,repeated,100)
        assert result.status_code==200
        last=result.json()['state']
        assert len(result.json()['actions'])==100
        original=copy.deepcopy(states[-1]);original.pop('generation');last.pop('generation')
        assert original==last
    exercise(tmp_path,run,SyntheticModels())


@pytest.mark.parametrize('body',[{'scenario':'unknown'},{'controller':'physical'},{'seed':58},{'seed':57.0},
    {'duration_seconds':59},{'duration_seconds':1801},{'duration_seconds':True},
    {'replicate':-1},{'replicate':100},{'model_fallback':'silent'},{'queues':{}}])
def test_invalid_reset_rejected_without_mutation(tmp_path,body):
    async def run(client,app):
        before=await reset(client)
        assert (await client.post('/simulation/reset',json=body)).status_code==422
        assert (await client.get('/simulation/state')).json()==before
    exercise(tmp_path,run)


@pytest.mark.parametrize('steps',[0,-1,101,True,1.0])
def test_step_caps_and_stale_clocks(tmp_path,steps):
    async def run(client,app):
        initial=await reset(client,duration_seconds=60)
        assert (await step(client,initial,steps)).status_code==422
        assert (await client.get('/simulation/state')).json()==initial
    exercise(tmp_path,run)


def test_stale_retry_generation_and_end_of_run(tmp_path):
    async def run(client,app):
        initial=await reset(client,duration_seconds=60)
        assert (await step(client,initial,61)).status_code==409
        done=(await step(client,initial,60)).json()['state']
        assert done['completed'] and done['tick']==60
        assert (await step(client,initial)).json()['detail']['code']=='tick_mismatch'
        assert (await step(client,done)).status_code==409
        await reset(client)
        assert (await step(client,done)).json()['detail']['code']=='generation_mismatch'
    exercise(tmp_path,run)


def test_missing_models_require_explicit_fallback_and_failed_reset_is_atomic(tmp_path):
    async def run(client,app):
        previous=await reset(client)
        denied=await client.post('/simulation/reset',json={'controller':'ml_assisted'})
        assert denied.status_code==503 and denied.json()['detail']['code']=='model_unavailable'
        assert (await client.get('/simulation/state')).json()==previous
        state=await reset(client,controller='ml_assisted',model_fallback='rule_only')
        assert state['effective_controller']=='rule_only' and state['ml']['fallback_active']
        assert state['ml']['predictions'] is None and state['ml']['fallback_reason']
        assert not any(state['model_availability'].values())
        result=await step(client,state,20)
        assert result.status_code==200
        assert all(a['prediction_status'].startswith('fallback') for a in result.json()['actions'])
    exercise(tmp_path,run)


@pytest.mark.parametrize('mode',['failure','negative'])
def test_multitick_ml_failure_rolls_back_and_explicit_fallback_runs(tmp_path,mode):
    models=SyntheticModels(fail_at=10 if mode=='failure' else None,negative_at=10 if mode=='negative' else None)
    async def run(client,app):
        initial=await reset(client,controller='ml_assisted')
        denied=await step(client,initial,20)
        assert denied.status_code==503
        assert (await client.get('/simulation/state')).json()==initial
        state=await reset(client,controller='ml_assisted',model_fallback='rule_only')
        advanced=(await step(client,state,20)).json()['state']
        assert advanced['tick']==20 and advanced['ml']['fallback_active']
        assert advanced['ml']['predictions'] is None
        assert advanced['effective_controller']=='rule_only'
    exercise(tmp_path,run,models)


def test_model_inputs_are_current_grid_snapshots_only(tmp_path):
    models=SyntheticModels()
    async def run(client,app):
        state=await reset(client,controller='ml_assisted')
        assert (await step(client,state,25)).status_code==200
        assert sorted(set(t for _,t,_ in models.calls))==[0,10,20]
        for task,second,observations in models.calls:
            for row in observations:
                assert row['timestamp_seconds']==second
                assert row['time_of_day']==second/3600
                assert 'future_wait_seconds' not in row and 'congestion_level' not in row
    exercise(tmp_path,run,models)


def test_concurrent_stale_steps_advance_exactly_once(tmp_path):
    async def run(client,app):
        before=await reset(client)
        first,second=await asyncio.gather(step(client,before,10),step(client,before,10))
        assert sorted([first.status_code,second.status_code])==[200,409]
        assert (await client.get('/simulation/state')).json()['tick']==10
    exercise(tmp_path,run)


def test_app_instances_are_isolated(tmp_path):
    async def run():
        a,b=create_app(tmp_path/'a'),create_app(tmp_path/'b')
        async with a.router.lifespan_context(a),b.router.lifespan_context(b):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=a),base_url='http://a') as ca,httpx.AsyncClient(transport=httpx.ASGITransport(app=b),base_url='http://b') as cb:
                await reset(ca)
                assert (await cb.get('/simulation/state')).status_code==409
    asyncio.run(run())


BENCH=dict(scenarios=['medium'],warmup_seconds=10,measurement_seconds=40,runs_per_scenario=2,model_fallback='rule_only')


def test_benchmark_pairing_cache_reproducibility_and_active_state_isolation(tmp_path):
    async def run(client,app):
        state=await reset(client)
        result=await client.post('/simulation/benchmark',json=BENCH)
        assert result.status_code==200,result.text
        data=result.json()
        assert len(data['run_metrics'])==6 and data['constraint_violations']==0
        assert data['fallback_used'] and data['active_demo_unchanged']
        assert all(r['effective_controller']=='rule_only' for r in data['run_metrics'] if r['controller']=='ml_assisted')
        for replicate in range(2):
            assert len({r['trace_sha256'] for r in data['run_metrics'] if r['replicate']==replicate})==1
        assert all(r['n']<=2 for r in data['uncertainty'])
        assert (await client.get('/simulation/state')).json()==state
        assert (await client.get('/simulation/benchmark')).json()==data
        assert (await client.post('/simulation/benchmark',json=BENCH)).json()==data
        denied=await client.post('/simulation/benchmark',json={**BENCH,'model_fallback':'error'})
        assert denied.status_code==503
        assert (await client.get('/simulation/benchmark')).json()==data
        app.state.simulation.benchmark_lock.acquire()
        try:assert (await client.post('/simulation/benchmark',json=BENCH)).status_code==409
        finally:app.state.simulation.benchmark_lock.release()
    exercise(tmp_path,run)


@pytest.mark.parametrize('body',[{'scenarios':['unknown']},{'scenarios':['low','low']},{'scenarios':[]},
    {'runs_per_scenario':1},{'warmup_seconds':0},{'measurement_seconds':301},{'seed':1},
    {'warmup_seconds':120,'measurement_seconds':300,'runs_per_scenario':3}, {'output_dir':'secret'}])
def test_benchmark_work_and_input_caps(tmp_path,body):
    async def run(client,app):
        assert (await client.post('/simulation/benchmark',json=body)).status_code==422
    exercise(tmp_path,run)


def test_benchmark_rejects_warmup_only_implicit_fallback(tmp_path):
    models=SyntheticModels(negative_at=0)
    original=models.predict
    def predict(task,observations):
        if observations[0].timestamp_seconds>0:
            return ['HIGH']*4 if task=='classification' else [10.]*4
        return original(task,observations)
    models.predict=predict
    async def run(client,app):
        denied=await client.post('/simulation/benchmark',json={**BENCH,'model_fallback':'error'})
        assert denied.status_code==503
    exercise(tmp_path,run,models)


def test_in_memory_trace_matches_offline_benchmark_generator(tmp_path):
    from simulation.benchmark import BenchmarkConfig,generate_traces,load_trace
    config=BenchmarkConfig(10,40,2,100)
    metadata=generate_traces(tmp_path,config)
    for scenario in ('low','asymmetric_rush_hour','incident'):
        meta=next(r for r in metadata if r['scenario']==scenario and r['replicate']==1)
        expected=load_trace(tmp_path,meta)
        actual,seed,_=make_trace(scenario,50,1,10)
        assert seed==meta['run_seed']
        for a,b in zip(actual,expected):np.testing.assert_array_equal(a,b)


def test_api_workflow_never_opens_offline_train_validation_or_test_data(tmp_path,monkeypatch):
    original=Path.open
    def guard(self,*args,**kwargs):
        if self.name in {'train.csv','validation.csv','test.csv','test_snapshot.csv','test_predictions.csv','test_usage_events.jsonl'}:
            raise AssertionError('offline ML data or test ledger accessed')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guard)
    async def run(client,app):
        state=await reset(client,controller='ml_assisted',model_fallback='rule_only')
        assert (await step(client,state,30)).status_code==200
        assert (await client.post('/simulation/benchmark',json=BENCH)).status_code==200
    exercise(tmp_path,run)
