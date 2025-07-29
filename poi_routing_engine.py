#!/usr/bin/env python3
"""
POI-Based Routing Engine
Implements time-constrained and preference-based routing using OSM data and POIs
"""

import json
import math
import networkx as nx
import osmnx as ox
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import heapq

class POIRoutingEngine:
    def __init__(self, enhanced_osm_file: str):
        """Initialize routing engine with enhanced OSM data"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading OSM data from {enhanced_osm_file}...")
        
        with open(enhanced_osm_file, 'r', encoding='utf-8') as f:
            self.osm_data = json.load(f)
        
        self.graph = None
        self.pois = self.osm_data.get('pois', [])
        self.poi_spatial_index = {}
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Loaded {len(self.pois)} POIs")
        self._build_graph()
        self._build_poi_spatial_index()
    
    def _build_graph(self):
        """Build NetworkX graph from OSM data"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Building routing graph...")
        
        self.graph = nx.DiGraph()
        
        # Add graph attributes for OSMnx compatibility
        self.graph.graph['crs'] = 'EPSG:4326'
        self.graph.graph['name'] = 'POI_routing_graph'
        
        # Add nodes
        for node_data in self.osm_data.get('nodes', []):
            node_id = node_data['node_id']
            self.graph.add_node(node_id, 
                               y=node_data['lat'], 
                               x=node_data['lng'],
                               **node_data.get('attributes', {}))
        
        # Add edges
        for edge_data in self.osm_data.get('edges', []):
            u = edge_data['from_node']
            v = edge_data['to_node']
            attrs = edge_data.get('attributes', {})
            
            # Convert string attributes to proper types
            length = float(attrs.get('length', 100))  # Default 100m if missing
            attrs['length'] = length
            attrs['weight'] = length  # Default weight = length
            
            # Add both directions for walking
            self.graph.add_edge(u, v, **attrs)
            self.graph.add_edge(v, u, **attrs)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Graph built: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges")
    
    def _build_poi_spatial_index(self):
        """Build spatial index for fast POI proximity queries"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Building POI spatial index...")
        
        # Simple grid-based spatial index
        grid_size = 0.001  # ~100m at these latitudes
        
        for poi in self.pois:
            if 'lat' not in poi or 'lng' not in poi:
                continue
                
            grid_lat = int(poi['lat'] / grid_size)
            grid_lng = int(poi['lng'] / grid_size)
            grid_key = (grid_lat, grid_lng)
            
            if grid_key not in self.poi_spatial_index:
                self.poi_spatial_index[grid_key] = []
            
            self.poi_spatial_index[grid_key].append(poi)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Spatial index built with {len(self.poi_spatial_index)} grid cells")
    
    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance between two points in meters"""
        R = 6371000  # Earth's radius in meters
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)
        
        a = (math.sin(delta_lat/2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    
    def _find_pois_near_edge(self, u: int, v: int, radius: float = 50.0) -> List[dict]:
        """Find POIs within radius of an edge"""
        if u not in self.graph.nodes or v not in self.graph.nodes:
            return []
        
        u_data = self.graph.nodes[u]
        v_data = self.graph.nodes[v]
        
        # Use midpoint of edge
        mid_lat = (u_data['y'] + v_data['y']) / 2
        mid_lng = (u_data['x'] + v_data['x']) / 2
        
        nearby_pois = []
        grid_size = 0.001
        
        # Check surrounding grid cells
        for dlat in [-1, 0, 1]:
            for dlng in [-1, 0, 1]:
                grid_lat = int(mid_lat / grid_size) + dlat
                grid_lng = int(mid_lng / grid_size) + dlng
                grid_key = (grid_lat, grid_lng)
                
                if grid_key in self.poi_spatial_index:
                    for poi in self.poi_spatial_index[grid_key]:
                        distance = self._calculate_distance(mid_lat, mid_lng, poi['lat'], poi['lng'])
                        if distance <= radius:
                            poi_copy = poi.copy()
                            poi_copy['distance_to_edge'] = distance
                            nearby_pois.append(poi_copy)
        
        return nearby_pois
    
    def _categorize_poi(self, poi: dict) -> str:
        """Categorize POI based on attributes"""
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
        
        # Viewpoints (high priority for nature routes)
        elif (attrs.get('tourism') == 'viewpoint' or 
              attrs.get('natural') in ['peak', 'summit'] or
              'viewpoint' in str(attrs.get('type', '')).lower() or
              'peak' in str(attrs.get('type', '')).lower()):
            return 'viewpoints'
        
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
        
        # Urban amenities (useful but not destination-worthy)
        elif attrs.get('amenity') in ['bench', 'waste_basket', 'toilets', 'atm']:
            return None  # Filter out - not useful for routing preferences
        
        # Default - keep minimal 'other' for truly unclassified
        return 'other'
    
    def apply_poi_weights(self, poi_preferences: Dict[str, float], influence_radius: float = 50.0, prefer_nature_paths: bool = False):
        """Apply POI-based weights to graph edges"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Applying POI weights with {influence_radius}m radius...")
        
        edge_count = 0
        poi_influenced_edges = 0
        viewpoint_influenced_edges = 0
        
        for u, v, data in self.graph.edges(data=True):
            base_weight = data.get('length', 100)
            poi_bonus = 0
            
            # Apply path type penalties/bonuses for nature routes
            path_multiplier = 1.0
            if prefer_nature_paths:
                highway_type = data.get('highway', '')
                if isinstance(highway_type, list):
                    highway_type = highway_type[0] if highway_type else ''
                
                # Heavily favor natural paths
                if highway_type in ['path', 'footway', 'track', 'bridleway']:
                    path_multiplier = 0.3  # Much more attractive
                elif highway_type in ['cycleway', 'pedestrian']:
                    path_multiplier = 0.5  # Moderately attractive
                elif highway_type in ['residential', 'living_street']:
                    path_multiplier = 1.5  # Slightly less attractive
                elif highway_type in ['primary', 'secondary', 'tertiary', 'trunk']:
                    path_multiplier = 3.0  # Much less attractive (avoid main roads)
                else:
                    path_multiplier = 2.0  # Default penalty for other roads
            
            # Find nearby POIs
            nearby_pois = self._find_pois_near_edge(u, v, influence_radius)
            
            if nearby_pois:
                poi_influenced_edges += 1
                
                for poi in nearby_pois:
                    category = self._categorize_poi(poi)
                    if category and category in poi_preferences:  # Skip None categories
                        # Distance-based influence (closer = more influence)
                        distance_factor = 1 - (poi['distance_to_edge'] / influence_radius)
                        poi_value = poi_preferences[category] * distance_factor
                        poi_bonus += poi_value
                        
                        # Track viewpoint influences
                        if category == 'viewpoints':
                            viewpoint_influenced_edges += 1
            
            # Apply POI bonus (lower weight = more attractive)
            # Use logarithmic scaling to prevent extreme weights
            poi_multiplier = 1 / (1 + math.log(1 + poi_bonus))
            data['poi_weight'] = base_weight * poi_multiplier * path_multiplier
            data['poi_bonus'] = poi_bonus
            data['path_multiplier'] = path_multiplier
            
            edge_count += 1
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Applied weights to {edge_count} edges, {poi_influenced_edges} influenced by POIs")
        if 'viewpoints' in poi_preferences:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {viewpoint_influenced_edges} edges influenced by viewpoints")
    
    def calculate_route_time(self, route: List[int], walking_speed_kmh: float = 4.5) -> float:
        """Calculate route time in minutes"""
        if len(route) < 2:
            return 0.0
        
        total_distance = 0
        for i in range(len(route) - 1):
            try:
                edge_data = self.graph[route[i]][route[i+1]]
                total_distance += edge_data.get('length', 0)
            except KeyError:
                continue
        
        # Convert to minutes
        time_hours = (total_distance / 1000) / walking_speed_kmh
        return time_hours * 60
    
    def find_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float, 
                   poi_preferences: Dict[str, float] = None, target_time_minutes: Optional[float] = None,
                   max_detour_factor: float = 2.0) -> Dict:
        """
        Find optimal route with POI preferences and optional time constraints
        """
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Finding route from ({start_lat:.6f}, {start_lng:.6f}) to ({end_lat:.6f}, {end_lng:.6f})")
        
        # Find nearest nodes
        start_node = ox.distance.nearest_nodes(self.graph, X=start_lng, Y=start_lat, return_dist=False)
        end_node = ox.distance.nearest_nodes(self.graph, X=end_lng, Y=end_lat, return_dist=False)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Start node: {start_node}, End node: {end_node}")
        
        # Early exit if start and end are the same node
        if start_node == end_node:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Start and end nodes are identical - returning minimal route")
            return self._format_route_result([start_node], 'same_location', 0.0, 0.0, [])
        
        # Calculate direct route first
        try:
            direct_route = nx.shortest_path(self.graph, start_node, end_node, weight='length')
            direct_time = self.calculate_route_time(direct_route)
            direct_distance = sum(self.graph[direct_route[i]][direct_route[i+1]].get('length', 0) 
                                for i in range(len(direct_route) - 1))
        except nx.NetworkXNoPath:
            return {'error': 'No route found between start and end points'}
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Direct route: {direct_distance:.0f}m, {direct_time:.1f} minutes")
        
        # If no POI preferences, return direct route
        if not poi_preferences:
            return self._format_route_result(direct_route, 'direct', direct_time, direct_distance, [])
        
        # Apply POI weights (with nature path preference for routes with nature/viewpoint preferences)
        prefer_paths = poi_preferences and ('nature' in poi_preferences or 'viewpoints' in poi_preferences)
        influence_radius = 100.0 if 'viewpoints' in poi_preferences else 50.0  # Larger radius for viewpoint routes
        self.apply_poi_weights(poi_preferences, influence_radius=influence_radius, prefer_nature_paths=prefer_paths)
        
        # Calculate POI-optimized route
        try:
            poi_route = nx.shortest_path(self.graph, start_node, end_node, weight='poi_weight')
            poi_time = self.calculate_route_time(poi_route)
            poi_distance = sum(self.graph[poi_route[i]][poi_route[i+1]].get('length', 0) 
                             for i in range(len(poi_route) - 1))
        except nx.NetworkXNoPath:
            poi_route = direct_route
            poi_time = direct_time
            poi_distance = direct_distance
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] POI route: {poi_distance:.0f}m, {poi_time:.1f} minutes")
        
        # Check time constraints
        selected_route = poi_route
        selected_time = poi_time
        selected_distance = poi_distance
        route_type = 'poi_optimized'
        
        if target_time_minutes:
            if poi_time > target_time_minutes:
                # POI route too long, use direct route if it fits
                if direct_time <= target_time_minutes:
                    selected_route = direct_route
                    selected_time = direct_time
                    selected_distance = direct_distance
                    route_type = 'direct_time_constrained'
                else:
                    route_type = 'poi_optimized_over_time'
            elif poi_time < target_time_minutes * 0.95:  # Route too short, try to add detours
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Route too short ({poi_time:.1f} < {target_time_minutes}), attempting time extension...")
                detour_route = self._find_time_filling_route(start_node, end_node, target_time_minutes, poi_preferences)
                if detour_route:
                    selected_route = detour_route['route']
                    selected_time = detour_route['time']
                    selected_distance = detour_route['distance']
                    route_type = 'time_extended'
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Extended route: {selected_distance:.0f}m, {selected_time:.1f} minutes")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Could not extend route, keeping original")
        
        # Find POIs along route
        route_pois = self._find_pois_along_route(selected_route)
        
        # For viewpoint routes, try aggressive viewpoint-seeking if we didn't get enough viewpoints
        if ('viewpoints' in poi_preferences and poi_preferences['viewpoints'] >= 20.0 and 
            len([poi for poi in route_pois if poi.get('category') == 'viewpoints']) < 5):  # Increased threshold to trigger more often
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Too few viewpoints found, attempting aggressive viewpoint routing...")
            aggressive_route = self._find_aggressive_viewpoint_route(start_node, end_node, target_time_minutes, poi_preferences)
            if aggressive_route:
                regular_viewpoints = len([poi for poi in route_pois if poi.get('category') == 'viewpoints'])
                aggressive_viewpoints = len([poi for poi in aggressive_route.get('detailed_pois', []) if poi.get('category') == 'viewpoints'])
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Regular route: {regular_viewpoints} viewpoints, Aggressive route: {aggressive_viewpoints} viewpoints")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Regular route time: {selected_time:.1f}min, Aggressive route time: {aggressive_route.get('time_minutes', 0):.1f}min")
                if aggressive_viewpoints > regular_viewpoints:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Aggressive route found more viewpoints! Using it.")
                    return aggressive_route
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Aggressive route didn't improve viewpoint count, keeping regular route")
        
        return self._format_route_result(selected_route, route_type, selected_time, selected_distance, route_pois)
    
    def _find_time_filling_route(self, start_node: int, end_node: int, target_time: float, 
                                poi_preferences: Dict[str, float]) -> Optional[Dict]:
        """Find route that fills target time by adding strategic detours"""
        # This is a simplified implementation - could be much more sophisticated
        direct_route = nx.shortest_path(self.graph, start_node, end_node, weight='length')
        direct_time = self.calculate_route_time(direct_route)
        
        if direct_time >= target_time:
            return None
        
        # Early exit if start == end (same node routes)
        if start_node == end_node:
            return None
        
        # Try adding waypoints through high-POI areas
        # Find midpoint of direct route
        mid_idx = len(direct_route) // 2
        mid_node = direct_route[mid_idx]
        
        # Optimize: Only check nodes within reasonable distance from midpoint
        mid_node_data = self.graph.nodes[mid_node]
        mid_lat, mid_lng = mid_node_data['y'], mid_node_data['x']
        max_search_distance = 800  # meters - balanced for performance
        
        candidate_waypoints = []
        nodes_checked = 0
        max_nodes_to_check = 100  # Reduced to prevent timeout
        
        for node in self.graph.nodes():
            if node == start_node or node == end_node:
                continue
            
            # Quick distance filter to avoid expensive path calculations
            node_data = self.graph.nodes[node]
            distance_to_mid = self._calculate_distance(mid_lat, mid_lng, node_data['y'], node_data['x'])
            
            if distance_to_mid > max_search_distance:
                continue
            
            nodes_checked += 1
            if nodes_checked > max_nodes_to_check:
                break
            
            try:
                detour_dist = (nx.shortest_path_length(self.graph, start_node, node, weight='length') +
                              nx.shortest_path_length(self.graph, node, end_node, weight='length'))
                direct_dist = nx.shortest_path_length(self.graph, start_node, end_node, weight='length')
                
                if detour_dist <= direct_dist * 3.5:  # Allow longer detours for time filling
                    # Calculate POI score for this node
                    poi_score = self._calculate_node_poi_score(node, poi_preferences)
                    if poi_score > 0:
                        candidate_waypoints.append({
                            'node': node,
                            'detour_distance': detour_dist - direct_dist,
                            'poi_score': poi_score
                        })
            except nx.NetworkXNoPath:
                continue
        
        if not candidate_waypoints:
            return None
        
        # Sort by combination of POI score and time target fit
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(candidate_waypoints)} candidate waypoints")
        
        best_route = None
        best_time_diff = float('inf')
        
        # Try multiple waypoints to find best time match
        for waypoint in candidate_waypoints[:5]:  # Try top 5 candidates to avoid timeout
            try:
                waypoint_route = (nx.shortest_path(self.graph, start_node, waypoint['node'], weight='poi_weight') +
                                 nx.shortest_path(self.graph, waypoint['node'], end_node, weight='poi_weight')[1:])
                
                waypoint_time = self.calculate_route_time(waypoint_route)
                waypoint_distance = sum(self.graph[waypoint_route[i]][waypoint_route[i+1]].get('length', 0) 
                                      for i in range(len(waypoint_route) - 1))
                
                time_diff = abs(waypoint_time - target_time)
                
                # Prefer routes closer to target time
                if time_diff < best_time_diff and waypoint_time > direct_time:
                    best_time_diff = time_diff
                    best_route = {
                        'route': waypoint_route,
                        'time': waypoint_time,
                        'distance': waypoint_distance
                    }
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Better waypoint found: {waypoint_time:.1f}min (target: {target_time})")
                
            except nx.NetworkXNoPath:
                continue
        
        return best_route
    
    def _find_aggressive_viewpoint_route(self, start_node: int, end_node: int, target_time: float, 
                                       poi_preferences: Dict[str, float]) -> Optional[Dict]:
        """Aggressively seek viewpoints by building route through multiple viewpoints"""
        # Find all viewpoints within reasonable distance
        viewpoint_pois = []
        for poi in self.pois:
            if 'lat' not in poi or 'lng' not in poi:
                continue
            category = self._categorize_poi(poi)
            if category == 'viewpoints':
                viewpoint_pois.append(poi)
        
        if not viewpoint_pois:
            return None
            
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(viewpoint_pois)} total viewpoints")
        
        # Find nearest nodes for each viewpoint
        viewpoint_nodes = []
        for poi in viewpoint_pois:
            try:
                nearest_node = ox.distance.nearest_nodes(self.graph, X=poi['lng'], Y=poi['lat'], return_dist=False)
                # Check if viewpoint is reachable
                try:
                    dist_from_start = nx.shortest_path_length(self.graph, start_node, nearest_node, weight='length')
                    dist_to_end = nx.shortest_path_length(self.graph, nearest_node, end_node, weight='length')
                    total_dist = dist_from_start + dist_to_end
                    direct_dist = nx.shortest_path_length(self.graph, start_node, end_node, weight='length')
                    
                    # Only consider viewpoints that don't make route impossibly long
                    if total_dist <= direct_dist * 4.0:  # Allow up to 4x detour
                        viewpoint_nodes.append({
                            'node': nearest_node,
                            'poi': poi,
                            'detour_cost': total_dist - direct_dist,
                            'total_dist': total_dist
                        })
                except nx.NetworkXNoPath:
                    continue
            except:
                continue
        
        if not viewpoint_nodes:
            return None
            
        # Sort viewpoints by detour cost (prefer closer ones)
        viewpoint_nodes.sort(key=lambda x: x['detour_cost'])
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(viewpoint_nodes)} reachable viewpoints")
        
        # Try to build routes through multiple viewpoints
        best_route = None
        best_viewpoint_count = 0
        
        # Try different combinations of viewpoints
        for num_viewpoints in range(min(6, len(viewpoint_nodes)), 0, -1):  # Try 6 down to 1 viewpoint
            for i in range(min(3, len(viewpoint_nodes) - num_viewpoints + 1)):  # Try 3 different starting positions
                try:
                    selected_viewpoints = viewpoint_nodes[i:i+num_viewpoints]
                    
                    # Build route through viewpoints
                    route_segments = []
                    current_node = start_node
                    
                    for vp in selected_viewpoints:
                        segment = nx.shortest_path(self.graph, current_node, vp['node'], weight='poi_weight')
                        if len(route_segments) > 0:
                            segment = segment[1:]  # Remove duplicate node
                        route_segments.extend(segment)
                        current_node = vp['node']
                    
                    # Add final segment to end
                    final_segment = nx.shortest_path(self.graph, current_node, end_node, weight='poi_weight')
                    if len(route_segments) > 0:
                        final_segment = final_segment[1:]  # Remove duplicate node
                    route_segments.extend(final_segment)
                    
                    # Calculate route metrics
                    route_time = self.calculate_route_time(route_segments)
                    route_distance = sum(self.graph[route_segments[j]][route_segments[j+1]].get('length', 0) 
                                       for j in range(len(route_segments) - 1))
                    
                    # Check if route fits time constraints (allow some flexibility)
                    if target_time and route_time > target_time * 1.6:  # Allow 60% over target for viewpoints (was 40%, now more flexible)
                        continue
                    
                    # Find POIs along this route
                    route_pois = self._find_pois_along_route(route_segments)
                    viewpoint_count = len([poi for poi in route_pois if poi.get('category') == 'viewpoints'])
                    
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Route with {num_viewpoints} planned viewpoints found {viewpoint_count} total viewpoints, {route_time:.1f}min")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] route_pois has {len(route_pois)} total POIs, {len([poi for poi in route_pois if poi.get('category') == 'viewpoints'])} viewpoints")
                    
                    if viewpoint_count > best_viewpoint_count:
                        best_viewpoint_count = viewpoint_count
                        best_route = self._format_route_result(
                            route_segments, 'aggressive_viewpoint', route_time, route_distance, route_pois
                        )
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Best route updated: {len(best_route.get('detailed_pois', []))} detailed_pois")
                        
                except (nx.NetworkXNoPath, IndexError, KeyError):
                    continue
                    
            if best_route:  # If we found a good route, don't try fewer viewpoints
                break
        
        return best_route
    
    def _calculate_node_poi_score(self, node: int, poi_preferences: Dict[str, float]) -> float:
        """Calculate POI score for a node based on nearby POIs"""
        if node not in self.graph.nodes:
            return 0.0
        
        node_data = self.graph.nodes[node]
        nearby_pois = self._find_pois_near_edge(node, node, radius=100)  # Larger radius for waypoints
        
        score = 0.0
        for poi in nearby_pois:
            category = self._categorize_poi(poi)
            if category and category in poi_preferences:  # Skip None categories
                distance_factor = 1 - (poi['distance_to_edge'] / 100)
                score += poi_preferences[category] * distance_factor
        
        return score
    
    def _find_pois_along_route(self, route: List[int], radius: float = 100.0) -> List[Dict]:
        """Find POIs along the route"""
        route_pois = []
        seen_pois = set()
        
        for i in range(len(route)):
            node = route[i]
            nearby_pois = self._find_pois_near_edge(node, node, radius)
            
            for poi in nearby_pois:
                poi_id = poi.get('osm_id')
                category = self._categorize_poi(poi)
                if poi_id not in seen_pois and category:  # Skip None categories
                    seen_pois.add(poi_id)
                    poi_info = poi.copy()
                    poi_info['category'] = category
                    poi_info['route_segment'] = i
                    route_pois.append(poi_info)
        
        return route_pois
    
    def _format_route_result(self, route: List[int], route_type: str, time: float, 
                           distance: float, pois: List[Dict]) -> Dict:
        """Format route result with coordinates and metadata"""
        coordinates = []
        for node in route:
            if node in self.graph.nodes:
                node_data = self.graph.nodes[node]
                coordinates.append({
                    'lat': node_data['y'],
                    'lng': node_data['x']
                })
        
        # Categorize POIs
        poi_summary = defaultdict(int)
        for poi in pois:
            poi_summary[poi['category']] += 1
        
        return {
            'route_type': route_type,
            'coordinates': coordinates,
            'nodes': route,
            'distance_meters': round(distance, 1),
            'time_minutes': round(time, 1),
            'waypoints': len(route),
            'pois_along_route': len(pois),
            'poi_categories': dict(poi_summary),
            'detailed_pois': pois[:20],  # Limit for brevity
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'algorithm': 'poi_weighted_shortest_path'
            }
        }

def generate_html_visualization(routes: List[Dict], output_file: str):
    """Generate HTML visualization for multiple routes"""
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multi-Route POI Visualization</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
        #map {{ height: 70vh; width: 100%; margin-bottom: 20px; }}
        .route-info {{ display: flex; flex-wrap: wrap; gap: 20px; }}
        .route-card {{
            border: 2px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            min-width: 300px;
            flex: 1;
        }}
        .route-title {{ font-size: 18px; font-weight: bold; margin-bottom: 10px; }}
        .route-stats {{ margin-bottom: 10px; }}
        .poi-categories {{ font-size: 14px; }}
        .legend {{ 
            position: absolute; 
            top: 10px; 
            right: 10px; 
            background: white; 
            padding: 10px; 
            border-radius: 5px; 
            box-shadow: 0 0 10px rgba(0,0,0,0.3);
            z-index: 1000;
        }}
    </style>
</head>
<body>
    <h1>Multi-Route POI-Based Navigation</h1>
    <div id="map"></div>
    
    <div class="route-info">
"""

    colors = ['#FF0000', '#00FF00', '#0000FF', '#FF00FF', '#00FFFF']
    
    for i, route in enumerate(routes):
        color = colors[i % len(colors)]
        html_content += f"""
        <div class="route-card" style="border-color: {color};">
            <div class="route-title" style="color: {color};">{route['name']}</div>
            <div class="route-stats">
                <strong>Distance:</strong> {route['result']['distance_meters']:.0f}m<br>
                <strong>Time:</strong> {route['result']['time_minutes']:.1f} min<br>
                <strong>POIs:</strong> {route['result']['pois_along_route']}
            </div>
            <div class="poi-categories">
                <strong>Categories:</strong><br>
"""
        for category, count in route['result']['poi_categories'].items():
            html_content += f"                • {category}: {count}<br>\\n"
        
        html_content += "            </div>\\n        </div>\\n"

    html_content += """
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        // Initialize map
        var map = L.map('map');
        
        // Add OpenStreetMap tiles
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);
        
        var routes = """ + json.dumps([r['result'] for r in routes]) + """;
        var routeNames = """ + json.dumps([r['name'] for r in routes]) + """;
        var colors = """ + json.dumps(colors) + """;
        
        var allBounds = [];
        
        // Add routes to map
        routes.forEach(function(route, index) {
            var color = colors[index % colors.length];
            var name = routeNames[index];
            
            if (route.coordinates && route.coordinates.length > 0) {
                var latlngs = route.coordinates.map(coord => [coord.lat, coord.lng]);
                
                // Add route line
                var polyline = L.polyline(latlngs, {
                    color: color,
                    weight: 4,
                    opacity: 0.8
                }).addTo(map);
                
                polyline.bindPopup('<b>' + name + '</b><br>' +
                                 'Distance: ' + route.distance_meters.toFixed(0) + 'm<br>' +
                                 'Time: ' + route.time_minutes.toFixed(1) + ' min');
                
                // Add start marker
                if (latlngs.length > 0) {
                    L.circleMarker(latlngs[0], {
                        color: color,
                        fillColor: color,
                        fillOpacity: 0.8,
                        radius: 8
                    }).addTo(map).bindPopup('Start: ' + name);
                }
                
                // Add end marker
                if (latlngs.length > 1) {
                    L.circleMarker(latlngs[latlngs.length - 1], {
                        color: color,
                        fillColor: 'white',
                        fillOpacity: 0.8,
                        radius: 6
                    }).addTo(map).bindPopup('End: ' + name);
                }
                
                // Collect bounds
                latlngs.forEach(latlng => allBounds.push(latlng));
            }
        });
        
        // Fit map to show all routes
        if (allBounds.length > 0) {
            map.fitBounds(allBounds, {padding: [20, 20]});
        }
        
        // Add legend
        var legend = L.control({position: 'topright'});
        legend.onAdd = function(map) {
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<h4>Routes</h4>';
            
            routeNames.forEach(function(name, index) {
                var color = colors[index % colors.length];
                div.innerHTML += '<div><span style="color: ' + color + '; font-weight: bold;">■</span> ' + name + '</div>';
            });
            
            return div;
        };
        legend.addTo(map);
    </script>
</body>
</html>
"""

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"HTML visualization saved to {output_file}")

def generate_timed_routes(osm_file: str, target_time_minutes: int = 120):
    """Generate multiple route examples with specified target time"""
    print(f"Target walking time: {target_time_minutes} minutes ({target_time_minutes/60:.1f} hours)")
    
    # Initialize engine
    engine = POIRoutingEngine(osm_file)
    
    # Define common start and end points for fair comparison (Swedish coordinates)
    start_lat, start_lng = 57.685, 11.920   # Southwest area
    end_lat, end_lng = 57.725, 11.975       # Northeast area
    
    print(f"\\nAll routes: ({start_lat}, {start_lng}) → ({end_lat}, {end_lng})")
    
    # Define multiple route scenarios
    routes = []
    
    # 1. Restaurant-focused route
    print("\\n" + "="*60)
    print("RESTAURANT ROUTE")
    print("="*60)
    
    restaurant_route = engine.find_route(
        start_lat=start_lat, start_lng=start_lng,
        end_lat=end_lat, end_lng=end_lng,
        poi_preferences={
            'restaurants': 5.0,
            'cafes': 2.0
        },
        target_time_minutes=target_time_minutes
    )
    routes.append({'name': 'Restaurant Route', 'result': restaurant_route})
    print_route_summary(restaurant_route, "Restaurant Route")
    
    # 2. Tourism & Culture route
    print("\\n" + "="*60)
    print("TOURISM & CULTURE ROUTE")
    print("="*60)
    
    tourism_route = engine.find_route(
        start_lat=start_lat, start_lng=start_lng,
        end_lat=end_lat, end_lng=end_lng,
        poi_preferences={
            'tourism': 5.0,
            'education': 2.0,
            'restaurants': 1.5
        },
        target_time_minutes=target_time_minutes
    )
    routes.append({'name': 'Tourism Route', 'result': tourism_route})
    print_route_summary(tourism_route, "Tourism Route")
    
    # 3. Shopping route
    print("\\n" + "="*60)
    print("SHOPPING ROUTE")
    print("="*60)
    
    shopping_route = engine.find_route(
        start_lat=start_lat, start_lng=start_lng,
        end_lat=end_lat, end_lng=end_lng,
        poi_preferences={
            'shops': 4.0,
            'restaurants': 1.5,
            'cafes': 1.0
        },
        target_time_minutes=target_time_minutes
    )
    routes.append({'name': 'Shopping Route', 'result': shopping_route})
    print_route_summary(shopping_route, "Shopping Route")
    
    # 4. Nightlife route
    print("\\n" + "="*60)
    print("NIGHTLIFE ROUTE")
    print("="*60)
    
    nightlife_route = engine.find_route(
        start_lat=start_lat, start_lng=start_lng,
        end_lat=end_lat, end_lng=end_lng,
        poi_preferences={
            'bars_pubs': 5.0,
            'restaurants': 2.0,
            'fast_food': 1.0
        },
        target_time_minutes=target_time_minutes
    )
    routes.append({'name': 'Nightlife Route', 'result': nightlife_route})
    print_route_summary(nightlife_route, "Nightlife Route")
    
    # 5. Nature & Recreation route
    print("\\n" + "="*60)
    print("NATURE & RECREATION ROUTE")
    print("="*60)
    
    nature_route = engine.find_route(
        start_lat=start_lat, start_lng=start_lng,
        end_lat=end_lat, end_lng=end_lng,
        poi_preferences={
            'viewpoints': 30.0,   # EXTREMELY high priority for viewpoints and peaks - 3x increase!
            'nature': 8.0,        # Significantly increased nature priority
            'recreation': 4.0,    # Increased recreation priority  
            'tourism': 1.0        # Reduced tourism priority
        },
        target_time_minutes=target_time_minutes
    )
    routes.append({'name': 'Nature Route', 'result': nature_route})
    print_route_summary(nature_route, "Nature Route")
    
    # Generate HTML visualization
    html_filename = f"timed_routes_{target_time_minutes}min_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    generate_html_visualization(routes, html_filename)
    
    # Save all routes to JSON
    all_routes_filename = f"timed_routes_{target_time_minutes}min_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(all_routes_filename, 'w', encoding='utf-8') as f:
        json.dump({
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'target_time_minutes': target_time_minutes,
                'total_routes': len(routes)
            },
            'routes': routes
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\\nAll routes saved to {all_routes_filename}")
    return routes

def main():
    """Generate multiple route examples with HTML visualization"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python poi_routing_engine.py <enhanced_osm_file.json> [target_time_minutes]")
        print("  target_time_minutes: Optional walking time in minutes (default: 120)")
        return
    
    osm_file = sys.argv[1]
    target_time = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    
    generate_timed_routes(osm_file, target_time)

def print_route_summary(result: Dict, route_name: str):
    """Print a summary of a single route"""
    if 'error' in result:
        print(f"Error in {route_name}: {result['error']}")
        return
    
    print(f"Distance: {result['distance_meters']:.0f}m")
    print(f"Time: {result['time_minutes']:.1f} minutes")
    print(f"POIs along route: {result['pois_along_route']}")
    
    if result['poi_categories']:
        print("Categories:", ", ".join([f"{cat}({count})" for cat, count in result['poi_categories'].items()]))

if __name__ == "__main__":
    main()