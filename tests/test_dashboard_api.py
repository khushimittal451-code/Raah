import asyncio
import hashlib
import json

import httpx
import pytest

from app.dashboard_api import load_metrics
from app.main import create_app
from app.models import ModelBundle
from app.simulation_api import ResetRequest, SimulationService, StepRequest
from test_simulation_api import SyntheticModels


def test_countdowns_and_predictions_are_backend_sourced(tmp_path):
    models=SyntheticModels()
    service=SimulationService(models)
    fixed=service.reset(ResetRequest())
    north=next(r for r in fixed['approaches'] if r['approach_id']=='north')
    east=next(r for r in fixed['approaches'] if r['approach_id']=='east')
    assert north['signal_color']=='GREEN' and north['countdown_seconds']==30
    assert east['signal_color']=='RED' and east['countdown_seconds']==34
    assert all(r['congestion_level']=='LOW' for r in fixed['approaches'])
    assert fixed['prediction_display']['available']
    assert all(r['congestion_level']=='HIGH' for r in fixed['prediction_display']['approaches'])
    assert fixed['totals']['mean_speed_kmh'] is None
    state=service.step(StepRequest(generation=fixed['generation'],expected_tick=0,steps=30))['state']
    n,e=state['approaches'][0],state['approaches'][2]
    assert n['signal_color']=='YELLOW' and n['countdown_seconds']==3
    assert e['countdown_seconds']==4
    adaptive=service.reset(ResetRequest(controller='rule_only'))
    assert adaptive['approaches'][0]['countdown_kind']=='green_review'
    assert adaptive['approaches'][2]['countdown_seconds'] is None


def test_advisory_negative_values_do_not_stop_rule_control():
    service=SimulationService(SyntheticModels(negative_at=0))
    state=service.reset(ResetRequest(controller='rule_only'))
    assert state['effective_controller']=='rule_only' and not state['ml']['fallback_active']
    assert state['prediction_display']['available']
    assert all(row['nonphysical_wait'] and row['future_wait_seconds']==-1 for row in state['prediction_display']['approaches'])


def test_metrics_missing_and_configuration_routes(tmp_path):
    async def run():
        app=create_app(tmp_path/'empty')
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                config=(await client.get('/simulation/config')).json()
                assert config['seed']==57 and len(config['controllers'])==3 and len(config['scenarios'])==5
                response=await client.get('/model-metrics')
                assert response.status_code==503 and response.json()['detail']['code']=='metrics_unavailable'
    asyncio.run(run())


def test_saved_aggregate_metrics_require_matching_provenance(tmp_path):
    folder=tmp_path/'final';folder.mkdir()
    selection=folder/'selection_manifest.json'
    selection.write_text(json.dumps({'comparison_hashes':{}}),encoding='utf-8')
    version=hashlib.sha256(selection.read_bytes()).hexdigest()
    (folder/'feature_schema.json').write_text(json.dumps({'tasks':{t:{'pipeline_sha256':t} for t in ('classification','regression')}}),encoding='utf-8')
    metrics=dict(selection_sha256=version,evaluation_split='test',pipeline_hashes={t:t for t in ('classification','regression')},
        classification={'model':'unit'},regression={'model':'unit'},status='UNVERIFIED',seed=57,evaluated_utc='unit fixture',test_rows=10)
    (folder/'metrics.json').write_text(json.dumps(metrics),encoding='utf-8')
    (folder/'test_access_claim.json').write_text(json.dumps(dict(status='COMPLETE', selection_sha256=version,
        metrics_sha256=hashlib.sha256((folder/'metrics.json').read_bytes()).hexdigest(), test_csv_reads=1,
        classification_predict_batches=1, regression_predict_batches=1)), encoding='utf-8')
    bundle=ModelBundle(folder);bundle.version=version
    data=load_metrics(bundle)
    assert data['classification']['model']=='unit'
    assert all(not row['available'] for row in data['comparisons'].values())
    metrics['selection_sha256']='wrong'
    (folder/'metrics.json').write_text(json.dumps(metrics),encoding='utf-8')
    import pytest
    with pytest.raises(ValueError,match='version'):load_metrics(bundle)


@pytest.mark.parametrize('change', ['metrics', 'missing_receipt', 'incomplete', 'selection', 'read_count'])
def test_saved_metrics_fail_closed_on_changed_or_incomplete_evidence(tmp_path, change):
    folder=tmp_path/'final';folder.mkdir()
    selection=folder/'selection_manifest.json'
    selection.write_text(json.dumps({'comparison_hashes':{}}),encoding='utf-8')
    version=hashlib.sha256(selection.read_bytes()).hexdigest()
    (folder/'feature_schema.json').write_text(json.dumps({'tasks':{t:{'pipeline_sha256':t} for t in ('classification','regression')}}),encoding='utf-8')
    metrics=dict(selection_sha256=version,evaluation_split='test',pipeline_hashes={t:t for t in ('classification','regression')},
        classification={'accuracy':.5},regression={'mae_seconds':2},status='UNVERIFIED',seed=57,evaluated_utc='fixture',test_rows=10)
    path=folder/'metrics.json';path.write_text(json.dumps(metrics),encoding='utf-8')
    receipt=dict(status='COMPLETE',selection_sha256=version,metrics_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                 test_csv_reads=1,classification_predict_batches=1,regression_predict_batches=1)
    if change=='metrics':
        metrics['classification']['accuracy']=.99
        path.write_text(json.dumps(metrics),encoding='utf-8')
    elif change=='incomplete':receipt['status']='CLAIMED_BEFORE_TEST_OPEN'
    elif change=='selection':receipt['selection_sha256']='wrong'
    elif change=='read_count':receipt['test_csv_reads']=2
    if change!='missing_receipt':
        (folder/'test_access_claim.json').write_text(json.dumps(receipt),encoding='utf-8')
    bundle=ModelBundle(folder);bundle.version=version
    with pytest.raises((ValueError,OSError),match='metrics|receipt|test_access_claim'):
        load_metrics(bundle)
    async def rejected_by_api():
        app=create_app(folder)
        async with app.router.lifespan_context(app):
            app.state.bundle=bundle
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                response=await client.get('/model-metrics')
                assert response.status_code==503
                assert response.json()['detail']['code']=='metrics_unavailable'
    asyncio.run(rejected_by_api())
