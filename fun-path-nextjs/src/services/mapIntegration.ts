import { Route } from '@/types/route';

export class MapIntegration {
  // Open route in Google Maps
  static openInGoogleMaps(route: Route) {
    const start = route.route[0];
    const end = route.route[route.route.length - 1];
    
    // Create waypoints string for intermediate points
    const waypoints = route.route.slice(1, -1);
    const waypointsStr = waypoints.length > 0 
      ? `&waypoints=${waypoints.map(w => `${w.lat},${w.lng}`).join('|')}`
      : '';
    
    const url = `https://www.google.com/maps/dir/${start.lat},${start.lng}/${end.lat},${end.lng}${waypointsStr}&dirflg=w`;
    window.open(url, '_blank');
  }

  // Open route in Apple Maps
  static openInAppleMaps(route: Route) {
    const start = route.route[0];
    const end = route.route[route.route.length - 1];
    
    const url = `http://maps.apple.com/?saddr=${start.lat},${start.lng}&daddr=${end.lat},${end.lng}&dirflg=w`;
    window.open(url, '_blank');
  }

  // Open route in Waze (if available)
  static openInWaze(route: Route) {
    const end = route.route[route.route.length - 1];
    const url = `https://waze.com/ul?ll=${end.lat},${end.lng}&navigate=yes`;
    window.open(url, '_blank');
  }

  // Share route via Web Share API
  static async shareRoute(route: Route) {
    if (navigator.share) {
      try {
        const start = route.route[0];
        const end = route.route[route.route.length - 1];
        
        await navigator.share({
          title: `${route.name} Route`,
          text: `Check out this ${route.description.toLowerCase()} - ${route.stats.distance.toFixed(0)}m in ${route.stats.estimated_time.toFixed(0)} minutes`,
          url: `${typeof window !== 'undefined' ? window.location.origin : ''}?start=${start.lat},${start.lng}&end=${end.lat},${end.lng}`
        });
      } catch (error) {
        console.error('Error sharing route:', error);
        this.fallbackShare(route);
      }
    } else {
      this.fallbackShare(route);
    }
  }

  // Fallback share method
  private static fallbackShare(route: Route) {
    const start = route.route[0];
    const end = route.route[route.route.length - 1];
    const url = `${typeof window !== 'undefined' ? window.location.origin : ''}?start=${start.lat},${start.lng}&end=${end.lat},${end.lng}`;
    
    navigator.clipboard.writeText(url).then(() => {
      alert('Route link copied to clipboard!');
    }).catch(() => {
      prompt('Copy this route link:', url);
    });
  }

  // Get route URL for sharing
  static getRouteURL(route: Route): string {
    const start = route.route[0];
    const end = route.route[route.route.length - 1];
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    return `${origin}?start=${start.lat},${start.lng}&end=${end.lat},${end.lng}`;
  }
}

export class RouteExporter {
  // Export route as GPX file
  static exportAsGPX(route: Route): void {
    const gpxContent = this.generateGPX(route);
    const blob = new Blob([gpxContent], { type: 'application/gpx+xml' });
    const url = URL.createObjectURL(blob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = `${route.name.toLowerCase()}_route.gpx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  // Export route as KML file
  static exportAsKML(route: Route): void {
    const kmlContent = this.generateKML(route);
    const blob = new Blob([kmlContent], { type: 'application/vnd.google-earth.kml+xml' });
    const url = URL.createObjectURL(blob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = `${route.name.toLowerCase()}_route.kml`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  // Export route as GeoJSON
  static exportAsGeoJSON(route: Route): void {
    const geoJsonContent = this.generateGeoJSON(route);
    const blob = new Blob([JSON.stringify(geoJsonContent, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = `${route.name.toLowerCase()}_route.geojson`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  private static generateGPX(route: Route): string {
    const trackPoints = route.route.map(coord => 
      `    <trkpt lat="${coord.lat}" lon="${coord.lng}"></trkpt>`
    ).join('\n');

    return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Fun Path Planner" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata>
    <name>${route.name} Route</name>
    <desc>${route.description}</desc>
    <time>${new Date().toISOString()}</time>
  </metadata>
  <trk>
    <name>${route.name}</name>
    <desc>${route.description} - ${route.stats.distance.toFixed(0)}m in ${route.stats.estimated_time.toFixed(0)} minutes</desc>
    <trkseg>
${trackPoints}
    </trkseg>
  </trk>
</gpx>`;
  }

  private static generateKML(route: Route): string {
    const coordinates = route.route.map(coord => `${coord.lng},${coord.lat},0`).join(' ');

    return `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>${route.name} Route</name>
    <description>${route.description}</description>
    <Style id="routeStyle">
      <LineStyle>
        <color>ff${route.color.substring(1)}</color>
        <width>4</width>
      </LineStyle>
    </Style>
    <Placemark>
      <name>${route.name}</name>
      <description>${route.description} - ${route.stats.distance.toFixed(0)}m in ${route.stats.estimated_time.toFixed(0)} minutes</description>
      <styleUrl>#routeStyle</styleUrl>
      <LineString>
        <coordinates>${coordinates}</coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>`;
  }

  private static generateGeoJSON(route: Route): object {
    return {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {
            name: route.name,
            description: route.description,
            distance: route.stats.distance,
            estimated_time: route.stats.estimated_time,
            fun_score: route.stats.fun_score,
            color: route.color,
            priority: route.priority
          },
          geometry: {
            type: 'LineString',
            coordinates: route.route.map(coord => [coord.lng, coord.lat])
          }
        }
      ]
    };
  }
}