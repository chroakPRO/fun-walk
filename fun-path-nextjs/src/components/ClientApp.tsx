'use client';

import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowUpRight,
  Binoculars,
  Building2,
  Car,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Crosshair,
  ExternalLink,
  Footprints,
  Leaf,
  LocateFixed,
  MapPin,
  Navigation,
  Ruler,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trees,
  Waves,
  Wind,
  X,
} from 'lucide-react';
import SpotMap from '@/components/SpotMap';
import ModeSwitch, { AppMode } from '@/components/ModeSwitch';
import RoutePlannerApp from '@/components/RoutePlannerApp';
import { CitySuggestion, CitySuggestionResponse, SmokeSpot, SpotSearchResponse } from '@/types/spot';

async function readJsonResponse<T>(response: Response, fallbackMessage: string): Promise<T> {
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.toLowerCase().includes('application/json')) {
    await response.text();
    throw new Error(fallbackMessage);
  }
  return response.json() as Promise<T>;
}

const DEMO_SPOTS: SmokeSpot[] = [
  {
    id: 'demo-1', name: 'Ramberget west ledge', kind: 'viewpoint', lat: 57.7147, lng: 11.9258,
    privacy: 92, quiet: 88, carAccess: 'Difficult', walkMinutes: 14,
    summary: 'A tucked-away rocky shelf above the tree line, away from the main lookout.',
    why: ['Set back from the marked viewpoint', 'Natural wind cover from the ridge', 'No direct vehicle access'],
    features: ['View', 'Rock seat', 'Wind cover'],
  },
  {
    id: 'demo-2', name: 'Saltholmen outer rocks', kind: 'waterside', lat: 57.6587, lng: 11.8437,
    privacy: 86, quiet: 81, carAccess: 'Limited', walkMinutes: 11,
    summary: 'Open waterfront rocks beyond the busiest ferry approaches.',
    why: ['Sightlines make it easy to keep your distance', 'Sea breeze disperses smoke', 'A short walk from the nearest road'],
    features: ['Waterfront', 'Sea breeze', 'Sunset'],
  },
  {
    id: 'demo-3', name: 'Delsjön forest edge', kind: 'nature', lat: 57.6902, lng: 12.0548,
    privacy: 83, quiet: 91, carAccess: 'Difficult', walkMinutes: 18,
    summary: 'A calm forest edge with space to step away from the main exercise loop.',
    why: ['Dense vegetation provides separation', 'Far from parking areas', 'Low road-noise exposure'],
    features: ['Forest', 'Sheltered', 'Low noise'],
  },
  {
    id: 'demo-4', name: 'Klippan river steps', kind: 'waterside', lat: 57.6915, lng: 11.9098,
    privacy: 78, quiet: 73, carAccess: 'Limited', walkMinutes: 7,
    summary: 'Wide stone edges beside the river with multiple places to sit apart.',
    why: ['Several separate seating levels', 'Good airflow along the river', 'Outside the busiest waterfront stretch'],
    features: ['River', 'Seating', 'Open sky'],
  },
  {
    id: 'demo-5', name: 'Änggårdsbergen clearing', kind: 'nature', lat: 57.6762, lng: 11.9539,
    privacy: 95, quiet: 94, carAccess: 'Difficult', walkMinutes: 22,
    summary: 'A small clearing deeper inside the nature reserve trail network.',
    why: ['Long walk-in naturally reduces traffic', 'Woodland buffer in every direction', 'No nearby through-road'],
    features: ['Clearing', 'Forest', 'Very quiet'],
  },
  {
    id: 'demo-6', name: 'Keillers park north slope', kind: 'park', lat: 57.7191, lng: 11.9348,
    privacy: 72, quiet: 79, carAccess: 'Limited', walkMinutes: 9,
    summary: 'A less-used grassy slope below the summit and away from the main path.',
    why: ['Away from the summit gathering point', 'Slope blocks nearby path visibility', 'Room to keep distance'],
    features: ['Grass', 'Evening sun', 'City view'],
  },
];

const kindIcon = {
  viewpoint: Binoculars,
  nature: Trees,
  waterside: Waves,
  shelter: Wind,
  park: Leaf,
  picnic: Sparkles,
  playground: Sparkles,
  cemetery: Trees,
};

export default function ClientApp() {
  const [mode, setMode] = useState<AppMode>('spots');
  return mode === 'routes' ? <RoutePlannerApp onModeChange={setMode} /> : <SmokeSpotsApp onModeChange={setMode} />;
}

