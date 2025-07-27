#!/usr/bin/env python3
import osmnx as ox
import networkx as nx
import folium
import folium.plugins
import time
from datetime import datetime

def fetch_graph(start, end, buffer_dist=5000):
    """
    Hämta ett gångnätverk (foot-paths) kring mittpunkten mellan start och end.
    buffer_dist är radien i meter.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching walking network...")
    start_time = time.time()
    
    mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Center point: {mid[0]:.4f}, {mid[1]:.4f}")
    
    G = ox.graph_from_point(mid, dist=buffer_dist, network_type='walk', simplify=True)
    
    elapsed = time.time() - start_time
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Graph fetched in {elapsed:.2f}s - {len(G.nodes)} nodes, {len(G.edges)} edges")
    return G

def annotate_fun_weights(G):
    """
    Sätter attribuet fun_weight = length / fun_score för varje kant.
    Höjer poängen för trails, parker och utsiktspunkter.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Calculating fun weights...")
    start_time = time.time()
    
    fun_highways = {'footway','path','pedestrian','track','steps','cycleway'}
    fun_edges = 0
    park_edges = 0
    attraction_edges = 0
    
    for u, v, k, data in G.edges(keys=True, data=True):
        hw = data.get('highway')
        if isinstance(hw, list): hw = hw[0]
        score = 1.0
        if hw in fun_highways:        
            score += 2.0
            fun_edges += 1
        if data.get('leisure')=='park':      
            score += 1.5
            park_edges += 1
        if data.get('tourism') in ('viewpoint','attraction'): 
            score += 3.0
            attraction_edges += 1
        data['fun_weight'] = data['length'] / score
    
    elapsed = time.time() - start_time
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fun weights calculated in {elapsed:.2f}s")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {fun_edges} fun paths, {park_edges} park edges, {attraction_edges} attractions")

