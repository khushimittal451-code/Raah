import { useEffect, useState } from 'react';
import axios from 'axios';
import JunctionMap from './components/JunctionMap.jsx';
import SignalPanel, { MapLegend } from './components/SignalPanel.jsx';
import { validateReplay } from './mapModel.js';

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '/api', timeout: 5000 });

export default function App() {
  const [connection, setConnection] = useState('checking');
  const [load, setLoad] = useState({ status: 'loading', replay: null });
  const [attempt, setAttempt] = useState(0);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api.get('/health', { signal: controller.signal })
      .then(({ data }) => setConnection(data.status === 'ok' ? 'connected' : 'unavailable'))
      .catch(error => { if (!axios.isCancel(error)) setConnection('unavailable'); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoad({ status: 'loading', replay: null });
    setPlaying(false);
    setIndex(0);
    fetch(`${import.meta.env.BASE_URL}data/junction-replay.json`, { signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error('Replay request failed');
        return response.json();
      })
      .then(data => setLoad({ status: 'ready', replay: validateReplay(data) }))
      .catch(error => {
        if (error.name !== 'AbortError') setLoad({ status: 'error', replay: null });
      });
    return () => controller.abort();
  }, [attempt]);
  const frames = load.replay?.frames ?? [];
  useEffect(() => {
    if (!playing) return undefined;
    if (index >= frames.length - 1) { setPlaying(false); return undefined; }
    const timer = setTimeout(() => setIndex(value => value + 1), 1000);
    return () => clearTimeout(timer);
  }, [playing, index, frames.length]);
  const frame = frames[index];
  const seek = next => { setPlaying(false); setIndex(next); };
  return <main>
    <header><a className="brand" href="./">raah<span> / virtual traffic lab</span></a><span className="simulation-badge">SIMULATED DATA</span></header>
    <section className="intro"><p className="eyebrow">ONE JUNCTION. TWO DIFFERENT STORIES.</p><h1>Traffic pressure.<br /><em>Signal decisions.</em></h1><p>Explore a recorded synthetic junction. Colored roads describe congestion; separate lamps show what the virtual controller did.</p></section>
    <div className="status-grid">
      <article><span>Data source</span><strong>Recorded simulation</strong><small>Seed 57 / no live GPS</small></article>
      <article><span>API liveness</span><strong className={connection === 'connected' ? 'connected' : ''}>{connection}</strong><small>Replay works independently of the API</small></article>
      <article><span>Syllabus alignment</span><strong>UNVERIFIED</strong><small>Educational virtual system</small></article>
    </div>
    {load.status === 'loading' && <section className="panel loading-panel" role="status" aria-busy="true"><div className="loading-lines" aria-hidden="true" /><h2>Loading synthetic replay…</h2><p>No traffic or signal values are displayed until the recording is validated.</p></section>}
    {load.status === 'error' && <section className="panel message error" role="alert"><h2>Simulation data unavailable</h2><p>The recorded data could not be loaded or validated. No replacement traffic values or signal colors have been invented.</p><button type="button" onClick={() => setAttempt(value => value + 1)}>Retry simulation data</button></section>}
    {frame && <>
      <section className="replay-controls" aria-label="Recorded simulation playback">
        <div><p className="eyebrow">READ-ONLY REPLAY / {load.replay.trace_id}</p><strong>t = {frame.timestamp_seconds}s</strong><span className="replay-caption">{frames.length}-second recording excerpt / {playing ? 'playing at 1×' : 'paused'}</span></div>
        <div className="playback-buttons">
          <button type="button" onClick={() => setPlaying(value => !value)} disabled={!playing && index === frames.length - 1}>{playing ? 'Pause replay' : 'Play replay'}</button>
          <button type="button" onClick={() => seek(Math.max(0, index - 1))} disabled={index === 0}>Previous second</button>
          <button type="button" onClick={() => seek(Math.min(frames.length - 1, index + 1))} disabled={index === frames.length - 1}>Next second</button>
          <button type="button" onClick={() => seek(0)}>Reset replay</button>
        </div>
        <label className="seek-label" htmlFor="replay-seek">Seek recorded seconds<input id="replay-seek" type="range" min="0" max={frames.length - 1} value={index} onChange={event => seek(Number(event.target.value))} /></label>
      </section>
      <section className="workspace">
        <article className="panel map-panel"><div className="panel-heading"><div><p className="eyebrow">ILLUSTRATIVE GEOGRAPHY</p><h2>Four approaches. One view.</h2></div><span className="tag">VIRTUAL ONLY</span></div>
          <JunctionMap frame={frame} />
          <MapLegend />
        </article>
        <SignalPanel frame={frame} />
      </section>
      <section className="panel observation-panel" aria-labelledby="observations-heading"><div className="panel-heading"><div><p className="eyebrow">CONGESTION OBSERVATIONS</p><h2 id="observations-heading">Same snapshot. Clear provenance.</h2></div><span className="tag">OBSERVED AT t = {frame.observed_at_seconds}s</span></div>
        <p className="muted">Road bands use the congestion-v1 rule on 10-second synthetic snapshots, not model predictions. Lamps update every recorded second. Snapshot age: {frame.timestamp_seconds - frame.observed_at_seconds}s.</p>
        <div className="table-scroll"><table><caption className="sr-only">Synthetic approach observations</caption><thead><tr><th>Approach</th><th>Congestion</th><th>Queue</th><th>Mean speed</th><th>Current wait</th></tr></thead><tbody>{frame.approaches.map(row => <tr key={row.approach_id}><th scope="row">{row.approach_id}</th><td><span className={`congestion-pill ${row.congestion_level.toLowerCase()}`}>{row.congestion_level}</span></td><td>{row.queue_length_vehicles} vehicles</td><td>{row.mean_speed_kmh === null ? 'No samples' : `${row.mean_speed_kmh.toFixed(1)} km/h`}</td><td>{row.mean_wait_seconds.toFixed(1)} s</td></tr>)}</tbody></table></div>
        <p className="caption">Signal source: constrained MLAdaptiveController recording. Playback and seeking inspect history; they do not run a controller or send signal commands.</p>
      </section>
    </>}
    <footer><span>Seed 57 / synthetic-only / virtual-only</span><span>No physical infrastructure. No live traffic claims.</span></footer>
  </main>;
}
