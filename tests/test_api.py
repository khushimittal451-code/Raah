"""API tests use tiny synthetic estimator doubles, never held-out observations."""
import asyncio
import hashlib
import json
import joblib
import numpy as np
import httpx
import pytest
from app.main import create_app
from app.models import FEATURES

PAYLOAD = dict(run_id='api-smoke-57', timestamp_seconds=600, intersection_id='junction-1',
    approach_id='north', mean_speed_kmh=50.0, free_flow_speed_kmh=60.0, vehicle_count=20,
    queue_length_vehicles=4, mean_wait_seconds=10.0, incoming_vehicles=2, outgoing_vehicles=1,
    current_phase='ns_green', seconds_in_phase=10.0, time_of_day=600/3600, gps_sample_count=10)

class TinyPipeline:
    def __init__(self, task):
        self.task = task
        self.feature_names_in_ = np.array(FEATURES[task])
    def __getitem__(self, key):
        return self
    def get_feature_names_out(self):
        return np.array(['test_feature'])
    def predict(self, frame):
        assert list(frame.columns) == FEATURES[self.task]
        if self.task == 'classification':
            return np.array(['LOW' if x == 2 else 'HIGH' for x in frame.incoming_vehicles])
        return np.array([-1.5] * len(frame))

@pytest.fixture
def artifacts(tmp_path):
    schema = {'version': 'final-feature-schema-v1', 'tasks': {}}
    choices = {}
    for task in FEATURES:
        filename = task + '_pipeline.joblib'
        joblib.dump(TinyPipeline(task), tmp_path / filename)
        choices[task] = {'model': 'test-' + task}
        schema['tasks'][task] = dict(model='test-' + task, pipeline_file=filename,
            pipeline_sha256=hashlib.sha256((tmp_path / filename).read_bytes()).hexdigest(),
            input_features=[{'name': f} for f in FEATURES[task]], transformed_feature_order=['test_feature'])
    (tmp_path / 'feature_schema.json').write_text(json.dumps(schema), encoding='utf-8')
    (tmp_path / 'selection_manifest.json').write_text(json.dumps({'choices': choices, 'feature_lists': FEATURES}), encoding='utf-8')
    return tmp_path

def requests(directory, operations):
    async def perform():
        app = create_app(directory)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
                return [await client.request(method, path, **kwargs) for method, path, kwargs in operations]
    return asyncio.run(perform())

def post(path, payload):
    return ('POST', path, {'json': payload})

def test_predictions_schema_order_and_negative_wait(artifacts):
    info, cls, wait, batch = requests(artifacts, [('GET', '/model-info', {}),
        post('/predict/congestion', PAYLOAD), post('/predict/wait', PAYLOAD),
        post('/predict/batch', {'observations': [PAYLOAD, {**PAYLOAD, 'incoming_vehicles': 3}]})])
    assert all(r.status_code == 200 for r in (info, cls, wait, batch))
    assert all(task['available'] for task in info.json()['tasks'].values())
    assert cls.json()['congestion_level'] == 'LOW'
    assert wait.json()['future_wait_seconds'] == -1.5
    assert wait.json()['nonphysical_wait'] is True
    assert wait.json()['warning'] == 'negative_model_output'
    assert [x['congestion_level'] for x in batch.json()['predictions']] == ['LOW', 'HIGH']
    assert cls.json()['model_version'] == info.json()['model_version']
    assert info.json()['tasks']['classification']['input_features'] == FEATURES['classification']

@pytest.mark.parametrize('change', [dict(vehicle_count=-1), dict(free_flow_speed_kmh=0),
    dict(mean_speed_kmh=161), dict(current_phase='bad'), dict(time_of_day=24),
    dict(queue_length_vehicles=21), dict(gps_sample_count=21), dict(seconds_in_phase=601),
    dict(mean_speed_kmh=None), dict(incoming_vehicles=True), dict(future_wait_seconds=99),
    dict(mean_wait_seconds=3601), dict(timestamp_seconds=601)])
def test_invalid_data_422(artifacts, change):
    for response in requests(artifacts, [post(path, {**PAYLOAD, **change}) for path in ['/predict/congestion', '/predict/wait']]):
        assert response.status_code == 422

