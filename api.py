#!/usr/bin/env python3
"""
FastAPI backend for Fun Path Planner
Uses the working OSMnx routing engine
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import osmnx as ox
import networkx as nx
import time
from datetime import datetime
import requests

app = FastAPI(title="Fun Path Planner API", version="1.0.0")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

class Coordinate(BaseModel):
    lat: float
    lng: float

class RouteRequest(BaseModel):
    start: Coordinate
    end: Coordinate
    buffer_dist: Optional[int] = 5000

class PathTypeStats(BaseModel):
    distance: float
    time: float
    speed: float
    description: str

class SurfaceTypeStats(BaseModel):
    distance: float
    time: float
    speed_modifier: float
    description: str

class SpecialAreaStats(BaseModel):
    distance: float
    time: float
    description: str

class RouteStats(BaseModel):
    distance: float
    fun_weight: float
    fun_score: float
    estimated_time: float
    waypoints: int
    path_types: Dict[str, PathTypeStats]
    surface_types: Dict[str, SurfaceTypeStats]
    special_areas: Dict[str, SpecialAreaStats]
    avg_speed: float
    node_type_distribution: Dict[str, int]

class Route(BaseModel):
    name: str
    description: str
    route: List[Coordinate]  # Changed from 'coordinates' to 'route' to match frontend
    stats: RouteStats
    color: str
    priority: str

class RouteResponse(BaseModel):
    routes: List[Route]
    success: bool
    message: Optional[str] = None

class AddressSearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 5

class AddressResult(BaseModel):
    display_name: str
    lat: float
    lng: float
    place_id: str
    importance: float

class AddressSearchResponse(BaseModel):
    results: List[AddressResult]
    success: bool
    message: Optional[str] = None

def fetch_graph(start, end, buffer_dist=5000):
    """
    Fetch walking network using OSMnx (same as original script)
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching walking network...")
    start_time = time.time()
    
    mid = ((start.lat + end.lat) / 2, (start.lng + end.lng) / 2)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Center point: {mid[0]:.4f}, {mid[1]:.4f}")
    
    G = ox.graph_from_point(mid, dist=buffer_dist, network_type='walk', simplify=True)
    
    elapsed = time.time() - start_time
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Graph fetched in {elapsed:.2f}s - {len(G.nodes)} nodes, {len(G.edges)} edges")
    return G

