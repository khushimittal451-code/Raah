import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';

const fmt = (value, digits = 2) => Number.isFinite(value) ? value.toFixed(digits) : 'Unavailable';

export function HistoryCharts({ history }) {
  return <section className="chart-grid" aria-label="Backend snapshot charts">
    {[['queue','Total queue','vehicles'],['speed','Mean sampled speed','km/h']].map(([key,title,unit]) =>
      <article className="panel" key={key}><p className="eyebrow">BACKEND SNAPSHOT HISTORY</p><h2>{title}</h2>
        <div className="history-chart" role="img" aria-label={`${title} chart in ${unit}; received backend snapshots only`}>
          <ResponsiveContainer width="100%" height="100%" minWidth={1}>
            <LineChart data={history}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="tick" name="Simulation second" /><YAxis /><Tooltip labelFormatter={tick => `t=${tick}s`} />
              <Line type="linear" dataKey={key} name={`${title} (${unit})`} stroke={key === 'queue' ? '#235f50' : '#357e9c'} strokeWidth={2} dot={history.length < 4} connectNulls={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div><p className="caption">Last {history.length} received snapshots. Missing speed samples stay missing. No frontend-generated traffic values.</p>
      </article>)}
  </section>;
}

export function PredictionPanel({ state }) {
  const data = state.prediction_display;
  return <section className="panel prediction-panel"><p className="eyebrow">MODEL OUTPUT / SEPARATE FROM OBSERVATIONS</p><h2>Congestion &amp; future wait predictions</h2>
    {!data?.available ? <p role="status">Predictions unavailable: {data?.reason || 'No backend predictions supplied'}. No substitute estimates are shown.</p> : <>
      <p className="muted">Generated at t={data.generated_at_seconds}s · {state.tick - data.generated_at_seconds}s old · wait horizon +{data.prediction_horizon_seconds}s from generation. Provisional models; predictions can disagree with road observations.</p>
      <div className="prediction-grid">{data.approaches.map(row => <article className="prediction-card" key={row.approach_id}>
        <h3>{row.approach_id}</h3><span className={`congestion-pill ${row.congestion_level.toLowerCase()}`}>{row.congestion_level}</span>
        <p>{fmt(row.future_wait_seconds)} s future wait</p>{row.nonphysical_wait && <strong className="warning-text">Nonphysical negative estimate. Not clipped; controller rejects it.</strong>}
      </article>)}</div>
    </>}
    {state.ml.fallback_active && <p className="message error">Control uses explicit queue-only fallback: {state.ml.fallback_reason}</p>}
  </section>;
}

export function ModelMetrics({ remote }) {
  if (remote.status === 'loading') return <section className="panel" role="status">Loading saved model metrics…</section>;
  if (remote.status !== 'ready') return <section className="panel message error" role="status"><h2>Model metrics unavailable</h2><p>{remote.error}</p><button onClick={remote.retry}>Retry model metrics</button></section>;
  const data = remote.data;
  const medium = data.classification?.per_class?.find(row => row.class === 'MEDIUM');
  return <section className="panel metrics-panel"><p className="eyebrow">SAVED EVALUATION / {data.status}</p><h2>Model evidence, not a live accuracy score.</h2>
    <p className="muted">Cached {data.evaluation_split} aggregate · {data.test_rows} rows · evaluated {data.evaluated_utc}. Opening this dashboard does not evaluate the holdout again.</p>
    <div className="metric-grid">
      <article><span>{data.classification.model} accuracy</span><strong>{fmt(data.classification.accuracy * 100, 1)}%</strong></article>
      <article><span>Macro-F1</span><strong>{fmt(data.classification.macro_f1, 3)}</strong></article>
      <article><span>MEDIUM recall</span><strong>{Number.isFinite(medium?.recall) ? `${fmt(medium.recall * 100, 1)}%` : 'Unavailable'}</strong></article>
      <article><span>{data.regression.model} MAE</span><strong>{fmt(data.regression.mae_seconds)} s</strong></article>
      <article><span>RMSE</span><strong>{fmt(data.regression.rmse_seconds)} s</strong></article>
      <article><span>R²</span><strong>{fmt(data.regression.r2, 3)}</strong></article>
    </div><p className="caption">{data.limitations.join(' · ')}. Model version {data.model_version?.slice(0, 12)}.</p>
    <div className="comparison-grid">{['classification','regression'].map(task => {
      const comparison = data.comparisons[task];
      return <section key={task}><h3>{task === 'classification' ? 'Classifier comparison — validation only' : 'Regressor comparison — validation only'}</h3>
        {!comparison.available ? <p>Comparison unavailable: {comparison.reason}</p> : <div className="table-scroll"><table>
          <caption className="sr-only">{task} validation comparison</caption>
          <thead><tr><th>Model</th>{task === 'classification' ? <><th>Accuracy</th><th>Macro-F1</th><th>Latency / row</th></> : <><th>MAE</th><th>RMSE</th><th>R²</th></>}</tr></thead>
          <tbody>{comparison.rows.map(row => <tr key={row.model}><th scope="row">{row.model}</th>{task === 'classification' ? <><td>{fmt(row.validation_accuracy * 100, 1)}%</td><td>{fmt(row.validation_macro_f1, 3)}</td><td>{fmt(row.single_row_median_ms)} ms</td></> : <><td>{fmt(row.validation_mae_seconds)} s</td><td>{fmt(row.validation_rmse_seconds)} s</td><td>{fmt(row.validation_r2, 3)}</td></>}</tr>)}</tbody>
        </table></div>}
      </section>;
    })}</div>
  </section>;
}
