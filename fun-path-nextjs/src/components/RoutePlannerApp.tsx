'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  ArrowRight,
  BarChart3,
  Crosshair,
  LocateFixed,
  Map as MapIcon,
  MapPin,
  MousePointer2,
  Route as RouteIcon,
  Sparkles,
  Wind,
} from 'lucide-react';
import AddressInput from '@/components/AddressInput';
import RouteActions from '@/components/RouteActions';
import RouteAnalysis from '@/components/RouteAnalysis';
import RouteComparison from '@/components/RouteComparison';
import RouteMap from '@/components/RouteMap';
import ModeSwitch, { AppMode } from '@/components/ModeSwitch';
import { Coordinate, Route, RouteRequest, RouteResponse, RouteType } from '@/types/route';

interface RoutePlannerAppProps {
  onModeChange: (mode: AppMode) => void;
}

type RouteView = 'map' | 'comparison' | 'analysis';

const routeTypeCopy: Record<RouteType, { label: string; description: string }> = {
  scenic: { label: 'Scenic & fun', description: 'Interesting streets, paths and pleasant detours' },
  nature: { label: 'Parks & nature', description: 'Prefer green areas, water and quieter trails' },
  shopping: { label: 'Shops & cafés', description: 'Markets, lively streets and places to stop' },
  balanced: { label: 'Balanced', description: 'A practical mix of speed and enjoyment' },
  fastest: { label: 'Fastest', description: 'The most direct walk to your destination' },
  all: { label: 'Compare all', description: 'Generate every route style side by side' },
};

