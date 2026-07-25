import { NextRequest, NextResponse } from 'next/server';
import { CitySuggestion } from '@/types/spot';

type PhotonFeature = {
  properties?: {
    osm_id?: number;
    osm_key?: string;
    osm_value?: string;
    type?: string;
    name?: string;
    city?: string;
    county?: string;
    state?: string;
    country?: string;
  };
  geometry?: {
    coordinates?: [number, number];
  };
};

type PhotonResponse = {
  features?: PhotonFeature[];
};

type NominatimResult = {
  osm_id?: number;
  lat?: string;
  lon?: string;
  name?: string;
  display_name?: string;
  type?: string;
  addresstype?: string;
  address?: {
    city?: string;
    town?: string;
    village?: string;
    municipality?: string;
    state?: string;
    county?: string;
    country?: string;
  };
};

function displayParts(name: string, properties: PhotonFeature['properties']) {
  return [name, properties?.state || properties?.county, properties?.country].filter(Boolean).join(', ');
}

function isCityLike(properties: PhotonFeature['properties']) {
  if (!properties?.name) return false;
  if (properties.type === 'city') return true;
  if (properties.osm_key === 'place' && ['city', 'town', 'village', 'municipality'].includes(properties.osm_value || '')) return true;
  if (properties.osm_key === 'boundary' && properties.osm_value === 'administrative' && properties.type === 'city') return true;
  return false;
}

function photonSuggestions(matches: PhotonResponse, query: string) {
  const seen = new Set<string>();
  const results: CitySuggestion[] = [];

  for (const match of matches.features ?? []) {
    const properties = match.properties;
    if (!isCityLike(properties)) continue;

    const name = properties?.name || query;
    const country = properties?.country || '';
    const coordinates = match.geometry?.coordinates;
    if (!coordinates) continue;
    const [lng, lat] = coordinates;
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;

    const key = `${name.toLowerCase()}-${country.toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);

    results.push({
      id: String(properties?.osm_id || key),
      name,
      country,
      displayName: displayParts(name, properties),
      lat,
      lng,
    });
  }
  return results;
}

function nominatimSuggestions(matches: NominatimResult[], query: string) {
  const seen = new Set<string>();
  const results: CitySuggestion[] = [];
  for (const match of matches) {
    if (!['city', 'town', 'village', 'municipality'].includes(match.addresstype || match.type || '')) continue;
    const address = match.address ?? {};
    const name = match.name || address.city || address.town || address.village || address.municipality || query;
    const country = address.country || '';
    const lat = Number(match.lat);
    const lng = Number(match.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
    const key = `${name.toLowerCase()}-${country.toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    results.push({
      id: String(match.osm_id || key),
      name,
      country,
      displayName: match.display_name || [name, address.state || address.county, country].filter(Boolean).join(', '),
      lat,
      lng,
    });
  }
  return results;
}

export async function POST(request: NextRequest) {
  try {
    const { query, limit = 6 } = await request.json();
    if (!query || typeof query !== 'string' || query.trim().length < 2) {
      return NextResponse.json({ success: true, results: [] });
    }

    const geoUrl = new URL('https://photon.komoot.io/api/');
    geoUrl.searchParams.set('q', query.trim());
    geoUrl.searchParams.set('limit', String(Math.min(Number(limit) || 6, 8)));
    geoUrl.searchParams.set('lang', 'en');

    let photonUnavailable = false;
    try {
      const response = await fetch(geoUrl, {
        headers: { 'User-Agent': 'HushCitySearch/1.0 (local prototype)' },
        next: { revalidate: 86400 },
      });
      if (!response.ok) throw new Error('Photon city search failed.');
      const results = photonSuggestions(await response.json() as PhotonResponse, query.trim());
      if (results.length) return NextResponse.json({ success: true, results });
    } catch {
      photonUnavailable = true;
    }

    const fallbackUrl = new URL('https://nominatim.openstreetmap.org/search');
    fallbackUrl.searchParams.set('q', query.trim());
    fallbackUrl.searchParams.set('format', 'jsonv2');
    fallbackUrl.searchParams.set('addressdetails', '1');
    fallbackUrl.searchParams.set('limit', String(Math.min(Number(limit) || 6, 8)));
    try {
      const fallbackResponse = await fetch(fallbackUrl, {
        headers: { 'User-Agent': 'HushCitySearch/1.0 (local prototype)' },
        next: { revalidate: 86400 },
      });
      if (!fallbackResponse.ok) throw new Error('Nominatim city search failed.');
      const results = nominatimSuggestions(await fallbackResponse.json() as NominatimResult[], query.trim());
      return NextResponse.json({ success: true, results });
    } catch {
      if (!photonUnavailable) return NextResponse.json({ success: true, results: [] });
      throw new Error('City suggestions are temporarily unavailable.');
    }
  } catch (error) {
    return NextResponse.json({
      success: false,
      error: error instanceof Error ? error.message : 'City search failed.',
    }, { status: 500 });
  }
}
