import { NextRequest, NextResponse } from 'next/server';
import { createHash } from 'node:crypto';
import { mkdir, readdir, readFile, rename, stat, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { SmokeSpot, SpotKind, SpotSearchResponse } from '@/types/spot';

type OsmElement = {
  type?: 'node' | 'way' | 'relation';
  id: number;
  lat?: number;
  lon?: number;
  center?: { lat: number; lon: number };
  geometry?: Array<{ lat: number; lon: number }>;
  members?: Array<{
    type?: 'node' | 'way' | 'relation';
    ref?: number;
    role?: string;
    geometry?: Array<{ lat: number; lon: number }>;
  }>;
  tags?: Record<string, string>;
};

type SpotCandidate = {
  element: OsmElement;
  spot: SmokeSpot;
  interiorClearanceMeters?: number;
  geometryHoles?: Array<Array<{ lat: number; lon: number }>>;
  searchAroundAnchor?: boolean;
  anchor?: { lat: number; lng: number };
  anchorDistanceMeters?: number;
  canopy?: {
    treeCoverPercent: number;
    denseCoverPercent: number;
    validPixelPercent: number;
  };
  vegetation?: {
    lowVegetationPercent: number;
    tallVegetationPercent: number;
    validPixelPercent: number;
  };
};

type TreeCoverResponse = {
  results?: Array<{
    id: string;
    tree_cover_percent: number;
    dense_cover_percent: number;
    valid_pixel_percent: number;
  }>;
};

type VegetationStructureResponse = {
  available?: boolean;
  results?: Array<{
    id: string;
    low_vegetation_percent: number;
    tall_vegetation_percent: number;
    valid_pixel_percent: number;
  }>;
};

const ACCESS_SEARCH_RADIUS_METERS = 180;
const PRIVACY_CONTEXT_RADIUS_METERS = 320;
const LANDMARK_SEARCH_RADIUS_METERS = 140;
const SPOT_SEARCH_RADIUS_METERS = 3200;
const WALKING_METERS_PER_MINUTE = 80;
const TRANSIT_SHELTER_RADIUS_METERS = 80;
const MIN_NMD_VALID_PERCENT = 50;
const SEARCH_CACHE_VERSION = 'v5-landmark-surroundings';
const SEARCH_CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const SEARCH_CACHE_STALE_MS = 30 * 24 * 60 * 60 * 1000;
const SEARCH_CACHE_MAX_FILES = 250;
const SEARCH_CACHE_DIR = process.env.SPOT_SEARCH_CACHE_DIR || path.join(process.cwd(), '.spot-cache');
let lastSearchCachePrune = 0;
const MAIN_ROAD_TYPES = new Set(['motorway', 'trunk', 'primary', 'secondary', 'tertiary']);
const DRIVABLE_ROAD_TYPES = new Set(['primary', 'secondary', 'tertiary', 'unclassified', 'residential', 'living_street', 'service', 'track', 'road']);
const WALKING_PATH_TYPES = new Set(['path', 'footway', 'pedestrian', 'cycleway', 'track']);
const THROUGH_ROAD_TYPES = new Set(['primary', 'secondary', 'tertiary', 'unclassified', 'residential', 'living_street', 'road']);

function isSwedishCountry(country: string) {
  const normalized = country.trim().toLocaleLowerCase('en');
  return normalized === 'sweden' || normalized === 'sverige' || normalized === 'se';
}

type SearchCacheEntry = {
  storedAt: number;
  response: SpotSearchResponse & { success: true; spots: SmokeSpot[] };
};

function searchCacheFilename(lat: number, lng: number, country: string) {
  const identity = [SEARCH_CACHE_VERSION, lat.toFixed(4), lng.toFixed(4), country.trim().toLocaleLowerCase('en')].join('|');
  const digest = createHash('sha256').update(identity).digest('hex');
  return path.join(SEARCH_CACHE_DIR, `${digest}.json`);
}

async function readSearchCache(lat: number, lng: number, country: string) {
  try {
    const entry = JSON.parse(await readFile(searchCacheFilename(lat, lng, country), 'utf8')) as SearchCacheEntry;
    const age = Date.now() - entry.storedAt;
    if (!entry.response?.success || !entry.response.spots?.length || age < 0 || age > SEARCH_CACHE_STALE_MS) return null;
    return { ...entry, fresh: age <= SEARCH_CACHE_TTL_MS };
  } catch {
    return null;
  }
}

async function pruneSearchCache() {
  const now = Date.now();
  if (now - lastSearchCachePrune < 60 * 60 * 1000) return;
  lastSearchCachePrune = now;
  try {
    const filenames = (await readdir(SEARCH_CACHE_DIR)).filter((filename) => filename.endsWith('.json'));
    const files = await Promise.all(filenames.map(async (filename) => {
      const fullPath = path.join(SEARCH_CACHE_DIR, filename);
      return { fullPath, modifiedAt: (await stat(fullPath)).mtimeMs };
    }));
    files.sort((a, b) => b.modifiedAt - a.modifiedAt);
    await Promise.all(files
      .filter((file, index) => index >= SEARCH_CACHE_MAX_FILES || now - file.modifiedAt > SEARCH_CACHE_STALE_MS)
      .map((file) => unlink(file.fullPath).catch(() => undefined)));
  } catch {
    // Cache cleanup must never make a city search fail.
  }
}

async function writeSearchCache(lat: number, lng: number, country: string, response: SearchCacheEntry['response']) {
  try {
    await mkdir(SEARCH_CACHE_DIR, { recursive: true });
    const filename = searchCacheFilename(lat, lng, country);
    const temporary = `${filename}.${process.pid}.${Date.now()}.tmp`;
    await writeFile(temporary, JSON.stringify({ storedAt: Date.now(), response } satisfies SearchCacheEntry), 'utf8');
    await rename(temporary, filename);
    await pruneSearchCache();
  } catch {
    // The external services still work when the optional disk cache is unavailable.
  }
}

function cachedSearchResponse(entry: SearchCacheEntry, status: 'HIT' | 'STALE') {
  return NextResponse.json(entry.response, {
    headers: { 'X-Spot-Cache': status, 'Server-Timing': 'cache;dur=0' },
  });
}

const kindSettings: Record<SpotKind, { privacy: number; quiet: number; walk: number; fallback: string }> = {
  viewpoint: { privacy: 77, quiet: 78, walk: 12, fallback: 'Quiet viewpoint' },
  nature: { privacy: 80, quiet: 84, walk: 18, fallback: 'Natural area' },
  waterside: { privacy: 74, quiet: 79, walk: 10, fallback: 'Waterside rocks' },
  shelter: { privacy: 84, quiet: 86, walk: 15, fallback: 'Trail shelter' },
  park: { privacy: 64, quiet: 70, walk: 6, fallback: 'Park edge' },
  picnic: { privacy: 69, quiet: 74, walk: 9, fallback: 'Picnic clearing' },
  playground: { privacy: 72, quiet: 76, walk: 5, fallback: 'Neighbourhood playground' },
  cemetery: { privacy: 86, quiet: 90, walk: 7, fallback: 'Cemetery grounds' },
};

function spotKind(tags: Record<string, string>): SpotKind {
  if (tags.tourism === 'viewpoint') return 'viewpoint';
  if (tags.amenity === 'shelter') return 'shelter';
  if (tags.landuse === 'cemetery' || tags.amenity === 'grave_yard') return 'cemetery';
  if (tags.tourism === 'picnic_site') return 'picnic';
  if (tags.leisure === 'playground') return 'playground';
  if (['beach', 'bay', 'shingle'].includes(tags.natural) || tags.man_made === 'pier') return 'waterside';
  if (tags.leisure === 'park') return 'park';
  return 'nature';
}

function placeTypeFor(kind: SpotKind, tags: Record<string, string>) {
  if (tags.natural === 'wood' || tags.landuse === 'forest') return 'Woodland';
  if (tags.natural === 'scrub') return 'Scrubland';
  if (tags.natural === 'heath') return 'Heathland';
  if (tags.natural === 'grassland') return 'Grassland';
  if (['bare_rock', 'scree'].includes(tags.natural)) return 'Rocky ground';
  if (tags.natural === 'shingle') return 'Shingle shoreline';
  if (tags.natural === 'beach' || tags.natural === 'bay') return 'Waterside';
  if (tags.man_made === 'pier') return 'Pier';
  if (tags.leisure === 'garden') return 'Garden';
  if (tags.leisure === 'recreation_ground' || tags.landuse === 'recreation_ground') return 'Recreation ground';
  if (tags.landuse === 'meadow') return 'Public meadow';
  if (tags.landuse === 'grass') return 'Public green';
  if (tags.leisure === 'nature_reserve') return 'Nature reserve';
  if (kind === 'cemetery') return 'Cemetery';
  if (kind === 'shelter') return 'Trail shelter';
  if (kind === 'viewpoint') return 'Viewpoint';
  if (kind === 'picnic') return 'Picnic site';
  if (kind === 'park') return 'Park';
  return 'Natural area';
}

function titleFor(kind: SpotKind, tags: Record<string, string>) {
  if (tags.name || tags['name:en']) return tags.name || tags['name:en'];
  if (tags.natural === 'wood' || tags.landuse === 'forest') return 'Woodland interior';
  if (tags.natural === 'scrub') return 'Scrubland cover';
  if (tags.natural === 'heath') return 'Heathland pocket';
  if (tags.natural === 'grassland') return 'Grassland edge';
  if (['bare_rock', 'scree'].includes(tags.natural)) return 'Rocky outcrop';
  if (tags.natural === 'shingle') return 'Shingle shoreline';
  if (tags.man_made === 'pier') return 'Quiet pier';
  if (tags.leisure === 'garden') return 'Garden edge';
  if (tags.leisure === 'recreation_ground' || tags.landuse === 'recreation_ground') return 'Recreation ground edge';
  if (tags.landuse === 'meadow') return 'Meadow edge';
  if (tags.landuse === 'grass') return 'Green-space edge';
  return kindSettings[kind].fallback;
}

function isPublicTransportShelter(element: OsmElement) {
  const tags = element.tags ?? {};
  if (tags.amenity !== 'shelter') return false;
  return tags.shelter_type === 'public_transport'
    || tags.highway === 'bus_stop'
    || Boolean(tags.public_transport)
    || ['yes', 'designated'].includes(tags.bus)
    || tags.railway === 'tram_stop';
}

function isSpotElement(element: OsmElement) {
  const tags = element.tags ?? {};
  return tags.tourism === 'viewpoint'
    || tags.tourism === 'picnic_site'
    || tags.amenity === 'shelter'
    || tags.landuse === 'cemetery'
    || tags.amenity === 'grave_yard'
    || tags.natural === 'beach'
    || tags.natural === 'wood'
    || tags.natural === 'scrub'
    || tags.natural === 'heath'
    || tags.natural === 'grassland'
    || tags.natural === 'bare_rock'
    || tags.natural === 'scree'
    || tags.natural === 'shingle'
    || tags.landuse === 'forest'
    || tags.landuse === 'recreation_ground'
    || (['meadow', 'grass'].includes(tags.landuse) && ['yes', 'permissive', 'designated'].includes(tags.access))
    || tags.leisure === 'nature_reserve'
    || tags.leisure === 'park'
    || tags.leisure === 'garden'
    || tags.leisure === 'recreation_ground'
    || tags.man_made === 'pier'
    || tags.leisure === 'playground';
}

function detailsFor(kind: SpotKind, tags: Record<string, string>) {
  const settings = kindSettings[kind];
  const named = Boolean(tags.name || tags['name:en']);
  const descriptions: Record<SpotKind, string> = {
    viewpoint: 'An open lookout with clear sightlines and room to keep your distance.',
    nature: 'A green public area where vegetation and distance soften city noise.',
    waterside: 'An open waterside spot with airflow and space between visitors.',
    shelter: 'A mapped outdoor shelter. Road access and surroundings still need verification.',
    park: 'A quieter edge of a public park, away from its busiest central areas.',
    picnic: 'A public clearing with informal seating and room to spread out.',
    playground: 'An evening-only option that may be calm after families have left.',
    cemetery: 'Quiet cemetery grounds with established paths. Be discreet and respect visitors, ceremonies, and posted rules.',
  };
  const reasons: Record<SpotKind, string[]> = {
    viewpoint: ['Clear sightlines around the spot', 'Natural airflow in an exposed position', 'Typically reached on foot'],
    nature: ['Vegetation creates a visual buffer', 'Separated from dense street activity', 'Low road-noise exposure'],
    waterside: ['Open air helps disperse smoke', 'Wide sightlines make distancing easier', 'Set apart from enclosed streets'],
    shelter: ['Shelter provides weather cover', 'Mapped as a public outdoor amenity', 'Check access and passing traffic before relying on the spot'],
    park: ['Space to move away from other visitors', 'Open-air setting', 'Quieter than dense street blocks'],
    picnic: ['Designed for short outdoor stops', 'Room to sit away from the path', 'Usually buffered by greenery'],
    playground: ['Consider only when completely empty', 'Often quiet later in the evening', 'Leave if children or families arrive'],
    cemetery: ['Usually low in through-traffic', 'Established paths and open space', 'Room to keep a respectful distance from visitors'],
  };
  const featureMap: Record<SpotKind, string[]> = {
    viewpoint: ['View', 'Open sky', 'Airflow'], nature: ['Greenery', 'Low noise', 'Walk-in'],
    waterside: ['Waterfront', 'Breeze', 'Open sky'], shelter: ['Cover', 'Trail access', 'Seating'],
    park: ['Grass', 'Open space', 'Easy walk'], picnic: ['Seating', 'Clearing', 'Greenery'],
    playground: ['Evening only', 'Only when empty', 'Easy access'],
    cemetery: ['Quiet paths', 'Open space', 'Respectful use'],
  };
  return {
    summary: descriptions[kind],
    why: reasons[kind],
    features: [...featureMap[kind], ...(named ? [] : ['Mapped place'])],
    settings,
  };
}

function representativeCoordinate(element: OsmElement) {
  if (element.lat != null && element.lon != null) return { lat: element.lat, lng: element.lon };
  if (element.center) return { lat: element.center.lat, lng: element.center.lon };
  const geometry = element.geometry?.length
    ? element.geometry
    : (element.members ?? []).flatMap((member) => member.geometry ?? []);
  if (!geometry.length) return null;
  return {
    lat: (Math.min(...geometry.map((point) => point.lat)) + Math.max(...geometry.map((point) => point.lat))) / 2,
    lng: (Math.min(...geometry.map((point) => point.lon)) + Math.max(...geometry.map((point) => point.lon))) / 2,
  };
}

function toSpot(element: OsmElement): SmokeSpot | null {
  const coordinate = representativeCoordinate(element);
  if (!coordinate) return null;
  const { lat, lng } = coordinate;
  const tags = element.tags ?? {};
  const kind = spotKind(tags);
  const placeType = placeTypeFor(kind, tags);
  const { summary, why, features, settings } = detailsFor(kind, tags);
  const accessBoost = tags.access === 'no' || tags.access === 'private' ? -30 : tags.highway === 'path' ? 5 : 0;
  const privacy = Math.max(50, Math.min(97, settings.privacy + accessBoost));
  const quiet = settings.quiet;
  return {
    id: `osm-${element.id}`,
    name: titleFor(kind, tags),
    kind,
    lat,
    lng,
    placeType,
    privacy,
    quiet,
    carAccess: 'Unknown',
    walkMinutes: null,
    accessNote: 'Road access has not been verified',
    summary,
    why,
    features,
  };
}

function pointDistanceMeters(a: { lat: number; lng: number }, b: { lat: number; lon: number }) {
  const y = (b.lat - a.lat) * 110_540;
  const x = (b.lon - a.lng) * 111_320 * Math.cos(a.lat * Math.PI / 180);
  return Math.hypot(x, y);
}

function pointToSegmentDistanceMeters(
  point: { lat: number; lng: number },
  start: { lat: number; lon: number },
  end: { lat: number; lon: number },
) {
  const scaleX = 111_320 * Math.cos(point.lat * Math.PI / 180);
  const ax = (start.lon - point.lng) * scaleX;
  const ay = (start.lat - point.lat) * 110_540;
  const bx = (end.lon - point.lng) * scaleX;
  const by = (end.lat - point.lat) * 110_540;
  const dx = bx - ax;
  const dy = by - ay;
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared === 0) return Math.hypot(ax, ay);
  const t = Math.max(0, Math.min(1, -(ax * dx + ay * dy) / lengthSquared));
  return Math.hypot(ax + t * dx, ay + t * dy);
}

