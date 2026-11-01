"""Real localhost HTTP checks; owned Uvicorn thread is stopped in finally."""
import json
import os
from pathlib import Path
import socket
import threading
import time
import httpx
import uvicorn
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ml-service'))
from app.main import create_app
OUT = ROOT/'work/api'
OUT.mkdir(parents=True,exist_ok=True)
PAYLOAD = dict(run_id='api-smoke-57', timestamp_seconds=600, intersection_id='junction-1',
    approach_id='north', mean_speed_kmh=50.0, free_flow_speed_kmh=60.0, vehicle_count=20,
    queue_length_vehicles=4, mean_wait_seconds=10.0, incoming_vehicles=2, outgoing_vehicles=1,
    current_phase='ns_green', seconds_in_phase=10.0, time_of_day=600/3600, gps_sample_count=10)
results = {'synthetic_request': PAYLOAD, 'cases': [], 'cleanup': []}

def run(mode):
    # Pass a pre-bound socket to Uvicorn, avoiding free-port races and Windows launcher children.
    listener = socket.socket()
    listener.bind(('127.0.0.1',0))
    port = listener.getsockname()[1]
    directory = ROOT/'artifacts/final' if mode=='saved-models' else OUT/'missing-models'
    server = uvicorn.Server(uvicorn.Config(create_app(directory), host='127.0.0.1', port=port, log_level='warning'))
    thread = threading.Thread(target=server.run, kwargs={'sockets':[listener]}, daemon=True)
    print('START',mode,'Uvicorn on 127.0.0.1:'+str(port),flush=True)
    thread.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=5,trust_env=False) as client:
            for _ in range(200):
                if not thread.is_alive():
                    raise RuntimeError('server exited before readiness')
                if server.started:
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('server readiness timeout')
            ready = mode=='saved-models'
            cases = [('GET','/health',None,200),('GET','/model-info',None,200),
                ('POST','/predict/congestion',PAYLOAD,200 if ready else 503),
                ('POST','/predict/wait',PAYLOAD,200 if ready else 503),
                ('POST','/predict/batch',{'observations':[PAYLOAD,{**PAYLOAD,'incoming_vehicles':3}]},200 if ready else 503),
                ('POST','/predict/wait',{**PAYLOAD,'vehicle_count':-1},422),
                ('POST','/predict/batch',{'observations':[PAYLOAD]*101},422)]
            for method,path,body,expected in cases:
                response=client.request(method,path,**({'json':body} if body is not None else {}))
                record={'mode':mode,'method':method,'path':path,'status':response.status_code,'expected':expected,'body':response.json()}
                results['cases'].append(record)
                # Keep full output in JSON, concise validation diagnostics on console.
                preview = record['body'] if response.status_code != 422 else [x['msg'] for x in record['body']['detail']]
                print(mode,method,path,response.status_code,json.dumps(preview),flush=True)
                assert response.status_code==expected, record
                if path=='/model-info':
                    assert all(value['available']==ready for value in response.json()['tasks'].values())
    finally:
        server.should_exit=True
        thread.join(timeout=10)
        listener.close()
        with socket.socket() as probe:
            probe.settimeout(.2)
            closed=probe.connect_ex(('127.0.0.1',port))!=0
        results['cleanup'].append({'mode':mode,'port':port,'port_closed':closed,'thread_stopped':not thread.is_alive()})
        print('STOPPED',mode,'thread_stopped',not thread.is_alive(),'port_closed',closed,flush=True)
        assert not thread.is_alive() and closed

try:
    run('saved-models')
    run('missing-models')
    results['status']='PASS'
finally:
    (OUT/'http_smoke.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
