#!/usr/bin/env python3
"""
Route Visualization Script
Creates interactive HTML maps for POI-based routes
"""

import json
import sys
from datetime import datetime

def create_route_map(route_file):
    """Create interactive map from route JSON"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Creating route map from {route_file}")
    
    with open(route_file, 'r', encoding='utf-8') as f:
        route_data = json.load(f)
    
    if not route_data.get('coordinates'):
        print("Error: No coordinates found in route data")
        return None
    
    coordinates = route_data['coordinates']
    center_lat = sum(coord['lat'] for coord in coordinates) / len(coordinates)
    center_lng = sum(coord['lng'] for coord in coordinates) / len(coordinates)
    
    # POI category colors
    poi_colors = {
        'restaurants': '#e74c3c',
        'fast_food': '#f39c12',
        'cafes': '#8b4513',
        'bars_pubs': '#9b59b6',
        'nature': '#2e7d32',
        'recreation': '#4caf50',
        'shops': '#3498db',
        'other': '#95a5a6'
    }
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>POI Route Visualization - {datetime.now().strftime('%Y-%m-%d')}</title>
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
        .route-info {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            z-index: 1000;
            max-width: 300px;
        }}
        .route-stats {{
            margin: 10px 0;
        }}
        .stat-item {{
            margin: 5px 0;
            display: flex;
            justify-content: space-between;
        }}
        .poi-legend {{
            position: absolute;
            bottom: 20px;
            left: 20px;
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            z-index: 1000;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin: 5px 0;
        }}
        .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 50%;
            margin-right: 8px;
        }}
        .route-type {{
            background: #3498db;
            color: white;
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 12px;
            display: inline-block;
            margin-bottom: 10px;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    
    <div class="route-info">
        <div class="route-type">{route_data.get('route_type', 'Unknown').replace('_', ' ').title()}</div>
        <h3>Route Details</h3>
        <div class="route-stats">
            <div class="stat-item">
                <span><strong>Distance:</strong></span>
                <span>{route_data.get('distance_meters', 0):.0f}m</span>
            </div>
            <div class="stat-item">
                <span><strong>Time:</strong></span>
                <span>{route_data.get('time_minutes', 0):.1f} min</span>
            </div>
            <div class="stat-item">
                <span><strong>Waypoints:</strong></span>
                <span>{route_data.get('waypoints', 0)}</span>
            </div>
            <div class="stat-item">
                <span><strong>POIs:</strong></span>
                <span>{route_data.get('pois_along_route', 0)}</span>
            </div>
        </div>
        
        {_generate_poi_category_html(route_data.get('poi_categories', {}))}
    </div>
    
    <div class="poi-legend">
        <h4 style="margin-top: 0;">POI Types</h4>
        {_generate_legend_html(poi_colors)}
    </div>
    
    <script>
        // Initialize map
        var map = L.map('map').setView([{center_lat}, {center_lng}], 15);
        
        // Add tile layer
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);
        
        // Route coordinates
        var routeCoords = {json.dumps([[coord['lat'], coord['lng']] for coord in coordinates])};
        
        // Draw route
        var routeLine = L.polyline(routeCoords, {{
            color: '#2980b9',
            weight: 6,
            opacity: 0.8
        }}).addTo(map);
        
        // Add start marker
        L.marker(routeCoords[0], {{
            icon: L.icon({{
                iconUrl: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iOCIgZmlsbD0iIzI3YWU2MCIgc3Ryb2tlPSIjZmZmIiBzdHJva2Utd2lkdGg9IjIiLz4KPHN2ZyB4PSI4IiB5PSI4IiB3aWR0aD0iOCIgaGVpZ2h0PSI4Ij4KICA8cGF0aCBkPSJNNCA0IEw4IDYgTDQgOCBaIiBmaWxsPSIjZmZmIi8+Cjwvc3ZnPgo8L3N2Zz4=',
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            }})
        }}).addTo(map).bindPopup('<strong>Start</strong><br>Route begins here');
        
        // Add end marker
        L.marker(routeCoords[routeCoords.length - 1], {{
            icon: L.icon({{
                iconUrl: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iOCIgZmlsbD0iI2U3NGMzYyIgc3Ryb2tlPSIjZmZmIiBzdHJva2Utd2lkdGg9IjIiLz4KPHN2ZyB4PSI4IiB5PSI4IiB3aWR0aD0iOCIgaGVpZ2h0PSI4Ij4KICA8cmVjdCB4PSIyIiB5PSIyIiB3aWR0aD0iNCIgaGVpZ2h0PSI0IiBmaWxsPSIjZmZmIi8+Cjwvc3ZnPgo8L3N2Zz4=',
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            }})
        }}).addTo(map).bindPopup('<strong>End</strong><br>Route ends here');
        
        // Add POI markers
        var poiColors = {json.dumps(poi_colors)};
        var poisData = {json.dumps(route_data.get('detailed_pois', []))};
        
        poisData.forEach(function(poi) {{
            if (!poi.lat || !poi.lng) return;
            
            var color = poiColors[poi.category] || '#95a5a6';
            var name = poi.attributes.name || 'Unnamed POI';
            var category = poi.category || 'unknown';
            var distance = poi.distance_to_edge || 0;
            
            var popupContent = '<strong>' + name + '</strong><br>' +
                              'Category: ' + category + '<br>' +
                              'Distance from route: ' + Math.round(distance) + 'm';
            
            // Add additional attributes if available
            if (poi.attributes.cuisine) {{
                popupContent += '<br>Cuisine: ' + poi.attributes.cuisine;
            }}
            if (poi.attributes.natural) {{
                popupContent += '<br>Natural feature: ' + poi.attributes.natural;
            }}
            
            L.circleMarker([poi.lat, poi.lng], {{
                radius: 6,
                fillColor: color,
                color: '#fff',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.8
            }}).bindPopup(popupContent).addTo(map);
        }});
        
        // Fit map to route bounds
        map.fitBounds(routeLine.getBounds(), {{padding: [20, 20]}});
    </script>
</body>
</html>"""
    
    # Save map
    map_filename = f"route_map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(map_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Route map saved to {map_filename}")
    return map_filename

def _generate_poi_category_html(poi_categories):
    """Generate HTML for POI category breakdown"""
    if not poi_categories:
        return ""
    
    html = "<div style='margin-top: 15px;'><h4>POI Categories:</h4>"
    for category, count in sorted(poi_categories.items(), key=lambda x: x[1], reverse=True):
        html += f"<div class='stat-item'><span>{category.title()}:</span><span>{count}</span></div>"
    html += "</div>"
    return html

def _generate_legend_html(poi_colors):
    """Generate HTML for POI legend"""
    html = ""
    for category, color in poi_colors.items():
        html += f"""
        <div class="legend-item">
            <div class="legend-color" style="background-color: {color};"></div>
            <span>{category.replace('_', ' ').title()}</span>
        </div>"""
    return html

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python visualize_route.py <route_file.json>")
        import glob
        route_files = glob.glob("generated_route_*.json")
        if route_files:
            print("\\nAvailable route files:")
            for f in route_files:
                print(f"  {f}")
        sys.exit(1)
    
    map_file = create_route_map(sys.argv[1])
    if map_file:
        print(f"\\nVisualization complete! Open {map_file} in your browser.")