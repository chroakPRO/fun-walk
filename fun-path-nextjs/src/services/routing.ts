import { Coordinate } from '@/types/route';
import { OpenRouteServiceResponse, OverpassResponse, NominatimResult, NominatimReverseResult } from '@/types/api';

// OpenRouteService API client
export class OpenRouteService {
  private static readonly BASE_URL = 'https://api.openrouteservice.org/v2';
  private static readonly API_KEY = '5b3ce3597851110001cf6248f24b3cc0c99f4187b2ab848cecd411ec'; // Demo key - will implement OSM-based routing instead

  static async getRoute(start: Coordinate, end: Coordinate, profile: 'foot-walking' | 'foot-hiking' = 'foot-walking'): Promise<OpenRouteServiceResponse> {
    const url = `${this.BASE_URL}/directions/${profile}`;
    
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': this.API_KEY,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          coordinates: [[start.lng, start.lat], [end.lng, end.lat]],
          format: 'geojson',
          instructions: true,
          elevation: true,
          extra_info: ['surface', 'waytype', 'steepness']
        })
      });

      if (!response.ok) {
        throw new Error(`OpenRouteService error: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('OpenRouteService routing error:', error);
      throw error;
    }
  }

  static async getMultipleRoutes(start: Coordinate, end: Coordinate) {
    try {
      // Get different route profiles
      const [walkingRoute, hikingRoute] = await Promise.allSettled([
        this.getRoute(start, end, 'foot-walking'),
        this.getRoute(start, end, 'foot-hiking')
      ]);

      const routes = [];
      
      if (walkingRoute.status === 'fulfilled') {
        routes.push({
          type: 'walking',
          data: walkingRoute.value
        });
      }

      if (hikingRoute.status === 'fulfilled') {
        routes.push({
          type: 'hiking', 
          data: hikingRoute.value
        });
      }

      return routes;
    } catch (error) {
      console.error('Error getting multiple routes:', error);
      throw error;
    }
  }
}

// Overpass API for POI data
export class OverpassAPI {
  private static readonly BASE_URL = 'https://overpass-api.de/api/interpreter';

  static async getPOIsNearRoute(coordinates: Coordinate[]): Promise<OverpassResponse> {
    // Create bounding box from coordinates
    const lats = coordinates.map(c => c.lat);
    const lngs = coordinates.map(c => c.lng);
    const bbox = {
      south: Math.min(...lats) - 0.01,
      west: Math.min(...lngs) - 0.01,
      north: Math.max(...lats) + 0.01,
      east: Math.max(...lngs) + 0.01
    };

    const query = `
      [out:json][timeout:25];
      (
        // Parks and green spaces
        way["leisure"="park"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        way["landuse"="forest"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        way["natural"="wood"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        
        // Viewpoints and attractions
        node["tourism"="viewpoint"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        node["tourism"="attraction"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        
        // Water features
        way["natural"="water"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        way["waterway"="river"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        
        // Trails and paths
        way["highway"="footway"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        way["highway"="path"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        way["highway"="track"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
      );
      out geom;
    `;

    try {
      const response = await fetch(this.BASE_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `data=${encodeURIComponent(query)}`
      });

      if (!response.ok) {
        throw new Error(`Overpass API error: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Overpass API error:', error);
      throw error;
    }
  }
}

// Nominatim API for geocoding
export class NominatimAPI {
  private static readonly BASE_URL = 'https://nominatim.openstreetmap.org';

  static async geocode(address: string): Promise<Coordinate[]> {
    try {
      const response = await fetch(
        `${this.BASE_URL}/search?format=json&q=${encodeURIComponent(address)}&limit=5`
      );

      if (!response.ok) {
        throw new Error(`Nominatim error: ${response.status}`);
      }

      const results: NominatimResult[] = await response.json();
      return results.map((result) => ({
        lat: parseFloat(result.lat),
        lng: parseFloat(result.lon),
        display_name: result.display_name
      }));
    } catch (error) {
      console.error('Geocoding error:', error);
      throw error;
    }
  }

  static async reverseGeocode(coordinate: Coordinate): Promise<string> {
    try {
      const response = await fetch(
        `${this.BASE_URL}/reverse?format=json&lat=${coordinate.lat}&lon=${coordinate.lng}`
      );

      if (!response.ok) {
        throw new Error(`Nominatim error: ${response.status}`);
      }

      const result: NominatimReverseResult = await response.json();
      return result.display_name || `${coordinate.lat}, ${coordinate.lng}`;
    } catch (error) {
      console.error('Reverse geocoding error:', error);
      return `${coordinate.lat}, ${coordinate.lng}`;
    }
  }
}