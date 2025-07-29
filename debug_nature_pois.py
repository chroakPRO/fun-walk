#!/usr/bin/env python3
"""
Debug script to investigate nature POIs and why they might not show on map
"""

import json

def debug_nature_pois(enhanced_osm_file: str):
    """Debug nature POIs to see what's wrong"""
    
    with open(enhanced_osm_file, 'r') as f:
        osm_data = json.load(f)
    
    # Filter for nature POIs using same logic as routing engine
    def categorize_poi(poi: dict) -> str:
        attrs = poi.get('attributes', {})
        if (attrs.get('natural') in ['tree', 'water', 'park'] or 
            attrs.get('landuse') in ['forest', 'grass', 'garden'] or
            attrs.get('leisure') in ['garden']):
            return 'nature'
        return 'other'
    
    nature_pois = []
    for poi in osm_data.get('pois', []):
        if categorize_poi(poi) == 'nature':
            nature_pois.append(poi)
    
    print(f"Nature POIs: {len(nature_pois)}")
    print(f"\nFirst 10 nature POIs:")
    
    valid_coords = 0
    invalid_coords = 0
    
    for i, poi in enumerate(nature_pois[:10]):
        print(f"\n{i+1}. OSM ID: {poi['osm_id']}")
        print(f"   Lat/Lng: {poi.get('lat', 'MISSING')}, {poi.get('lng', 'MISSING')}")
        print(f"   Attributes: {poi['attributes']}")
        
        if poi.get('lat') and poi.get('lng'):
            valid_coords += 1
        else:
            invalid_coords += 1
    
    # Check all nature POIs for coordinates
    for poi in nature_pois:
        if poi.get('lat') and poi.get('lng'):
            valid_coords += 1
        else:
            invalid_coords += 1
    
    print(f"\nCoordinate Summary:")
    print(f"Valid coordinates: {valid_coords}")
    print(f"Invalid coordinates: {invalid_coords}")
    
    # Check what types of nature features we have
    nature_types = {}
    for poi in nature_pois:
        attrs = poi['attributes']
        for key, value in attrs.items():
            if key.startswith('natural') or key.startswith('landuse'):
                nature_type = f"{key}={value}"
                nature_types[nature_type] = nature_types.get(nature_type, 0) + 1
    
    print(f"\nNature types breakdown:")
    for nature_type, count in sorted(nature_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {nature_type}: {count}")
    
    # Create HTML map
    create_nature_html_map(nature_pois, osm_data['metadata'])

def create_nature_html_map(nature_pois, metadata):
    """Create HTML map of nature POIs"""
    from datetime import datetime
    
    bbox = metadata['bounding_box']
    center_lat = bbox['center']['lat']
    center_lng = bbox['center']['lng']
    
    # Sample POIs for performance (show max 5000)
    sample_pois = nature_pois[:5000] if len(nature_pois) > 5000 else nature_pois
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Nature POIs - Gothenburg</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body {{ margin: 0; padding: 20px; font-family: Arial, sans-serif; }}
        #map {{ height: 80vh; width: 100%; }}
        .info {{ background: white; padding: 15px; margin-bottom: 10px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .stats {{ display: flex; gap: 20px; }}
        .stat {{ text-align: center; }}
        .stat-num {{ font-size: 24px; font-weight: bold; color: #2e7d32; }}
        .stat-label {{ font-size: 14px; color: #666; }}
    </style>
</head>
<body>
    <div class="info">
        <h1>Nature POIs - Gothenburg Area</h1>
        <div class="stats">
            <div class="stat">
                <div class="stat-num">{len(nature_pois)}</div>
                <div class="stat-label">Total Nature POIs</div>
            </div>
            <div class="stat">
                <div class="stat-num">{len(sample_pois)}</div>
                <div class="stat-label">Shown on Map</div>
            </div>
        </div>
    </div>
    
    <div id="map"></div>
    
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        var map = L.map('map').setView([{center_lat}, {center_lng}], 13);
        
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);
        
        var naturePOIs = {json.dumps(sample_pois)};
        
        // Color by type
        function getColor(poi) {{
            var attrs = poi.attributes;
            if (attrs.natural === 'tree') return '#4CAF50';
            if (attrs.landuse === 'grass') return '#8BC34A';
            if (attrs.landuse === 'forest') return '#2E7D32';
            if (attrs.natural === 'water') return '#2196F3';
            return '#9E9E9E';
        }}
        
        naturePOIs.forEach(function(poi) {{
            if (poi.lat && poi.lng) {{
                var color = getColor(poi);
                var name = poi.attributes.name || 'Unnamed';
                var type = poi.attributes.natural || poi.attributes.landuse || 'unknown';
                
                L.circleMarker([poi.lat, poi.lng], {{
                    radius: 4,
                    fillColor: color,
                    color: color,
                    weight: 1,
                    opacity: 0.8,
                    fillOpacity: 0.6
                }}).addTo(map).bindPopup('<b>' + name + '</b><br>Type: ' + type);
            }}
        }});
        
        // Legend
        var legend = L.control({{position: 'topright'}});
        legend.onAdd = function(map) {{
            var div = L.DomUtil.create('div', 'info legend');
            div.innerHTML = '<h4>Nature Types</h4>' +
                          '<i style="background:#4CAF50; width:18px; height:18px; float:left; margin-right:8px; opacity:0.7; border-radius:50%;"></i> Trees<br>' +
                          '<i style="background:#8BC34A; width:18px; height:18px; float:left; margin-right:8px; opacity:0.7; border-radius:50%;"></i> Grass<br>' +
                          '<i style="background:#2E7D32; width:18px; height:18px; float:left; margin-right:8px; opacity:0.7; border-radius:50%;"></i> Forest<br>' +
                          '<i style="background:#2196F3; width:18px; height:18px; float:left; margin-right:8px; opacity:0.7; border-radius:50%;"></i> Water<br>';
            return div;
        }};
        legend.addTo(map);
    </script>
</body>
</html>
"""
    
    filename = f"gothenburg_nature_pois_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\nHTML map created: {filename}")
    return filename

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python debug_nature_pois.py <enhanced_osm_file.json>")
        sys.exit(1)
    
    debug_nature_pois(sys.argv[1])