def annotate_fun_weights(G):
    """
    Set fun_weight attribute for each edge using a more intuitive scoring model.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Calculating fun weights with new, improved model...")
    start_time = time.time()

    # Define bonuses and penalties
    highway_bonuses = {
        'track': 4.0,       # High bonus for tracks/trails
        'footway': 3.0,     # Good bonus for dedicated footways
        'pedestrian': 3.0,  # and pedestrian streets
        'path': 2.0,        # A decent bonus for generic paths
        'cycleway': 1.5,    # A small bonus for cycleways
        'steps': 0.9,       # Slight penalty for steps
    }
    path_penalty_factor = 3.0  # Heavily penalize generic 'path' ways
    # Penalties are divisors for major roads
    highway_penalties = {
        'primary': 3.0,
        'secondary': 2.5,
        'tertiary': 2.0,
        'residential': 1.2, # Very slight penalty for residential roads
        'service': 1.5,
    }
    tag_bonuses = {
        ('leisure', 'park'): 3.0,
        ('leisure', 'nature_reserve'): 4.0,
        ('tourism', 'viewpoint'): 3.0,
        ('natural', 'wood'): 2.5,
    }

    for u, v, k, data in G.edges(keys=True, data=True):
        base_score = 1.0
        hw = data.get('highway')
        hws = hw if isinstance(hw, list) else [hw]

        for h in hws:
            if h in highway_bonuses:
                base_score *= highway_bonuses[h]
            elif h in highway_penalties:
                base_score /= highway_penalties[h]

        for (tag_key, tag_value), bonus in tag_bonuses.items():
            tag_val = data.get(tag_key)
            if (isinstance(tag_val, list) and tag_value in tag_val) or (tag_val == tag_value):
                base_score += bonus

        # Final fun_weight is length divided by the fun score
        # A higher score means a lower weight, making it more likely to be chosen
        weight = data['length'] / max(base_score, 0.1)
        if 'path' in hws:
            weight *= path_penalty_factor
        data['fun_weight'] = weight

    elapsed = time.time() - start_time
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fun weights calculated in {elapsed:.2f}s")

def calculate_detailed_route_stats(G, route):
    """
    Calculate detailed route statistics, including node type distribution.
    """
    total_distance = 0
    total_fun_weight = 0
    node_type_counts = {}

    # Basic path types
    path_types = {
        'footway': {'distance': 0, 'time': 0, 'speed': 4.5, 'description': 'Dedicated walkways'},
        'path': {'distance': 0, 'time': 0, 'speed': 4.0, 'description': 'Natural trails and paths'},
        'residential': {'distance': 0, 'time': 0, 'speed': 4.8, 'description': 'Residential streets'},
        'other': {'distance': 0, 'time': 0, 'speed': 4.0, 'description': 'Other walkable paths'}
    }
    
    surface_types = {
        'paved': {'distance': 0, 'time': 0, 'speed_modifier': 1.0, 'description': 'Paved surfaces'},
        'unpaved': {'distance': 0, 'time': 0, 'speed_modifier': 0.8, 'description': 'Natural surfaces'},
        'unknown': {'distance': 0, 'time': 0, 'speed_modifier': 0.9, 'description': 'Mixed surfaces'}
    }
    
    special_areas = {}
    
    # Count node types
    for node_id in route:
        # To get the 'type' of a node, we check the highway tags of its connected edges.
        # This is a simplification; a node at an intersection has multiple edge types.
        # We'll count the dominant highway type for simplicity.
        if G.has_node(node_id):
            incident_edges = G.edges(node_id, data=True)
            if incident_edges:
                # Get highway types from all connected edges
                hws = [d.get('highway') for u,v,d in incident_edges]
                # Flatten the list in case some are lists themselves
                hws_flat = []
                for hw in hws:
                    if isinstance(hw, list):
                        hws_flat.extend(hw)
                    else:
                        hws_flat.append(hw)
                
                # Count the most common highway type for this node
                if hws_flat:
                    dominant_hw = max(set(hws_flat), key=hws_flat.count)
                    node_type_counts[dominant_hw] = node_type_counts.get(dominant_hw, 0) + 1

    for i in range(len(route) - 1):
        u, v = route[i], route[i + 1]
        edge_data = G.get_edge_data(u, v)
        if edge_data:
            edge = list(edge_data.values())[0]
            length = edge.get('length', 0)
            total_distance += length
            total_fun_weight += edge.get('fun_weight', length)
            
            hw = edge.get('highway', 'other')
            if isinstance(hw, list): hw = hw[0]
            path_type = hw if hw in path_types else 'other'
            
            base_speed = path_types[path_type]['speed']
            segment_time = (length / 1000) * (60 / base_speed)
            
            path_types[path_type]['distance'] += length
            path_types[path_type]['time'] += segment_time
            
            surface_types['paved']['distance'] += length * 0.7
            surface_types['paved']['time'] += segment_time * 0.7
            surface_types['unpaved']['distance'] += length * 0.3
            surface_types['unpaved']['time'] += segment_time * 0.3
            
            if edge.get('leisure') == 'park':
                if 'park' not in special_areas:
                    special_areas['park'] = {'distance': 0, 'time': 0, 'description': 'Parks and green areas'}
                special_areas['park']['distance'] += length
                special_areas['park']['time'] += segment_time
    
    total_time = sum(data['time'] for data in path_types.values() if data['time'] > 0)
    if total_time == 0: total_time = total_distance / 1000 * (60 / 4.2)
    
    return {
        'distance': total_distance,
        'fun_weight': total_fun_weight,
        'fun_score': total_distance / total_fun_weight if total_fun_weight > 0 else 1.0,
        'estimated_time': total_time,
        'waypoints': len(route),
        'path_types': path_types,
        'surface_types': surface_types,
        'special_areas': special_areas,
        'avg_speed': (total_distance / 1000) / (total_time / 60) if total_time > 0 else 4.2,
        'node_type_distribution': node_type_counts
    }

def scan_for_nature_features(G):
    """
    Scan all nodes and edges for parks, nature areas, and fun features
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning for parks and nature features...")
    
    nature_nodes = []
    nature_edges = []
    
    # Scan edges for nature features
    for u, v, k, data in G.edges(keys=True, data=True):
        score = 0
        tags = []
        
        # Check for nature/park tags
        if data.get('leisure') == 'park':
            score += 5.0
            tags.append('park')
        if data.get('leisure') == 'nature_reserve':
            score += 6.0
            tags.append('nature_reserve')
        if data.get('natural') == 'wood':
            score += 4.0
            tags.append('forest')
        if data.get('landuse') == 'forest':
            score += 4.0
            tags.append('forest')
        if data.get('tourism') == 'viewpoint':
            score += 5.0
            tags.append('viewpoint')
        if data.get('highway') == 'footway':
            score += 2.0
            tags.append('footway')
        if data.get('highway') == 'track':
            score += 3.0
            tags.append('trail')
        if data.get('highway') == 'pedestrian':
            score += 2.5
            tags.append('pedestrian')
        if data.get('waterway'):
            score += 3.0
            tags.append('waterway')
        
        # Penalize generic paths as requested
        if data.get('highway') == 'path':
            score -= 2.0
            tags.append('generic_path')
            
        if score > 0:
            nature_edges.append({
                'edge': (u, v, k),
                'score': score,
                'tags': tags,
                'length': data.get('length', 0)
            })
    
    # Scan nodes for nature features by checking their connected edges
    for node_id, node_data in G.nodes(data=True):
        score = 0
        tags = []
        
        # Check connected edges for nature features
        connected_edges = list(G.edges(node_id, data=True))
        for _, _, edge_data in connected_edges:
            if edge_data.get('leisure') == 'park':
                score += 3.0  # Higher score for park nodes
                if 'park' not in tags:
                    tags.append('park')
            if edge_data.get('natural') == 'wood' or edge_data.get('landuse') == 'forest':
                score += 2.0  # Forest nodes
                if 'forest' not in tags:
                    tags.append('forest')
            if edge_data.get('highway') == 'footway':
                score += 1.0  # Footway nodes
                if 'footway' not in tags:
                    tags.append('footway')
            if edge_data.get('highway') == 'track':
                score += 1.5  # Trail nodes
                if 'trail' not in tags:
                    tags.append('trail')
            if edge_data.get('tourism') == 'viewpoint':
                score += 4.0  # Viewpoint nodes
                if 'viewpoint' not in tags:
                    tags.append('viewpoint')
        
        # Also check the node itself for any tags
        if node_data.get('leisure') == 'park':
            score += 5.0
            if 'park' not in tags:
                tags.append('park')
        if node_data.get('natural') == 'wood':
            score += 3.0
            if 'forest' not in tags:
                tags.append('forest')
        if node_data.get('tourism') == 'viewpoint':
            score += 5.0
            if 'viewpoint' not in tags:
                tags.append('viewpoint')
        
        if score > 0:
            nature_nodes.append({
                'node': node_id,
                'score': score,
                'tags': tags,
                'lat': node_data['y'],
                'lng': node_data['x']
            })
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(nature_edges)} nature edges and {len(nature_nodes)} nature nodes")
    return {'nodes': nature_nodes, 'edges': nature_edges}

