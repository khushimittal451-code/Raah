import { useCallback, useEffect, useRef, useState } from 'react';
import { apiRequest, validateState } from '../api.js';

export function useRemote(path) {
  const [value, setValue] = useState({ status: 'loading', data: null });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); let active = true;
    setValue({ status: 'loading', data: null });
    apiRequest(path, { signal: controller.signal })
      .then(data => { if (active) setValue({ status: 'ready', data }); })
      .catch(error => { if (active) setValue({ status: 'error', data: null, error: error.message }); });
    return () => { active = false; controller.abort(); };
  }, [path, revision]);
  return { ...value, retry: () => setRevision(n => n + 1) };
}

export default function useSimulation() {
  const [state, setState] = useState(null);
  const [history, setHistory] = useState([]);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [connection, setConnection] = useState('connecting');
  const current = useRef(null), run = useRef(false), manual = useRef(false);
  const mounted = useRef(false), epoch = useRef(0), pending = useRef(null);
  const controllers = useRef(new Set());
  const accept = useCallback(data => {
    data = validateState(data);
    current.current = data; setState(data); setConnection('connected');
    setHistory(previous => {
      const last = previous.at(-1);
      if (last?.generation === data.generation && last.tick === data.tick) return previous;
      const sample = { generation: data.generation, tick: data.tick, queue: data.totals.vehicle_count, speed: data.totals.mean_speed_kmh };
      return last?.generation === data.generation && data.tick === last.tick + 1 ? [...previous.slice(-119), sample] : [sample];
    });
    if (data.completed) { run.current = false; setRunning(false); }
    return data;
  }, []);
  const pause = useCallback(() => { run.current = false; setRunning(false); }, []);
  const request = useCallback((path, options = {}) => {
    const controller = new AbortController(); controllers.current.add(controller);
    const promise = apiRequest(path, { ...options, signal: controller.signal });
    pending.current = promise;
    return promise.finally(() => {
      controllers.current.delete(controller);
      if (pending.current === promise) pending.current = null;
    });
  }, []);
  useEffect(() => {
    mounted.current = true; const token = ++epoch.current; let timer;
    async function poll() {
      if (!mounted.current || token !== epoch.current) return;
      if (manual.current || pending.current) { timer = setTimeout(poll, 200); return; }
      const stepping = run.current && current.current && !current.current.completed;
      try {
        const data = await request(stepping ? '/simulation/step' : '/simulation/state', stepping ? {
          method: 'POST', body: { generation: current.current.generation, expected_tick: current.current.tick, steps: 1 },
        } : {});
        if (mounted.current && token === epoch.current && !manual.current) accept(stepping ? data.state : data);
      } catch (failure) {
        if (!mounted.current || token !== epoch.current) return;
        pause();
        if (failure.code === 'simulation_not_initialized') {
          current.current = null; setState(null); setHistory([]); setConnection('connected');
        } else {
          setConnection('error'); setError(`${failure.message} Simulation paused; refresh state before continuing.`);
        }
      } finally {
        if (mounted.current && token === epoch.current) timer = setTimeout(poll, 1000);
      }
    }
    poll();
    return () => {
      mounted.current = false; ++epoch.current; run.current = false;
      clearTimeout(timer); controllers.current.forEach(controller => controller.abort());
    };
  }, [accept, pause, request]);
  const reset = useCallback(async body => {
    pause(); manual.current = true; setBusy(true); setError(null);
    try {
      if (pending.current) await pending.current.catch(() => {});
      if (!mounted.current) return null;
      const data = await request('/simulation/reset', { method: 'POST', body });
      return mounted.current ? accept(data) : null;
    } catch (failure) {
      if (mounted.current) { setError(failure.message); setConnection('error'); }
      return null;
    } finally { manual.current = false; if (mounted.current) setBusy(false); }
  }, [accept, pause, request]);
  const start = useCallback(async body => {
    if (manual.current || running) return;
    let data = current.current;
    if (!data) data = await reset(body);
    if (data && !data.completed && mounted.current) { setError(null); run.current = true; setRunning(true); }
  }, [reset, running]);
  const refresh = useCallback(async () => {
    pause(); manual.current = true; setBusy(true);
    try {
      if (pending.current) await pending.current.catch(() => {});
      if (!mounted.current) return;
      const data = await request('/simulation/state');
      if (mounted.current) { accept(data); setError(null); }
    } catch (failure) {
      if (mounted.current) {
        if (failure.code === 'simulation_not_initialized') { current.current = null; setState(null); setHistory([]); setError(null); setConnection('connected'); }
        else setError(failure.message);
      }
    } finally { manual.current = false; if (mounted.current) setBusy(false); }
  }, [accept, pause, request]);
  return { state, history, running, busy, error, connection, start, pause, reset, refresh };
}