function SmokeSpotsApp({ onModeChange }: { onModeChange: (mode: AppMode) => void }) {
  const [query, setQuery] = useState('Gothenburg');
  const [city, setCity] = useState({ name: 'Gothenburg', country: 'Sweden', lat: 57.7089, lng: 11.9746 });
  const [spots, setSpots] = useState<SmokeSpot[]>(DEMO_SPOTS);
  const [selectedId, setSelectedId] = useState(DEMO_SPOTS[0].id);
  const [loading, setLoading] = useState(false);
  const [calculatingSpots, setCalculatingSpots] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [minPrivacy, setMinPrivacy] = useState(70);
  const [walkInOnly, setWalkInOnly] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [listOpen, setListOpen] = useState(true);
  const [mapFocus, setMapFocus] = useState<{ lat: number; lng: number; zoom: number; token: number } | null>(null);
  const [citySuggestions, setCitySuggestions] = useState<CitySuggestion[]>([]);
  const [citySuggestionsOpen, setCitySuggestionsOpen] = useState(false);
  const [citySuggestionsLoading, setCitySuggestionsLoading] = useState(false);
  const [citySuggestionIndex, setCitySuggestionIndex] = useState(-1);
  const citySearchRef = useRef<HTMLFormElement>(null);
  const citySearchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const citySuggestionRequestRef = useRef(0);

  const filteredSpots = useMemo(() => spots
    .filter((spot) => spot.privacy >= minPrivacy)
    .filter((spot) => !walkInOnly || spot.carAccess !== 'Easy')
    .sort((a, b) => b.privacy - a.privacy), [spots, minPrivacy, walkInOnly]);

  const selected = selectedId === '' ? null : filteredSpots.find((spot) => spot.id === selectedId) ?? filteredSpots[0] ?? null;

  async function performCitySearch(cityQuery = query, resolvedCity?: CitySuggestion) {
    const trimmedQuery = cityQuery.trim();
    if (!trimmedQuery) return;
    setLoading(true);
    setCalculatingSpots(false);
    setError(null);
    setCitySuggestionsOpen(false);
    setCitySuggestions([]);
    citySuggestionRequestRef.current += 1;
    if (citySearchTimeoutRef.current) clearTimeout(citySearchTimeoutRef.current);
    try {
      let targetCity = resolvedCity;
      if (!targetCity) {
        const cityResponse = await fetch('/api/search-cities', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: trimmedQuery, limit: 1 }),
        });
        const cityData = await readJsonResponse<CitySuggestionResponse>(
          cityResponse,
          'The city search service is temporarily unavailable. Please try again.',
        );
        targetCity = cityData.results?.[0];
        if (!cityResponse.ok || !cityData.success || !targetCity) {
          throw new Error(cityData.error || `We couldn't find “${trimmedQuery}”. Try a city and country.`);
        }
      }

      setCity({ name: targetCity.name, country: targetCity.country, lat: targetCity.lat, lng: targetCity.lng });
      setSpots([]);
      setSelectedId('');
      setListOpen(true);
      setMapFocus({ lat: targetCity.lat, lng: targetCity.lng, zoom: 12, token: Date.now() });
      setCalculatingSpots(true);
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));

      const response = await fetch('/api/find-spots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          city: targetCity.displayName,
          location: {
            name: targetCity.name,
            country: targetCity.country,
            lat: targetCity.lat,
            lng: targetCity.lng,
          },
        }),
      });
      const data = await readJsonResponse<SpotSearchResponse>(
        response,
        'The spot search service is temporarily unavailable. Please try again.',
      );
      if (!response.ok || !data.success || !data.city || !data.spots?.length) {
        throw new Error(data.error || 'No suitable public spots found here yet.');
      }
      setCity(data.city);
      setSpots(data.spots);
      setSelectedId(data.spots[0].id);
      setListOpen(true);
      setCitySuggestionsOpen(false);
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : 'Search failed. Please try another city.');
    } finally {
      setCalculatingSpots(false);
      setLoading(false);
    }
  }

  function searchCity(event: FormEvent) {
    event.preventDefault();
    void performCitySearch();
  }

  async function searchCitySuggestions(searchQuery: string) {
    const requestId = ++citySuggestionRequestRef.current;
    const trimmedQuery = searchQuery.trim();
    if (trimmedQuery.length < 2) {
      setCitySuggestions([]);
      setCitySuggestionsOpen(false);
      setCitySuggestionsLoading(false);
      return;
    }

    setCitySuggestionsLoading(true);
    try {
      const response = await fetch('/api/search-cities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: trimmedQuery, limit: 6 }),
      });
      const data = await readJsonResponse<CitySuggestionResponse>(
        response,
        'City suggestions are temporarily unavailable.',
      );
      if (!response.ok || !data.success) throw new Error(data.error || 'City suggestions failed.');
      if (requestId !== citySuggestionRequestRef.current) return;
      setCitySuggestions(data.results ?? []);
      setCitySuggestionsOpen(Boolean(data.results?.length));
    } catch {
      if (requestId !== citySuggestionRequestRef.current) return;
      setCitySuggestions([]);
      setCitySuggestionsOpen(false);
    } finally {
      if (requestId === citySuggestionRequestRef.current) setCitySuggestionsLoading(false);
    }
  }

  function handleCityInputChange(value: string) {
    setQuery(value);
    setCitySuggestionIndex(-1);

    if (citySearchTimeoutRef.current) clearTimeout(citySearchTimeoutRef.current);
    citySearchTimeoutRef.current = setTimeout(() => {
      void searchCitySuggestions(value);
    }, 250);
  }

  function chooseCitySuggestion(suggestion: CitySuggestion) {
    setQuery(suggestion.displayName);
    setCitySuggestionsOpen(false);
    setCitySuggestionIndex(-1);
    void performCitySearch(suggestion.displayName, suggestion);
  }

  function handleCityInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!citySuggestionsOpen || citySuggestions.length === 0) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setCitySuggestionIndex((index) => Math.min(index + 1, citySuggestions.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setCitySuggestionIndex((index) => Math.max(index - 1, -1));
    } else if (event.key === 'Enter' && citySuggestionIndex >= 0) {
      event.preventDefault();
      chooseCitySuggestion(citySuggestions[citySuggestionIndex]);
    } else if (event.key === 'Escape') {
      setCitySuggestionsOpen(false);
      setCitySuggestionIndex(-1);
    }
  }

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (citySearchRef.current && !citySearchRef.current.contains(event.target as Node)) {
        setCitySuggestionsOpen(false);
        setCitySuggestionIndex(-1);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      if (citySearchTimeoutRef.current) clearTimeout(citySearchTimeoutRef.current);
    };
  }, []);

  const selectSpot = useCallback((spot: SmokeSpot) => {
    setSelectedId(spot.id);
    if (window.innerWidth < 768) setListOpen(false);
  }, []);

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setError('Location is not available in this browser.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => setMapFocus({ lat: coords.latitude, lng: coords.longitude, zoom: 14, token: Date.now() }),
      () => setError('We could not access your location. You can still search by city.'),
      { enableHighAccuracy: false, timeout: 8000 },
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="Hush home">
          <span className="brand-mark"><Wind size={19} strokeWidth={2.2} /></span>
          <span>HUSH</span>
          <span className="brand-dot">•</span>
        </a>

        <ModeSwitch mode="spots" onChange={onModeChange} />

        <form className={`city-search ${citySuggestionsOpen ? 'is-open' : ''}`} onSubmit={searchCity} ref={citySearchRef}>
          <Search size={18} aria-hidden="true" />
          <input
            value={query}
            onChange={(event) => handleCityInputChange(event.target.value)}
            onFocus={() => {
              if (citySuggestions.length > 0) setCitySuggestionsOpen(true);
            }}
            onKeyDown={handleCityInputKeyDown}
            placeholder="Search a city"
            aria-label="Search a city"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={citySuggestionsOpen}
            aria-controls="city-suggestions"
          />
          <button type="submit" disabled={loading}>
            {loading ? <span className="search-loader" /> : 'Find spots'}
          </button>
          {(citySuggestionsOpen || citySuggestionsLoading) && (
            <div id="city-suggestions" className="city-suggestion-menu" role="listbox" aria-label="City suggestions">
              {citySuggestionsLoading ? (
                <div className="city-suggestion-status"><span className="search-loader" /> Searching cities</div>
              ) : citySuggestions.map((suggestion, index) => (
                <button
                  type="button"
                  key={suggestion.id}
                  className={index === citySuggestionIndex ? 'active' : ''}
                  onMouseEnter={() => setCitySuggestionIndex(index)}
                  onClick={() => chooseCitySuggestion(suggestion)}
                  role="option"
                  aria-selected={index === citySuggestionIndex}
                >
                  <MapPin size={14} />
                  <span><b>{suggestion.name}</b><small>{suggestion.country}</small></span>
                </button>
              ))}
            </div>
          )}
        </form>

        <div className="header-actions">
          <button className="icon-button" title="About privacy estimates" aria-label="About privacy estimates"><CircleHelp size={19} /></button>
          <button className="avatar" aria-label="Profile">C</button>
        </div>
      </header>

      <section className="workspace">
        <aside className={`spot-panel ${listOpen ? 'is-open' : ''}`}>
          <div className="panel-heading">
            <div>
              <p className="eyebrow"><MapPin size={13} /> {city.country}</p>
              <h1>Quiet spots in<br />{city.name}</h1>
              <p className="intro">Low-key public places, ranked by privacy and calm.</p>
            </div>
            <button className="mobile-close" onClick={() => setListOpen(false)} aria-label="Close list"><X size={19} /></button>
          </div>

          <div className="filter-row">
            <button className={filtersOpen ? 'active' : ''} onClick={() => setFiltersOpen(!filtersOpen)}>
              <SlidersHorizontal size={15} /> Filters
              {(minPrivacy > 70 || walkInOnly) && <span className="filter-count">{Number(minPrivacy > 70) + Number(walkInOnly)}</span>}
            </button>
            <span>{filteredSpots.length} spots</span>
          </div>

          {filtersOpen && (
            <div className="filter-box">
              <label>
                <span>Minimum privacy <b>{minPrivacy}%</b></span>
                <input type="range" min="50" max="95" step="5" value={minPrivacy} onChange={(e) => setMinPrivacy(Number(e.target.value))} />
              </label>
              <label className="check-row">
                <input type="checkbox" checked={walkInOnly} onChange={(e) => setWalkInOnly(e.target.checked)} />
                <span className="fake-check">{walkInOnly && <Check size={13} />}</span>
                Avoid easy car access
              </label>
            </div>
          )}

          {error && <div className="error-note">{error}</div>}

          <div className="spot-list">
            {filteredSpots.map((spot, index) => {
              const Icon = kindIcon[spot.kind];
              const isSelected = selected?.id === spot.id;
              return (
                <button className={`spot-card ${isSelected ? 'selected' : ''}`} key={spot.id} onClick={() => selectSpot(spot)}>
                  <span className="rank">{String(index + 1).padStart(2, '0')}</span>
                  <span className="spot-copy">
                    <span className="spot-title-row">
                      <span className="spot-title"><Icon size={16} /> {spot.name}</span>
                      <ChevronRight size={17} />
                    </span>
                    {spot.placeType && <span className="spot-place-type">{spot.placeType}</span>}
                    <span className="spot-summary">{spot.summary}</span>
                    <span className="score-row">
                      <span className="privacy-pill"><ShieldCheck size={13} /> {spot.privacy}% private</span>
                      {spot.treeCoverPercent != null && <span><Trees size={13} /> {spot.treeCoverPercent}% canopy</span>}
                      <span><Car size={13} /> {spot.carAccess}</span>
                      <span>{spot.walkMinutes == null ? (spot.accessNote ?? 'Road access unverified') : `~${spot.walkMinutes} min from road`}</span>
                    </span>
                  </span>
                </button>
              );
            })}
            {filteredSpots.length === 0 && (
              <div className="empty-state"><Trees size={28} /><b>{calculatingSpots ? 'Analyzing the city' : 'No spots match'}</b><span>{calculatingSpots ? 'Checking satellite cover, roads, paths, and buildings…' : 'Try lowering the privacy filter.'}</span></div>
            )}
          </div>

          <div className="panel-footnote">
            <ShieldCheck size={15} />
            <span>Privacy is estimated from map features—not live foot traffic. Follow local rules and keep your distance from others.</span>
          </div>
        </aside>

        <div className="map-wrap">
          <SpotMap spots={filteredSpots} selectedId={selected?.id ?? null} city={city} focus={mapFocus} onSelect={selectSpot} />

          {calculatingSpots && (
            <div className="map-analysis-status" role="status" aria-live="polite">
              <span className="map-analysis-spinner" />
              <span><b>Finding hidden locations</b><small>Checking canopy, roads, paths, and buildings</small></span>
            </div>
          )}

          <div className="map-city-label">
            <span>{city.name}</span>
            <small>{city.country}</small>
          </div>

          <div className="map-controls">
            <button onClick={useCurrentLocation} aria-label="Use my location" title="Use my location"><LocateFixed size={18} /></button>
            <button onClick={() => setMapFocus({ lat: city.lat, lng: city.lng, zoom: 12, token: Date.now() })} aria-label="Recenter map" title="Recenter map"><Crosshair size={18} /></button>
          </div>

          <button className="mobile-list-toggle" onClick={() => setListOpen(true)}><ChevronLeft size={16} /> {filteredSpots.length} spots</button>

          {selected && (
            <article className="detail-card" key={selected.id}>
              <button className="detail-close" onClick={() => setSelectedId('')} aria-label="Close details"><X size={17} /></button>
              <div className="detail-topline">
                <span className="privacy-score"><ShieldCheck size={14} /> {selected.privacy}% privacy</span>
                <span className="quiet-score">{selected.quiet}% calm</span>
                {selected.placeType && <span className="place-type-score">{selected.placeType}</span>}
              </div>
              <h2>{selected.name}</h2>
              <p>{selected.summary}</p>
              <div className="detail-grid">
                <div>
                  <span>WHY IT WORKS</span>
                  <ul>{selected.why.map((reason) => <li key={reason}><Check size={13} />{reason}</li>)}</ul>
                </div>
                <div className="access-block">
                  <span>ACCESS</span>
                  <b><Car size={15} /> {selected.carAccess === 'Unknown' ? 'Car access unknown' : `${selected.carAccess} by car`}</b>
                  <small>{selected.accessNote ?? (selected.walkMinutes == null ? 'Road access has not been verified' : `About ${selected.walkMinutes} min walk from the nearest road`)}</small>
                </div>
              </div>
              {selected.evidence && (
                <section className="site-evidence" aria-label="Measured site evidence">
                  <span className="site-evidence-title">MEASURED SITE EVIDENCE</span>
                  <div className="site-evidence-grid">
                    {selected.evidence.treeCanopyPercent != null && (
                      <div><Trees size={15} /><span><b>{selected.evidence.treeCanopyPercent}%</b><small>tree canopy</small></span></div>
                    )}
                    {selected.evidence.eyeLevelVegetationPercent != null && (
                      <div><Leaf size={15} /><span><b>{selected.evidence.eyeLevelVegetationPercent}%</b><small>eye-level cover</small></span></div>
                    )}
                    {selected.evidence.nearestRoadMeters != null && (
                      <div><Car size={15} /><span><b>{selected.evidence.nearestRoadMeters} m</b><small>nearest road</small></span></div>
                    )}
                    {selected.evidence.nearestBuildingMeters != null && (
                      <div><Building2 size={15} /><span><b>{selected.evidence.nearestBuildingMeters} m</b><small>nearest building</small></span></div>
                    )}
                    {selected.evidence.nearestPathMeters != null && (
                      <div><Footprints size={15} /><span><b>{selected.evidence.nearestPathMeters} m</b><small>nearest path</small></span></div>
                    )}
                    {selected.evidence.interiorClearanceMeters != null && (
                      <div><Ruler size={15} /><span><b>{selected.evidence.interiorClearanceMeters} m</b><small>inside area edge</small></span></div>
                    )}
                  </div>
                  <small className="site-evidence-source">Sources: {selected.evidence.sources.join(' · ')}</small>
                </section>
              )}
              <div className="feature-row">
                {selected.features.map((feature) => <span key={feature}>{feature}</span>)}
                <a className="spot-details-link"
                  href={`https://www.openstreetmap.org/?mlat=${selected.lat}&mlon=${selected.lng}#map=17/${selected.lat}/${selected.lng}`}
                  target="_blank" rel="noreferrer" title="Open this coordinate in OpenStreetMap"
                >Details <ArrowUpRight size={14} /></a>
              </div>
              <div className="spot-navigation-row">
                <span><Navigation size={13} /> Navigate there</span>
                <a
                  href={`https://www.google.com/maps/dir/?api=1&destination=${selected.lat},${selected.lng}&travelmode=walking`}
                  target="_blank" rel="noreferrer"
                  aria-label={`Navigate to ${selected.name} with Google Maps`}
                >Google Maps <ExternalLink size={12} /></a>
                <a
                  href={`https://maps.apple.com/?daddr=${selected.lat},${selected.lng}&dirflg=w`}
                  target="_blank" rel="noreferrer"
                  aria-label={`Navigate to ${selected.name} with Apple Maps`}
                >Apple Maps <ExternalLink size={12} /></a>
              </div>
            </article>
          )}
        </div>
      </section>
    </main>
  );
}