function pointInPolygon(point: { lat: number; lng: number }, geometry: Array<{ lat: number; lon: number }>) {
  let inside = false;
  for (let index = 0, previous = geometry.length - 1; index < geometry.length; previous = index, index += 1) {
    const currentPoint = geometry[index];
    const previousPoint = geometry[previous];
    const crossesLatitude = (currentPoint.lat > point.lat) !== (previousPoint.lat > point.lat);
    const crossingLongitude = (previousPoint.lon - currentPoint.lon) * (point.lat - currentPoint.lat)
      / (previousPoint.lat - currentPoint.lat || Number.EPSILON) + currentPoint.lon;
    if (crossesLatitude && point.lng < crossingLongitude) inside = !inside;
  }
  return inside;
}

function polygonEdgeDistanceMeters(point: { lat: number; lng: number }, geometry: Array<{ lat: number; lon: number }>) {
  let nearest = Number.POSITIVE_INFINITY;
  for (let index = 0; index < geometry.length; index += 1) {
    const nextIndex = (index + 1) % geometry.length;
    nearest = Math.min(nearest, pointToSegmentDistanceMeters(point, geometry[index], geometry[nextIndex]));
  }
  return nearest;
}

function deepestInteriorPoint(
  geometry: Array<{ lat: number; lon: number }>,
  holes: Array<Array<{ lat: number; lon: number }>> = [],
) {
  if (geometry.length < 4) return null;
  const minLat = Math.min(...geometry.map((point) => point.lat));
  const maxLat = Math.max(...geometry.map((point) => point.lat));
  const minLng = Math.min(...geometry.map((point) => point.lon));
  const maxLng = Math.max(...geometry.map((point) => point.lon));
  if (minLat === maxLat || minLng === maxLng) return null;

  let best: { lat: number; lng: number; clearanceMeters: number } | null = null;
  const divisions = 14;
  for (let row = 0; row < divisions; row += 1) {
    for (let column = 0; column < divisions; column += 1) {
      const point = {
        lat: minLat + (maxLat - minLat) * (row + 0.5) / divisions,
        lng: minLng + (maxLng - minLng) * (column + 0.5) / divisions,
      };
      if (!pointInPolygon(point, geometry)) continue;
      if (holes.some((hole) => pointInPolygon(point, hole))) continue;
      const clearanceMeters = Math.min(
        polygonEdgeDistanceMeters(point, geometry),
        ...holes.map((hole) => polygonEdgeDistanceMeters(point, hole)),
      );
      if (!best || clearanceMeters > best.clearanceMeters) best = { ...point, clearanceMeters };
    }
  }
  return best;
}

