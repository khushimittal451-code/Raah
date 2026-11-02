"""Real localhost integration evidence; owns and stops each Uvicorn server."""
import json
from pathlib import Path
import socket
import sys
import threading
import time
import httpx
import uvicorn
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ml-service'))
from app.main import create_app
OUT=ROOT/'work/simulation-api'
OUT.mkdir(parents=True,exist_ok=True)
evidence={'cases':[],'cleanup':[]}

def run(mode,directory):
    listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(directory),host='127.0.0.1',port=port,log_level='warning'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
    print('START',mode,'127.0.0.1:'+str(port),flush=True);thread.start()
    try:
        for _ in range(300):
            if server.started:break
            if not thread.is_alive():raise RuntimeError('server failed during startup')
            time.sleep(.1)
        else:raise RuntimeError('startup timeout')
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=60,trust_env=False) as client:
            def check(method,path,expected,body=None):
                response=client.request(method,path,**({'json':body} if body is not None else {}))
                payload=response.json()
                evidence['cases'].append(dict(mode=mode,method=method,path=path,status=response.status_code,body=payload))
                assert response.status_code in ([expected] if isinstance(expected,int) else expected),(path,response.text)
                print(mode,method,path,response.status_code,flush=True)
                return response,payload
            check('GET','/health',200)
            check('GET','/model-info',200)
            check('GET','/simulation/state',409)
            check('GET','/simulation/benchmark',409)
            _,fixed=check('POST','/simulation/reset',200,{'scenario':'medium','controller':'fixed_time'})
            request=dict(generation=fixed['generation'],expected_tick=0,steps=35)
            _,advanced=check('POST','/simulation/step',200,request)
            assert len(advanced['actions'])==35 and advanced['state']['tick']==35
            check('POST','/simulation/step',409,request)
            check('POST','/simulation/step',422,{**request,'steps':101})
            check('POST','/simulation/reset',422,{'scenario':'live-gps'})
            _,before=check('GET','/simulation/state',200)
            response,payload=check('POST','/simulation/reset',[200,503] if mode=='saved-models' else 503,{'controller':'ml_assisted'})
            if response.status_code==503:
                assert payload['detail']['code']=='model_unavailable'
                _,unchanged=check('GET','/simulation/state',200);assert unchanged==before
            _,ml=check('POST','/simulation/reset',200,{'controller':'ml_assisted','model_fallback':'rule_only'})
            _,ml_step=check('POST','/simulation/step',200,{'generation':ml['generation'],'expected_tick':0,'steps':35})
            if mode=='missing-models':
                assert ml_step['state']['ml']['predictions'] is None and ml_step['state']['effective_controller']=='rule_only'
            _,before_benchmark=check('GET','/simulation/state',200)
            config={'model_fallback':'rule_only'} if mode=='saved-models' else dict(scenarios=['low'],warmup_seconds=10,measurement_seconds=60,model_fallback='rule_only')
            _,comparison=check('POST','/simulation/benchmark',200,config)
            assert comparison['constraint_violations']==0
            _,cached=check('GET','/simulation/benchmark',200);assert cached==comparison
            _,after_benchmark=check('GET','/simulation/state',200);assert after_benchmark==before_benchmark
            print(mode,'BENCHMARK',len(comparison['run_metrics']),'runs',comparison['total_controller_ticks'],'ticks','fallback_used',comparison['fallback_used'],flush=True)
            if mode=='missing-models':
                assert all(r['effective_controller']=='rule_only' for r in comparison['run_metrics'] if r['controller']=='ml_assisted')
            _,repeated=check('POST','/simulation/reset',200,{'controller':'ml_assisted','model_fallback':'rule_only'})
            for _ in range(5):
                _,part=check('POST','/simulation/step',200,{'generation':repeated['generation'],'expected_tick':repeated['tick'],'steps':7})
                repeated=part['state']
            original=dict(ml_step['state']);original.pop('generation')
            repeated.pop('generation')
            assert original==repeated
            print(mode,'REPRODUCIBILITY PASS: 35 ticks == 5 requests x 7 ticks',flush=True)
    finally:
        server.should_exit=True;thread.join(timeout=10);listener.close()
        with socket.socket() as probe:
            probe.settimeout(.2);closed=probe.connect_ex(('127.0.0.1',port))!=0
        record=dict(mode=mode,port=port,thread_stopped=not thread.is_alive(),port_closed=closed)
        evidence['cleanup'].append(record);print('STOPPED',json.dumps(record),flush=True)
        assert record['thread_stopped'] and closed

try:
    run('saved-models',ROOT/'artifacts/final')
    run('missing-models',OUT/'no-models')
    evidence['status']='PASS'
finally:
    (OUT/'http_evidence.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n',encoding='utf-8')
