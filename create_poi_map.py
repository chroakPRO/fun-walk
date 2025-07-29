#!/usr/bin/env python3
"""
Create interactive HTML map visualization of POI data
"""

import json
import sys
from datetime import datetime

def create_poi_map(analysis_file):
    """
    Create interactive HTML map from POI analysis data
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Creating POI map from {analysis_file}")
    
    with open(analysis_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    center_lat, center_lng = data['metadata']['center_coordinates']
    
    # Color scheme for different categories
    category_colors = {
        'restaurants': '#e74c3c',      # Red
        'fast_food': '#f39c12',        # Orange  
        'cafes': '#8b4513',            # Brown
        'bars_pubs': '#9b59b6',        # Purple
        'food_other': '#f1c40f',       # Yellow
        'shops': '#3498db',            # Blue
        'entertainment': '#e91e63',     # Pink
        'recreation': '#4caf50',        # Green
        'transport': '#95a5a6',         # Gray
        'accommodation': '#00bcd4',     # Cyan
        'healthcare': '#ff5722',        # Deep Orange
        'education': '#673ab7',         # Deep Purple
        'nature': '#8bc34a',           # Light Green
        'historic_culture': '#795548',  # Brown
        'services': '#607d8b',         # Blue Gray
        'other': '#9e9e9e'             # Light Gray
    }
    
    # Start building HTML
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>POI Analysis Map - {datetime.now().strftime('%Y-%m-%d')}</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: 'Arial', sans-serif;
        }}
        #map {{
            height: 100vh;
            width: 100%;
        }}
        .legend {{
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 0 15px rgba(0,0,0,0.2);
            line-height: 18px;
            color: #555;
        }}
        .legend h4 {{
            margin: 0 0 5px;
            color: #777;
        }}
        .legend-item {{
            margin: 3px 0;
        }}
        .legend-color {{
            width: 18px;
            height: 18px;
            display: inline-block;
            margin-right: 8px;
            border-radius: 50%;
        }}
        .info-panel {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 15px;
            border-radius: 5px;
            box-shadow: 0 0 15px rgba(0,0,0,0.2);
            z-index: 1000;
            max-width: 300px;
        }}
        .stats {{
            margin-top: 10px;
        }}
        .stat-item {{
            margin: 2px 0;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="info-panel">
        <h3>POI Analysis</h3>
        <p><strong>Total POIs:</strong> {data['metadata']['total_pois']:,}</p>
        <div class="stats">
"""
    
    # Add category stats to info panel
    for category, count in sorted(data['category_summary'].items(), key=lambda x: x[1], reverse=True)[:10]:
        if count > 0:
            html_content += f'            <div class="stat-item"><strong>{category.replace("_", " ").title()}:</strong> {count}</div>\n'
    
    html_content += """        </div>
    </div>
    
    <script>
        // Initialize map
        var map = L.map('map').setView([{}, {}], 13);
        
        // Add tile layer
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);
        
        // Define category colors
        var categoryColors = {}
        
        // Layer groups for each category
        var layerGroups = {{}};
        
""".format(center_lat, center_lng, json.dumps(category_colors))
    
    # Add JavaScript to create layer groups
    for category in category_colors.keys():
        html_content += f"        layerGroups['{category}'] = L.layerGroup();\n"
    
    html_content += """
        // Add POI markers
        var poiData = """ + json.dumps(data['detailed_categories']) + """;
        
        Object.keys(poiData).forEach(function(category) {
            if (!layerGroups[category]) return;
            
            poiData[category].forEach(function(poi) {
                if (!poi.lat || !poi.lng) return;
                
                var color = categoryColors[category] || '#666';
                var name = poi.attributes.name || 'Unnamed';
                var cuisine = poi.attributes.cuisine || '';
                var brand = poi.attributes.brand || '';
                var address = poi.attributes['addr:street'] || '';
                
                // Create popup content
                var popupContent = '<strong>' + name + '</strong><br>';
                if (cuisine) popupContent += 'Cuisine: ' + cuisine + '<br>';
                if (brand) popupContent += 'Brand: ' + brand + '<br>';
                if (address) popupContent += 'Address: ' + address + '<br>';
                popupContent += 'Category: ' + category.replace('_', ' ') + '<br>';
                popupContent += 'Distance: ' + Math.round(poi.distance_from_center) + 'm from center';
                
                // Create marker
                var marker = L.circleMarker([poi.lat, poi.lng], {
                    radius: 5,
                    fillColor: color,
                    color: '#000',
                    weight: 1,
                    opacity: 1,
                    fillOpacity: 0.8
                }).bindPopup(popupContent);
                
                layerGroups[category].addLayer(marker);
            });
            
            // Add layer to map by default for food categories
            if (['restaurants', 'fast_food', 'cafes', 'bars_pubs'].includes(category)) {
                layerGroups[category].addTo(map);
            }
        });
        
        // Create legend
        var legend = L.control({position: 'bottomleft'});
        legend.onAdd = function (map) {
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<h4>POI Categories</h4>';
            
            Object.keys(categoryColors).forEach(function(category) {
                var count = poiData[category] ? poiData[category].length : 0;
                if (count > 0) {
                    div.innerHTML += '<div class="legend-item">' +
                        '<span class="legend-color" style="background:' + categoryColors[category] + '"></span>' +
                        category.replace('_', ' ') + ' (' + count + ')' +
                        '</div>';
                }
            });
            
            return div;
        };
        legend.addTo(map);
        
        // Layer control
        var overlayMaps = {};
        Object.keys(layerGroups).forEach(function(category) {
            var count = poiData[category] ? poiData[category].length : 0;
            if (count > 0) {
                overlayMaps[category.replace('_', ' ') + ' (' + count + ')'] = layerGroups[category];
            }
        });
        
        L.control.layers(null, overlayMaps, {collapsed: false}).addTo(map);
        
        // Add center marker
        L.marker([""" + str(center_lat) + """, """ + str(center_lng) + """], {
            icon: L.icon({
                iconUrl: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iOCIgZmlsbD0iIzAwMCIgc3Ryb2tlPSIjZmZmIiBzdHJva2Utd2lkdGg9IjIiLz4KPC9zdmc+',
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            })
        }).addTo(map).bindPopup('<strong>Search Center</strong><br>Coordinates: ' + """ + str(center_lat) + """ + ', ' + """ + str(center_lng) + """);
    </script>
</body>
</html>"""
    
    # Save map
    map_filename = f"poi_map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(map_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Interactive map saved to {map_filename}")
    print(f"Open the file in your browser to view the map!")
    
    return map_filename

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python create_poi_map.py <poi_analysis_file.json>")
        import glob
        analysis_files = glob.glob("poi_analysis_*.json")
        if analysis_files:
            print("\\nAvailable analysis files:")
            for f in analysis_files:
                print(f"  {f}")
        sys.exit(1)
    
    map_file = create_poi_map(sys.argv[1])
    print(f"\\nMap creation complete! Open {map_file} in your browser.")