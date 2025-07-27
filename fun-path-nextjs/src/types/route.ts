export interface Coordinate {
  lat: number;
  lng: number;
}

export interface PathTypeStats {
  distance: number;
  time: number;
  speed: number;
  description: string;
}

export interface SurfaceTypeStats {
  distance: number;
  time: number;
  speed_modifier: number;
  description: string;
}

export interface SpecialAreaStats {
  distance: number;
  time: number;
  description: string;
}

export interface RouteSegment {
  length: number;
  time: number;
  path_type: string;
  surface_type: string;
  speed: number;
  features: string[];
  name: string;
}

export interface RouteStats {
  distance: number;
  fun_weight: number;
  fun_score: number;
  estimated_time: number;
  waypoints: number;
  path_types: Record<string, PathTypeStats>;
  surface_types: Record<string, SurfaceTypeStats>;
  special_areas: Record<string, SpecialAreaStats>;
  segments: RouteSegment[];
  avg_speed: number;
}

export interface Route {
  name: string;
  description: string;
  route: Coordinate[];
  stats: RouteStats;
  color: string;
  priority: 'speed' | 'fun' | 'balanced';
}

export interface RouteRequest {
  start: Coordinate;
  end: Coordinate;
  buffer_dist?: number;
}

export interface RouteResponse {
  routes: Route[];
  success: boolean;
  error?: string;
}