def test_missing_required_field(artifacts):
    payload = {k: v for k, v in PAYLOAD.items() if k != 'mean_speed_kmh'}
    assert requests(artifacts, [post('/predict/congestion', payload)])[0].status_code == 422

@pytest.mark.parametrize('size,expected', [(0,422), (100,200), (101,422)])
def test_batch_limit(artifacts, size, expected):
    assert requests(artifacts, [post('/predict/batch', {'observations': [PAYLOAD]*size})])[0].status_code == expected

def test_invalid_batch_row(artifacts):
    assert requests(artifacts, [post('/predict/batch', {'observations': [PAYLOAD, {**PAYLOAD, 'vehicle_count': -1}]})])[0].status_code == 422

def test_missing_bundle_explicitly_unavailable(tmp_path):
    health, info, cls, wait, batch = requests(tmp_path, [('GET','/health',{}), ('GET','/model-info',{}),
        post('/predict/congestion',PAYLOAD), post('/predict/wait',PAYLOAD), post('/predict/batch',{'observations':[PAYLOAD]})])
    assert health.status_code == 200
    assert not any(v['available'] for v in info.json()['tasks'].values())
    for response in (cls,wait,batch):
        assert response.status_code == 503
        assert response.json()['detail']['code'] == 'model_unavailable'
        assert 'congestion_level' not in response.json()

def test_missing_one_model_and_hash_corruption(artifacts):
    (artifacts/'regression_pipeline.joblib').unlink()
    cls, wait, batch = requests(artifacts, [post('/predict/congestion',PAYLOAD),post('/predict/wait',PAYLOAD),post('/predict/batch',{'observations':[PAYLOAD]})])
    assert [r.status_code for r in (cls,wait,batch)] == [200,503,503]
    with (artifacts/'classification_pipeline.joblib').open('ab') as stream:
        stream.write(b'corrupt')
    response = requests(artifacts, [post('/predict/congestion',PAYLOAD)])[0]
    assert response.status_code == 503 and 'hash mismatch' in response.json()['detail']['reason']

def test_schema_drift_rejected(artifacts):
    path = artifacts/'feature_schema.json'
    schema = json.loads(path.read_text(encoding='utf-8'))
    schema['tasks']['classification']['input_features'].reverse()
    path.write_text(json.dumps(schema), encoding='utf-8')
    assert requests(artifacts,[post('/predict/congestion',PAYLOAD)])[0].status_code == 503

def test_inference_failure_never_returns_fake_output(artifacts, monkeypatch):
    def fail(*args):
        raise RuntimeError('broken estimator')
    monkeypatch.setattr(TinyPipeline, 'predict', fail)
    response = requests(artifacts,[post('/predict/wait',PAYLOAD)])[0]
    assert response.status_code == 503 and 'inference_failed' in response.json()['detail']['reason']

def test_post_cors(artifacts):
    response = requests(artifacts,[('OPTIONS','/predict/wait',{'headers': {'Origin':'http://localhost:5173','Access-Control-Request-Method':'POST'}})])[0]
    assert response.status_code == 200
    assert 'POST' in response.headers['access-control-allow-methods']

def test_missing_speed_with_zero_samples_is_valid(artifacts):
    response = requests(artifacts,[post('/predict/wait',{**PAYLOAD,'mean_speed_kmh':None,'gps_sample_count':0})])[0]
    assert response.status_code == 200


def test_nonfinite_model_output_is_unavailable(artifacts, monkeypatch):
    monkeypatch.setattr(TinyPipeline, 'predict', lambda self, frame: np.full(len(frame),np.nan))
    assert requests(artifacts,[post('/predict/wait',PAYLOAD)])[0].status_code == 503


def test_transformed_schema_drift_rejected(artifacts):
    path=artifacts/'feature_schema.json'
    schema=json.loads(path.read_text(encoding='utf-8'))
    schema['tasks']['regression']['transformed_feature_order']=['wrong']
    path.write_text(json.dumps(schema),encoding='utf-8')
    assert requests(artifacts,[post('/predict/wait',PAYLOAD)])[0].status_code == 503