function sameCoordinate(
  first: { lat: number; lon: number },
  second: { lat: number; lon: number },
) {
  return Math.abs(first.lat - second.lat) < 1e-7 && Math.abs(first.lon - second.lon) < 1e-7;
}

function joinedRelationRings(element: OsmElement, role: 'outer' | 'inner') {
  const segments = (element.members ?? [])
    .filter((member) => member.type === 'way' && member.role === role && (member.geometry?.length ?? 0) >= 2)
    .map((member) => [...member.geometry!]);
  const rings: Array<Array<{ lat: number; lon: number }>> = [];

  while (segments.length) {
    let ring = segments.shift()!;
    let extended = true;
    while (extended && !sameCoordinate(ring[0], ring[ring.length - 1])) {
      extended = false;
      for (let index = 0; index < segments.length; index += 1) {
        const segment = segments[index];
        const first = ring[0];
        const last = ring[ring.length - 1];
        if (sameCoordinate(last, segment[0])) {
          ring = [...ring, ...segment.slice(1)];
        } else if (sameCoordinate(last, segment[segment.length - 1])) {
          ring = [...ring, ...[...segment].reverse().slice(1)];
        } else if (sameCoordinate(first, segment[segment.length - 1])) {
          ring = [...segment.slice(0, -1), ...ring];
        } else if (sameCoordinate(first, segment[0])) {
          ring = [...[...segment].reverse().slice(0, -1), ...ring];
        } else {
          continue;
        }
        segments.splice(index, 1);
        extended = true;
        break;
      }
    }
    if (ring.length >= 4 && sameCoordinate(ring[0], ring[ring.length - 1])) rings.push(ring);
  }
  return rings;
}

function elementAreaParts(element: OsmElement) {
  if (element.geometry?.length) return [{ geometry: element.geometry, holes: [] as Array<Array<{ lat: number; lon: number }>> }];
  if (element.type !== 'relation') return [];
  const outerRings = joinedRelationRings(element, 'outer');
  const innerRings = joinedRelationRings(element, 'inner');
  return outerRings.map((geometry) => ({
    geometry,
    holes: innerRings.filter((hole) => hole[0] && pointInPolygon({ lat: hole[0].lat, lng: hole[0].lon }, geometry)),
  }));
}

function pointInCandidateArea(point: { lat: number; lng: number }, candidate: SpotCandidate) {
  const geometry = candidate.element.geometry;
  return Boolean(geometry?.length)
    && pointInPolygon(point, geometry!)
    && !(candidate.geometryHoles ?? []).some((hole) => pointInPolygon(point, hole));
}

function candidateEdgeDistanceMeters(point: { lat: number; lng: number }, candidate: SpotCandidate) {
  const geometry = candidate.element.geometry;
  if (!geometry?.length) return 0;
  return Math.min(
    polygonEdgeDistanceMeters(point, geometry),
    ...(candidate.geometryHoles ?? []).map((hole) => polygonEdgeDistanceMeters(point, hole)),
  );
}

function distanceToRoadMeters(spot: { lat: number; lng: number }, road: OsmElement) {
  const geometry = road.geometry ?? [];
  if (geometry.length === 1) return pointDistanceMeters(spot, geometry[0]);
  let nearest = Number.POSITIVE_INFINITY;
  for (let index = 1; index < geometry.length; index += 1) {
    nearest = Math.min(nearest, pointToSegmentDistanceMeters(spot, geometry[index - 1], geometry[index]));
  }
  return nearest;
}

function screeningStrength(tags: Record<string, string>) {
  if (tags.natural === 'wood' || tags.landuse === 'forest') return 3;
  if (['scrub', 'heath'].includes(tags.natural) || ['hedge', 'wall'].includes(tags.barrier)) return 2;
  if (tags.covered === 'yes') return 1;
  return 0;
}

function satelliteScreeningStrength(candidate: SpotCandidate) {
  const canopy = candidate.canopy;
  if (!canopy || canopy.validPixelPercent < 70) return null;
  if (canopy.treeCoverPercent >= 60 || canopy.denseCoverPercent >= 55) return 3;
  if (canopy.treeCoverPercent >= 35 || canopy.denseCoverPercent >= 30) return 2;
  if (canopy.treeCoverPercent >= 18 || canopy.denseCoverPercent >= 15) return 1;
  return 0;
}

function vegetationScreeningStrength(candidate: SpotCandidate) {
  const vegetation = candidate.vegetation;
  if (!vegetation || vegetation.validPixelPercent < MIN_NMD_VALID_PERCENT) return null;
  if (vegetation.lowVegetationPercent >= 55) return 3;
  if (vegetation.lowVegetationPercent >= 35) return 2;
  if (vegetation.lowVegetationPercent >= 18) return 1;
  return 0;
}

function candidateScreeningStrength(candidate: SpotCandidate) {
  const mappedStrength = screeningStrength(candidate.element.tags ?? {});
  const satelliteStrength = satelliteScreeningStrength(candidate);
  const vegetationStrength = vegetationScreeningStrength(candidate);
  // NMD measures objects at roughly eye level, so valid local evidence takes
  // precedence over overhead canopy and broad OSM land-cover tags.
  if (vegetationStrength != null) return vegetationStrength;
  if (satelliteStrength == null) return mappedStrength;
  if (satelliteStrength === 0 && mappedStrength >= 2) return 0;
  return Math.max(mappedStrength, satelliteStrength);
}

async function withVegetationStructureEvidence(candidates: SpotCandidate[]) {
  if (!candidates.length) return candidates;
  const backendUrl = process.env.ROUTING_API_URL || 'http://localhost:8000';
  try {
    const requestPoints = candidates.map(({ spot }, index) => ({
      id: `${spot.id}::${index}`,
      lat: spot.lat,
      lng: spot.lng,
    }));
    const response = await fetch(`${backendUrl}/api/vegetation-structure`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        points: requestPoints,
        sample_radius_meters: 35,
      }),
      cache: 'no-store',
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) return candidates;
    const data = await response.json() as VegetationStructureResponse;
    if (!data.available) return candidates;
    const byId = new Map((data.results ?? []).map((result) => [result.id, result]));
    return candidates.map((candidate, index) => {
      const result = byId.get(requestPoints[index].id);
      if (!result) return candidate;
      return {
        ...candidate,
        vegetation: {
          lowVegetationPercent: result.low_vegetation_percent,
          tallVegetationPercent: result.tall_vegetation_percent,
          validPixelPercent: result.valid_pixel_percent,
        },
      };
    });
  } catch (error) {
    console.warn('Local vegetation-height lookup failed; continuing without it.', error);
    return candidates;
  }
}

