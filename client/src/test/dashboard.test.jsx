import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import fixtures from './fixtures/dashboard-api.json';

vi.mock('react-leaflet', () => ({
  MapContainer: p => <div data-testid="backend-map">{p.children}</div>, TileLayer: () => null,
  Polyline: p => <div>{p.children}</div>, CircleMarker: p => <div>{p.children}</div>, Tooltip: p => <span>{p.children}</span>,
  useMap: () => ({ invalidateSize: vi.fn(), getContainer: () => document.body }),
}));
vi.mock('recharts', () => ({
  ResponsiveContainer: p => <div>{p.children}</div>,
  LineChart: p => <div data-testid="history-series" data-points={JSON.stringify(p.data)}>{p.children}</div>,
  Line: () => null, XAxis: () => null, YAxis: () => null, CartesianGrid: () => null, Tooltip: () => null,
}));
import App from '../App.jsx';

let current, key, generation, calls, metricsFail, stepFailure, deferredStep;
const copy = data => structuredClone(data);
const response = (data, status = 200) => Promise.resolve({ ok: status < 400, status, json: async () => copy(data) });
function snapshot(tick) { return { ...copy(fixtures.sets[key][String(tick)]), generation }; }
beforeEach(() => {
  current = null; key = 'medium/fixed_time'; generation = 0; calls = []; metricsFail = false; stepFailure = null; deferredStep = null;
  vi.stubGlobal('fetch', vi.fn((url, options = {}) => {
    const path = url.replace('/api', ''); const body = options.body ? JSON.parse(options.body) : undefined;
    calls.push({ path, method: options.method, body, signal: options.signal });
    if (path === '/simulation/config') return response(fixtures.config);
    if (path === '/model-metrics') return metricsFail ? response({ detail: { reason: 'Saved metrics missing' } }, 503) : response(fixtures.metrics);
    if (path === '/simulation/state') return current ? response(current) : response({ detail: { code: 'simulation_not_initialized' } }, 409);
    if (path === '/simulation/reset') {
      if (body.controller === 'ml_assisted' && body.model_fallback === 'error') return response({ detail: { reason: 'ML estimates unavailable; choose explicit fallback' } }, 503);
      key = body.scenario + '/' + body.controller; generation += 1; current = snapshot(0);
      return response(current);
    }
    if (path === '/simulation/step') {
      if (stepFailure) return response({ detail: stepFailure }, stepFailure.code === 'tick_mismatch' ? 409 : 503);
      if (deferredStep) return new Promise(resolve => { deferredStep.resolve = () => { current = snapshot(body.expected_tick + 1); resolve({ ok: true, status: 200, json: async () => ({ state: current, actions: [] }) }); }; });
      current = snapshot(body.expected_tick + 1); return response({ state: current, actions: [] });
    }
    if (path === '/simulation/benchmark') return response(fixtures.benchmark);
    throw new Error('Unexpected request: '+path);
  }));
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
async function boot() { await act(async () => { render(<App />); }); }
function existing(tick = 0) { generation = 1; current = snapshot(tick); }

it('does not substitute a recording or random values when no backend demo exists', async () => {
  await boot();
  expect(screen.getByText('No active backend simulation')).toBeVisible();
  expect(screen.queryByTestId('backend-map')).not.toBeInTheDocument();
  expect(calls.some(c => c.path.includes('junction-replay'))).toBe(false);
  expect(calls.some(c => c.path === '/simulation/reset')).toBe(false);
  expect(screen.getByRole('button', { name: 'Initialize & run' })).toBeEnabled();
});

it('initializes using backend configuration and starts with no invented tick', async () => {
  await boot();
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Initialize & run' })));
  expect(calls.find(c => c.path === '/simulation/reset').body).toEqual({ scenario: 'medium', controller: 'fixed_time', seed: 57, duration_seconds: 600, model_fallback: 'error' });
  expect(screen.getByTestId('backend-map')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Pause' })).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
});

it('uses backend countdowns including unknown adaptive next-green times', async () => {
  key = 'medium/rule_only'; existing(); await boot();
  expect(screen.getAllByText('Not scheduled')).toHaveLength(2);
  expect(screen.getAllByText('Until adaptive review; may extend')).toHaveLength(2);
  expect(screen.getAllByText('15s')).toHaveLength(2);
});

it('polls sequential backend ticks, pauses without a local countdown timer and charts only received samples', async () => {
  vi.useFakeTimers(); existing(); await boot();
  fireEvent.click(screen.getByRole('button', { name: 'Run' }));
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(calls.filter(c => c.path === '/simulation/step')).toHaveLength(1);
  expect(calls.find(c => c.path === '/simulation/step').body).toEqual({ generation: 1, expected_tick: 0, steps: 1 });
  const points = JSON.parse(screen.getAllByTestId('history-series')[0].dataset.points);
  expect(points.map(p => p.tick)).toEqual([0,1]);
  expect(points[1].queue).toBe(fixtures.sets[key]['1'].totals.vehicle_count);
  expect(points[0].speed).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
  const remaining = screen.getAllByText('29s').length;
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(calls.filter(c => c.path === '/simulation/step')).toHaveLength(1);
  expect(screen.getAllByText('29s')).toHaveLength(remaining);
});

it('waits for an in-flight step and never issues overlapping steps', async () => {
  vi.useFakeTimers(); existing(); deferredStep = {}; await boot();
  fireEvent.click(screen.getByRole('button', { name: 'Run' }));
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(calls.filter(c => c.path === '/simulation/step')).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
  await act(async () => deferredStep.resolve());
  expect(current.tick).toBe(1);
});

it('pauses and shows API errors without retrying a rejected mutation', async () => {
  vi.useFakeTimers(); existing(); await boot();
  stepFailure = { code: 'tick_mismatch', reason: 'Stale tick' };
  fireEvent.click(screen.getByRole('button', { name: 'Run' }));
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(screen.getByRole('alert')).toHaveTextContent('Stale tick');
  expect(screen.getByRole('button', { name: 'Run' })).toBeDisabled();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(calls.filter(c => c.path === '/simulation/step')).toHaveLength(1);
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Refresh backend state' })));
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('keeps the active state visible while scenario/controller changes wait for reset', async () => {
  existing(); await boot();
  fireEvent.change(screen.getByRole('combobox', { name: 'Scenario' }), { target: { value: 'incident' } });
  fireEvent.click(screen.getByRole('radio', { name: 'rule only' }));
  expect(screen.getByRole('button', { name: 'Run' })).toBeDisabled();
  expect(screen.getByText(/Choices changed/)).toBeVisible();
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Reset simulation' })));
  expect(calls.find(c => c.path === '/simulation/reset').body).toMatchObject({ scenario: 'incident', controller: 'rule_only' });
  expect(current.scenario).toBe('incident');
  expect(screen.getByRole('button', { name: 'Run' })).toBeEnabled();
});

it('requires an explicit checkbox before retrying ML with queue-only fallback', async () => {
  await boot();
  fireEvent.click(screen.getByRole('radio', { name: 'ml assisted' }));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Reset simulation' })));
  expect(screen.getByRole('alert')).toHaveTextContent('choose explicit fallback');
  expect(calls.filter(c => c.path === '/simulation/reset')).toHaveLength(1);
  fireEvent.click(screen.getByRole('checkbox'));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Reset simulation' })));
  expect(calls.filter(c => c.path === '/simulation/reset')[1].body.model_fallback).toBe('rule_only');
  expect(screen.getByText(/Control uses explicit queue-only fallback/)).toBeVisible();
});

it('displays saved evaluation and validation comparisons from the metrics API', async () => {
  await boot();
  expect(screen.getByText('68.4%')).toBeVisible();
  expect(screen.getByRole('table', { name: 'classification validation comparison' })).toHaveTextContent('LogisticRegression');
  expect(screen.getByRole('table', { name: 'regression validation comparison' })).toHaveTextContent('last_observed_wait');
  expect(screen.getByText(/does not evaluate the holdout again/)).toBeVisible();
});

it('shows unavailable metrics independently of working simulation state', async () => {
  metricsFail = true; existing(); await boot();
  expect(screen.getByText('Model metrics unavailable')).toBeVisible();
  expect(screen.getByTestId('backend-map')).toBeVisible();
});

it('shows backend model predictions separately from observed road bands', async () => {
  existing(); await boot();
  expect(screen.getByText('Congestion & future wait predictions')).toBeVisible();
  expect(screen.getAllByText(/Nonphysical negative estimate/).length).toBeGreaterThan(0);
  expect(screen.getByRole('table', { name: 'Backend approach observations' })).toBeVisible();
});

it('runs the bounded controller comparison and displays returned measurements', async () => {
  existing(); await boot(); fireEvent.click(screen.getByRole('checkbox'));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Run controller comparison' })));
  expect(calls.find(c => c.path === '/simulation/benchmark').body).toEqual({ scenarios: ['medium'], model_fallback: 'rule_only' });
  expect(screen.getByRole('table', { name: 'Backend controller comparison' })).toHaveTextContent('ml_assisted');
});

it('aborts outstanding reads and clears scheduled polling on unmount', async () => {
  vi.useFakeTimers(); let aborted = false;
  const original = fetch;
  vi.stubGlobal('fetch', vi.fn((url,options) => url.endsWith('/simulation/state') ? new Promise((resolve,reject) => {
    options.signal.addEventListener('abort', () => { aborted = true; reject(new DOMException('aborted','AbortError')); });
  }) : original(url,options)));
  let view; await act(async () => { view = render(<App />); });
  view.unmount();
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(aborted).toBe(true);
  expect(calls.filter(c => c.path === '/simulation/step')).toHaveLength(0);
});
