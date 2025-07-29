#!/usr/bin/env python3
"""
Create a map showing only nature POIs from the enhanced OSM data
"""

import json
from datetime import datetime

def create_nature_poi_map(enhanced_osm_file: str):
    """Create HTML map showing nature POIs"""
    print(f"Loading OSM data from {enhanced_osm_file}...")
    
    with open(enhanced_osm_file, 'r', encoding='utf-8') as f:
        osm_data = json.load(f)
    
    pois = osm_data.get('pois', [])
    print(f"Total POIs: {len(pois)}")
    
    def categorize_poi(poi: dict) -> str:
        """Same categorization as in routing engine"""
        attrs = poi.get('attributes', {})
        
        # Nature categories
        if (attrs.get('natural') in ['tree', 'water', 'park'] or 
            attrs.get('landuse') in ['forest', 'grass', 'garden'] or
            attrs.get('leisure') in ['garden']):
            return 'nature'
        
        # Recreation & Sports
        elif attrs.get('leisure') in ['park', 'playground', 'sports_centre', 'pitch']:
            return 'recreation'
        
        return 'other'
    
    # Filter for nature and recreation POIs
    nature_pois = []
    recreation_pois = []
    
    for poi in pois:
        if 'lat' not in poi or 'lng' not in poi:
            continue
            
        category = categorize_poi(poi)
        
        if category == 'nature':
            nature_pois.append(poi)
        elif category == 'recreation':
            recreation_pois.append(poi)
    
    print(f"Nature POIs: {len(nature_pois)}")
    print(f"Recreation POIs: {len(recreation_pois)}")
    
    # Get bounding box from metadata
    bbox = osm_data['metadata']['bounding_box']
    center_lat = bbox['center']['lat']
    center_lng = bbox['center']['lng']
    
    # Create HTML map
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nature POIs - Swedish Area</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body {{ 
            font-family: Arial, sans-serif; 
            margin: 0; 
            padding: 20px; 
        }}
        #map {{ 
            height: 80vh; 
            width: 100%; 
            margin-bottom: 20px; 
        }}
        .info-panel {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .stats {{
            display: flex;
            gap: 30px;
            margin-bottom: 15px;
        }}
        .stat {{
            text-align: center;
        }}
        .stat-number {{
            font-size: 24px;
            font-weight: bold;
            color: #2e7d32;
        }}
        .stat-label {{
            font-size: 14px;
            color: #666;
        }}
        .legend {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 15px;
            border-radius: 5px;
            box-shadow: 0 0 10px rgba(0,0,0,0.3);
            z-index: 1000;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin-bottom: 8px;
        }}
        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 50%;
            margin-right: 10px;
        }}
    </style>
</head>
<body>
    <h1>Nature POIs - Gothenburg Area</h1>
    
    <div class="info-panel">
        <div class="stats">
            <div class="stat">
                <div class="stat-number">{len(nature_pois)}</div>
                <div class="stat-label">Nature POIs</div>
            </div>
            <div class="stat">
                <div class="stat-number">{len(recreation_pois)}</div>
                <div class="stat-label">Recreation POIs</div>
            </div>
            <div class="stat">
                <div class="stat-number">{len(nature_pois) + len(recreation_pois)}</div>
                <div class="stat-label">Total Green/Outdoor POIs</div>
            </div>
        </div>
        <p><strong>Area:</strong> {bbox['point1']['lat']:.4f}, {bbox['point1']['lng']:.4f} to {bbox['point2']['lat']:.4f}, {bbox['point2']['lng']:.4f}</p>
    </div>
    
    <div id="map"></div>
    
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        // Initialize map
        var map = L.map('map').setView([{center_lat}, {center_lng}], 13);
        
        // Add OpenStreetMap tiles
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);
        
        // Nature POIs data
        var naturePOIs = {json.dumps(nature_pois)};
        var recreationPOIs = {json.dumps(recreation_pois)};
        
        // Add nature POIs
        naturePOIs.forEach(function(poi) {{
            if (poi.lat && poi.lng) {{
                var name = poi.attributes.name || 'Unnamed Nature Area';
                var natural = poi.attributes.natural || '';
                var landuse = poi.attributes.landuse || '';
                var leisure = poi.attributes.leisure || '';
                
                var type = natural || landuse || leisure || 'unknown';
                
                var marker = L.circleMarker([poi.lat, poi.lng], {{
                    radius: 6,
                    fillColor: '#4CAF50',
                    color: '#2E7D32',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.8
                }}).addTo(map);
                
                var popupContent = '<b>' + name + '</b><br>' +
                                 'Type: ' + type + '<br>' +
                                 'Category: Nature';
                
                marker.bindPopup(popupContent);
            }}
        }});
        
        // Add recreation POIs
        recreationPOIs.forEach(function(poi) {{
            if (poi.lat && poi.lng) {{
                var name = poi.attributes.name || 'Unnamed Recreation Area';
                var leisure = poi.attributes.leisure || 'recreation';
                
                var marker = L.circleMarker([poi.lat, poi.lng], {{
                    radius: 6,
                    fillColor: '#8BC34A',
                    color: '#558B2F',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.8
                }}).addTo(map);
                
                var popupContent = '<b>' + name + '</b><br>' +
                                 'Type: ' + leisure + '<br>' +
                                 'Category: Recreation';
                
                marker.bindPopup(popupContent);
            }}
        }});
        
        // Add legend
        var legend = L.control({{position: 'topright'}});
        legend.onAdd = function(map) {{
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<h4>Nature & Recreation POIs</h4>' +
                          '<div class="legend-item">' +
                          '<div class="legend-color" style="background-color: #4CAF50;"></div>' +
                          'Nature Areas (' + naturePOIs.length + ')' +
                          '</div>' +
                          '<div class="legend-item">' +
                          '<div class="legend-color" style="background-color: #8BC34A;"></div>' +
                          'Recreation Areas (' + recreationPOIs.length + ')' +
                          '</div>';
            return div;
        }};
        legend.addTo(map);
        
        // Fit map to show all POIs
        var allPOIs = naturePOIs.concat(recreationPOIs);
        if (allPOIs.length > 0) {{
            var group = new L.featureGroup();
            allPOIs.forEach(function(poi) {{
                if (poi.lat && poi.lng) {{
                    group.addLayer(L.marker([poi.lat, poi.lng]));
                }}
            }});
            map.fitBounds(group.getBounds().pad(0.1));
        }}
    </script>
</body>
</html>
"""
    
    # Save map
    filename = f"nature_poi_map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Nature POI map saved to {filename}")
    
    # Show some examples of nature POIs
    print("\\nExample Nature POIs:")
    for i, poi in enumerate(nature_pois[:10]):
        name = poi['attributes'].get('name', 'Unnamed')
        natural = poi['attributes'].get('natural', '')
        landuse = poi['attributes'].get('landuse', '')
        leisure = poi['attributes'].get('leisure', '')
        poi_type = natural or landuse or leisure or 'unknown'
        print(f"  {i+1}. {name} ({poi_type}) at {poi['lat']:.4f}, {poi['lng']:.4f}")
    
    return filename

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python create_nature_poi_map.py <enhanced_osm_file.json>")
        sys.exit(1)
    
    create_nature_poi_map(sys.argv[1])