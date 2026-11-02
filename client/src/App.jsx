import { useEffect, useRef, useState } from 'react';
import JunctionMap from './components/JunctionMap.jsx';
import SignalPanel, { MapLegend } from './components/SignalPanel.jsx';
import { HistoryCharts, ModelMetrics, PredictionPanel } from './components/DashboardPanels.jsx';
import useSimulation, { useRemote } from './hooks/useSimulation.js';
import { apiRequest } from './api.js';

export default function App() {
  const sim = useSimulation();
  const config = useRemote('/simulation/config');
  const metrics = useRemote('/model-metrics');
  const [draft, setDraft] = useState(null);
  const [touched, setTouched] = useState(false);
  const [benchmark, setBenchmark] = useState(null);
  const [benchError, setBenchError] = useState(null);
  const [benchBusy, setBenchBusy] = useState(false);
  const benchAbort = useRef(null);
  const cfg = config.data;
  const cfgReady = config.status === 'ready' && Array.isArray(cfg?.scenarios) && Array.isArray(cfg?.controllers);
  useEffect(() => {
    if (cfgReady && !touched) setDraft({ scenario: sim.state?.scenario || cfg.default_scenario,
      controller: sim.state?.requested_controller || cfg.default_controller,
      allowFallback: sim.state?.ml.fallback_policy === 'rule_only' });
  }, [cfgReady, cfg, sim.state?.generation, touched]);
  useEffect(() => () => benchAbort.current?.abort(), []);
  const state = sim.state;
  const body = draft && cfgReady ? { scenario: draft.scenario, controller: draft.controller,
    seed: cfg.seed, duration_seconds: cfg.duration_seconds, model_fallback: draft.allowFallback ? 'rule_only' : 'error' } : null;
  const pending = Boolean(state && draft && (draft.scenario !== state.scenario || draft.controller !== state.requested_controller || body.model_fallback !== state.ml.fallback_policy));
  const change = values => { sim.pause(); setTouched(true); setDraft(previous => ({ ...previous, ...values })); };
  async function compare() {
    sim.pause(); setBenchBusy(true); setBenchError(null);
    const controller = new AbortController(); benchAbort.current = controller;
    try {
      const result = await apiRequest('/simulation/benchmark', { method: 'POST', signal: controller.signal,
        body: { scenarios: [state.scenario], model_fallback: draft.allowFallback ? 'rule_only' : 'error' } });
      if (!controller.signal.aborted) setBenchmark(result);
    } catch (error) { if (!controller.signal.aborted) setBenchError(error.message); }
    finally { if (!controller.signal.aborted) setBenchBusy(false); }
  }
  return <main>
    <header><a className="brand" href="./">raah<span> / virtual traffic lab</span></a><span className="simulation-badge">SIMULATED DATA</span></header>
    <section className="intro dashboard-intro"><p className="eyebrow">OBSERVE. COMPARE. KEEP THE CONSTRAINTS.</p><h1>One junction.<br /><em>Every decision visible.</em></h1><p>A backend-driven virtual traffic workspace. Every count, chart point, prediction and countdown comes from the API. No live GPS or physical signal control.</p></section>
    <div className="status-grid">
      <article><span>Backend connection</span><strong className={sim.connection === 'connected' ? 'connected' : ''}>{sim.connection}</strong><small>{sim.running ? 'Running virtual ticks' : 'Paused / state polling only'}</small></article>
      <article><span>Simulation clock</span><strong>{state ? `t = ${state.tick}s` : 'Not initialized'}</strong><small>Seed {cfg?.seed ?? '—'} · {cfg?.state_scope || 'Loading state contract'}</small></article>
      <article><span>Syllabus / mode</span><strong>{cfg?.syllabus_status || 'Unavailable'}</strong><small>{state ? `${state.requested_controller} → ${state.effective_controller}` : 'Initialize a backend demo below'}</small></article>
    </div>
    {sim.error && <section className="message error" role="alert"><strong>API action failed; simulation paused.</strong><p>{sim.error}</p><p>Any displayed snapshot is the last received state. Timers do not advance locally.</p><button onClick={sim.refresh} disabled={sim.busy}>Refresh backend state</button></section>}
    <section className="panel controls-panel" aria-label="Simulation controls">
      {!cfgReady || !draft ? <><p role="status">{config.status === 'error' ? `Control configuration unavailable: ${config.error}` : 'Loading backend control configuration…'}</p><button onClick={config.retry}>Retry configuration</button></> : <>
        <div className="controls-fields"><label>Scenario<select aria-label="Scenario" value={draft.scenario} onChange={event => change({ scenario: event.target.value })} disabled={sim.busy || benchBusy}>{cfg.scenarios.map(name => <option key={name} value={name}>{name.replaceAll('_', ' ')}</option>)}</select></label>
          <fieldset><legend>Controller</legend><div className="controller-toggle">{cfg.controllers.map(name => <label key={name}><input type="radio" name="controller" value={name} checked={draft.controller === name} onChange={() => change({ controller: name })} disabled={sim.busy || benchBusy} /><span>{name.replaceAll('_', ' ')}</span></label>)}</div></fieldset></div>
        <label className="fallback-choice"><input type="checkbox" checked={draft.allowFallback} onChange={event => change({ allowFallback: event.target.checked })} disabled={sim.busy || benchBusy} />I explicitly permit queue-only fallback for unavailable or invalid ML estimates (also applies to comparisons).</label>
        <div className="playback-buttons dashboard-buttons"><button onClick={() => sim.start(body)} disabled={sim.busy || benchBusy || sim.running || pending || Boolean(sim.error) || state?.completed}>{state ? 'Run' : 'Initialize & run'}</button><button onClick={sim.pause} disabled={!sim.running}>Pause</button><button onClick={() => sim.reset(body)} disabled={sim.busy || benchBusy}>Reset simulation</button><button onClick={sim.refresh} disabled={sim.busy}>Refresh state</button></div>
        <p className="caption">{pending ? 'Choices changed. Reset to apply them; the displayed state still belongs to the previous configuration.' : 'Run advances one backend tick at a time. Pause allows an in-flight tick to finish, then only reads state.'} One shared demo per API worker.</p>
      </>}
    </section>
    {!state ? <section className="panel no-state" role="status"><h2>{sim.connection === 'connecting' ? 'Loading backend state…' : 'No active backend simulation'}</h2><p>Initialize a scenario to show the map, measurements and model output. No sample traffic will be substituted.</p></section> : <>
      <section className="workspace"><article className="panel map-panel"><div className="panel-heading"><div><p className="eyebrow">CURRENT BACKEND OBSERVATIONS</p><h2>Congestion on the roads.</h2></div><span className="tag">t = {state.tick}s</span></div><JunctionMap frame={state} /><MapLegend /></article><SignalPanel frame={{ ...state, seconds_in_phase: state.timers.seconds_in_phase, controller_reason: state.last_action.reason, prediction_status: state.ml.status }} live /></section>
      <HistoryCharts history={sim.history} />
      <PredictionPanel state={state} />
      <section className="panel observation-panel"><h2>Per-approach observations</h2><p className="caption">Current backend snapshot · {state.congestion_source}. Speeds without GPS-like samples stay unavailable.</p><div className="table-scroll"><table><caption className="sr-only">Backend approach observations</caption><thead><tr><th>Approach</th><th>Congestion</th><th>Queue</th><th>Mean speed</th><th>Current wait</th></tr></thead><tbody>{state.approaches.map(row => <tr key={row.approach_id}><th scope="row">{row.approach_id}</th><td><span className={`congestion-pill ${row.congestion_level.toLowerCase()}`}>{row.congestion_level}</span></td><td>{row.queue_length_vehicles} vehicles</td><td>{row.mean_speed_kmh === null ? 'No samples' : `${row.mean_speed_kmh.toFixed(2)} km/h`}</td><td>{row.mean_wait_seconds.toFixed(1)} s</td></tr>)}</tbody></table></div></section>
      <section className="panel comparison-panel"><p className="eyebrow">PAIRED CONTROLLER COMPARISON</p><h2>Compare on the same arrivals.</h2><p className="muted">The backend uses shared traces, warm-up and two independent runs for the active scenario. This pauses the dashboard; results do not claim improvements.</p><button onClick={compare} disabled={benchBusy || sim.busy || !draft}>{benchBusy ? 'Comparing…' : 'Run controller comparison'}</button>{benchError && <p role="alert" className="message error">Comparison failed: {benchError}</p>}
        {benchmark && <><p className="caption">Backend scenario: {benchmark.config.scenarios.join(', ')} · {benchmark.total_controller_ticks} controller-ticks · fallback used: {String(benchmark.fallback_used)}. Observed waits are right-censored at the horizon.</p><div className="table-scroll"><table><caption className="sr-only">Backend controller comparison</caption><thead><tr><th>Controller / run</th><th>Effective</th><th>Mean wait</th><th>p95 wait</th><th>Throughput</th><th>Violations</th></tr></thead><tbody>{benchmark.run_metrics.map(row => <tr key={`${row.scenario}-${row.controller}-${row.replicate}`}><th>{row.controller} / {row.replicate + 1}</th><td>{row.effective_controller}</td><td>{row.mean_wait_seconds === null ? 'Unavailable' : `${row.mean_wait_seconds.toFixed(2)} s`}</td><td>{row.p95_wait_seconds === null ? 'Unavailable' : `${row.p95_wait_seconds.toFixed(2)} s`}</td><td>{row.throughput_vehicles}</td><td>{row.constraint_violations}</td></tr>)}</tbody></table></div></>}
      </section>
    </>}
    <ModelMetrics remote={metrics} />
    <footer><span>Backend data only / synthetic-only / virtual-only</span><span>No physical infrastructure. No live traffic claims.</span></footer>
  </main>;
}