def compute_fun_route(start, end, buffer_dist=5000):
    """
    Returnerar routen (lista av noder) och grafen G.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing fun route from {start} to {end}")
    total_start = time.time()
    
    G = fetch_graph(start, end, buffer_dist)
    annotate_fun_weights(G)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Finding nearest nodes...")
    orig = ox.distance.nearest_nodes(G, X=start[1], Y=start[0])
    dest = ox.distance.nearest_nodes(G, X=end[1], Y=end[0])
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing shortest fun path...")
    route_start = time.time()
    route = nx.shortest_path(G, orig, dest, weight='fun_weight')
    route_time = time.time() - route_start
    
    total_time = time.time() - total_start
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Route computed in {route_time:.2f}s (total: {total_time:.2f}s)")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Route has {len(route)} waypoints")
    
    return route, G

def create_multi_route_map(G, routes, start, end):
    """
    Skapar en interaktiv karta med flera rutter på OpenStreetMap.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Creating multi-route interactive map...")
    
    # Skapa karta centrerad på mittpunkten
    center_lat = (start[0] + end[0]) / 2
    center_lon = (start[1] + end[1]) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14)
    
    # Bygg info-panel med alla rutter
    routes_info = ""
    for i, route_data in enumerate(routes):
        stats = route_data['stats']
        
        # Räkna trail segments (path + track + footway)
        trail_time = (stats['path_types']['path']['time'] + 
                     stats['path_types']['track']['time'] + 
                     stats['path_types']['footway']['time'])
        
        # Räkna park tid
        park_time = stats['special_areas']['park']['time']
        
        routes_info += f"""
        │ <span style="color: {route_data['color']};">■</span> <span style="color: #ffff00;">{route_data['name']}</span><br>
        │   TIME: {stats['estimated_time']:.0f}min | DIST: {stats['distance']/1000:.2f}km<br>
        │   FUN: <span style="color: #ff6600;">{stats['fun_score']:.2f}</span> | TRAILS: {trail_time:.0f}min | PARKS: {park_time:.0f}min<br>
        │<br>"""
    
    info_html = f"""
    <div style="position: fixed; 
                top: 10px; left: 10px; width: 400px; height: auto;
                background-color: #1e1e1e; color: #00ff00; 
                border: 2px solid #00ff00; border-radius: 5px;
                font-family: 'Courier New', monospace; font-size: 11px;
                padding: 10px; z-index: 9999; box-shadow: 0 0 10px rgba(0,255,0,0.3);">
        <div style="color: #ffff00; font-weight: bold; margin-bottom: 8px;">
        ┌─[ MULTI-ROUTE COMPARISON ]──────────────────┐
        </div>
        <div style="margin-left: 5px;">
        │ <span style="color: #00ffff;">ROUTES COMPUTED:</span> {len(routes)}<br>
        │ <span style="color: #00ffff;">COORDS:</span><br>
        │   START: <span style="color: #90ee90;">{start[0]:.6f}, {start[1]:.6f}</span><br>
        │   END:   <span style="color: #ff6b6b;">{end[0]:.6f}, {end[1]:.6f}</span><br>
        │<br>
        {routes_info}
        │ <span style="color: #ffff00;">CONTROLS:</span><br>
        │ <span style="color: #888;">Click routes for details</span><br>
        │ <span style="color: #888;">Zoom: Mouse wheel</span><br>
        │ <span style="color: #888;">Pan: Click + drag</span>
        </div>
        <div style="color: #ffff00; font-weight: bold; margin-top: 8px;">
        └─────────────────────────────────────────────┘
        </div>
    </div>
    """
    
    # Lägg till info-panelen
    m.get_root().html.add_child(folium.Element(info_html))
    
    # Lägg till scale control
    folium.plugins.MeasureControl(
        primary_length_unit='meters',
        secondary_length_unit='kilometers',
        primary_area_unit='sqmeters',
        secondary_area_unit='hectares'
    ).add_to(m)
    
    # Lägg till start- och slutpunkter
    start_popup = f"""
    <div style="font-family: 'Courier New', monospace; background: #1e1e1e; color: #00ff00; padding: 8px; border-radius: 3px;">
    <b style="color: #ffff00;">[START POINT]</b><br>
    LAT: {start[0]:.6f}<br>
    LON: {start[1]:.6f}<br>
    <span style="color: #888;">{len(routes)} routes computed</span>
    </div>
    """
    
    end_popup = f"""
    <div style="font-family: 'Courier New', monospace; background: #1e1e1e; color: #00ff00; padding: 8px; border-radius: 3px;">
    <b style="color: #ffff00;">[DESTINATION]</b><br>
    LAT: {end[0]:.6f}<br>
    LON: {end[1]:.6f}<br>
    <span style="color: #888;">All routes end here</span>
    </div>
    """
    
    folium.Marker(
        location=[start[0], start[1]], 
        popup=folium.Popup(start_popup, max_width=200),
        icon=folium.Icon(color='green', icon='play')
    ).add_to(m)
    
    folium.Marker(
        location=[end[0], end[1]], 
        popup=folium.Popup(end_popup, max_width=200),
        icon=folium.Icon(color='red', icon='stop')
    ).add_to(m)
    
    # Rita alla rutter
    all_coords = []
    for route_data in routes:
        coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route_data['route']]
        all_coords.append(coords)
        stats = route_data['stats']
        
        # Hitta huvudsakliga vägtyper och ytor
        main_path = max(stats['path_types'].items(), 
                       key=lambda x: x[1]['distance'] if x[1]['distance'] > 0 else 0)
        main_surface = max(stats['surface_types'].items(), 
                          key=lambda x: x[1]['distance'] if x[1]['distance'] > 0 else 0)
        
        # Räkna speciella områden
        special_areas_list = [k for k, v in stats['special_areas'].items() if v['distance'] > 0]
        
        route_popup = f"""
        <div style="font-family: 'Courier New', monospace; background: #1e1e1e; color: #00ff00; padding: 8px; border-radius: 3px; max-width: 300px;">
        <b style="color: #ffff00;">[{route_data['name']} ROUTE]</b><br>
        <span style="color: #888;">{route_data['description']}</span><br><br>
        DISTANCE: {stats['distance']:.0f}m ({stats['distance']/1000:.2f}km)<br>
        TIME EST: <span style="color: #00ffff;">{stats['estimated_time']:.0f} minutes</span><br>
        AVG SPEED: {stats['avg_speed']:.1f} km/h<br>
        FUN SCORE: <span style="color: #ff6600;">{stats['fun_score']:.2f}</span><br><br>
        <b style="color: #ffff00;">MAIN PATH TYPE:</b><br>
        {main_path[0].upper()}: {main_path[1]['time']:.0f}min ({main_path[1]['distance']:.0f}m)<br>
        <span style="color: #888;">{main_path[1]['description']}</span><br><br>
        <b style="color: #ffff00;">SURFACE:</b><br>
        {main_surface[0].upper()}: {main_surface[1]['time']:.0f}min<br>
        <span style="color: #888;">{main_surface[1]['description']}</span><br><br>
        <b style="color: #ffff00;">SPECIAL AREAS:</b><br>
        {', '.join(special_areas_list) if special_areas_list else 'None detected'}
        </div>
        """
        
        # Olika linjestilar för olika rutter
        if route_data['name'] == 'SHORTEST':
            dash_array = '10,5'
            weight = 3
        elif route_data['name'] == 'MOST_FUN':
            dash_array = None
            weight = 5
        else:  # BALANCED
            dash_array = '15,10,5,10'
            weight = 4
        
        folium.PolyLine(
            locations=coords,
            color=route_data['color'],
            weight=weight,
            opacity=0.8,
            dash_array=dash_array,
            popup=folium.Popup(route_popup, max_width=300)
        ).add_to(m)
    
    # Spara kartan
    map_file = 'multi_route_map.html'
    m.save(map_file)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Multi-route map saved as {map_file}")
    
    return all_coords, map_file

