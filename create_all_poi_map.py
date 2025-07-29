#!/usr/bin/env python3
"""
Create a comprehensive map showing all POI categories
"""

import json
from datetime import datetime

def create_all_poi_map(enhanced_osm_file: str):
    """Create HTML map showing all POI categories"""
    print(f"Loading OSM data from {enhanced_osm_file}...")
    
    with open(enhanced_osm_file, 'r', encoding='utf-8') as f:
        osm_data = json.load(f)
    
    pois = osm_data.get('pois', [])
    print(f"Total POIs: {len(pois)}")
    
    def categorize_poi(poi: dict) -> str:
        """Same categorization as in routing engine"""
        attrs = poi.get('attributes', {})
        
        # Food categories
        if attrs.get('amenity') == 'restaurant':
            return 'restaurants'
        elif attrs.get('amenity') == 'fast_food':
            return 'fast_food'
        elif attrs.get('amenity') == 'cafe':
            return 'cafes'
        elif attrs.get('amenity') in ['bar', 'pub']:
            return 'bars_pubs'
        
        # Nature categories
        elif (attrs.get('natural') in ['tree', 'water', 'park'] or 
              attrs.get('landuse') in ['forest', 'grass', 'garden'] or
              attrs.get('leisure') in ['garden']):
            return 'nature'
        
        # Recreation & Sports
        elif attrs.get('leisure') in ['park', 'playground', 'sports_centre', 'pitch']:
            return 'recreation'
        
        # Shopping
        elif attrs.get('shop'):
            return 'shops'
        
        # Tourism & Culture
        elif (attrs.get('tourism') in ['attraction', 'museum', 'gallery', 'monument'] or
              attrs.get('historic') or
              attrs.get('amenity') in ['theatre', 'cinema', 'arts_centre']):
            return 'tourism'
        
        # Education
        elif attrs.get('amenity') in ['school', 'university', 'college', 'library']:
            return 'education'
        
        # Transportation
        elif (attrs.get('amenity') in ['bicycle_parking', 'parking_space', 'bicycle_rental'] or
              attrs.get('highway') in ['bus_stop'] or
              attrs.get('public_transport')):
            return 'transport'
        
        # Urban amenities (filtered out in routing but shown here)
        elif attrs.get('amenity') in ['bench', 'waste_basket', 'toilets', 'atm']:
            return 'urban_amenities'
        
        # Default
        return 'other'
    
    # Categorize all POIs
    categorized_pois = {}
    category_counts = {}
    
    for poi in pois:
        if 'lat' not in poi or 'lng' not in poi:
            continue
            
        category = categorize_poi(poi)
        
        if category not in categorized_pois:
            categorized_pois[category] = []
            category_counts[category] = 0
            
        categorized_pois[category].append(poi)
        category_counts[category] += 1
    
    print("\\nPOI Categories:")
    for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {category}: {count}")
    
    # Sample POIs for performance (max 1000 per category)
    sampled_pois = {}
    for category, poi_list in categorized_pois.items():
        sampled_pois[category] = poi_list[:1000] if len(poi_list) > 1000 else poi_list
    
    # Get bounding box
    bbox = osm_data['metadata']['bounding_box']
    center_lat = bbox['center']['lat']
    center_lng = bbox['center']['lng']
    
    # Define colors for each category
    colors = {
        'restaurants': '#FF5722',      # Deep Orange
        'fast_food': '#FF9800',        # Orange
        'cafes': '#FFC107',            # Amber
        'bars_pubs': '#9C27B0',        # Purple
        'nature': '#4CAF50',           # Green
        'recreation': '#8BC34A',       # Light Green
        'shops': '#2196F3',            # Blue
        'tourism': '#E91E63',          # Pink
        'education': '#3F51B5',        # Indigo
        'transport': '#607D8B',        # Blue Grey
        'urban_amenities': '#9E9E9E',  # Grey
        'other': '#795548'             # Brown
    }
    
    # Create HTML
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>All POIs - Gothenburg</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body {{ margin: 0; padding: 20px; font-family: Arial, sans-serif; }}
        #map {{ height: 80vh; width: 100%; }}
        .info {{ background: white; padding: 15px; margin-bottom: 10px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }}
        .stat {{ text-align: center; padding: 10px; border-radius: 5px; }}
        .stat-num {{ font-size: 18px; font-weight: bold; }}
        .stat-label {{ font-size: 12px; margin-top: 5px; }}
        .legend {{ background: white; padding: 10px; border-radius: 5px; max-height: 400px; overflow-y: auto; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 5px; }}
        .legend-color {{ width: 15px; height: 15px; border-radius: 50%; margin-right: 8px; }}
        .control-panel {{ position: absolute; top: 10px; left: 10px; z-index: 1000; }}
        .toggle-btn {{ 
            background: white; 
            border: none; 
            padding: 8px 12px; 
            margin: 2px; 
            border-radius: 3px; 
            cursor: pointer; 
            font-size: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }}
        .toggle-btn.active {{ background: #007cff; color: white; }}
    </style>
</head>
<body>
    <div class="info">
        <h1>All POIs - Gothenburg Area</h1>
        <div class="stats">
"""
    
    # Add stats for each category
    for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        color = colors.get(category, '#000000')
        html_content += f"""
            <div class="stat" style="background-color: {color}20; border-left: 4px solid {color};">
                <div class="stat-num">{count}</div>
                <div class="stat-label">{category.replace('_', ' ').title()}</div>
            </div>
"""
    
    html_content += f"""
        </div>
    </div>
    
    <div id="map"></div>
    
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        var map = L.map('map').setView([{center_lat}, {center_lng}], 13);
        
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);
        
        var colors = {json.dumps(colors)};
        var poiData = {json.dumps(sampled_pois)};
        var layers = {{}};
        
        // Create layers for each category
        Object.keys(poiData).forEach(function(category) {{
            layers[category] = L.layerGroup();
            var categoryPois = poiData[category];
            var color = colors[category] || '#000000';
            
            categoryPois.forEach(function(poi) {{
                if (poi.lat && poi.lng) {{
                    var name = poi.attributes.name || 'Unnamed';
                    var marker = L.circleMarker([poi.lat, poi.lng], {{
                        radius: 4,
                        fillColor: color,
                        color: color,
                        weight: 1,
                        opacity: 0.8,
                        fillOpacity: 0.6
                    }});
                    
                    var popupContent = '<b>' + name + '</b><br>' +
                                     'Category: ' + category.replace('_', ' ') + '<br>' +
                                     'Type: ' + (poi.attributes.amenity || poi.attributes.shop || poi.attributes.natural || poi.attributes.leisure || poi.attributes.tourism || 'unknown');
                    
                    marker.bindPopup(popupContent);
                    layers[category].addLayer(marker);
                }}
            }});
            
            // Add to map by default
            map.addLayer(layers[category]);
        }});
        
        // Create layer control
        var overlayMaps = {{}};
        Object.keys(layers).forEach(function(category) {{
            var displayName = category.replace('_', ' ').replace(/\\b\\w/g, l => l.toUpperCase()) + 
                             ' (' + poiData[category].length + ')';
            overlayMaps[displayName] = layers[category];
        }});
        
        L.control.layers(null, overlayMaps, {{ collapsed: false }}).addTo(map);
        
        // Add legend
        var legend = L.control({{position: 'bottomright'}});
        legend.onAdd = function(map) {{
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<h4>POI Categories</h4>';
            
            Object.keys(colors).forEach(function(category) {{
                var color = colors[category];
                var count = poiData[category] ? poiData[category].length : 0;
                var displayName = category.replace('_', ' ').replace(/\\b\\w/g, l => l.toUpperCase());
                
                div.innerHTML += 
                    '<div class="legend-item">' +
                    '<div class="legend-color" style="background-color:' + color + ';"></div>' +
                    displayName + ' (' + count + ')' +
                    '</div>';
            }});
            
            return div;
        }};
        legend.addTo(map);
    </script>
</body>
</html>
"""
    
    # Save map
    filename = f"all_pois_gothenburg_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\\nAll POIs map created: {filename}")
    print(f"Total POIs mapped: {sum(len(pois) for pois in sampled_pois.values())}")
    return filename

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python create_all_poi_map.py <enhanced_osm_file.json>")
        sys.exit(1)
    
    create_all_poi_map(sys.argv[1])