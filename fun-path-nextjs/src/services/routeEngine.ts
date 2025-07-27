import { Coordinate, Route } from '@/types/route';

export class RouteEngine {
  static async calculateMultipleRoutes(start: Coordinate, end: Coordinate): Promise<Route[]> {
    console.log('RouteEngine: Calling Python FastAPI backend from', start, 'to', end);
    
    try {
      // Call the Python FastAPI backend
      const response = await fetch('http://localhost:8000/api/routes', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          start: { lat: start.lat, lng: start.lng },
          end: { lat: end.lat, lng: end.lng },
          buffer_dist: 3000
        }),
        signal: AbortSignal.timeout(30000) // 30 second timeout
      });

      if (!response.ok) {
        throw new Error(`Python API error: ${response.status}`);
      }

      const data = await response.json();
      
      if (!data.success || !data.routes) {
        throw new Error('No routes found from Python API');
      }

      console.log(`RouteEngine: Received ${data.routes.length} routes from Python API`);
      
      // Convert Python API response to our Route format
      const routes: Route[] = data.routes.map((route: {
        name: string;
        description: string;
        coordinates: Array<{lat: number; lng: number}>;
        stats: Record<string, unknown>;
        color: string;
        priority: string;
      }) => ({
        name: route.name,
        description: route.description,
        route: route.coordinates.map((coord: {lat: number; lng: number}) => ({ lat: coord.lat, lng: coord.lng })),
        stats: route.stats,
        color: route.color,
        priority: route.priority
      }));

      return routes;

    } catch (error) {
      console.error('Python API error:', error);
      
      // Fallback to simple direct route
      return this.createFallbackRoutes(start, end);
    }
  }





  private static createFallbackRoutes(start: Coordinate, end: Coordinate): Route[] {
    // Create simple fallback routes when API fails
    const directRoute: Coordinate[] = [start, end];
    
    const distance = this.calculateDistance(start, end) * 1000; // Convert to meters
    const estimatedTime = distance / 1000 * (60 / 4.2); // Walking speed 4.2 km/h
    
    const baseStats = {
      distance,
      fun_weight: distance,
      fun_score: 1.0,
      estimated_time: estimatedTime,
      waypoints: 2,
      path_types: {
        other: {
          distance,
          time: estimatedTime,
          speed: 4.2,
          description: 'Direct route (limited data)'
        }
      },
      surface_types: {
        unknown: {
          distance,
          time: estimatedTime,
          speed_modifier: 1.0,
          description: 'Unknown surface'
        }
      },
      special_areas: {},
      segments: [],
      avg_speed: 4.2
    };

    return [
      {
        name: 'DIRECT',
        description: 'Direct route (limited OSM data)',
        route: directRoute,
        stats: baseStats,
        color: '#888888',
        priority: 'speed'
      }
    ];
  }

  private static calculateDistance(start: Coordinate, end: Coordinate): number {
    // Haversine formula for distance calculation
    const R = 6371; // Earth's radius in km
    const dLat = this.toRad(end.lat - start.lat);
    const dLng = this.toRad(end.lng - start.lng);
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(this.toRad(start.lat)) * Math.cos(this.toRad(end.lat)) *
              Math.sin(dLng/2) * Math.sin(dLng/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
  }

  private static toRad(degrees: number): number {
    return degrees * (Math.PI / 180);
  }
}