def calculate_detailed_route_stats(G, route):
    """
    Beräknar mycket detaljerad statistik för rutten med tidsuppdelning.
    """
    # Grundläggande statistik
    total_distance = 0
    total_fun_weight = 0
    
    # Detaljerad uppdelning av vägtypes
    path_types = {
        'sidewalk': {'distance': 0, 'time': 0, 'speed': 5.0, 'description': 'Trottoarer och gångbanor'},
        'footway': {'distance': 0, 'time': 0, 'speed': 4.5, 'description': 'Dedikerade gångvägar'},
        'path': {'distance': 0, 'time': 0, 'speed': 4.0, 'description': 'Naturliga stigar och vägar'},
        'track': {'distance': 0, 'time': 0, 'speed': 3.5, 'description': 'Skogsstigar och jordvägar'},
        'steps': {'distance': 0, 'time': 0, 'speed': 2.5, 'description': 'Trappor och stegar'},
        'pedestrian': {'distance': 0, 'time': 0, 'speed': 4.8, 'description': 'Gågator och torg'},
        'cycleway': {'distance': 0, 'time': 0, 'speed': 4.2, 'description': 'Cykelvägar (gång tillåten)'},
        'residential': {'distance': 0, 'time': 0, 'speed': 4.8, 'description': 'Bostadsgator'},
        'service': {'distance': 0, 'time': 0, 'speed': 4.5, 'description': 'Servicevägar'},
        'other': {'distance': 0, 'time': 0, 'speed': 4.0, 'description': 'Övriga vägar'}
    }
    
    # Yttyper
    surface_types = {
        'paved': {'distance': 0, 'time': 0, 'speed_modifier': 1.0, 'description': 'Asfalt/betong'},
        'unpaved': {'distance': 0, 'time': 0, 'speed_modifier': 0.8, 'description': 'Grus/jord'},
        'grass': {'distance': 0, 'time': 0, 'speed_modifier': 0.7, 'description': 'Gräs'},
        'sand': {'distance': 0, 'time': 0, 'speed_modifier': 0.6, 'description': 'Sand'},
        'unknown': {'distance': 0, 'time': 0, 'speed_modifier': 0.9, 'description': 'Okänd yta'}
    }
    
    # Speciella områden
    special_areas = {
        'park': {'distance': 0, 'time': 0, 'description': 'Parker och grönområden'},
        'forest': {'distance': 0, 'time': 0, 'description': 'Skog och naturområden'},
        'waterfront': {'distance': 0, 'time': 0, 'description': 'Strandpromenader'},
        'historic': {'distance': 0, 'time': 0, 'description': 'Historiska områden'},
        'viewpoint': {'distance': 0, 'time': 0, 'description': 'Utsiktspunkter'},
        'attraction': {'distance': 0, 'time': 0, 'description': 'Turistattraktioner'}
    }
    
    # Detaljerad segmentanalys
    segments = []
    
    for i in range(len(route) - 1):
        u, v = route[i], route[i + 1]
        edge_data = G.get_edge_data(u, v)
        if edge_data:
            edge = list(edge_data.values())[0]
            length = edge.get('length', 0)
            total_distance += length
            total_fun_weight += edge.get('fun_weight', length)
            
            # Bestäm vägtyp
            hw = edge.get('highway')
            if isinstance(hw, list): 
                hw = hw[0] if hw else 'other'
            
            path_type = hw if hw in path_types else 'other'
            
            # Bestäm yttyp
            surface = edge.get('surface', 'unknown')
            if surface in ['asphalt', 'concrete', 'paved', 'paving_stones']:
                surface_type = 'paved'
            elif surface in ['gravel', 'dirt', 'earth', 'unpaved']:
                surface_type = 'unpaved'
            elif surface in ['grass', 'ground']:
                surface_type = 'grass'
            elif surface in ['sand']:
                surface_type = 'sand'
            else:
                surface_type = 'unknown'
            
            # Beräkna hastighet baserat på vägtyp och yta
            base_speed = path_types[path_type]['speed']
            speed_modifier = surface_types[surface_type]['speed_modifier']
            actual_speed = base_speed * speed_modifier
            
            # Beräkna tid för detta segment
            segment_time = (length / 1000) * (60 / actual_speed)  # minuter
            
            # Uppdatera statistik
            path_types[path_type]['distance'] += length
            path_types[path_type]['time'] += segment_time
            
            surface_types[surface_type]['distance'] += length
            surface_types[surface_type]['time'] += segment_time
            
            # Kolla speciella områden
            segment_features = []
            if edge.get('leisure') == 'park':
                special_areas['park']['distance'] += length
                special_areas['park']['time'] += segment_time
                segment_features.append('park')
            
            if edge.get('natural') == 'wood':
                special_areas['forest']['distance'] += length
                special_areas['forest']['time'] += segment_time
                segment_features.append('forest')
            
            if edge.get('tourism') == 'viewpoint':
                special_areas['viewpoint']['distance'] += length
                special_areas['viewpoint']['time'] += segment_time
                segment_features.append('viewpoint')
            
            if edge.get('tourism') == 'attraction':
                special_areas['attraction']['distance'] += length
                special_areas['attraction']['time'] += segment_time
                segment_features.append('attraction')
            
            if edge.get('waterway') or 'water' in edge.get('name', '').lower():
                special_areas['waterfront']['distance'] += length
                special_areas['waterfront']['time'] += segment_time
                segment_features.append('waterfront')
            
            # Spara segmentinfo
            segments.append({
                'length': length,
                'time': segment_time,
                'path_type': path_type,
                'surface_type': surface_type,
                'speed': actual_speed,
                'features': segment_features,
                'name': edge.get('name', f'Segment {i+1}')
            })
    
    # Beräkna total tid
    total_time = sum(seg['time'] for seg in segments)
    
    return {
        'distance': total_distance,
        'fun_weight': total_fun_weight,
        'fun_score': total_distance / total_fun_weight if total_fun_weight > 0 else 0,
        'estimated_time': total_time,
        'waypoints': len(route),
        'path_types': path_types,
        'surface_types': surface_types,
        'special_areas': special_areas,
        'segments': segments,
        'avg_speed': (total_distance / 1000) / (total_time / 60) if total_time > 0 else 0
    }

