import { useEffect, useState } from 'react';
import axios from 'axios';
import { CRS } from 'leaflet';
import { MapContainer, Polyline, CircleMarker, Tooltip } from 'react-leaflet';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid } from 'recharts';

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '/api', timeout: 5000 });
const junctions = [[30, 30], [30, 70], [70, 30], [70, 70]];

export default function App() {
  const [health, setHealth] = useState(null);
  const [connection, setConnection] = useState('checking');
  useEffect(() => {
    const controller = new AbortController();
    api.get('/health', { signal: controller.signal })
      .then(({ data }) => {
        setHealth(data);
        setConnection(data.status === 'ok' ? 'connected' : 'unavailable');
      })
      .catch((error) => { if (!axios.isCancel(error)) setConnection('unavailable'); });
    return () => controller.abort();
  }, []);

  return (
    <main>
      <header><a className="brand" href="./">raah<span> / virtual traffic lab</span></a><span className="tag">PHASE 01</span></header>
      <section className="intro"><p className="eyebrow">SYNTHETIC DATA. TRANSPARENT DECISIONS.</p><h1>A clearer view<br />of traffic flow.</h1><p>A semester ML workspace for congestion estimation and constrained virtual signals. The foundation is ready; experiments come next.</p></section>
      <div className="status-grid">
        <article><span>API connection</span><strong className={connection === 'connected' ? 'connected' : ''} role="status">{connection}</strong><small>Liveness check only</small></article>
        <article><span>Experiment seed</span><strong>{health?.seed ?? 57}</strong><small>Reproducible by design</small></article>
        <article><span>Syllabus alignment</span><strong>UNVERIFIED</strong><small>Official syllabus pending</small></article>
      </div>
      <section className="workspace">
        <article className="panel"><div className="panel-heading"><div><p className="eyebrow">VIRTUAL NETWORK</p><h2>A canvas for simulation</h2></div><span className="tag">LAYOUT ONLY</span></div>
          <MapContainer crs={CRS.Simple} center={[50, 50]} zoom={1} minZoom={0} maxZoom={3} scrollWheelZoom={false} attributionControl={false} aria-label="Abstract virtual junction layout">
            <Polyline positions={[[30, 0], [30, 100]]} pathOptions={{ color: '#9fb1a5', weight: 12 }} />
            <Polyline positions={[[70, 0], [70, 100]]} pathOptions={{ color: '#9fb1a5', weight: 12 }} />
            <Polyline positions={[[0, 30], [100, 30]]} pathOptions={{ color: '#9fb1a5', weight: 12 }} />
            <Polyline positions={[[0, 70], [100, 70]]} pathOptions={{ color: '#9fb1a5', weight: 12 }} />
            {junctions.map((position, index) => <CircleMarker key={index} center={position} radius={9} pathOptions={{ color: '#fff', fillColor: '#235f50', fillOpacity: 1 }}><Tooltip>Virtual junction {index + 1}: no controller running</Tooltip></CircleMarker>)}
          </MapContainer><p className="caption">Abstract coordinates, no geographic GPS or external map tiles. No signal controller is running.</p>
        </article>
        <article className="panel"><p className="eyebrow">MODEL COMPARISON</p><h2>Results begin with evidence.</h2><p className="muted">No models have been trained or evaluated. Metrics will appear after grouped experiments are implemented.</p>
          <div className="chart" aria-label="Empty model results chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={[]}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="scenario" /><YAxis /><Line dataKey="metric" stroke="#235f50" /></LineChart></ResponsiveContainer></div>
          <p className="caption">Awaiting measurements. No sample accuracy or traffic values are presented.</p>
        </article>
      </section>
      <footer><span>Seed 57 / synthetic-only / virtual-only</span><span>No reinforcement learning or deep learning</span></footer>
    </main>
  );
}
