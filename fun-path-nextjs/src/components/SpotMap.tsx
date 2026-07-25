'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { SmokeSpot } from '@/types/spot';

interface SpotMapProps {
  spots: SmokeSpot[];
  selectedId: string | null;
  city: { lat: number; lng: number };
  focus: { lat: number; lng: number; zoom: number; token: number } | null;
  onSelect: (spot: SmokeSpot) => void;
}

export default function SpotMap({ spots, selectedId, city, focus, onSelect }: SpotMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: false, attributionControl: false }).setView([city.lat, city.lng], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
    L.control.attribution({ position: 'bottomright', prefix: false }).addAttribution('© OpenStreetMap').addTo(map);
    mapRef.current = map;
    layerRef.current = L.layerGroup().addTo(map);
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [city.lat, city.lng]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();

    spots.forEach((spot, index) => {
      const selected = spot.id === selectedId;
      const icon = L.divIcon({
        className: 'hush-pin-wrap',
        html: `<div class="hush-pin ${selected ? 'is-selected' : ''}"><span>${index + 1}</span></div>`,
        iconSize: selected ? [46, 54] : [38, 46],
        iconAnchor: selected ? [23, 52] : [19, 44],
      });
      L.marker([spot.lat, spot.lng], { icon, zIndexOffset: selected ? 1000 : 0 })
        .addTo(layer)
        .on('click', () => onSelect(spot));
    });

    if (spots.length) {
      const bounds = L.latLngBounds(spots.map((spot) => [spot.lat, spot.lng]));
      map.fitBounds(bounds, { paddingTopLeft: [60, 60], paddingBottomRight: [60, 180], maxZoom: 13 });
    } else {
      map.setView([city.lat, city.lng], 12);
    }
  }, [spots, selectedId, city.lat, city.lng, onSelect]);

  useEffect(() => {
    if (focus && mapRef.current) mapRef.current.setView([focus.lat, focus.lng], focus.zoom, { animate: true });
  }, [focus]);

  return <div ref={containerRef} className="spot-map" aria-label="Map of quiet spots" />;
}