def compute_multiple_routes(start, end, buffer_dist=5000):
    """
    Beräknar flera rutter med olika optimeringsstrategier.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing multiple route options...")
    total_start = time.time()
    
    G = fetch_graph(start, end, buffer_dist)
    
    # Hitta närmaste noder
    orig = ox.distance.nearest_nodes(G, X=start[1], Y=start[0])
    dest = ox.distance.nearest_nodes(G, X=end[1], Y=end[0])
    
    routes = []
    
    # 1. Kortaste rutt (standard längd)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing shortest route...")
    try:
        route_shortest = nx.shortest_path(G, orig, dest, weight='length')
        stats = calculate_detailed_route_stats(G, route_shortest)
        routes.append({
            'name': 'SHORTEST',
            'description': 'Fastest direct route',
            'route': route_shortest,
            'stats': stats,
            'color': '#ff4444',
            'priority': 'speed'
        })
    except nx.NetworkXNoPath:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No shortest path found")
    
    # 2. Roligaste rutt (fun_weight)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing most fun route...")
    annotate_fun_weights(G)
    try:
        route_fun = nx.shortest_path(G, orig, dest, weight='fun_weight')
        stats = calculate_detailed_route_stats(G, route_fun)
        routes.append({
            'name': 'MOST_FUN',
            'description': 'Maximum fun score route',
            'route': route_fun,
            'stats': stats,
            'color': '#44ff44',
            'priority': 'fun'
        })
    except nx.NetworkXNoPath:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No fun path found")
    
    # 3. Balanserad rutt (kombination av längd och fun)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing balanced route...")
    for u, v, k, data in G.edges(keys=True, data=True):
        fun_weight = data.get('fun_weight', data.get('length', 0))
        length = data.get('length', 0)
        data['balanced_weight'] = (length * 0.7) + (fun_weight * 0.3)
    
    try:
        route_balanced = nx.shortest_path(G, orig, dest, weight='balanced_weight')
        stats = calculate_detailed_route_stats(G, route_balanced)
        routes.append({
            'name': 'BALANCED',
            'description': 'Good mix of speed and fun',
            'route': route_balanced,
            'stats': stats,
            'color': '#4444ff',
            'priority': 'balanced'
        })
    except nx.NetworkXNoPath:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No balanced path found")
    
    total_time = time.time() - total_start
    print(f"[{datetime.now().strftime('%H:%M:%S')}] All routes computed in {total_time:.2f}s")
    
    return routes, G

def display_route_comparison(routes):
    """
    Visar en terminal-style jämförelse av alla rutter.
    """
    print("\n" + "=" * 80)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ROUTE COMPARISON TABLE")
    print("=" * 80)
    
    # Header
    print(f"{'ROUTE':<12} {'TIME':<8} {'DIST':<8} {'FUN':<6} {'SPEED':<7} {'SURFACE':<8} {'SPECIAL':<8}")
    print("-" * 80)
    
    # Sortera rutter efter olika kriterier
    routes_by_time = sorted(routes, key=lambda r: r['stats']['estimated_time'])
    routes_by_fun = sorted(routes, key=lambda r: r['stats']['fun_score'], reverse=True)
    routes_by_distance = sorted(routes, key=lambda r: r['stats']['distance'])
    
    for route in routes:
        stats = route['stats']
        
        # Hitta huvudsaklig yttyp
        main_surface = max(stats['surface_types'].items(), 
                          key=lambda x: x[1]['distance'] if x[1]['distance'] > 0 else 0)[0]
        
        # Räkna speciella områden
        special_count = sum(1 for v in stats['special_areas'].values() if v['distance'] > 0)
        
        print(f"{route['name']:<12} "
              f"{stats['estimated_time']:.0f}min "
              f"{stats['distance']/1000:.2f}km "
              f"{stats['fun_score']:.2f} "
              f"{stats['avg_speed']:.1f}km/h "
              f"{main_surface:<8} "
              f"{special_count} areas")
    
    print("-" * 80)
    print(f"FASTEST:     {routes_by_time[0]['name']} ({routes_by_time[0]['stats']['estimated_time']:.0f}min)")
    print(f"MOST FUN:    {routes_by_fun[0]['name']} (score: {routes_by_fun[0]['stats']['fun_score']:.2f})")
    print(f"SHORTEST:    {routes_by_distance[0]['name']} ({routes_by_distance[0]['stats']['distance']/1000:.2f}km)")
    print("=" * 80)
    
    return {
        'fastest': routes_by_time[0],
        'most_fun': routes_by_fun[0],
        'shortest': routes_by_distance[0]
    }

def display_detailed_walkthrough(route_data):
    """
    Visar detaljerad genomgång av vad du går igenom på rutten.
    """
    stats = route_data['stats']
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] DETAILED WALKTHROUGH: {route_data['name']} ROUTE")
    print("=" * 80)
    print(f"TOTAL: {stats['distance']:.0f}m ({stats['distance']/1000:.2f}km) in {stats['estimated_time']:.0f} minutes")
    print(f"AVERAGE SPEED: {stats['avg_speed']:.1f} km/h")
    print("-" * 80)
    
    # Visa tidsuppdelning per vägtyp
    print("TIME BREAKDOWN BY PATH TYPE:")
    for path_type, data in stats['path_types'].items():
        if data['distance'] > 0:
            print(f"  {path_type.upper():<12} {data['time']:.1f}min ({data['distance']:.0f}m) - {data['description']}")
    
    print("\nTIME BREAKDOWN BY SURFACE:")
    for surface_type, data in stats['surface_types'].items():
        if data['distance'] > 0:
            print(f"  {surface_type.upper():<8} {data['time']:.1f}min ({data['distance']:.0f}m) - {data['description']}")
    
    print("\nSPECIAL AREAS YOU'LL WALK THROUGH:")
    special_found = False
    for area_type, data in stats['special_areas'].items():
        if data['distance'] > 0:
            special_found = True
            print(f"  {area_type.upper():<12} {data['time']:.1f}min ({data['distance']:.0f}m) - {data['description']}")
    
    if not special_found:
        print("  No special areas detected on this route")
    
    # Visa de längsta segmenten
    print(f"\nLONGEST SEGMENTS (showing top 5):")
    longest_segments = sorted(stats['segments'], key=lambda x: x['length'], reverse=True)[:5]
    for i, seg in enumerate(longest_segments, 1):
        features_str = f" [{', '.join(seg['features'])}]" if seg['features'] else ""
        print(f"  {i}. {seg['length']:.0f}m ({seg['time']:.1f}min) - {seg['path_type']} on {seg['surface_type']}{features_str}")
        if seg['name'] and seg['name'] != f"Segment {i}":
            print(f"     Name: {seg['name']}")
    
    print("-" * 80)

def display_route_recommendations(routes):
    """
    Visar rekommendationer baserat på olika preferenser.
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ROUTE RECOMMENDATIONS")
    print("=" * 80)
    
    for route_data in routes:
        stats = route_data['stats']
        print(f"\n{route_data['name']} ROUTE - {route_data['description']}")
        print(f"  Time: {stats['estimated_time']:.0f} minutes | Distance: {stats['distance']/1000:.2f}km")
        print(f"  Fun Score: {stats['fun_score']:.2f} | Avg Speed: {stats['avg_speed']:.1f} km/h")
        
        # Visa huvudsakliga vägtyper
        main_paths = [(k, v) for k, v in stats['path_types'].items() if v['distance'] > 0]
        main_paths.sort(key=lambda x: x[1]['distance'], reverse=True)
        if main_paths:
            top_path = main_paths[0]
            print(f"  Mainly: {top_path[1]['description']} ({top_path[1]['time']:.0f}min)")
        
        # Visa speciella funktioner
        special_features = [k for k, v in stats['special_areas'].items() if v['distance'] > 0]
        if special_features:
            print(f"  Features: {', '.join(special_features)}")
        
        print(f"  Best for: ", end="")
        if route_data['priority'] == 'speed':
            print("Getting there quickly")
        elif route_data['priority'] == 'fun':
            print("Scenic walks and interesting paths")
        else:
            print("Balance of speed and enjoyment")
    
    print("=" * 80)

