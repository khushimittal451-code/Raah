import { CONGESTION_COLORS, lampFor } from '../mapModel.js';

export function MapLegend() {
  return <div className="legend-grid">
    <section aria-label="Road congestion legend"><h3>Road congestion</h3><ul className="legend-list">
      {Object.entries(CONGESTION_COLORS).map(([label, color]) => <li key={label}><i className="road-swatch" style={{ backgroundColor: color }} aria-hidden="true" />{label}</li>)}
    </ul><p>Line color is a rule-derived synthetic congestion band, not a traffic light.</p></section>
    <section aria-label="Virtual signal legend"><h3>Virtual signal lamps</h3><ul className="legend-list">
      {['RED', 'YELLOW', 'GREEN'].map(label => <li key={label}><i className={`lamp-swatch ${label.toLowerCase()}`} aria-hidden="true" />{label}</li>)}
    </ul><p>Round lamps show recorded controller indications. A red road can have a green signal.</p></section>
  </div>;
}

export default function SignalPanel({ frame }) {
  return <section className="panel signals-panel" aria-labelledby="signals-heading">
    <p className="eyebrow">RECORDED VIRTUAL STATE</p><h2 id="signals-heading">Signals, separately.</h2>
    <p className="phase-name">{frame.current_phase.replaceAll('_', ' ')} <span>· {frame.seconds_in_phase}s in phase</span></p>
    <div className="signal-grid">{frame.approaches.map(row => {
      const indication = lampFor(frame.current_phase, row.approach_id);
      return <article key={row.approach_id} className="signal-card" aria-label={`${row.approach_id} signal ${indication}`}>
        <div className="signal-housing" aria-hidden="true">{['RED', 'YELLOW', 'GREEN'].map(color =>
          <span key={color} className={`signal-bulb ${color.toLowerCase()} ${indication === color ? 'lit' : ''}`} />)}</div>
        <div><h3>{row.approach_id}</h3><strong>{indication}</strong><small>{row.queue_length_vehicles} queued · {row.congestion_level}</small></div>
      </article>;
    })}</div>
    <p className="caption">Virtual through movements only. Yellow and all-red clearances follow the recorded safety controller. No physical signals are connected.</p>
    <details><summary>Why this action?</summary><p>{frame.controller_reason?.replaceAll('_', ' ')}</p><p className="caption">{frame.prediction_status?.startsWith('fallback') ? 'The controller rejected an ML estimate and used queue-only rules.' : 'Recorded ML-assisted controller; hard timing and fairness constraints take priority.'}</p></details>
  </section>;
}
