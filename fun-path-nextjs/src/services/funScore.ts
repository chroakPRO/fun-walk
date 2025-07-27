import { Coordinate, RouteStats } from '@/types/route';
import { OpenRouteServiceResponse } from '@/types/api';

export interface POI {
  id: string;
  type: 'park' | 'forest' | 'viewpoint' | 'attraction' | 'water' | 'trail';
  coordinates: Coordinate[];
  name?: string;
  tags: Record<string, string>;
}

export class FunScoreCalculator {
  // Scoring weights for different features
  private static readonly WEIGHTS = {
    park: 2.0,
    forest: 2.5,
    viewpoint: 3.0,
    attraction: 2.5,
    water: 1.5,
    trail: 2.0,
    footway: 1.8,
    path: 2.2,
    track: 1.5,
    steps: 0.8, // Steps are less fun
    residential: 0.5,
    primary: 0.3, // Main roads are less fun
  };

  // Surface type modifiers
  private static readonly SURFACE_MODIFIERS = {
    paved: 1.0,
    asphalt: 1.0,
    concrete: 0.9,
    unpaved: 1.2,
    gravel: 1.3,
    dirt: 1.4,
    grass: 1.5,
    sand: 1.2,
    unknown: 1.0
  };

  static calculateRouteScore(
    routeCoordinates: Coordinate[],
    pois: POI[],
    routeData: OpenRouteServiceResponse
  ): number {
    let totalScore = 0;
    let totalDistance = 0;

    // Calculate base score from route segments
    if (routeData?.features?.[0]?.properties?.segments) {
      for (const segment of routeData.features[0].properties.segments) {
        const segmentDistance = segment.distance;
        totalDistance += segmentDistance;

        // Score based on way type
        const wayType = this.getWayType(segment);
        const wayScore = this.WEIGHTS[wayType as keyof typeof this.WEIGHTS] || 1.0;

        // Score based on surface
        const surface = this.getSurface(segment);
        const surfaceModifier = this.SURFACE_MODIFIERS[surface as keyof typeof this.SURFACE_MODIFIERS] || 1.0;

        totalScore += segmentDistance * wayScore * surfaceModifier;
      }
    }

    // Add POI proximity bonuses
    const poiBonus = this.calculatePOIBonus(routeCoordinates, pois);
    totalScore += poiBonus;

    // Calculate final fun score (higher is more fun)
    return totalDistance > 0 ? totalScore / totalDistance : 1.0;
  }

  private static getWayType(segment: OpenRouteServiceResponse['features'][0]['properties']['segments'][0]): string {
    // Extract way type from OpenRouteService segment data
    if (segment.extras?.waytype?.values) {
      const wayTypeValue = segment.extras.waytype.values[0]?.[2];
      const wayTypes = ['unknown', 'state_road', 'road', 'street', 'path', 'track', 'cycleway', 'footway', 'steps', 'ferry', 'construction'];
      return wayTypes[wayTypeValue] || 'unknown';
    }
    return 'unknown';
  }

  private static getSurface(segment: OpenRouteServiceResponse['features'][0]['properties']['segments'][0]): string {
    // Extract surface type from OpenRouteService segment data
    if (segment.extras?.surface?.values) {
      const surfaceValue = segment.extras.surface.values[0]?.[2];
      const surfaces = ['unknown', 'paved', 'unpaved', 'asphalt', 'concrete', 'cobblestone', 'metal', 'wood', 'compacted_gravel', 'fine_gravel', 'gravel', 'dirt', 'grass', 'ground', 'ice', 'paving_stones', 'salt', 'sand', 'snow'];
      return surfaces[surfaceValue] || 'unknown';
    }
    return 'unknown';
  }

  private static calculatePOIBonus(routeCoordinates: Coordinate[], pois: POI[]): number {
    let bonus = 0;
    const proximityThreshold = 0.001; // ~100m in degrees

    for (const poi of pois) {
      const poiWeight = this.WEIGHTS[poi.type] || 1.0;
      
      // Check if route passes near this POI
      const isNearRoute = routeCoordinates.some(coord => 
        poi.coordinates.some(poiCoord => 
          this.getDistance(coord, poiCoord) < proximityThreshold
        )
      );

      if (isNearRoute) {
        bonus += poiWeight * 100; // Bonus points for passing near POIs
      }
    }

    return bonus;
  }

  private static getDistance(coord1: Coordinate, coord2: Coordinate): number {
    // Simple Euclidean distance for proximity check
    const latDiff = coord1.lat - coord2.lat;
    const lngDiff = coord1.lng - coord2.lng;
    return Math.sqrt(latDiff * latDiff + lngDiff * lngDiff);
  }