def filter_viable_parks(nature_features, start_node, end_node, G, max_detour_factor=1.8):
    """
    Filter parks that are viable waypoints (not too far from direct route)
    """
    try:
        direct_distance = nx.shortest_path_length(G, start_node, end_node, weight='length')
    except nx.NetworkXNoPath:
        return []
    
    max_detour_distance = direct_distance * max_detour_factor
    viable_parks = []
    
    # Group nature nodes by location proximity
    park_clusters = []
    processed_nodes = set()
    
    for feature in nature_features['nodes']:
        if feature['node'] in processed_nodes:
            continue
            
        try:
            # Calculate total distance: start -> park -> end
            dist_to_park = nx.shortest_path_length(G, start_node, feature['node'], weight='length')
            dist_from_park = nx.shortest_path_length(G, feature['node'], end_node, weight='length')
            total_distance = dist_to_park + dist_from_park
            
            if total_distance <= max_detour_distance:
                park_clusters.append({
                    'node': feature['node'],
                    'score': feature['score'],
                    'tags': feature['tags'],
                    'detour_factor': total_distance / direct_distance,
                    'lat': feature['lat'],
                    'lng': feature['lng']
                })
                processed_nodes.add(feature['node'])
                
        except nx.NetworkXNoPath:
            continue
    
    # Sort by score and limit to best parks
    park_clusters.sort(key=lambda x: x['score'] / x['detour_factor'], reverse=True)
    viable_parks = park_clusters[:3]  # Top 3 parks
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(viable_parks)} viable parks for routing")
    return viable_parks

