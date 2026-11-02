import { Component, Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { CRS } from 'leaflet';
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet';
import { CONGESTION_COLORS, EXAMPLE_JUNCTION, geometryFor, lampFor, LAMP_COLORS, TILE_OPTIONS } from '../mapModel.js';

function ResizeMap() {
  const map = useMap();
  useEffect(() => {
    if (!globalThis.ResizeObserver) return undefined;
    const observer = new ResizeObserver(() => map.invalidateSize({ pan: false }));
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);
  return null;
}

export class MapBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div role="alert" className="message error">The map could not render. The recorded approach table and signal lamps below remain available. Reload the page to retry.</div>;
    return this.props.children;
  }
}

export default function JunctionMap({ frame }) {
  const [mode, setMode] = useState('osm');
  const [tiles, setTiles] = useState('loading');
  const [notice, setNotice] = useState('');
  const fallback = useCallback((reason) => {
    setMode('schematic');
    setTiles('unavailable');
    setNotice(reason);
  }, []);
  const tileEvents = useMemo(() => ({
    load: () => setTiles('ready'),
    tileerror: () => fallback('OpenStreetMap tiles could not load. Showing the offline schematic; simulation data is unchanged.'),
  }), [fallback]);
  useEffect(() => {
    if (mode !== 'osm' || tiles !== 'loading') return undefined;
    const timer = setTimeout(() => fallback('Basemap loading timed out. Showing the offline schematic; no automatic tile retries.'), 8000);
    return () => clearTimeout(timer);
  }, [mode, tiles, fallback]);
  const changeMode = () => {
    if (mode === 'osm') {
      setMode('schematic'); setTiles('idle'); setNotice('Offline schematic selected. No map tiles are requested in this mode.');
    } else {
      setNotice(''); setTiles('loading'); setMode('osm');
    }
  };
  return <div className="map-region">
    <div className="map-toolbar">
      <span className="mode-label">{mode === 'osm' ? 'OPENSTREETMAP / EXAMPLE LOCATION' : 'OFFLINE / SCHEMATIC'}</span>
      <button type="button" onClick={changeMode}>{mode === 'osm' ? 'Use offline schematic' : 'Load OpenStreetMap'}</button>
    </div>
    {notice && <p role="status" className="message map-notice">{notice}</p>}
    <div className="map-shell" aria-label="Virtual junction map" aria-busy={mode === 'osm' && tiles === 'loading'}>
      <div className="map-simulation-label">SIMULATED DATA</div>
      {mode === 'osm' && tiles === 'loading' && <div role="status" className="tile-loading">Loading basemap…</div>}
      <MapBoundary key={mode}>
        <MapContainer key={mode} center={mode === 'osm' ? EXAMPLE_JUNCTION.center : [50, 50]}
          crs={mode === 'osm' ? CRS.EPSG3857 : CRS.Simple} zoom={mode === 'osm' ? 17 : 2}
          minZoom={mode === 'osm' ? 17 : 1} maxZoom={mode === 'osm' ? 18 : 3}
          maxBounds={mode === 'osm' ? EXAMPLE_JUNCTION.bounds : [[-30, -60], [130, 160]]}
          maxBoundsViscosity={1} scrollWheelZoom={false} doubleClickZoom={false} touchZoom={false}
          boxZoom={false} fadeAnimation={false} zoomAnimation={false} attributionControl={true}>
          <ResizeMap />
          {mode === 'osm' && <TileLayer {...TILE_OPTIONS} bounds={EXAMPLE_JUNCTION.bounds} eventHandlers={tileEvents} />}
          {frame.approaches.map(row => {
            const shape = geometryFor(row.approach_id, mode);
            const lamp = lampFor(frame.current_phase, row.approach_id);
            return <Fragment key={row.approach_id}>
              <Polyline positions={shape.road} pathOptions={{ color: '#ffffff', weight: 14, opacity: .9 }} interactive={false} />
              <Polyline positions={shape.road} pathOptions={{ color: CONGESTION_COLORS[row.congestion_level], weight: 8, opacity: .95 }}>
                <Tooltip>{row.approach_id}: {row.congestion_level} congestion · {row.queue_length_vehicles} queued (synthetic snapshot)</Tooltip>
              </Polyline>
              <CircleMarker center={shape.lamp} radius={9} pathOptions={{ color: '#172c32', weight: 4, fillColor: LAMP_COLORS[lamp], fillOpacity: 1 }}>
                <Tooltip>{row.approach_id} virtual signal: {lamp} · recorded phase, not congestion</Tooltip>
              </CircleMarker>
            </Fragment>;
          })}
        </MapContainer>
      </MapBoundary>
    </div>
    <p className="caption">{mode === 'osm' ? <>Illustrative location: <a href={EXAMPLE_JUNCTION.source} target="_blank" rel="noreferrer">{EXAMPLE_JUNCTION.name}</a>. Overlays are approximate schematic approaches, not surveyed roads or Berlin traffic.</> : 'Abstract four-approach junction. Coordinates are schematic; no geographic location or tiles are needed.'}</p>
    <p className="attribution">Basemap when enabled: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>. <a href="https://www.openstreetmap.org/fixthemap" target="_blank" rel="noreferrer">Report a map issue</a>.</p>
  </div>;
}