async function withTreeCoverEvidence(candidates: SpotCandidate[]) {
  if (!candidates.length) return candidates;
  const backendUrl = process.env.ROUTING_API_URL || 'http://localhost:8000';
  try {
    const requestPoints = candidates.map(({ spot }, index) => ({
      id: `${spot.id}::${index}`,
      lat: spot.lat,
      lng: spot.lng,
    }));
    const response = await fetch(`${backendUrl}/api/tree-cover`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        points: requestPoints,
        sample_radius_meters: 35,
      }),
      cache: 'no-store',
      signal: AbortSignal.timeout(55000),
    });
    if (!response.ok) return candidates;
    const data = await response.json() as TreeCoverResponse;
    const byId = new Map((data.results ?? []).map((result) => [result.id, result]));
    return candidates.map((candidate, index) => {
      const result = byId.get(requestPoints[index].id);
      if (!result) return candidate;
      return {
        ...candidate,
        canopy: {
          treeCoverPercent: result.tree_cover_percent,
          denseCoverPercent: result.dense_cover_percent,
          validPixelPercent: result.valid_pixel_percent,
        },
      };
    });
  } catch (error) {
    console.warn('CDSE tree-cover lookup failed; continuing with mapped cover only.', error);
    return candidates;
  }
}

function mainRoadExclusionRadius(road: OsmElement) {
  const tags = road.tags ?? {};
  const baseRadius: Record<string, number> = {
    motorway: 180,
    trunk: 140,
    primary: 100,
    secondary: 70,
    tertiary: 40,
  };
  let radius = baseRadius[tags.highway] ?? 0;
  const speed = Number.parseInt(tags.maxspeed ?? '', 10);
  const lanes = Number.parseInt(tags.lanes ?? '', 10);
  if (Number.isFinite(speed) && speed >= 70) radius = Math.max(radius, 120);
  if (Number.isFinite(lanes) && lanes >= 4) radius = Math.max(radius, 100);
  return radius;
}

function isTooCloseToMainRoad(candidate: SpotCandidate, mainRoads: OsmElement[]) {
  const screen = candidateScreeningStrength(candidate);
  const screenFactor = screen >= 3 ? 0.45 : screen === 2 ? 0.65 : screen === 1 ? 0.8 : 1;
  return mainRoads.some((road) => distanceToRoadMeters(candidate.spot, road) <= mainRoadExclusionRadius(road) * screenFactor);
}

function elementDistanceMeters(spot: { lat: number; lng: number }, element: OsmElement) {
  if (element.geometry?.length) return distanceToRoadMeters(spot, element);
  const coordinate = representativeCoordinate(element);
  return coordinate == null
    ? Number.POSITIVE_INFINITY
    : pointDistanceMeters(spot, { lat: coordinate.lat, lon: coordinate.lng });
}

function searchDistanceMeters(origin: { lat: number; lng: number }, element: OsmElement) {
  const directDistance = elementDistanceMeters(origin, element);
  const memberDistance = (element.members ?? []).reduce((nearest, member) => {
    if (!member.geometry?.length) return nearest;
    return Math.min(nearest, distanceToRoadMeters(origin, { id: member.ref ?? 0, geometry: member.geometry }));
  }, Number.POSITIVE_INFINITY);
  return Math.min(directDistance, memberDistance);
}

function nearestDistanceMeters(spot: SmokeSpot, elements: OsmElement[]) {
  return elements.reduce((nearest, element) => Math.min(nearest, elementDistanceMeters(spot, element)), Number.POSITIVE_INFINITY);
}

function roundedFiniteDistance(distance: number) {
  return Number.isFinite(distance) ? Math.round(distance) : undefined;
}

function privacyEligible(
  candidate: SpotCandidate,
  roads: OsmElement[],
  paths: OsmElement[],
  buildings: OsmElement[],
  mainRoads: OsmElement[],
) {
  if (isTooCloseToMainRoad(candidate, mainRoads)) return false;

  const screen = candidateScreeningStrength(candidate);
  const nearestRoad = nearestDistanceMeters(candidate.spot, roads);
  const throughRoads = roads.filter((road) => THROUGH_ROAD_TYPES.has(road.tags?.highway ?? ''));
  const nearestThroughRoad = nearestDistanceMeters(candidate.spot, throughRoads);
  const nearestBuilding = nearestDistanceMeters(candidate.spot, buildings);
  const nearestPath = nearestDistanceMeters(candidate.spot, paths);
  const nearbyPathCount = paths.filter((path) => elementDistanceMeters(candidate.spot, path) <= 60).length;
  const clearance = candidate.interiorClearanceMeters;

  if (nearestBuilding < 35) return false;
  if (candidate.spot.kind === 'cemetery') {
    if (candidate.searchAroundAnchor) {
      return screen >= 2
        && nearestRoad >= 60
        && nearestThroughRoad >= 90
        && nearestBuilding >= 70
        && nearestPath >= 8 && nearestPath <= 130
        && nearbyPathCount <= 6;
    }
    return screen >= 1
      && clearance != null && clearance >= 55
      && nearestRoad >= 70
      && nearestThroughRoad >= 100
      && nearestBuilding >= 70
      && nearbyPathCount <= 6;
  }
  if (candidate.spot.kind === 'viewpoint' && screen < 2) return false;
  if (candidate.spot.kind === 'playground') return false;
  if (screen >= 3) return clearance != null && clearance >= 35
    && nearestRoad >= 70 && nearestBuilding >= 50
    && nearestPath >= 10 && nearestPath <= 120
    && nearbyPathCount <= 12;
  if (screen === 2) return nearestRoad >= 45 && nearbyPathCount <= 5;
  return false;
}

function potentiallyPrivacyEligible(
  candidate: SpotCandidate,
  roads: OsmElement[],
  paths: OsmElement[],
  buildings: OsmElement[],
  mainRoads: OsmElement[],
) {
  const insideHardRoadBuffer = mainRoads.some((road) => distanceToRoadMeters(candidate.spot, road)
    <= mainRoadExclusionRadius(road) * 0.45);
  if (insideHardRoadBuffer) return false;

  const nearestRoad = nearestDistanceMeters(candidate.spot, roads);
  const throughRoads = roads.filter((road) => THROUGH_ROAD_TYPES.has(road.tags?.highway ?? ''));
  const nearestThroughRoad = nearestDistanceMeters(candidate.spot, throughRoads);
  const nearestBuilding = nearestDistanceMeters(candidate.spot, buildings);
  const nearestPath = nearestDistanceMeters(candidate.spot, paths);
  const nearbyPathCount = paths.filter((path) => elementDistanceMeters(candidate.spot, path) <= 60).length;
  const clearance = candidate.interiorClearanceMeters;

  if (nearestBuilding < 35 || candidate.spot.kind === 'playground') return false;
  if (candidate.spot.kind === 'cemetery') {
    if (candidate.searchAroundAnchor) {
      return nearestRoad >= 60
        && nearestThroughRoad >= 90
        && nearestBuilding >= 70
        && nearestPath >= 8 && nearestPath <= 130
        && nearbyPathCount <= 6;
    }
    return clearance != null && clearance >= 55
      && nearestRoad >= 70
      && nearestThroughRoad >= 100
      && nearestBuilding >= 70
      && nearbyPathCount <= 6;
  }

  const couldPassWithStrongScreening = clearance != null && clearance >= 35
    && nearestRoad >= 70 && nearestBuilding >= 50
    && nearestPath >= 10 && nearestPath <= 120
    && nearbyPathCount <= 12;
  const couldPassWithModerateScreening = nearestRoad >= 45 && nearbyPathCount <= 5;
  return couldPassWithStrongScreening || couldPassWithModerateScreening;
}

