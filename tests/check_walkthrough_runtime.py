import hashlib,json,socket,sys,threading,time
from pathlib import Path
import httpx,uvicorn
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
(root/'work/handoff').mkdir(parents=True,exist_ok=True)
from simulation.walkthrough import preview_app
listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(preview_app(),host='127.0.0.1',port=port,log_level='warning'))
thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);thread.start()
receipt={'status':'PENDING','cases':[]}
try:
 for _ in range(200):
  if server.started:break
  if not thread.is_alive():raise RuntimeError('preview failed')
  time.sleep(.1)
 else:raise RuntimeError('startup timeout')
 with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=15,trust_env=False) as client:
  for path in ['/','/api/health','/api/model-info','/api/model-metrics','/api/simulation/config','/evidence/benchmark_comparisons.png','/evidence/training_clusters.png','/evidence/training_pca_variance.png']:
   r=client.get(path);assert r.status_code==200,(path,r.status_code)
   receipt['cases'].append({'path':path,'status':r.status_code})
  receipt['paired_states']=[]
  for kind in ['fixed_time','ml_assisted']:
   r=client.post('/api/simulation/reset',json=dict(scenario='medium',controller=kind,seed=57,replicate=0,duration_seconds=600,model_fallback='rule_only'));r.raise_for_status();state=r.json()
   r=client.post('/api/simulation/step',json=dict(generation=state['generation'],expected_tick=0,steps=60));r.raise_for_status();state=r.json()['state']
   receipt['paired_states'].append(dict(controller=kind,trace_sha256=state['trace_sha256'],arrivals=state['totals']['arrivals'],tick=state['tick']))
  a,b=receipt['paired_states'];assert a['trace_sha256']==b['trace_sha256'] and a['arrivals']==b['arrivals']==48
 receipt['status']='PASS'
finally:
 server.should_exit=True;thread.join(timeout=10);listener.close()
 with socket.socket() as probe:
  probe.settimeout(.2);closed=probe.connect_ex(('127.0.0.1',port))!=0
 receipt['cleanup']=dict(thread_stopped=not thread.is_alive(),port_closed=closed)
 (root/'work/handoff/preview-http.json').write_text(json.dumps(receipt,indent=2)+'\n')
 assert not thread.is_alive() and closed
print('PREVIEW HTTP PASS: 8 GET routes, paired resets + 60 steps, server stopped')