if __name__ == '__main__':
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting Multi-Route Fun Path Planner")
    print("=" * 80)
    
    # Ange dina koordinater här (lat, lon)
    start = (58.508594, 15.487358)
    end   = (58.490666, 15.498153)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Start: {start}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] End: {end}")
    
    # Beräkna flera rutter
    routes, G = compute_multiple_routes(start, end)
    
    if not routes:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: No routes found!")
        exit(1)
    
    # Visa jämförelse
    best_routes = display_route_comparison(routes)
    
    # Visa detaljerade rekommendationer
    display_route_recommendations(routes)
    
    # Visa detaljerad genomgång av den roligaste rutten
    display_detailed_walkthrough(best_routes['most_fun'])
    
    # Skapa karta med alla rutter
    all_coords, map_file = create_multi_route_map(G, routes, start, end)
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] FINAL SUMMARY:")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] For speed: Choose {best_routes['fastest']['name']} route ({best_routes['fastest']['stats']['estimated_time']:.0f}min)")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] For fun: Choose {best_routes['most_fun']['name']} route (score: {best_routes['most_fun']['stats']['fun_score']:.2f})")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] For distance: Choose {best_routes['shortest']['name']} route ({best_routes['shortest']['stats']['distance']/1000:.2f}km)")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Interactive map: {map_file}")
    print("=" * 80)