function withPrivacyEvidence(
  candidate: SpotCandidate,
  roads: OsmElement[],
  paths: OsmElement[],
  buildings: OsmElement[],
) {
  const screen = candidateScreeningStrength(candidate);
  const nearestRoad = nearestDistanceMeters(candidate.spot, roads);
  const nearestBuilding = nearestDistanceMeters(candidate.spot, buildings);
  const nearestPath = nearestDistanceMeters(candidate.spot, paths);
  const nearbyPathCount = paths.filter((path) => elementDistanceMeters(candidate.spot, path) <= 60).length;
  const clearance = candidate.interiorClearanceMeters ?? 0;
  const roadScore = nearestRoad >= 300 ? 3 : nearestRoad >= 150 ? 2 : nearestRoad < 80 ? -8 : 0;
  const buildingScore = nearestBuilding >= 200 ? 3 : nearestBuilding >= 100 ? 2 : nearestBuilding < 60 ? -8 : 0;
  const pathScore = nearbyPathCount === 0 ? 2 : nearbyPathCount <= 2 ? 1 : nearbyPathCount > 5 ? -6 : 0;
  const clearanceScore = clearance >= 120 ? 4 : clearance >= 70 ? 2 : clearance < 35 ? -8 : 0;
  const lowVegetationCover = candidate.vegetation && candidate.vegetation.validPixelPercent >= MIN_NMD_VALID_PERCENT
    ? Math.round(candidate.vegetation.lowVegetationPercent)
    : null;
  const tallVegetationCover = candidate.vegetation && candidate.vegetation.validPixelPercent >= MIN_NMD_VALID_PERCENT
    ? Math.round(candidate.vegetation.tallVegetationPercent)
    : null;
  const lowVegetationScore = lowVegetationCover != null && lowVegetationCover >= 55
    ? 4 : lowVegetationCover != null && lowVegetationCover >= 35 ? 2 : 0;
  const calculatedPrivacy = candidate.spot.privacy + screen * 2 + roadScore + buildingScore
    + pathScore + clearanceScore + lowVegetationScore;
  const privacy = Math.max(50, Math.min(95, calculatedPrivacy));
  const quiet = Math.max(52, Math.min(95, candidate.spot.quiet + screen * 2 + roadScore + Math.min(3, buildingScore)));
  const screenedNaturalArea = screen >= 2 && candidate.spot.kind === 'nature';
  const satelliteCover = candidate.canopy && candidate.canopy.validPixelPercent >= 70
    ? Math.round(candidate.canopy.treeCoverPercent)
    : null;
  const satelliteReason = satelliteCover != null && satelliteCover >= 18
    ? `Copernicus satellite data estimates ${satelliteCover}% tree cover nearby`
    : null;
  const vegetationReason = lowVegetationCover != null && lowVegetationCover >= 18
    ? `NMD height data estimates ${lowVegetationCover}% eye-level vegetation nearby`
    : null;
  const evidenceSources = [
    'OpenStreetMap layout',
    ...(satelliteCover != null ? ['Copernicus canopy'] : []),
    ...(lowVegetationCover != null ? ['NMD eye-level vegetation'] : []),
  ];
  return {
    ...candidate,
    spot: {
      ...candidate.spot,
      privacy,
      quiet,
      ...(satelliteCover != null ? { treeCoverPercent: satelliteCover } : {}),
      ...(lowVegetationCover != null ? { lowVegetationPercent: lowVegetationCover } : {}),
      ...(tallVegetationCover != null ? { tallVegetationPercent: tallVegetationCover } : {}),
      evidence: {
        ...(satelliteCover != null ? { treeCanopyPercent: satelliteCover } : {}),
        ...(lowVegetationCover != null ? { eyeLevelVegetationPercent: lowVegetationCover } : {}),
        ...(roundedFiniteDistance(nearestRoad) != null ? { nearestRoadMeters: roundedFiniteDistance(nearestRoad) } : {}),
        ...(roundedFiniteDistance(nearestBuilding) != null ? { nearestBuildingMeters: roundedFiniteDistance(nearestBuilding) } : {}),
        ...(roundedFiniteDistance(nearestPath) != null ? { nearestPathMeters: roundedFiniteDistance(nearestPath) } : {}),
        ...(candidate.interiorClearanceMeters != null
          ? { interiorClearanceMeters: Math.round(candidate.interiorClearanceMeters) } : {}),
        nearbyPathCount,
        sources: evidenceSources,
      },
      ...(screenedNaturalArea ? {
        summary: `A mapped ${(candidate.spot.placeType ?? 'natural area').toLowerCase()} where measured vegetation provides meaningful visual cover.`,
        why: [vegetationReason || satelliteReason || 'Mapped vegetation provides screening', 'Separated from nearby buildings', 'Low exposure to the road network'],
        features: [candidate.spot.placeType ?? 'Natural cover', ...(lowVegetationCover != null
          ? [`${lowVegetationCover}% low cover`]
          : satelliteCover != null ? [`${satelliteCover}% tree cover`] : ['Natural cover']), 'Low exposure'],
      } : vegetationReason || satelliteReason ? {
        why: [vegetationReason || satelliteReason!, ...candidate.spot.why.slice(0, 2)],
        features: [vegetationReason ? `${lowVegetationCover}% low cover` : `${satelliteCover}% tree cover`, ...candidate.spot.features.slice(0, 2)],
      } : {}),
    },
  };
}

function withAreaGeometry(candidates: SpotCandidate[], geometryElements: OsmElement[]) {
  const byId = new Map(geometryElements.map((element) => [`${element.type}-${element.id}`, element]));
  return candidates.map((candidate) => {
    const geometryElement = byId.get(`${candidate.element.type}-${candidate.element.id}`);
    if (!geometryElement) return candidate;
    const parts = elementAreaParts(geometryElement);
    const bestPart = parts
      .map(({ geometry, holes }) => ({ geometry, holes, interior: deepestInteriorPoint(geometry, holes) }))
      .filter((part): part is typeof part & { interior: NonNullable<typeof part.interior> } => Boolean(part.interior))
      .sort((first, second) => second.interior.clearanceMeters - first.interior.clearanceMeters)[0];
    if (!bestPart) return candidate;
    if (candidate.spot.kind === 'cemetery' && bestPart.interior.clearanceMeters < 20) {
      const anchor = { lat: bestPart.interior.lat, lng: bestPart.interior.lng };
      return {
        ...candidate,
        element: { ...candidate.element, geometry: bestPart.geometry },
        geometryHoles: bestPart.holes,
        searchAroundAnchor: true,
        anchor,
        spot: {
          ...candidate.spot,
          name: `${candidate.spot.name} surroundings`,
          placeType: 'Landmark surroundings',
          lat: anchor.lat,
          lng: anchor.lng,
          summary: 'Screened outdoor ground near the mapped landmark. The selected point is in the surroundings, not on the grave itself.',
          why: ['Nearby vegetation can provide visual cover', 'Set away from roads and buildings', 'Use the area respectfully and leave if others are present'],
          features: ['Nearby cover', 'Landmark vicinity', 'Respectful use'],
        },
      };
    }
    return {
      ...candidate,
      element: { ...candidate.element, geometry: bestPart.geometry },
      geometryHoles: bestPart.holes,
      spot: { ...candidate.spot, lat: bestPart.interior.lat, lng: bestPart.interior.lng },
      interiorClearanceMeters: bestPart.interior.clearanceMeters,
    };
  });
}

function landmarkRefinementOptions(
  candidate: SpotCandidate,
  roads: OsmElement[],
  paths: OsmElement[],
  buildings: OsmElement[],
  mainRoads: OsmElement[],
  limit: number,
) {
  const anchor = candidate.anchor ?? { lat: candidate.spot.lat, lng: candidate.spot.lng };
  const stepMeters = 25;
  const steps = Math.ceil(LANDMARK_SEARCH_RADIUS_METERS / stepMeters);
  const options: Array<{ candidate: SpotCandidate; score: number }> = [];

  for (let row = -steps; row <= steps; row += 1) {
    for (let column = -steps; column <= steps; column += 1) {
      const point = {
        lat: anchor.lat + row * stepMeters / 110_540,
        lng: anchor.lng + column * stepMeters / (111_320 * Math.cos(anchor.lat * Math.PI / 180)),
      };
      const anchorDistanceMeters = pointDistanceMeters(point, { lat: anchor.lat, lon: anchor.lng });
      if (anchorDistanceMeters > LANDMARK_SEARCH_RADIUS_METERS) continue;
      const option: SpotCandidate = {
        ...candidate,
        spot: { ...candidate.spot, lat: point.lat, lng: point.lng },
        interiorClearanceMeters: undefined,
        anchorDistanceMeters,
        vegetation: undefined,
      };
      if (!potentiallyPrivacyEligible(option, roads, paths, buildings, mainRoads)) continue;
      const nearestRoad = nearestDistanceMeters(option.spot, roads);
      const nearestBuilding = nearestDistanceMeters(option.spot, buildings);
      const nearestPath = nearestDistanceMeters(option.spot, paths);
      const nearbyPathCount = paths.filter((path) => elementDistanceMeters(option.spot, path) <= 60).length;
      const score = Math.min(nearestRoad, 220) * 0.55
        + Math.min(nearestBuilding, 180) * 0.35
        - Math.abs(nearestPath - 35) * 0.45
        - nearbyPathCount * 4
        - anchorDistanceMeters * 0.08;
      options.push({ candidate: option, score });
    }
  }
  return options.sort((first, second) => second.score - first.score)
    .slice(0, limit)
    .map(({ candidate: option }) => option);
}

