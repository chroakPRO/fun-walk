'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Route, Coordinate } from '@/types/route';

// Fix for default markers in Next.js
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

interface RouteMapProps {
  routes: Route[];
  start: Coordinate;
  end: Coordinate;
  className?: string;
}

export default function RouteMap({ routes, start, end, className = '' }: RouteMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    // Initialize map
    const map = L.map(mapRef.current).setView([start.lat, start.lng], 14);
    mapInstanceRef.current = map;

    // Add tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // Add start marker
    const startIcon = L.divIcon({
      html: '<div class="bg-green-500 w-4 h-4 rounded-full border-2 border-white shadow-lg"></div>',
      className: 'custom-marker',
      iconSize: [16, 16],
      iconAnchor: [8, 8]
    });

    L.marker([start.lat, start.lng], { icon: startIcon })
      .addTo(map)
      .bindPopup(`
        <div class="font-mono text-xs bg-gray-900 text-green-400 p-2 rounded">
          <b class="text-yellow-400">[START POINT]</b><br>
          LAT: ${start.lat.toFixed(6)}<br>
          LON: ${start.lng.toFixed(6)}<br>
          <span class="text-gray-400">${routes.length} routes computed</span>
        </div>
      `);

    // Add end marker
    const endIcon = L.divIcon({
      html: '<div class="bg-red-500 w-4 h-4 rounded-full border-2 border-white shadow-lg"></div>',
      className: 'custom-marker',
      iconSize: [16, 16],
      iconAnchor: [8, 8]
    });

    L.marker([end.lat, end.lng], { icon: endIcon })
      .addTo(map)
      .bindPopup(`
        <div class="font-mono text-xs bg-gray-900 text-green-400 p-2 rounded">
          <b class="text-yellow-400">[DESTINATION]</b><br>
          LAT: ${end.lat.toFixed(6)}<br>
          LON: ${end.lng.toFixed(6)}<br>
          <span class="text-gray-400">All routes end here</span>
        </div>
      `);

    // Add routes
    routes.forEach((route) => {
      const coordinates: [number, number][] = route.route.map(coord => [coord.lat, coord.lng]);
      
      let dashArray: string | undefined;
      let weight = 4;
      
      if (route.name === 'SHORTEST') {
        dashArray = '10,5';
        weight = 3;
      } else if (route.name === 'MOST_FUN') {
        weight = 5;
      } else {
        dashArray = '15,10,5,10';
      }

      const polyline = L.polyline(coordinates, {
        color: route.color,
        weight,
        opacity: 0.8,
        dashArray
      }).addTo(map);

        // Create detailed popup
        const mainPath = Object.entries(route.stats.path_types)
          .filter(([, data]) => data.distance > 0)
          .sort(([, a], [, b]) => b.distance - a.distance)[0];

        const mainSurface = Object.entries(route.stats.surface_types)
          .filter(([, data]) => data.distance > 0)
          .sort(([, a], [, b]) => b.distance - a.distance)[0];
      const specialAreas = Object.keys(route.stats.special_areas)
        .filter(key => route.stats.special_areas[key].distance > 0);

      polyline.bindPopup(`
        <div class="font-mono text-xs bg-gray-900 text-green-400 p-3 rounded max-w-xs">
          <b class="text-yellow-400">[${route.name} ROUTE]</b><br>
          <span class="text-gray-400">${route.description}</span><br><br>
          DISTANCE: ${route.stats.distance.toFixed(0)}m (${(route.stats.distance/1000).toFixed(2)}km)<br>
          TIME EST: <span class="text-cyan-400">${route.stats.estimated_time.toFixed(0)} minutes</span><br>
          AVG SPEED: ${route.stats.avg_speed.toFixed(1)} km/h<br>
          FUN SCORE: <span class="text-orange-400">${route.stats.fun_score.toFixed(2)}</span><br><br>
          ${mainPath ? `
            <b class="text-yellow-400">MAIN PATH TYPE:</b><br>
            ${mainPath[0].toUpperCase()}: ${mainPath[1].time.toFixed(0)}min (${mainPath[1].distance.toFixed(0)}m)<br>
            <span class="text-gray-400">${mainPath[1].description}</span><br><br>
          ` : ''}
          ${mainSurface ? `
            <b class="text-yellow-400">SURFACE:</b><br>
            ${mainSurface[0].toUpperCase()}: ${mainSurface[1].time.toFixed(0)}min<br>
            <span class="text-gray-400">${mainSurface[1].description}</span><br><br>
          ` : ''}
          <b class="text-yellow-400">SPECIAL AREAS:</b><br>
          ${specialAreas.length > 0 ? specialAreas.join(', ') : 'None detected'}
        </div>
      `);
    });

    // Fit map to show all routes
    if (routes.length > 0) {
      const allCoords = routes.flatMap(route => 
        route.route.map(coord => [coord.lat, coord.lng] as [number, number])
      );
      const bounds = L.latLngBounds(allCoords);
      map.fitBounds(bounds, { padding: [20, 20] });
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, [routes, start, end]);

  return (
    <div 
      ref={mapRef} 
      className={`w-full h-full min-h-[400px] rounded-lg overflow-hidden ${className}`}
    />
  );
}