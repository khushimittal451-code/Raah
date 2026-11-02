"""Repeatable local demo verification or single-process preview. Synthetic/virtual only."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'ml-service'))

from app.models import ModelBundle  # noqa: E402
from app.simulation_api import ResetRequest, SimulationService, StepRequest  # noqa: E402
from simulation.compare_controllers import audit  # noqa: E402


def record_run(service, controller, allow_rule_fallback):
    state = service.reset(ResetRequest(scenario='medium', controller=controller,
        seed=57, replicate=0, duration_seconds=600,
        model_fallback='rule_only' if allow_rule_fallback else 'error'))
    trace, run_seed = state['trace_sha256'], state['run_seed']
    states = [service.session.snapshot]
    arrivals = []
    policies = Counter()
    for second in range(1, 61):
        result = service.step(StepRequest(generation=state['generation'], expected_tick=state['tick']))
        state = result['state']
        if state['tick'] != second:
            raise AssertionError('walkthrough clock mismatch')
        states.append(service.session.snapshot)
        arrivals.append(state['last_interval']['arrivals'])
        policies[state['effective_controller']] += 1
    violations, max_red = audit(states, service.session.controller.config)
    if violations:
        raise AssertionError('walkthrough controller violations: ' + repr(violations))
    return dict(controller=controller, trace_sha256=trace, run_seed=run_seed,
        arrivals=arrivals, arrivals_sha256=hashlib.sha256(json.dumps(arrivals,separators=(',',':')).encode()).hexdigest(),
        total_arrivals=state['totals']['arrivals'], ticks=60, maximum_red_seconds=max_red,
        constraint_violations=len(violations), effective_policy_ticks=dict(sorted(policies.items())), ending_state=state)


def verify_pair(fixed, ml):
    for field in ('trace_sha256', 'run_seed', 'arrivals', 'arrivals_sha256', 'total_arrivals', 'ticks'):
        if fixed[field] != ml[field]:
            raise AssertionError('controller runs did not replay identical arrivals: ' + field)
    return True


def verify(output, allow_rule_fallback=False, bundle=None):
    # A private service instance never touches an already-running user's demo.
    if bundle is None:
        bundle = ModelBundle(ROOT / 'artifacts/final')
        bundle.load()
    folder = Path(output)
    if folder.exists() and any(folder.iterdir()):
        raise ValueError('choose a fresh empty walkthrough output directory')
    service = SimulationService(bundle)
    fixed = record_run(service, 'fixed_time', allow_rule_fallback)
    ml = record_run(service, 'ml_assisted', allow_rule_fallback)
    verify_pair(fixed, ml)
    report = dict(status='PASS', seed=57, scenario='medium', replicate=0,
        duration_seconds=600, compared_ticks=60, identical_arrivals=True,
        model_fallback='rule_only' if allow_rule_fallback else 'error', models=bundle.describe(),
        fixed=fixed, ml=ml, heldout_evaluation_executed=False,
        limitation='This is deterministic replay/invariant evidence, not a 60-second traffic performance study or a timed browser rehearsal.')
    folder.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report,indent=2,allow_nan=False)+'\n'
    (folder/'receipt.json').write_text(payload,encoding='utf-8')
    return json.loads(payload)  # same JSON types as the persisted receipt


def preview_app():
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from app.main import create_app
    if not (ROOT/'client/dist/index.html').is_file():
        raise RuntimeError('client build missing; run npm --prefix client run build first')
    inner = create_app()
    @asynccontextmanager
    async def lifespan(_application):
        async with inner.router.lifespan_context(inner):
            yield
    outer = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    outer.mount('/api', inner)
    outer.mount('/evidence', StaticFiles(directory=ROOT/'docs/figures'))
    outer.mount('/', StaticFiles(directory=ROOT/'client/dist', html=True))
    return outer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--verify', action='store_true')
    mode.add_argument('--serve', action='store_true')
    parser.add_argument('--allow-rule-fallback', action='store_true', help='explicit opt-in for verification only')
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/demo_walkthrough')
    parser.add_argument('--port', type=int, default=5173)
    args = parser.parse_args()
    if args.serve:
        if not 1024 <= args.port <= 65535:
            parser.error('port must be in [1024,65535]')
        import uvicorn
        uvicorn.run(preview_app(), host='127.0.0.1', port=args.port, workers=1, log_level='warning')
    else:
        report = verify(args.output, args.allow_rule_fallback)
        print(json.dumps(dict(status=report['status'], identical_arrivals=True, scenario=report['scenario'],
            trace_sha256=report['fixed']['trace_sha256'], total_arrivals=report['fixed']['total_arrivals'],
            compared_ticks=60, ml_effective_policy_ticks=report['ml']['effective_policy_ticks'],
            constraint_violations=report['fixed']['constraint_violations']+report['ml']['constraint_violations'],
            receipt=str(args.output/'receipt.json')), indent=2))


if __name__ == '__main__':
    main()