function refineAreaCandidate(
  candidate: SpotCandidate,
  roads: OsmElement[],
  paths: OsmElement[],
  buildings: OsmElement[],
  mainRoads: OsmElement[],
) {
  const geometry = candidate.element.geometry;
  if (!geometry?.length || candidate.element.type === 'node') return candidate;
  const minLat = Math.min(...geometry.map((point) => point.lat));
  const maxLat = Math.max(...geometry.map((point) => point.lat));
  const minLng = Math.min(...geometry.map((point) => point.lon));
  const maxLng = Math.max(...geometry.map((point) => point.lon));
  const divisions = 16;
  let best: { candidate: SpotCandidate; score: number } | null = null;

  for (let row = 0; row < divisions; row += 1) {
    for (let column = 0; column < divisions; column += 1) {
      const point = {
        lat: minLat + (maxLat - minLat) * (row + 0.5) / divisions,
        lng: minLng + (maxLng - minLng) * (column + 0.5) / divisions,
      };
      if (!pointInCandidateArea(point, candidate)) continue;
      if (pointDistanceMeters(candidate.spot, { lat: point.lat, lon: point.lng }) > 160) continue;
      const clearanceMeters = candidateEdgeDistanceMeters(point, candidate);
      const refinedCandidate: SpotCandidate = {
        ...candidate,
        spot: { ...candidate.spot, lat: point.lat, lng: point.lng },
        interiorClearanceMeters: clearanceMeters,
      };
      if (!privacyEligible(refinedCandidate, roads, paths, buildings, mainRoads)) continue;
      const nearestRoad = nearestDistanceMeters(refinedCandidate.spot, roads);
      const nearestBuilding = nearestDistanceMeters(refinedCandidate.spot, buildings);
      const nearestPath = nearestDistanceMeters(refinedCandidate.spot, paths);
      const nearbyPathCount = paths.filter((path) => elementDistanceMeters(refinedCandidate.spot, path) <= 60).length;
      const score = clearanceMeters
        + Math.min(nearestRoad, 220) * 0.55
        + Math.min(nearestBuilding, 180) * 0.35
        - Math.abs(nearestPath - 35) * 0.45
        - nearbyPathCount * 4;
      if (!best || score > best.score) best = { candidate: refinedCandidate, score };
    }
  }
  return best?.candidate ?? null;
}

function vegetationRefinementOptions(
  candidate: SpotCandidate,
  roads: OsmElement[],
  paths: OsmElement[],
  buildings: OsmElement[],
  mainRoads: OsmElement[],
  limit: number,
) {
  if (candidate.searchAroundAnchor) {
    return landmarkRefinementOptions(candidate, roads, paths, buildings, mainRoads, limit);
  }
  const geometry = candidate.element.geometry;
  if (!geometry?.length || candidate.element.type === 'node') return [candidate];
  const minLat = Math.min(...geometry.map((point) => point.lat));
  const maxLat = Math.max(...geometry.map((point) => point.lat));
  const minLng = Math.min(...geometry.map((point) => point.lon));
  const maxLng = Math.max(...geometry.map((point) => point.lon));
  const divisions = 16;
  const options: Array<{ candidate: SpotCandidate; score: number }> = [];

  for (let row = 0; row < divisions; row += 1) {
    for (let column = 0; column < divisions; column += 1) {
      const point = {
        lat: minLat + (maxLat - minLat) * (row + 0.5) / divisions,
        lng: minLng + (maxLng - minLng) * (column + 0.5) / divisions,
      };
      if (!pointInCandidateArea(point, candidate)) continue;
      if (pointDistanceMeters(candidate.spot, { lat: point.lat, lon: point.lng }) > 160) continue;
      const clearanceMeters = candidateEdgeDistanceMeters(point, candidate);
      const minimumClearance = candidate.spot.kind === 'cemetery' ? 55 : 35;
      if (clearanceMeters < minimumClearance) continue;
      const option: SpotCandidate = {
        ...candidate,
        spot: { ...candidate.spot, lat: point.lat, lng: point.lng },
        interiorClearanceMeters: clearanceMeters,
        vegetation: undefined,
      };
      if (!potentiallyPrivacyEligible(option, roads, paths, buildings, mainRoads)) continue;
      const nearestRoad = nearestDistanceMeters(option.spot, roads);
      const nearestBuilding = nearestDistanceMeters(option.spot, buildings);
      const nearestPath = nearestDistanceMeters(option.spot, paths);
      const nearbyPathCount = paths.filter((path) => elementDistanceMeters(option.spot, path) <= 60).length;
      const score = clearanceMeters
        + Math.min(nearestRoad, 220) * 0.55
        + Math.min(nearestBuilding, 180) * 0.35
        - Math.abs(nearestPath - 35) * 0.45
        - nearbyPathCount * 4;
      options.push({ candidate: option, score });
    }
  }
  return options.sort((a, b) => b.score - a.score).slice(0, limit).map(({ candidate: option }) => option);
}

function selectVegetationRefinedCandidates(
  options: SpotCandidate[],
  roads: OsmElement[],
  paths: OsmElement[],
  buildings: OsmElement[],
  mainRoads: OsmElement[],
) {
  const bestBySpot = new Map<string, { candidate: SpotCandidate; score: number }>();
  for (const option of options) {
    if (!privacyEligible(option, roads, paths, buildings, mainRoads)) continue;
    const lowCover = option.vegetation?.lowVegetationPercent ?? 0;
    const tallCover = option.vegetation?.tallVegetationPercent ?? 0;
    const nearestRoad = nearestDistanceMeters(option.spot, roads);
    const nearestBuilding = nearestDistanceMeters(option.spot, buildings);
    const nearestPath = nearestDistanceMeters(option.spot, paths);
    const nearbyPathCount = paths.filter((path) => elementDistanceMeters(option.spot, path) <= 60).length;
    const score = lowCover * 2.4
      + tallCover * 0.15
      + (option.interiorClearanceMeters ?? 0)
      + Math.min(nearestRoad, 220) * 0.55
      + Math.min(nearestBuilding, 180) * 0.35
      - Math.abs(nearestPath - 35) * 0.45
      - nearbyPathCount * 4;
    const current = bestBySpot.get(option.spot.id);
    if (!current || score > current.score) bestBySpot.set(option.spot.id, { candidate: option, score });
  }
  return [...bestBySpot.values()].map(({ candidate: option }) => option);
}

function uniqueCandidates(candidates: SpotCandidate[]) {
  const seen = new Set<string>();
  return candidates.filter((candidate) => {
    if (seen.has(candidate.spot.id)) return false;
    seen.add(candidate.spot.id);
    return true;
  });
}

function spatiallyDiverseCandidates(
  candidates: SpotCandidate[],
  limit: number,
  origin: { lat: number; lng: number },
) {
  const remaining = [...candidates];
  const selected: SpotCandidate[] = [];
  while (remaining.length && selected.length < limit) {
    let bestIndex = 0;
    let bestDistance = Number.NEGATIVE_INFINITY;
    for (let index = 0; index < remaining.length; index += 1) {
      const candidate = remaining[index];
      const distance = selected.length
        ? Math.min(...selected.map(({ spot }) => pointDistanceMeters(candidate.spot, { lat: spot.lat, lon: spot.lng })))
        : -pointDistanceMeters(candidate.spot, { lat: origin.lat, lon: origin.lng });
      if (distance > bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    }
    selected.push(remaining.splice(bestIndex, 1)[0]);
  }
  return selected;
}

function selectDiverseSpots(candidates: SpotCandidate[], limit: number) {
  const selected: SpotCandidate[] = [];
  const kindCounts = new Map<SpotKind, number>();
  const kindLimits: Partial<Record<SpotKind, number>> = { nature: 12, cemetery: 6, park: 4, shelter: 4, viewpoint: 4 };
  const spacing: Partial<Record<SpotKind, number>> = { nature: 300, cemetery: 180, park: 180, shelter: 150, viewpoint: 200 };

  for (const candidate of candidates) {
    if (selected.length >= limit) break;
    const count = kindCounts.get(candidate.spot.kind) ?? 0;
    if (count >= (kindLimits[candidate.spot.kind] ?? 5)) continue;
    const minimumSpacing = spacing[candidate.spot.kind] ?? 150;
    const tooCloseToSimilar = selected.some(({ spot }) => spot.kind === candidate.spot.kind
      && pointDistanceMeters(candidate.spot, { lat: spot.lat, lon: spot.lng }) < minimumSpacing);
    if (tooCloseToSimilar) continue;
    selected.push(candidate);
    kindCounts.set(candidate.spot.kind, count + 1);
  }
  return selected;
}

function withRoadAccess(spot: SmokeSpot, roads: OsmElement[]): SmokeSpot {
  const nearestRoadMeters = roads.reduce(
    (nearest, road) => Math.min(nearest, distanceToRoadMeters(spot, road)),
    Number.POSITIVE_INFINITY,
  );

  if (!Number.isFinite(nearestRoadMeters) || nearestRoadMeters > ACCESS_SEARCH_RADIUS_METERS) {
    const minimumMinutes = Math.ceil(ACCESS_SEARCH_RADIUS_METERS / WALKING_METERS_PER_MINUTE);
    return {
      ...spot,
      carAccess: 'Unknown',
      walkMinutes: null,
      accessNote: `More than ${minimumMinutes} min walk from the nearest mapped road`,
      ...(spot.kind === 'shelter' ? {
        summary: 'A mapped outdoor shelter reached by a longer walk from the nearest drivable road.',
        why: ['Away from the nearest mapped road', 'Walk-in access reduces passing traffic', 'Shelter provides weather cover'],
      } : {}),
    };
  }

  const walkMinutes = Math.max(1, Math.ceil(nearestRoadMeters / WALKING_METERS_PER_MINUTE));
  const carAccess = nearestRoadMeters <= 50 ? 'Easy' : nearestRoadMeters <= 250 ? 'Limited' : 'Difficult';
  const accessNote = `About ${walkMinutes} min walk from the nearest mapped road`;
  if (spot.kind !== 'shelter') return { ...spot, carAccess, walkMinutes, accessNote };

  if (carAccess === 'Easy') {
    return {
      ...spot,
      carAccess,
      walkMinutes,
      accessNote,
      summary: 'A mapped outdoor shelter close to a drivable road or track.',
      why: ['Shelter provides weather cover', 'Close to mapped road access', 'Expect more passing traffic than at a walk-in shelter'],
      features: ['Cover', 'Roadside access', 'Seating'],
    };
  }

  return {
    ...spot,
    carAccess,
    walkMinutes,
    accessNote,
    summary: 'A mapped outdoor shelter a short walk from the nearest drivable road.',
    why: ['Shelter provides weather cover', 'Set back from the nearest mapped road', 'Some walk-in separation from passing traffic'],
  };
}

async function fetchOverpass(query: string) {
  const controller = new AbortController();
  const endpoints = [
    { url: 'https://maps.mail.ru/osm/tools/overpass/api/interpreter', delay: 0 },
    { url: 'https://overpass-api.de/api/interpreter', delay: 8500 },
    { url: 'https://overpass.private.coffee/api/interpreter', delay: 17000 },
  ];
  const waitForStart = (delay: number) => new Promise<void>((resolve, reject) => {
    if (!delay) {
      resolve();
      return;
    }
    const timer = setTimeout(resolve, delay);
    controller.signal.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(new Error('Overpass request cancelled.'));
    }, { once: true });
  });
  const attempt = async ({ url, delay }: (typeof endpoints)[number]) => {
    await waitForStart(delay);
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(25000)]);
    const candidate = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'User-Agent': 'HushQuietSpots/1.0 (local prototype)',
        },
        body: new URLSearchParams({ data: query }),
        signal,
        // The complete city result is already persisted for 24 hours. Avoid the
        // framework's POST fetch cache here because a stalled cache fill can hold
        // every fallback behind the same slow request.
        cache: 'no-store',
      });
    if (!candidate.ok) throw new Error(`Overpass returned ${candidate.status}.`);
    return candidate.json();
  };
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      Promise.any(endpoints.map(attempt)),
      new Promise<never>((_, reject) => {
        timeout = setTimeout(() => reject(new Error('Overpass request timed out.')), 35000);
      }),
    ]);
  } catch {
    throw new Error('Map places are temporarily unavailable. Try again shortly.');
  } finally {
    if (timeout) clearTimeout(timeout);
    controller.abort();
  }
}