def create_park_route(G, start_node, end_node, viable_parks):
    """
    Create route that goes through selected parks
    """
    if not viable_parks:
        return None
    
    # Select best parks based on score and detour
    selected_parks = []
    
    # Always include the highest scoring park
    if viable_parks:
        selected_parks.append(viable_parks[0])
    
    # Add second park if it's significantly different location and good score
    if len(viable_parks) > 1:
        first_park = viable_parks[0]
        for park in viable_parks[1:]:
            # Check if park is far enough from first park
            park_distance = ((park['lat'] - first_park['lat'])**2 + (park['lng'] - first_park['lng'])**2)**0.5
            if park_distance > 0.001 and park['score'] > 2.0:  # Different location and good score
                selected_parks.append(park)
                break
    
    # Create waypoint route
    waypoints = [start_node] + [park['node'] for park in selected_parks] + [end_node]
    full_route = []
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Creating route through {len(selected_parks)} parks...")
    
    # Connect waypoints
    for i in range(len(waypoints) - 1):
        try:
            segment = nx.shortest_path(G, waypoints[i], waypoints[i+1], weight='fun_weight')
            if i > 0:
                segment = segment[1:]  # Remove duplicate node
            full_route.extend(segment)
        except nx.NetworkXNoPath:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Could not connect waypoint {i} to {i+1}")
            return None
    
    return full_route