  static generateRouteStats(
    routeData: OpenRouteServiceResponse,
    pois: POI[],
    funScore: number
  ): RouteStats {
    const coordinates = routeData.features[0].geometry.coordinates.map(
      (coord) => ({ lat: coord[1], lng: coord[0] })
    );

    const distance = routeData.features[0].properties.summary.distance;
    const duration = routeData.features[0].properties.summary.duration;

    // Analyze path types from route segments
    const pathTypes: Record<string, {
      distance: number;
      time: number;
      speed: number;
      description: string;
    }> = {};
    const surfaceTypes: Record<string, {
      distance: number;
      time: number;
      speed_modifier: number;
      description: string;
    }> = {};
    const specialAreas: Record<string, {
      distance: number;
      time: number;
      description: string;
    }> = {};

    // Initialize default types
    const defaultPathTypes = ['footway', 'path', 'track', 'steps', 'sidewalk', 'residential', 'other'];
    const defaultSurfaces = ['paved', 'unpaved', 'grass', 'gravel', 'unknown'];

    defaultPathTypes.forEach(type => {
      pathTypes[type] = {
        distance: 0,
        time: 0,
        speed: this.getSpeedForPathType(type),
        description: this.getPathTypeDescription(type)
      };
    });

    defaultSurfaces.forEach(surface => {
      surfaceTypes[surface] = {
        distance: 0,
        time: 0,
        speed_modifier: this.SURFACE_MODIFIERS[surface as keyof typeof this.SURFACE_MODIFIERS] || 1.0,
        description: this.getSurfaceDescription(surface)
      };
    });

    // Process route segments
    if (routeData.features[0].properties.segments) {
      for (const segment of routeData.features[0].properties.segments) {
        const segmentDistance = segment.distance;
        const segmentDuration = segment.duration / 60; // Convert to minutes

        const wayType = this.getWayType(segment);
        const surface = this.getSurface(segment);

        // Update path types
        const pathType = this.mapWayTypeToPathType(wayType);
        if (pathTypes[pathType]) {
          pathTypes[pathType].distance += segmentDistance;
          pathTypes[pathType].time += segmentDuration;
        }

        // Update surface types
        if (surfaceTypes[surface]) {
          surfaceTypes[surface].distance += segmentDistance;
          surfaceTypes[surface].time += segmentDuration;
        }
      }
    }

    // Analyze POIs for special areas
    const poiTypes = ['park', 'forest', 'viewpoint', 'attraction', 'water'];
    poiTypes.forEach(type => {
      const poisOfType = pois.filter(poi => poi.type === type);
      if (poisOfType.length > 0) {
        specialAreas[type] = {
          distance: poisOfType.length * 50, // Estimate 50m per POI
          time: poisOfType.length * 2, // Estimate 2 minutes per POI
          description: this.getSpecialAreaDescription(type)
        };
      }
    });

    return {
      distance,
      fun_weight: distance / funScore,
      fun_score: funScore,
      estimated_time: duration / 60, // Convert to minutes
      waypoints: coordinates.length,
      path_types: pathTypes,
      surface_types: surfaceTypes,
      special_areas: specialAreas,
      segments: [], // Could be populated with detailed segment data
      avg_speed: (distance / 1000) / (duration / 3600) // km/h
    };
  }

  private static getSpeedForPathType(type: string): number {
    const speeds: Record<string, number> = {
      sidewalk: 5.0,
      footway: 4.5,
      path: 4.0,
      track: 3.5,
      steps: 2.5,
      residential: 4.8,
      other: 4.0
    };
    return speeds[type] || 4.0;
  }

  private static getPathTypeDescription(type: string): string {
    const descriptions: Record<string, string> = {
      sidewalk: 'Sidewalks and walkways',
      footway: 'Dedicated walking paths',
      path: 'Natural trails and paths',
      track: 'Forest trails and dirt roads',
      steps: 'Stairs and stepped paths',
      residential: 'Residential streets',
      other: 'Other road types'
    };
    return descriptions[type] || 'Unknown path type';
  }

  private static getSurfaceDescription(surface: string): string {
    const descriptions: Record<string, string> = {
      paved: 'Paved surfaces (asphalt/concrete)',
      unpaved: 'Unpaved surfaces (gravel/dirt)',
      grass: 'Grass and natural ground',
      gravel: 'Gravel surfaces',
      unknown: 'Unknown surface type'
    };
    return descriptions[surface] || 'Unknown surface';
  }

  private static getSpecialAreaDescription(type: string): string {
    const descriptions: Record<string, string> = {
      park: 'Parks and green spaces',
      forest: 'Forests and wooded areas',
      viewpoint: 'Scenic viewpoints',
      attraction: 'Tourist attractions',
      water: 'Water features and waterfront'
    };
    return descriptions[type] || 'Special area';
  }

  private static mapWayTypeToPathType(wayType: string): string {
    const mapping: Record<string, string> = {
      footway: 'footway',
      path: 'path',
      track: 'track',
      steps: 'steps',
      street: 'residential',
      road: 'residential',
      cycleway: 'footway'
    };
    return mapping[wayType] || 'other';
  }
}