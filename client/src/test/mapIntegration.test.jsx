import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import replay from '../../public/data/junction-replay.json';
import JunctionMap from '../components/JunctionMap.jsx';

it('mounts real Leaflet SVG road overlays, separate lamps and OSM attribution', () => {
  const frame = structuredClone(replay.frames[0]);
  frame.current_phase = 'ns_green';
  frame.approaches[0].congestion_level = 'HIGH';
  frame.approaches[1].congestion_level = 'MEDIUM';
  frame.approaches[2].congestion_level = 'LOW';
  const { container } = render(<JunctionMap frame={frame} />);
  expect(container.querySelector('.leaflet-container')).toBeInTheDocument();
  expect(container.querySelector('.leaflet-control-attribution')).toHaveTextContent('OpenStreetMap contributors');
  ['#168249', '#d49113', '#dc3545'].forEach(color => {
    expect(container.querySelector(`path[stroke="${color}"]`)).not.toBeNull();
  });
  expect(container.querySelectorAll('path[fill="#22c55e"]')).toHaveLength(2);
  expect(container.querySelectorAll('path[fill="#ef4444"]')).toHaveLength(2);
  // jsdom does not download tile images; dispatch a real TileLayer image error explicitly.
  const image = container.querySelector('img.leaflet-tile');
  expect(image).not.toBeNull();
  fireEvent.error(image);
  expect(screen.getByText('OFFLINE / SCHEMATIC')).toBeVisible();
  expect(container.querySelector('img.leaflet-tile')).toBeNull();
});