def compute_multiple_routes(start: Coordinate, end: Coordinate, buffer_dist: int = 5000):
    """
    Compute multiple routes with different optimization strategies including park-hunting
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing multiple route options...")
    total_start = time.time()
    
    G = fetch_graph(start, end, buffer_dist)
    annotate_fun_weights(G) # Annotate graph before any pathfinding
    
    # Find nearest nodes
    orig = ox.distance.nearest_nodes(G, X=start.lng, Y=start.lat)
    dest = ox.distance.nearest_nodes(G, X=end.lng, Y=end.lat)
    
    routes = []
    
    # 1. Shortest route (standard length)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing shortest route...")
    try:
        route_shortest = nx.shortest_path(G, orig, dest, weight='length')
        stats = calculate_detailed_route_stats(G, route_shortest)
        
        # Convert to coordinates
        coordinates = []
        for node_id in route_shortest:
            node = G.nodes[node_id]
            coordinates.append(Coordinate(lat=node['y'], lng=node['x']))
        
        routes.append({
            'name': 'SHORTEST',
            'description': 'Fastest direct route',
            'coordinates': coordinates,
            'stats': stats,
            'color': '#ff4444',
            'priority': 'speed'
        })
    except nx.NetworkXNoPath:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No shortest path found")
    
    # 2. Most fun route (fun_weight)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing most fun route...")
    try:
        route_fun = nx.shortest_path(G, orig, dest, weight='fun_weight')
        stats = calculate_detailed_route_stats(G, route_fun)
        
        # Convert to coordinates
        coordinates = []
        for node_id in route_fun:
            node = G.nodes[node_id]
            coordinates.append(Coordinate(lat=node['y'], lng=node['x']))
        
        routes.append({
            'name': 'MOST_FUN',
            'description': 'Maximum fun score route',
            'coordinates': coordinates,
            'stats': stats,
            'color': '#44ff44',
            'priority': 'fun'
        })
    except nx.NetworkXNoPath:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No fun path found")
    
    # 3. NEW: Park Hunter route
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing park hunter route...")
    try:
        nature_features = scan_for_nature_features(G)
        viable_parks = filter_viable_parks(nature_features, orig, dest, G)
        route_parks = create_park_route(G, orig, dest, viable_parks)
        
        if route_parks and len(route_parks) > 2:
            stats = calculate_detailed_route_stats(G, route_parks)
            
            # Convert to coordinates
            coordinates = []
            for node_id in route_parks:
                node = G.nodes[node_id]
                coordinates.append(Coordinate(lat=node['y'], lng=node['x']))
            
            routes.append({
                'name': 'PARK_HUNTER',
                'description': f'Route through {len(viable_parks)} parks and nature areas',
                'coordinates': coordinates,
                'stats': stats,
                'color': '#00aa00',
                'priority': 'park'
            })
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No viable park route found")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Park hunter route failed: {str(e)}")
    
    # 4. Balanced route
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing balanced route...")
    for u, v, k, data in G.edges(keys=True, data=True):
        fun_weight = data.get('fun_weight', data.get('length', 0))
        length = data.get('length', 0)
        data['balanced_weight'] = (length * 0.7) + (fun_weight * 0.3)
    
    try:
        route_balanced = nx.shortest_path(G, orig, dest, weight='balanced_weight')
        stats = calculate_detailed_route_stats(G, route_balanced)
        
        # Convert to coordinates
        coordinates = []
        for node_id in route_balanced:
            node = G.nodes[node_id]
            coordinates.append(Coordinate(lat=node['y'], lng=node['x']))
        
        routes.append({
            'name': 'BALANCED',
            'description': 'Good mix of speed and fun',
            'coordinates': coordinates,
            'stats': stats,
            'color': '#4444ff',
            'priority': 'balanced'
        })
    except nx.NetworkXNoPath:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No balanced path found")
    
    total_time = time.time() - total_start
    print(f"[{datetime.now().strftime('%H:%M:%S')}] All routes computed in {total_time:.2f}s")
    
    return routes

def search_addresses(query: str, limit: int = 5) -> List[AddressResult]:
    """
    Search for addresses, house numbers, stores, and POIs using Nominatim
    """
    try:
        # Use Nominatim API for comprehensive geocoding
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'limit': limit * 2,  # Get more results to filter and sort
            'addressdetails': 1,
            'extratags': 1,
            'namedetails': 1,
            'dedupe': 1,  # Remove duplicates
        }
        
        headers = {
            'User-Agent': 'FunPathPlanner/1.0 (contact@example.com)'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        for item in data:
            # Get location type and category
            place_type = item.get('type', '')
            place_class = item.get('class', '')
            osm_type = item.get('osm_type', '')
            
            # Calculate relevance score based on type
            relevance_score = float(item.get('importance', 0.5))
            
            # Boost scores for useful location types
            if place_type in ['house', 'building', 'address']:
                relevance_score += 0.3  # Houses and addresses
            elif place_type in ['shop', 'store', 'retail']:
                relevance_score += 0.25  # Shops and stores
            elif place_type in ['restaurant', 'cafe', 'bar', 'pub', 'fast_food']:
                relevance_score += 0.25  # Food and drink
            elif place_type in ['hotel', 'hostel', 'guest_house']:
                relevance_score += 0.2  # Accommodation
            elif place_type in ['hospital', 'clinic', 'pharmacy', 'dentist']:
                relevance_score += 0.2  # Healthcare
            elif place_type in ['school', 'university', 'college', 'library']:
                relevance_score += 0.2  # Education
            elif place_type in ['bank', 'atm', 'post_office']:
                relevance_score += 0.15  # Services
            elif place_type in ['park', 'garden', 'playground']:
                relevance_score += 0.15  # Recreation
            elif place_type in ['bus_stop', 'train_station', 'subway_entrance']:
                relevance_score += 0.1  # Transport
            
            # Boost if it has a house number
            address = item.get('address', {})
            if address.get('house_number'):
                relevance_score += 0.2
            
            # Create enhanced display name with house numbers
            display_name = item['display_name']
            address = item.get('address', {})
            
            # Extract and format address components
            house_number = address.get('house_number', '')
            street = address.get('road', '')
            city = address.get('city', address.get('town', address.get('village', '')))
            
            # Create a better formatted address for houses/buildings
            if house_number and street:
                # Format as "Street Number, City" for addresses
                formatted_address = f"{street} {house_number}"
                if city:
                    formatted_address += f", {city}"
                
                # Use the formatted address as the main display
                display_name = formatted_address + ", " + ", ".join(display_name.split(', ')[2:])
            
            # Add type information for POIs (stores, restaurants, etc.)
            if place_type and place_type not in ['house', 'building', 'address', 'road']:
                type_info = place_type.replace('_', ' ').title()
                if place_class and place_class != place_type:
                    type_info = f"{place_class.title()} - {type_info}"
                
                # Add type info to display name if not already present
                name_parts = display_name.split(',')
                if len(name_parts) > 0 and type_info.lower() not in name_parts[0].lower():
                    name_parts[0] = f"{name_parts[0]} ({type_info})"
                    display_name = ', '.join(name_parts)
            
            results.append(AddressResult(
                display_name=display_name,
                lat=float(item['lat']),
                lng=float(item['lon']),
                place_id=str(item['place_id']),
                importance=relevance_score
            ))
        
        # Sort by relevance score (higher is better)
        results.sort(key=lambda x: x.importance, reverse=True)
        
        # Remove very similar results (within 50m)
        filtered_results = []
        for result in results:
            is_duplicate = False
            for existing in filtered_results:
                # Calculate rough distance (simplified)
                lat_diff = abs(result.lat - existing.lat)
                lng_diff = abs(result.lng - existing.lng)
                if lat_diff < 0.0005 and lng_diff < 0.0005:  # ~50m
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                filtered_results.append(result)
                
            if len(filtered_results) >= limit:
                break
        
        return filtered_results
        
    except Exception as e:
        print(f"Geocoding error: {str(e)}")
        return []

@app.get("/")
async def root():
    return {"message": "Fun Path Planner API", "status": "running"}

@app.post("/api/search-addresses", response_model=AddressSearchResponse)
async def search_addresses_endpoint(request: AddressSearchRequest):
    """
    Search for addresses and return coordinates
    """
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Address search: '{request.query}'")
        
        if len(request.query.strip()) < 3:
            return AddressSearchResponse(
                results=[],
                success=False,
                message="Query too short (minimum 3 characters)"
            )
        
        results = search_addresses(request.query, request.limit)
        
        return AddressSearchResponse(
            results=results,
            success=True,
            message=f"Found {len(results)} addresses"
        )
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Address search error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Address search failed: {str(e)}")

@app.get("/api/debug-node-details")
async def debug_node_details():
    """
    Temporary endpoint to get debug information for a sample node and its edges.
    """
    try:
        sample_point = (58.54, 15.03)
        G = ox.graph_from_point(sample_point, dist=500, network_type='walk', simplify=True)
        
        node_ids = list(G.nodes)
        if not node_ids:
            return {"error": "Could not fetch any nodes."}

        sample_node_id = node_ids[0]
        node_data = G.nodes[sample_node_id]
        
        incident_edges = list(G.in_edges(sample_node_id, data=True)) + list(G.out_edges(sample_node_id, data=True))
        
        edge_details = []
        for u, v, data in incident_edges:
            # Sanitize edge data to ensure it's JSON serializable
            sanitized_data = {k: str(v) for k, v in data.items()}
            edge_info = {
                "from_node": u,
                "to_node": v,
                "data": sanitized_data
            }
            edge_details.append(edge_info)

        return {
            "node_id": sample_node_id, 
            "node_data": node_data,
            "connected_edges": edge_details
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/routes", response_model=RouteResponse)
async def calculate_routes(request: RouteRequest):
    """
    Calculate multiple walking routes between two points
    """
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Route request: {request.start} -> {request.end}")
        
        routes_data = compute_multiple_routes(request.start, request.end, request.buffer_dist)
        
        if not routes_data:
            raise HTTPException(status_code=404, detail="No routes found")
        
        # Convert to API format
        routes = []
        for route_data in routes_data:
            # Convert stats to proper format
            stats_dict = route_data['stats']
            
            # Convert path_types
            path_types = {}
            for key, value in stats_dict['path_types'].items():
                if value['distance'] > 0:  # Only include non-zero entries
                    path_types[key] = PathTypeStats(**value)
            
            # Convert surface_types  
            surface_types = {}
            for key, value in stats_dict['surface_types'].items():
                if value['distance'] > 0:  # Only include non-zero entries
                    surface_types[key] = SurfaceTypeStats(**value)
            
            # Convert special_areas
            special_areas = {}
            for key, value in stats_dict['special_areas'].items():
                special_areas[key] = SpecialAreaStats(**value)
            
            stats = RouteStats(
                distance=stats_dict['distance'],
                fun_weight=stats_dict['fun_weight'],
                fun_score=stats_dict['fun_score'],
                estimated_time=stats_dict['estimated_time'],
                waypoints=stats_dict['waypoints'],
                path_types=path_types,
                surface_types=surface_types,
                special_areas=special_areas,
                avg_speed=stats_dict['avg_speed'],
                node_type_distribution=stats_dict.get('node_type_distribution', {})
            )
            
            route = Route(
                name=route_data['name'],
                description=route_data['description'],
                route=route_data['coordinates'],  # Frontend expects 'route', not 'coordinates'
                stats=stats,
                color=route_data['color'],
                priority=route_data['priority']
            )
            routes.append(route)
        
        return RouteResponse(
            routes=routes,
            success=True,
            message=f"Found {len(routes)} routes"
        )
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Route calculation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("Starting Fun Path Planner API...")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)