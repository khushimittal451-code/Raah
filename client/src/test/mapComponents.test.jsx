import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import replay from '../../public/data/junction-replay.json';

const observed = vi.hoisted(() => ({ tile: null, mounts: 0, map: null }));
vi.mock('react-leaflet', () => ({
  MapContainer: props => { observed.map = props; return <div data-testid="leaflet-map">{props.children}</div>; },
  TileLayer: function Tile(props) {
    observed.tile = props;
    React.useEffect(() => { observed.mounts += 1; }, []);
    return <div data-testid="tile-layer" data-url={props.url} />;
  },
  Polyline: props => <div data-testid="road-line" data-color={props.pathOptions.color}>{props.children}</div>,
  CircleMarker: props => <div data-testid="virtual-lamp" data-color={props.pathOptions.fillColor}>{props.children}</div>,
  Tooltip: props => <span>{props.children}</span>,
  useMap: () => ({ invalidateSize: vi.fn(), getContainer: () => document.body }),
}));
vi.mock('axios', () => ({ default: { create: () => ({ get: vi.fn().mockResolvedValue({ data: { status: 'ok' } }) }), isCancel: () => false } }));

import JunctionMap from '../components/JunctionMap.jsx';
import SignalPanel, { MapLegend } from '../components/SignalPanel.jsx';
import App from '../App.jsx';

beforeEach(() => {
  observed.tile = null; observed.mounts = 0;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => structuredClone(replay) }));
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('map components', () => {
  it('keeps visible OSM attribution and bounded map options', () => {
    render(<JunctionMap frame={replay.frames[0]} />);
    expect(screen.getByRole('link', { name: '© OpenStreetMap contributors' })).toHaveAttribute('href', 'https://www.openstreetmap.org/copyright');
    expect(observed.tile.attribution).toContain('OpenStreetMap contributors');
    expect(observed.map.attributionControl).toBe(true);
    expect(observed.map.scrollWheelZoom).toBe(false);
    expect(observed.map.minZoom).toBe(17);
    expect(observed.map.maxZoom).toBe(18);
    expect(screen.getByText('SIMULATED DATA')).toBeVisible();
    expect(screen.getByText('Loading basemap…')).toBeVisible();
  });
  it('shows LOW/MEDIUM/HIGH road colors independently from green virtual lamps', () => {
    const frame = structuredClone(replay.frames[0]);
    frame.current_phase = 'ns_green';
    frame.approaches[0].congestion_level = 'HIGH';
    frame.approaches[1].congestion_level = 'MEDIUM';
    frame.approaches[2].congestion_level = 'LOW';
    render(<><JunctionMap frame={frame} /><SignalPanel frame={frame} /><MapLegend /></>);
    const roadColors = screen.getAllByTestId('road-line').map(x => x.dataset.color);
    expect(roadColors).toEqual(expect.arrayContaining(['#168249', '#d49113', '#dc3545']));
    expect(screen.getByLabelText('north signal GREEN')).toBeVisible();
    expect(screen.getAllByTestId('virtual-lamp')[0]).toHaveAttribute('data-color', '#22c55e');
    expect(screen.getByRole('region', { name: 'Road congestion legend' })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Virtual signal legend' })).toBeVisible();
  });
  it('all-red clearances illuminate red lamps on all four approaches', () => {
    const frame = { ...replay.frames[0], current_phase: 'all_red_to_ew', seconds_in_phase: 0 };
    const { container } = render(<SignalPanel frame={frame} />);
    expect(container.querySelectorAll('.signal-bulb.red.lit')).toHaveLength(4);
    expect(container.querySelectorAll('.signal-bulb.green.lit')).toHaveLength(0);
  });
  it('falls back on tile error without changing the frame or making automatic retries', () => {
    vi.useFakeTimers();
    render(<JunctionMap frame={replay.frames[0]} />);
    act(() => observed.tile.eventHandlers.tileerror());
    expect(screen.queryByTestId('tile-layer')).not.toBeInTheDocument();
    expect(screen.getByText(/tiles could not load/)).toBeVisible();
    expect(screen.getByText('OFFLINE / SCHEMATIC')).toBeVisible();
    act(() => vi.advanceTimersByTime(20000));
    expect(observed.mounts).toBe(1);
    fireEvent.click(screen.getByRole('button', { name: 'Load OpenStreetMap' }));
    expect(screen.getByTestId('tile-layer')).toBeVisible();
    expect(observed.mounts).toBe(2);
  });
  it('falls back after a bounded tile loading timeout', () => {
    vi.useFakeTimers();
    render(<JunctionMap frame={replay.frames[0]} />);
    act(() => vi.advanceTimersByTime(8000));
    expect(screen.getByText(/Basemap loading timed out/)).toBeVisible();
    expect(screen.queryByTestId('tile-layer')).not.toBeInTheDocument();
  });
  it('removes loading state after tile completion and does not remount tiles on replay ticks', () => {
    const { rerender } = render(<JunctionMap frame={replay.frames[0]} />);
    act(() => observed.tile.eventHandlers.load());
    expect(screen.queryByText('Loading basemap…')).not.toBeInTheDocument();
    rerender(<JunctionMap frame={replay.frames[1]} />);
    expect(observed.mounts).toBe(1);
  });
  it('allows an offline mode that requests no tiles', () => {
    render(<JunctionMap frame={replay.frames[0]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Use offline schematic' }));
    expect(screen.queryByTestId('tile-layer')).not.toBeInTheDocument();
    expect(screen.getByText(/No map tiles are requested/)).toBeVisible();
  });
});

describe('recorded map application', () => {
  it('shows loading first, then real recorded data and a readable observation table', async () => {
    render(<App />);
    expect(screen.getByText('Loading synthetic replay…')).toBeVisible();
    expect(await screen.findByText('t = 180s')).toBeVisible();
    expect(screen.getByRole('table', { name: 'Synthetic approach observations' })).toBeVisible();
    expect(screen.getAllByText('SIMULATED DATA')).toHaveLength(2);
    expect(screen.getByText(/not model predictions/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Previous second' })).toBeDisabled();
  });
  it('does not invent a map or values on data failure and can retry explicitly', async () => {
    fetch.mockResolvedValueOnce({ ok: false });
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Simulation data unavailable');
    expect(screen.queryByTestId('leaflet-map')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry simulation data' }));
    expect(await screen.findByText('t = 180s')).toBeVisible();
  });
  it('shows an explicit data error for malformed recorded phases', async () => {
    const bad = structuredClone(replay); bad.frames[0].current_phase = 'both_green';
    fetch.mockResolvedValueOnce({ ok: true, json: async () => bad });
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Simulation data unavailable');
  });
  it('steps and seeks read-only recorded phases, then stops at the end without looping', async () => {
    render(<App />);
    await screen.findByText('t = 180s');
    fireEvent.click(screen.getByRole('button', { name: 'Next second' }));
    expect(screen.getByText('t = 181s')).toBeVisible();
    fireEvent.change(screen.getByRole('slider', { name: 'Seek recorded seconds' }), { target: { value: 118 } });
    expect(screen.getByText('t = 298s')).toBeVisible();
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole('button', { name: 'Play replay' }));
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText('t = 299s')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Play replay' })).toBeDisabled();
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByText('t = 299s')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Reset replay' }));
    expect(screen.getByText('t = 180s')).toBeVisible();
  });
});
