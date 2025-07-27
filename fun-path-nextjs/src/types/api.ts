// OpenRouteService API types
export interface OpenRouteServiceResponse {
  features: Array<{
    geometry: {
      coordinates: [number, number][];
    };
    properties: {
      summary: {
        distance: number;
        duration: number;
      };
      segments: Array<{
        distance: number;
        duration: number;
        extras?: {
          waytype?: {
            values: Array<[number, number, number]>;
          };
          surface?: {
            values: Array<[number, number, number]>;
          };
          steepness?: {
            values: Array<[number, number, number]>;
          };
        };
      }>;
    };
  }>;
}

// Overpass API types
export interface OverpassElement {
  id: number;
  type: 'node' | 'way' | 'relation';
  lat?: number;
  lon?: number;
  nodes?: number[];
  geometry?: Array<{
    lat: number;
    lon: number;
  }>;
  tags: Record<string, string>;
}

export interface OverpassResponse {
  elements: OverpassElement[];
}

// Nominatim API types
export interface NominatimResult {
  lat: string;
  lon: string;
  display_name: string;
  place_id: number;
  licence: string;
  osm_type: string;
  osm_id: number;
  boundingbox: [string, string, string, string];
  class: string;
  type: string;
  importance: number;
}

export interface NominatimReverseResult {
  place_id: number;
  licence: string;
  osm_type: string;
  osm_id: number;
  lat: string;
  lon: string;
  display_name: string;
  address: Record<string, string>;
  boundingbox: [string, string, string, string];
}