export default function RoutePlannerApp({ onModeChange }: RoutePlannerAppProps) {
  const [start, setStart] = useState<Coordinate>({ lat: 58.508594, lng: 15.487358 });
  const [end, setEnd] = useState<Coordinate>({ lat: 58.490666, lng: 15.498153 });
  const [startInput, setStartInput] = useState('58.508594, 15.487358');
  const [endInput, setEndInput] = useState('58.490666, 15.498153');
  const [routeType, setRouteType] = useState<RouteType>('scenic');
  const [routes, setRoutes] = useState<Route[]>([]);
  const [selectedRoute, setSelectedRoute] = useState<Route | null>(null);
  const [view, setView] = useState<RouteView>('map');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickingDestination, setPickingDestination] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const parse = (value: string | null) => {
      if (!value) return null;
      const [lat, lng] = value.split(',').map(Number);
      return Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : null;
    };
    const urlStart = parse(params.get('start'));
    const urlEnd = parse(params.get('end'));
    if (urlStart) setStart(urlStart);
    if (urlEnd) setEnd(urlEnd);
  }, []);

  useEffect(() => setStartInput(`${start.lat}, ${start.lng}`), [start]);
  useEffect(() => setEndInput(`${end.lat}, ${end.lng}`), [end]);

  function updateCoordinate(value: string, setter: (coordinate: Coordinate) => void, inputSetter: (value: string) => void) {
    inputSetter(value);
    const [lat, lng] = value.split(/[,\s]+/).map(Number);
    if (Number.isFinite(lat) && Number.isFinite(lng)) setter({ lat, lng });
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setError('Location is not available in this browser.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => setStart({ lat: coords.latitude, lng: coords.longitude }),
      () => setError('We could not access your location. Enter a start point instead.'),
      { enableHighAccuracy: false, timeout: 8000 },
    );
  }

  const chooseDestination = useCallback((coordinate: Coordinate) => {
    setEnd(coordinate);
    setRoutes([]);
    setSelectedRoute(null);
    setError(null);
    setPickingDestination(false);
  }, []);

  function beginMapPick() {
    setView('map');
    setPickingDestination(true);
  }

  async function calculateRoutes() {
    setLoading(true);
    setError(null);
    try {
      const request: RouteRequest = { start, end, route_type: routeType };
      const response = await fetch('/api/routes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });
      const data: RouteResponse = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || 'Could not calculate routes.');
      setRoutes(data.routes);
      setSelectedRoute(data.routes[0] ?? null);
      setView('map');
    } catch (routeError) {
      setError(routeError instanceof Error ? routeError.message : 'Route calculation failed.');
    } finally {
      setLoading(false);
    }
  }

  const selectedIndex = selectedRoute ? routes.findIndex((route) => route.name === selectedRoute.name) : -1;

  return (
    <main className="route-app">
      <header className="topbar route-topbar">
        <a className="brand" href="#" aria-label="Hush home">
          <span className="brand-mark"><Wind size={19} /></span>
          <span>HUSH</span><span className="brand-dot">•</span>
        </a>
        <ModeSwitch mode="routes" onChange={onModeChange} />
        <div className="route-header-note"><RouteIcon size={15} /> Path planner</div>
      </header>

      <section className="route-workspace">
        <div className="route-layout">
          <aside className="route-sidebar">
            <section className="route-card route-form-card">
              <div className="route-card-heading">
                <span className="step-number">01</span>
                <div><b>Plan your walk</b><small>Set two points and a route mood</small></div>
              </div>

              <div className="route-field">
                <label><span className="point-dot start" /> Start</label>
                <AddressInput placeholder="Search start address" onLocationSelect={setStart} />
                <div className="coordinate-field">
                  <Crosshair size={14} />
                  <input value={startInput} onChange={(event) => updateCoordinate(event.target.value, setStart, setStartInput)} aria-label="Start coordinates" />
                </div>
                <button className="route-secondary-button" onClick={useCurrentLocation}><LocateFixed size={15} /> Use my location</button>
              </div>

              <div className="route-connector" />

              <div className="route-field">
                <label><span className="point-dot end" /> Destination</label>
                <AddressInput placeholder="Search destination" onLocationSelect={chooseDestination} />
                <div className="coordinate-field">
                  <Crosshair size={14} />
                  <input value={endInput} onChange={(event) => {
                    updateCoordinate(event.target.value, chooseDestination, setEndInput);
                    setPickingDestination(false);
                  }} aria-label="Destination coordinates" />
                </div>
                <button className={`map-pick-button ${pickingDestination ? 'active' : ''}`} onClick={pickingDestination ? () => setPickingDestination(false) : beginMapPick}>
                  <MousePointer2 size={15} /> {pickingDestination ? 'Cancel map selection' : 'Pick destination on map'}
                </button>
              </div>

              <div className="route-field route-style-field">
                <label>Route style</label>
                <select value={routeType} onChange={(event) => {
                  setRouteType(event.target.value as RouteType);
                  setRoutes([]);
                  setSelectedRoute(null);
                }}>
                  {Object.entries(routeTypeCopy).map(([value, copy]) => <option value={value} key={value}>{copy.label}</option>)}
                </select>
                <small>{routeTypeCopy[routeType].description}</small>
              </div>

              <button className="route-primary-button" onClick={calculateRoutes} disabled={loading}>
                {loading ? <><span className="search-loader" /> Finding your route…</> : <>{routeType === 'all' ? 'Compare route styles' : 'Find this route'} <ArrowRight size={16} /></>}
              </button>
              {error && <div className="route-error">{error}</div>}
            </section>

            {routes.length > 0 && (
              <section className="route-card route-results-card">
                <div className="route-card-heading compact">
                  <span className="step-number">02</span>
                  <div><b>{routes.length} route{routes.length === 1 ? '' : 's'} ready</b><small>Choose one to inspect or export</small></div>
                </div>
                <div className="route-choice-list">
                  {routes.map((route, index) => (
                    <button key={`${route.name}-${index}`} className={selectedIndex === index ? 'selected' : ''} onClick={() => setSelectedRoute(route)}>
                      <span className="route-swatch" style={{ backgroundColor: route.color }} />
                      <span><b>{route.name.replaceAll('_', ' ')}</b><small>{(route.stats.distance / 1000).toFixed(2)} km · {Math.round(route.stats.estimated_time)} min</small></span>
                      <strong>{route.stats.fun_score.toFixed(1)}</strong>
                    </button>
                  ))}
                </div>
              </section>
            )}

            {selectedRoute && <div className="hush-route-actions"><RouteActions route={selectedRoute} /></div>}
          </aside>

          <section className={`route-main route-view-${view}`}>
            <div className="route-view-tabs" role="tablist" aria-label="Route result view">
              <button className={view === 'map' ? 'active' : ''} onClick={() => setView('map')}><MapIcon size={15} /> Map</button>
              <button className={view === 'comparison' ? 'active' : ''} onClick={() => setView('comparison')}><BarChart3 size={15} /> Compare</button>
              <button className={view === 'analysis' ? 'active' : ''} onClick={() => setView('analysis')}><Sparkles size={15} /> Analysis</button>
            </div>

            {view === 'map' && (
              <div className="route-map-card" id="route-map-panel">
                <RouteMap
                  routes={routes}
                  start={start}
                  end={end}
                  className={`route-map-canvas ${pickingDestination ? 'is-picking' : ''}`}
                  pickingDestination={pickingDestination}
                  onDestinationSelect={chooseDestination}
                />
                {pickingDestination ? (
                  <div className="route-map-pick-banner"><MousePointer2 size={15} /> Click anywhere to set your destination</div>
                ) : routes.length === 0 ? (
                  <div className="route-map-hint">
                    <span><MapPin size={17} /></span>
                    <div><b>Your route will appear here</b><small>Use “Pick destination on map” or enter an address.</small></div>
                  </div>
                ) : null}
              </div>
            )}
            {view === 'comparison' && (routes.length ? <RouteComparison routes={routes} /> : <RouteEmptyState icon={BarChart3} text="Generate routes to compare them." />)}
            {view === 'analysis' && (selectedRoute ? <RouteAnalysis route={selectedRoute} /> : <RouteEmptyState icon={Sparkles} text="Choose a generated route to see its analysis." />)}
          </section>
        </div>
      </section>
    </main>
  );
}

function RouteEmptyState({ icon: Icon, text }: { icon: typeof MapPin; text: string }) {
  return <div className="route-card route-tab-empty"><Icon size={28} /><p>{text}</p></div>;
}
