export type SpotKind = 'viewpoint' | 'nature' | 'waterside' | 'shelter' | 'park' | 'picnic' | 'playground' | 'cemetery';

export interface SpotEvidence {
  treeCanopyPercent?: number;
  eyeLevelVegetationPercent?: number;
  nearestRoadMeters?: number;
  nearestBuildingMeters?: number;
  nearestPathMeters?: number;
  interiorClearanceMeters?: number;
  nearbyPathCount?: number;
  sources: string[];
}

export interface SmokeSpot {
  id: string;
  name: string;
  kind: SpotKind;
  lat: number;
  lng: number;
  placeType?: string;
  privacy: number;
  quiet: number;
  treeCoverPercent?: number;
  lowVegetationPercent?: number;
  tallVegetationPercent?: number;
  carAccess: 'Difficult' | 'Limited' | 'Easy' | 'Unknown';
  walkMinutes: number | null;
  accessNote?: string;
  summary: string;
  why: string[];
  features: string[];
  evidence?: SpotEvidence;
}

export interface SpotSearchResponse {
  success: boolean;
  city?: {
    name: string;
    country: string;
    lat: number;
    lng: number;
  };
  spots?: SmokeSpot[];
  source?: string;
  error?: string;
}

export interface CitySuggestion {
  id: string;
  name: string;
  country: string;
  displayName: string;
  lat: number;
  lng: number;
}

export interface CitySuggestionResponse {
  success: boolean;
  results?: CitySuggestion[];
  error?: string;
}