function privacyContextQuery(candidates: SpotCandidate[]) {
  const coordinates = [...new Map(candidates.map(({ spot }) => [
    `${spot.lat.toFixed(6)},${spot.lng.toFixed(6)}`,
    { lat: spot.lat, lng: spot.lng },
  ])).values()];
  const aroundEach = (selector: string) => coordinates
    .map(({ lat, lng }) => `${selector}(around:${PRIVACY_CONTEXT_RADIUS_METERS},${lat},${lng});`)
    .join('\n');
  return `[out:json][timeout:20];
    (
      ${aroundEach('way[highway~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|track|road)$"][area!=yes][access!~"^(no|private)$"][vehicle!~"^(no|private)$"][motor_vehicle!~"^(no|private)$"]')}
    )->.roads;
    (
      ${aroundEach('way[highway~"^(path|footway|pedestrian|cycleway|track)$"][access!~"^(no|private)$"]')}
    )->.paths;
    (
      ${aroundEach('nwr[building]')}
    )->.buildings;
    .roads out tags geom;
    .paths out tags geom;
    .buildings out center tags;`;
}

export async function POST(request: NextRequest) {
  const requestStartedAt = performance.now();
  const serverTimings: string[] = [];
  async function measure<T>(name: string, operation: () => Promise<T>) {
    const startedAt = performance.now();
    try {
      return await operation();
    } finally {
      serverTimings.push(`${name};dur=${(performance.now() - startedAt).toFixed(1)}`);
    }
  }
  let staleCache: SearchCacheEntry | null = null;
  try {
    const { city, location } = await request.json();
    if (!city || typeof city !== 'string') {
      return NextResponse.json({ success: false, error: 'Enter a city to search.' }, { status: 400 });
    }

    const suppliedLat = Number(location?.lat);
    const suppliedLng = Number(location?.lng);
    const hasSuppliedLocation = Number.isFinite(suppliedLat) && Number.isFinite(suppliedLng)
      && suppliedLat >= -90 && suppliedLat <= 90 && suppliedLng >= -180 && suppliedLng <= 180;
    let match: {
      lat: string;
      lon: string;
      name?: string;
      address?: { city?: string; town?: string; municipality?: string; country?: string };
    };

    if (hasSuppliedLocation) {
      match = {
        lat: String(suppliedLat),
        lon: String(suppliedLng),
        name: typeof location?.name === 'string' ? location.name : city,
        address: {
          city: typeof location?.name === 'string' ? location.name : city,
          country: typeof location?.country === 'string' ? location.country : '',
        },
      };
    } else {
      const geoUrl = new URL('https://nominatim.openstreetmap.org/search');
      geoUrl.searchParams.set('q', city);
      geoUrl.searchParams.set('format', 'jsonv2');
      geoUrl.searchParams.set('limit', '1');
      geoUrl.searchParams.set('addressdetails', '1');
      const geoResponse = await fetch(geoUrl, {
        headers: { 'User-Agent': 'HushQuietSpots/1.0 (local prototype)' },
        next: { revalidate: 86400 },
      });
      if (!geoResponse.ok) throw new Error('City lookup is temporarily unavailable.');
      const matches = await geoResponse.json();
      if (!matches.length) {
        return NextResponse.json({ success: false, error: `We couldn't find “${city}”. Try a city and country.` }, { status: 404 });
      }
      match = matches[0];
    }

    const lat = Number(match.lat);
    const lng = Number(match.lon);
    const resolvedCountry = match.address?.country || (typeof location?.country === 'string' ? location.country : '');
    const useSwedishNmd = isSwedishCountry(resolvedCountry);
    const cached = await readSearchCache(lat, lng, resolvedCountry);
    if (cached?.fresh) return cachedSearchResponse(cached, 'HIT');
    staleCache = cached;
    const latitudeRadius = SPOT_SEARCH_RADIUS_METERS / 110_540;
    const longitudeRadius = SPOT_SEARCH_RADIUS_METERS / Math.max(1, 111_320 * Math.cos(lat * Math.PI / 180));
    const searchBounds = [
      lat - latitudeRadius,
      lng - longitudeRadius,
      lat + latitudeRadius,
      lng + longitudeRadius,
    ].join(',');
    const query = `[out:json][timeout:18];
      node(${searchBounds})[amenity=shelter][access!=private][shelter_type!=public_transport][highway!=bus_stop]->.shelters;
    (
      node(${searchBounds})[tourism~"^(viewpoint|picnic_site)$"];
      node.shelters;
      nwr(${searchBounds})[natural~"^(beach|wood|scrub|heath|grassland|bare_rock|scree|shingle)$"];
      nwr(${searchBounds})[leisure~"^(nature_reserve|park|garden|recreation_ground)$"];
      nwr(${searchBounds})[landuse~"^(forest|recreation_ground|cemetery)$"];
      nwr(${searchBounds})[landuse~"^(meadow|grass)$"][access~"^(yes|permissive|designated)$"];
      nwr(${searchBounds})[amenity=grave_yard];
      nwr(${searchBounds})[man_made=pier];
    )->.spots;
    .spots out body geom;
    (
      node(around.shelters:${TRANSIT_SHELTER_RADIUS_METERS})[highway=bus_stop];
      nwr(around.shelters:${TRANSIT_SHELTER_RADIUS_METERS})[public_transport=platform][bus~"^(yes|designated)$"];
      node(around.shelters:${TRANSIT_SHELTER_RADIUS_METERS})[railway=tram_stop];
    );out center;`;
    const osmData = await measure('osm_places', () => fetchOverpass(query));
    const osmElements = osmData.elements as OsmElement[];
    const nearbyTransitStops = osmElements.filter((element) => {
      const tags = element.tags ?? {};
      return tags.highway === 'bus_stop'
        || tags.railway === 'tram_stop'
        || (tags.public_transport === 'platform' && ['yes', 'designated'].includes(tags.bus));
    });
    const seen = new Set<string>();
    const rankedCandidates = osmElements
      .filter(isSpotElement)
      .filter((element) => searchDistanceMeters({ lat, lng }, element) <= SPOT_SEARCH_RADIUS_METERS)
      .filter((element) => !isPublicTransportShelter(element))
      .filter((element) => !['no', 'private'].includes(element.tags?.access ?? ''))
      .filter((element) => {
        const coordinate = representativeCoordinate(element);
        if (element.tags?.amenity !== 'shelter' || element.tags.shelter_type || !coordinate) return true;
        return !nearbyTransitStops.some((stop) => {
          const stopCoordinate = representativeCoordinate(stop);
          return stopCoordinate != null
            && pointDistanceMeters(coordinate, { lat: stopCoordinate.lat, lon: stopCoordinate.lng }) <= TRANSIT_SHELTER_RADIUS_METERS;
        });
      })
      .map((element): SpotCandidate | null => {
        const spot = toSpot(element);
        return spot ? { element, spot } : null;
      })
      .filter((candidate): candidate is SpotCandidate => Boolean(candidate))
      .filter(({ spot }) => {
        const key = `${spot.name}-${spot.lat.toFixed(3)}-${spot.lng.toFixed(3)}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((a, b) => b.spot.privacy - a.spot.privacy);

    const woodedCandidates = rankedCandidates.filter(({ element, spot }) => spot.kind === 'nature' && screeningStrength(element.tags ?? {}) >= 2);
    const cemeteryCandidates = rankedCandidates.filter(({ spot }) => spot.kind === 'cemetery');
    const otherCandidates = rankedCandidates.filter(({ element, spot }) => spot.kind !== 'cemetery'
      && !(spot.kind === 'nature' && screeningStrength(element.tags ?? {}) >= 2));
    const searchOrigin = { lat, lng };
    const nearbyWoodedCandidates = [...woodedCandidates]
      .sort((first, second) => pointDistanceMeters(first.spot, { lat, lon: lng })
        - pointDistanceMeters(second.spot, { lat, lon: lng }));
    const relationWoodedCandidates = nearbyWoodedCandidates.filter(({ element }) => element.type === 'relation');
    const sampledWoodedCandidates = uniqueCandidates([
      ...relationWoodedCandidates.slice(0, 6),
      ...nearbyWoodedCandidates.slice(0, 8),
      ...spatiallyDiverseCandidates(woodedCandidates, 14, searchOrigin),
    ]).slice(0, 24);
    const nearbyOtherCandidates = [...otherCandidates]
      .sort((first, second) => pointDistanceMeters(first.spot, { lat, lon: lng })
        - pointDistanceMeters(second.spot, { lat, lon: lng }));
    const relationOtherCandidates = nearbyOtherCandidates.filter(({ element }) => element.type === 'relation');
    const sampledOtherCandidates = uniqueCandidates([
      ...relationOtherCandidates.slice(0, 4),
      ...nearbyOtherCandidates.slice(0, 8),
      ...spatiallyDiverseCandidates(otherCandidates, 12, searchOrigin),
    ]).slice(0, 18);
    const accessCandidates = uniqueCandidates([
      ...sampledWoodedCandidates,
      ...cemeteryCandidates.slice(0, 6),
      ...sampledOtherCandidates,
    ]);

    // Candidate geometry is returned with the initial bbox query, avoiding a
    // second public Overpass round trip before privacy analysis can begin.
    let evidenceCandidates = withAreaGeometry(accessCandidates, osmElements);

    let checkedCandidates: SpotCandidate[] = [];
    let usedCdse = false;
    let usedNmd = false;
    try {
      // Road/building context and the first evidence pass are independent. Run
      // them together so public OSM latency does not stack on top of raster work.
      // In Sweden, local NMD is enough to choose refinement points; Copernicus is
      // then sampled once for all of those points instead of once before and once
      // after refinement.
      const [contextData, initialEvidenceCandidates] = await Promise.all([
        measure('osm_context', () => fetchOverpass(privacyContextQuery(evidenceCandidates))),
        measure('initial_evidence', () => (useSwedishNmd
          ? withVegetationStructureEvidence(evidenceCandidates)
          : withTreeCoverEvidence(evidenceCandidates))),
      ]);
      evidenceCandidates = initialEvidenceCandidates;
      usedCdse = evidenceCandidates.some((candidate) => Boolean(candidate.canopy));
      usedNmd = evidenceCandidates.some((candidate) => (candidate.vegetation?.validPixelPercent ?? 0) >= MIN_NMD_VALID_PERCENT);
      const contextElements = contextData.elements as OsmElement[];
      const allRoads = contextElements.filter((element) => element.type === 'way'
        && Boolean(element.tags?.highway));
      const roads = allRoads.filter((element) => element.type === 'way'
        && DRIVABLE_ROAD_TYPES.has(element.tags?.highway ?? ''));
      const paths = contextElements.filter((element) => element.type === 'way' && WALKING_PATH_TYPES.has(element.tags?.highway ?? ''));
      const buildings = contextElements.filter((element) => Boolean(element.tags?.building));
      const mainRoads = allRoads.filter((element) => MAIN_ROAD_TYPES.has(element.tags?.highway ?? ''));
      let refinedCandidates: SpotCandidate[];
      let finalCoverCandidates: SpotCandidate[];
      if (usedNmd) {
        const optionSets = evidenceCandidates.map((candidate) => vegetationRefinementOptions(
          candidate, roads, paths, buildings, mainRoads, 3,
        ));
        const refinementOptions: SpotCandidate[] = [];
        for (let rank = 0; rank < 3 && refinementOptions.length < 80; rank += 1) {
          for (const options of optionSets) {
            if (options[rank]) refinementOptions.push(options[rank]);
            if (refinementOptions.length >= 80) break;
          }
        }
        const [vegetationOptions, canopyOptions] = await Promise.all([
          measure('nmd_refinement', () => withVegetationStructureEvidence(refinementOptions)),
          measure('cdse_refinement', () => withTreeCoverEvidence(refinementOptions)),
        ]);
        const measuredOptions = vegetationOptions.map((candidate, index) => ({
          ...candidate,
          ...(canopyOptions[index]?.canopy ? { canopy: canopyOptions[index].canopy } : {}),
        }));
        refinedCandidates = selectVegetationRefinedCandidates(
          measuredOptions, roads, paths, buildings, mainRoads,
        );
        finalCoverCandidates = refinedCandidates;
      } else {
        refinedCandidates = evidenceCandidates
          .map((candidate) => refineAreaCandidate(candidate, roads, paths, buildings, mainRoads))
          .filter((candidate): candidate is SpotCandidate => Boolean(candidate));
        finalCoverCandidates = await measure('cdse_final', () => withTreeCoverEvidence(refinedCandidates));
      }
      usedCdse = usedCdse || finalCoverCandidates.some((candidate) => Boolean(candidate.canopy));
      usedNmd = usedNmd || finalCoverCandidates.some((candidate) => (candidate.vegetation?.validPixelPercent ?? 0) >= MIN_NMD_VALID_PERCENT);
      checkedCandidates = finalCoverCandidates
        .filter((candidate) => privacyEligible(candidate, roads, paths, buildings, mainRoads))
        .map((candidate) => withPrivacyEvidence(candidate, roads, paths, buildings))
        .map(({ element, spot, interiorClearanceMeters, canopy, vegetation }) => ({
          element,
          interiorClearanceMeters,
          canopy,
          vegetation,
          spot: withRoadAccess(spot, roads),
        }))
        .sort((a, b) => b.spot.privacy - a.spot.privacy);
    } catch (error) {
      console.warn('Privacy context lookup failed.', error);
      // On context failure, keep only places with strong mapped screening evidence.
    }

    const selectedCandidates = selectDiverseSpots(checkedCandidates, 20);
    const spots = selectedCandidates.map(({ spot }) => spot);

    if (!spots.length) {
      if (staleCache) return cachedSearchResponse(staleCache, 'STALE');
      return NextResponse.json({ success: false, error: 'No suitable mapped public outdoor places were found nearby.' }, { status: 404 });
    }

    const cityName = match.address?.city || match.address?.town || match.address?.municipality || match.name || city;
    const response: SearchCacheEntry['response'] = {
      success: true,
      city: { name: cityName, country: resolvedCountry, lat, lng },
      spots,
      source: [
        'OpenStreetMap',
        ...(usedCdse ? ['Copernicus CDSE'] : []),
        ...(usedNmd ? ['NMD vegetation height'] : []),
      ].join(' + '),
    };
    await writeSearchCache(lat, lng, resolvedCountry, response);
    serverTimings.push(`total;dur=${(performance.now() - requestStartedAt).toFixed(1)}`);
    return NextResponse.json(response, {
      headers: {
        'X-Spot-Cache': 'MISS',
        'Server-Timing': serverTimings.join(', '),
      },
    });
  } catch (error) {
    if (staleCache) return cachedSearchResponse(staleCache, 'STALE');
    return NextResponse.json({
      success: false,
      error: error instanceof Error ? error.message : 'Something went wrong while finding spots.',
    }, { status: 500 });
  }
}
