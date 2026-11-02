import { describe, expect, it } from 'vitest';
import replay from '../../public/data/junction-replay.json';
import { APPROACHES, CONGESTION_COLORS, geometryFor, lampFor, PHASES, TILE_OPTIONS, validateReplay } from '../mapModel.js';

describe('recorded virtual map contract', () => {
  it('validates the real recorded excerpt and all six phases', () => {
    expect(validateReplay(replay)).toBe(replay);
    expect(replay.frames).toHaveLength(120);
    expect(new Set(replay.frames.map(f => f.current_phase))).toEqual(new Set(PHASES));
  });
  it.each(PHASES)('%s never gives conflicting virtual greens', phase => {
    const greens = APPROACHES.filter(a => lampFor(phase, a) === 'GREEN');
    expect([[], ['north', 'south'], ['east', 'west']]).toContainEqual(greens);
    if (phase.startsWith('all_red')) expect(APPROACHES.every(a => lampFor(phase, a) === 'RED')).toBe(true);
  });
  it('separates HIGH road congestion from a GREEN signal', () => {
    expect(CONGESTION_COLORS.HIGH).toBe('#dc3545');
    expect(lampFor('ns_green', 'north')).toBe('GREEN');
    expect(lampFor('ns_yellow', 'north')).toBe('YELLOW');
    expect(lampFor('ns_yellow', 'east')).toBe('RED');
    expect(() => lampFor('bogus', 'north')).toThrow();
  });
  it('has explicit colors for all three congestion bands', () => {
    expect(CONGESTION_COLORS).toEqual({ LOW: '#168249', MEDIUM: '#d49113', HIGH: '#dc3545' });
  });
  it('uses bounded non-retina cached tiles without extra buffers', () => {
    expect(TILE_OPTIONS.url).toBe('https://tile.openstreetmap.org/{z}/{x}/{y}.png');
    expect(TILE_OPTIONS.attribution).toContain('OpenStreetMap contributors');
    expect(TILE_OPTIONS.detectRetina).toBe(false);
    expect(TILE_OPTIONS.keepBuffer).toBe(0);
    expect(TILE_OPTIONS.updateWhenIdle).toBe(true);
    expect(TILE_OPTIONS.updateWhenZooming).toBe(false);
    expect(TILE_OPTIONS.referrerPolicy).toBe('strict-origin-when-cross-origin');
    expect(TILE_OPTIONS.maxZoom - TILE_OPTIONS.minZoom).toBe(1);
  });
  it('has finite independent schematic/geographic geometry for every approach', () => {
    APPROACHES.forEach(a => {
      expect(geometryFor(a, 'schematic')).not.toEqual(geometryFor(a, 'osm'));
      expect(geometryFor(a, 'osm').road.flat().every(Number.isFinite)).toBe(true);
    });
  });
  it.each(['unknown-class', 'missing-approach', 'duplicate-approach', 'unknown-phase', 'skipped-clock', 'negative-queue', 'future-snapshot', 'nonfinite', 'clearance-skip', 'wrong-reason'])('rejects %s rather than substituting traffic values', failure => {
    const data = structuredClone(replay);
    const first = data.frames[0];
    if (failure === 'unknown-class') first.approaches[0].congestion_level = 'UNKNOWN';
    if (failure === 'missing-approach') first.approaches.pop();
    if (failure === 'duplicate-approach') first.approaches[1].approach_id = first.approaches[0].approach_id;
    if (failure === 'unknown-phase') first.current_phase = 'both_green';
    if (failure === 'skipped-clock') data.frames[1].timestamp_seconds += 1;
    if (failure === 'negative-queue') first.approaches[0].queue_length_vehicles = -1;
    if (failure === 'future-snapshot') first.observed_at_seconds = 190;
    if (failure === 'nonfinite') first.approaches[0].mean_wait_seconds = Infinity;
    if (failure === 'clearance-skip') { first.current_phase = 'ns_yellow'; first.seconds_in_phase = 0; data.frames[1].current_phase = 'all_red_to_ew'; data.frames[1].seconds_in_phase = 0; }
    if (failure === 'wrong-reason') first.controller_reason = {};
    expect(() => validateReplay(data)).toThrow();
  });
});
