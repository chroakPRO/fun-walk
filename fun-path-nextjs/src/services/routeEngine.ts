import { Coordinate, Route, RouteType } from '@/types/route';

export class RouteEngine {
  static async calculateMultipleRoutes(
    start: Coordinate,
    end: Coordinate,
    routeType: RouteType = 'scenic'
  ): Promise<Route[]> {
    console.log('RouteEngine: Calling Python FastAPI backend from', start, 'to', end);
    const backendUrl = (process.env.ROUTING_API_URL || 'http://localhost:8000').replace(/\/$/, '');
    
    try {
      // Call the Python FastAPI backend
      const response = await fetch(`${backendUrl}/api/routes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          start: { lat: start.lat, lng: start.lng },
          end: { lat: end.lat, lng: end.lng },
          buffer_dist: 3000,
          route_type: routeType
        }),
        signal: AbortSignal.timeout(120000)
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(`Python API error ${response.status}: ${errorBody || response.statusText}`);
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
        route: Array<{lat: number; lng: number}>;  // Backend now sends 'route', not 'coordinates'
        stats: Route['stats'];
        color: string;
        priority: Route['priority'];
      }) => ({
        name: route.name,
        description: route.description,
        route: route.route.map((coord: {lat: number; lng: number}) => ({ lat: coord.lat, lng: coord.lng })),
        stats: route.stats,
        color: route.color,
        priority: route.priority
      }));

      return routes;

    } catch (error) {
      console.error('Python API error:', error);
      const message = error instanceof Error ? error.message : 'Unknown routing backend error';
      throw new Error(`Routing backend unavailable; refusing to return an invalid straight-line route: ${message}`);
    }
  }
}
