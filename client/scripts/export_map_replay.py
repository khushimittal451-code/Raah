"""Export a synthetic map replay after the default paired benchmark; no training or held-out reads."""
from pathlib import Path
import gzip,json,sys,hashlib
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root));sys.path.insert(0,str(root/'ml-service'))
from simulation.benchmark import BenchmarkConfig,load_trace,simulate
from simulation.controllers import MLAdaptiveController
from app.models import ModelBundle
from app.schemas import congestion_level_for
meta=json.loads((root/'artifacts/benchmark/trace_manifest.json').read_text(encoding='utf-8'))
trace=next(t for t in meta['traces'] if t['trace_id']=='medium-r01')
config=BenchmarkConfig(**meta['config'])
models=ModelBundle(root/'artifacts/final');models.load();models.require(['classification','regression'])
class Capture:
    version=models.version
    snapshots={}
    def predict(self,task,observations):
        if task=='classification':self.snapshots[observations[0].timestamp_seconds]=observations
        return models.predict(task,observations)
capture=Capture();controller=MLAdaptiveController()
simulate(controller,load_trace(root/'artifacts/benchmark',trace),config,capture)
with gzip.open(root/'artifacts/benchmark/action_logs/medium-r01_MLAdaptiveController.jsonl.gz','rt',encoding='utf-8') as h:original=[json.loads(line) for line in h]
assert [r.phase for r in controller.action_log]==[r['phase'] for r in original]
frames=[]
for t in range(180,300):
    action=controller.action_log[t];observed_at=t//10*10
    observations=capture.snapshots[observed_at]
    frames.append(dict(timestamp_seconds=t,current_phase=action.phase,seconds_in_phase=action.seconds_in_phase,
        observed_at_seconds=observed_at,controller_reason=action.reason,prediction_status=action.prediction_status,
        approaches=[dict(approach_id=row.approach_id,congestion_level=congestion_level_for(row).upper(),
            queue_length_vehicles=row.queue_length_vehicles,mean_speed_kmh=row.mean_speed_kmh,
            mean_wait_seconds=round(row.mean_wait_seconds,6)) for row in observations]))
result=dict(schema_version='map-replay-v1',seed=57,trace_id=trace['trace_id'],trace_sha256=trace['sha256'],
    controller='MLAdaptiveController',model_version=models.version,
    source='Recorded paired virtual benchmark; 120-second excerpt; no live GPS',
    congestion_basis='congestion-v1 rule on 10-second synthetic observations, not ML predictions',
    signal_basis='One-second recorded controller phases; no physical signal control',frames=frames)
path=root/'client/public/data/junction-replay.json'
path.write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
print('Replay:',len(frames),'frames; phases:',sorted({f['current_phase'] for f in frames}),
      'congestion classes:',sorted({a['congestion_level'] for f in frames for a in f['approaches']}))
print('Fixture SHA256:',hashlib.sha256(path.read_bytes()).hexdigest())
