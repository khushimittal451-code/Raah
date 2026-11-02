// Public illustrative location, not measured city traffic or surveyed road geometry.
export const EXAMPLE_JUNCTION = {
  name: 'Friedrichstraße × Unter den Linden, Berlin',
  center: [52.517, 13.389],
  bounds: [[52.513, 13.383], [52.521, 13.395]],
  source: 'https://www.openstreetmap.org/#map=18/52.5170/13.3890',
};
export const APPROACHES = ['north', 'south', 'east', 'west'];
export const PHASES = ['ns_green', 'ns_yellow', 'all_red_to_ew', 'ew_green', 'ew_yellow', 'all_red_to_ns'];
export const CONGESTION_COLORS = { LOW: '#168249', MEDIUM: '#d49113', HIGH: '#dc3545' };
export const LAMP_COLORS = { RED: '#ef4444', YELLOW: '#fbbf24', GREEN: '#22c55e' };
export const TILE_OPTIONS = Object.freeze({
  url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
  minZoom: 17, maxZoom: 18, noWrap: true, detectRetina: false,
  keepBuffer: 0, updateWhenIdle: true, updateWhenZooming: false,
  referrerPolicy: 'strict-origin-when-cross-origin',
});

export function lampFor(phase, approach) {
  if (!PHASES.includes(phase) || !APPROACHES.includes(approach)) throw new Error('Unknown virtual phase or approach');
  const axis = ['north', 'south'].includes(approach) ? 'ns' : 'ew';
  if (phase === `${axis}_green`) return 'GREEN';
  if (phase === `${axis}_yellow`) return 'YELLOW';
  return 'RED';
}

const SCHEMATIC = {
  north: { road: [[100, 50], [60, 50]], lamp: [57, 50] },
  south: { road: [[0, 50], [40, 50]], lamp: [43, 50] },
  east: { road: [[50, 100], [50, 60]], lamp: [50, 57] },
  west: { road: [[50, 0], [50, 40]], lamp: [50, 43] },
};
export function geometryFor(approach, mode) {
  const shape = SCHEMATIC[approach];
  if (!shape) throw new Error('Unknown approach');
  if (mode === 'schematic') return shape;
  const project = ([y, x]) => [52.517 + (y - 50) * .000022, 13.389 + (x - 50) * .000036];
  return { road: shape.road.map(project), lamp: project(shape.lamp) };
}

export function validateReplay(payload) {
  if (payload?.schema_version !== 'map-replay-v1' || payload.seed !== 57 ||
      typeof payload.controller !== 'string' || typeof payload.trace_id !== 'string' ||
      !Array.isArray(payload.frames) || !payload.frames.length) {
    throw new Error('Unsupported or missing synthetic replay');
  }
  payload.frames.forEach((frame, index) => {
    const previous = payload.frames[index - 1];
    const validNumber = (value, min, max) => typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
    if (!Number.isInteger(frame.timestamp_seconds) || frame.timestamp_seconds < 0 ||
        !PHASES.includes(frame.current_phase) || !Number.isInteger(frame.seconds_in_phase) || frame.seconds_in_phase < 0 ||
        frame.seconds_in_phase > frame.timestamp_seconds || !Number.isInteger(frame.observed_at_seconds) ||
        frame.observed_at_seconds % 10 !== 0 || typeof frame.controller_reason !== 'string' || typeof frame.prediction_status !== 'string' ||
        frame.observed_at_seconds < 0 || frame.observed_at_seconds > frame.timestamp_seconds ||
        frame.timestamp_seconds - frame.observed_at_seconds > 9 || !Array.isArray(frame.approaches) ||
        frame.approaches.length !== 4 || new Set(frame.approaches.map(a => a.approach_id)).size !== 4) {
      throw new Error('Invalid recorded frame; no substitute values displayed');
    }
    if (previous && (frame.timestamp_seconds !== previous.timestamp_seconds + 1 ||
        (frame.current_phase === previous.current_phase ? frame.seconds_in_phase !== previous.seconds_in_phase + 1 :
          frame.current_phase !== PHASES[(PHASES.indexOf(previous.current_phase) + 1) % PHASES.length] || frame.seconds_in_phase !== 0))) {
      throw new Error('Nonconsecutive clock or illegal recorded phase transition');
    }
    const green = frame.current_phase.endsWith('_green');
    const duration = green ? 60 : frame.current_phase.endsWith('_yellow') ? 3 : 1;
    if (frame.seconds_in_phase >= duration) throw new Error('Recorded phase exceeds its timing limit');
    if (previous && frame.current_phase !== previous.current_phase) {
      const elapsed = previous.seconds_in_phase + 1;
      if (previous.current_phase.endsWith('_green') ? elapsed < 15 || elapsed > 60 :
          elapsed !== (previous.current_phase.endsWith('_yellow') ? 3 : 1)) {
        throw new Error('Recorded transition violates clearance or minimum green');
      }
    }
    frame.approaches.forEach(row => {
      if (!APPROACHES.includes(row.approach_id) || !Object.hasOwn(CONGESTION_COLORS, row.congestion_level) ||
          !Number.isInteger(row.queue_length_vehicles) || !validNumber(row.queue_length_vehicles, 0, 10000) ||
          !validNumber(row.mean_wait_seconds, 0, 3600) ||
          (row.mean_speed_kmh !== null && !validNumber(row.mean_speed_kmh, 0, 160))) {
        throw new Error('Invalid approach measurements; no substitute colors displayed');
      }
    });
  });
  return payload;
}
