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
    
    def _validate_route_edge_usage(self, route: List[int], max_edge_usage: int = 2) -> bool:
        """Check if route respects maximum edge usage constraint"""
        edge_usage = {}
        
        for i in range(len(route) - 1):
            u, v = route[i], route[i + 1]
            # Create canonical edge representation (smaller node first)
            edge = (min(u, v), max(u, v))
            edge_usage[edge] = edge_usage.get(edge, 0) + 1
            
            if edge_usage[edge] > max_edge_usage:
                return False
        
        return True
    
    def _get_route_edge_usage(self, route: List[int]) -> Dict[Tuple[int, int], int]:
        """Get edge usage count for a route"""
        edge_usage = {}
        
        for i in range(len(route) - 1):
            u, v = route[i], route[i + 1]
            # Create canonical edge representation (smaller node first)
            edge = (min(u, v), max(u, v))
            edge_usage[edge] = edge_usage.get(edge, 0) + 1
        
        return edge_usage
    
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
    
    def generate_trail(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float,
                      poi_preferences: Dict[str, float] = None, deviation_factor: float = 0.4) -> Dict:
        """
        Generate a trail between points A and B with specified deviation allowance
        
        Args:
            start_lat, start_lng: Starting coordinates
            end_lat, end_lng: Ending coordinates  
            poi_preferences: Dictionary of POI category preferences (e.g. {'viewpoints': 30.0, 'nature': 8.0})
            deviation_factor: Maximum allowed deviation as fraction of direct route (0.4 = 40%)
        
        Returns:
            Dictionary with route information including coordinates, distance, time, and POIs
        """
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Generating trail from ({start_lat:.6f}, {start_lng:.6f}) to ({end_lat:.6f}, {end_lng:.6f})")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Deviation allowance: {deviation_factor*100:.0f}% of direct route")
        
        # Find nearest nodes
        start_node = ox.distance.nearest_nodes(self.graph, X=start_lng, Y=start_lat, return_dist=False)
        end_node = ox.distance.nearest_nodes(self.graph, X=end_lng, Y=end_lat, return_dist=False)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Start node: {start_node}, End node: {end_node}")
        
        # Early exit if start and end are the same node
        if start_node == end_node:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Start and end nodes are identical - returning minimal route")
            return self._format_route_result([start_node], 'same_location', 0.0, 0.0, [])
        
        # Calculate direct route first to establish baseline
        try:
            direct_route = nx.shortest_path(self.graph, start_node, end_node, weight='length')
            direct_time = self.calculate_route_time(direct_route)
            direct_distance = sum(self.graph[direct_route[i]][direct_route[i+1]].get('length', 0) 
                                for i in range(len(direct_route) - 1))
        except nx.NetworkXNoPath:
            return {'error': 'No route found between start and end points'}
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Direct route: {direct_distance:.0f}m, {direct_time:.1f} minutes")
        
        # Calculate maximum allowed distance based on deviation factor
        max_allowed_distance = direct_distance * (1 + deviation_factor)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Maximum allowed distance: {max_allowed_distance:.0f}m")
        
        # If no POI preferences, return direct route
        if not poi_preferences:
            return self._format_route_result(direct_route, 'direct', direct_time, direct_distance, [])
        
        # Apply POI weights (with nature path preference for routes with nature/viewpoint preferences)
        prefer_paths = poi_preferences and ('nature' in poi_preferences or 'viewpoints' in poi_preferences)
        influence_radius = 100.0 if 'viewpoints' in poi_preferences else 50.0
        self.apply_poi_weights(poi_preferences, influence_radius=influence_radius, prefer_nature_paths=prefer_paths)
        
        # Try POI-optimized route first
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
        
        # Select best route within deviation constraints
        selected_route = poi_route
        selected_time = poi_time
        selected_distance = poi_distance
        route_type = 'poi_optimized'
        
        # If POI route exceeds deviation limit, check if we can find a better compromise
        if poi_distance > max_allowed_distance:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] POI route exceeds deviation limit, trying alternative approaches...")
            
            # Try finding a route through strategic waypoints within deviation limit
            waypoint_route = self._find_trail_with_waypoints(start_node, end_node, max_allowed_distance, poi_preferences)
            
            if waypoint_route and waypoint_route['distance'] <= max_allowed_distance:
                selected_route = waypoint_route['route']
                selected_time = waypoint_route['time']
                selected_distance = waypoint_route['distance']
                route_type = 'waypoint_optimized'
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Waypoint route: {selected_distance:.0f}m, {selected_time:.1f} minutes")
            else:
                # Fall back to direct route if nothing fits within deviation
                selected_route = direct_route
                selected_time = direct_time
                selected_distance = direct_distance
                route_type = 'direct_fallback'
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Using direct route as fallback")
        
        # Find POIs along final route
        route_pois = self._find_pois_along_route(selected_route)
        
        # For viewpoint routes, try aggressive viewpoint-seeking if within deviation limit
        if ('viewpoints' in poi_preferences and poi_preferences['viewpoints'] >= 20.0 and 
            len([poi for poi in route_pois if poi.get('category') == 'viewpoints']) < 3):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Trying aggressive viewpoint routing within deviation limit...")
            aggressive_route = self._find_aggressive_viewpoint_trail(start_node, end_node, max_allowed_distance, poi_preferences)
            if aggressive_route and aggressive_route.get('distance_meters', 0) <= max_allowed_distance:
                aggressive_viewpoints = len([poi for poi in aggressive_route.get('detailed_pois', []) if poi.get('category') == 'viewpoints'])
                regular_viewpoints = len([poi for poi in route_pois if poi.get('category') == 'viewpoints'])
                if aggressive_viewpoints > regular_viewpoints:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Aggressive route found more viewpoints within deviation limit!")
                    return aggressive_route
        
        return self._format_route_result(selected_route, route_type, selected_time, selected_distance, route_pois)

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
        
        # Try aggressive routing for all high-priority POI preferences (not just viewpoints)
        high_priority_categories = [cat for cat, score in poi_preferences.items() if score >= 15.0] if poi_preferences else []
        
        if high_priority_categories and target_time_minutes and selected_time < target_time_minutes * 0.8:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Route too short for high-priority categories {high_priority_categories}, attempting aggressive POI routing...")
            
            # For viewpoint routes, use the specialized viewpoint algorithm
            if 'viewpoints' in high_priority_categories and poi_preferences['viewpoints'] >= 20.0:
                aggressive_route = self._find_aggressive_viewpoint_route(start_node, end_node, target_time_minutes, poi_preferences)
                if aggressive_route:
                    regular_viewpoints = len([poi for poi in route_pois if poi.get('category') == 'viewpoints'])
                    aggressive_viewpoints = len([poi for poi in aggressive_route.get('detailed_pois', []) if poi.get('category') == 'viewpoints'])
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Regular route: {regular_viewpoints} viewpoints, Aggressive route: {aggressive_viewpoints} viewpoints")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Regular route time: {selected_time:.1f}min, Aggressive route time: {aggressive_route.get('time_minutes', 0):.1f}min")
                    if aggressive_viewpoints > regular_viewpoints:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Aggressive viewpoint route found more viewpoints! Using it.")
                        return aggressive_route
            
            # For all other routes, use the generic aggressive POI routing
            else:
                aggressive_route = self._find_aggressive_poi_route(start_node, end_node, target_time_minutes, poi_preferences)
                if aggressive_route:
                    # Calculate preferred POI counts for comparison
                    regular_preferred_pois = sum(1 for poi in route_pois 
                                               if poi.get('category') in high_priority_categories)
                    # Get total POI counts from the aggressive route, not just detailed_pois
                    aggressive_poi_categories = aggressive_route.get('poi_categories', {})
                    aggressive_preferred_pois = sum(aggressive_poi_categories.get(cat, 0) 
                                                  for cat in high_priority_categories)
                    
                    # Debug: Show breakdown of POI counts
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] High-priority categories: {high_priority_categories}")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Regular route POI categories: {dict((cat, sum(1 for poi in route_pois if poi.get('category') == cat)) for cat in high_priority_categories)}")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Aggressive route POI categories: {dict((cat, aggressive_poi_categories.get(cat, 0)) for cat in high_priority_categories)}")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Regular route: {regular_preferred_pois} preferred POIs, Aggressive route: {aggressive_preferred_pois} preferred POIs")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Regular route time: {selected_time:.1f}min, Aggressive route time: {aggressive_route.get('time_minutes', 0):.1f}min")
                    
                    # Use aggressive route if it has more preferred POIs OR much better time utilization  
                    time_improvement = aggressive_route.get('time_minutes', 0) / selected_time if selected_time > 0 else 1
                    poi_improvement = aggressive_preferred_pois / regular_preferred_pois if regular_preferred_pois > 0 else 1
                    
                    # More lenient criteria: use aggressive route if it's significantly longer OR has more POIs
                    if (aggressive_preferred_pois > regular_preferred_pois * 1.2 or  # 20% more POIs
                        time_improvement > 1.4 or  # 40% longer time 
                        (aggressive_preferred_pois >= regular_preferred_pois and time_improvement > 1.2)):  # Same POIs but 20% longer
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Aggressive POI route is significantly better! Using it.")
                        return aggressive_route
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Aggressive POI route didn't provide significant improvement, keeping regular route")
        
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
                
                # Check if route respects edge usage constraint (max 2 times per street)
                if not self._validate_route_edge_usage(waypoint_route, max_edge_usage=2):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Waypoint route rejected: too much street repetition")
                    continue
                
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
        ramberget_found = False
        for poi in self.pois:
            if 'lat' not in poi or 'lng' not in poi:
                continue
            category = self._categorize_poi(poi)
            if category == 'viewpoints':
                viewpoint_pois.append(poi)
                poi_name = poi.get('attributes', {}).get('name', 'Unnamed')
                if poi_name == 'Ramberget':
                    ramberget_found = True
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found Ramberget in viewpoint POIs at ({poi['lat']}, {poi['lng']})")
        
        if not ramberget_found:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] WARNING: Ramberget not found in viewpoint POIs!")
        
        if not viewpoint_pois:
            return None
            
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(viewpoint_pois)} total viewpoints")
        
        # Find nearest nodes for each viewpoint
        viewpoint_nodes = []
        ramberget_processed = False
        for poi in viewpoint_pois:
            poi_name = poi.get('attributes', {}).get('name', 'Unnamed')
            try:
                nearest_node = ox.distance.nearest_nodes(self.graph, X=poi['lng'], Y=poi['lat'], return_dist=False)
                # Check if viewpoint is reachable
                try:
                    dist_from_start = nx.shortest_path_length(self.graph, start_node, nearest_node, weight='length')
                    dist_to_end = nx.shortest_path_length(self.graph, nearest_node, end_node, weight='length')
                    total_dist = dist_from_start + dist_to_end
                    direct_dist = nx.shortest_path_length(self.graph, start_node, end_node, weight='length')
                    
                    detour_factor = total_dist / direct_dist
                    
                    if poi_name == 'Ramberget':
                        ramberget_processed = True
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing Ramberget: detour {detour_factor:.2f}x (threshold: 4.0x)")
                    
                    # Only consider viewpoints that don't make route impossibly long
                    if total_dist <= direct_dist * 4.0:  # Allow up to 4x detour
                        viewpoint_nodes.append({
                            'node': nearest_node,
                            'poi': poi,
                            'detour_cost': total_dist - direct_dist,
                            'total_dist': total_dist
                        })
                        if poi_name == 'Ramberget':
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ramberget ACCEPTED as reachable viewpoint")
                    else:
                        if poi_name == 'Ramberget':
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ramberget REJECTED: detour too large ({detour_factor:.2f}x > 4.0x)")
                except nx.NetworkXNoPath:
                    if poi_name == 'Ramberget':
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Ramberget REJECTED: no path found")
                    continue
            except Exception as e:
                if poi_name == 'Ramberget':
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Ramberget REJECTED: exception {e}")
                continue
        
        if not ramberget_processed:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] WARNING: Ramberget was not processed in reachability check!")
        
        if not viewpoint_nodes:
            return None
            
        # Sort viewpoints by priority: named peaks/viewpoints first, then by detour cost
        def viewpoint_priority(vp):
            poi = vp['poi']
            attrs = poi.get('attributes', {})
            
            # Highest priority: named peaks with elevation
            if attrs.get('natural') == 'peak' and attrs.get('name') and attrs.get('ele'):
                return (0, vp['detour_cost'])  # Sort group 0 by detour cost
            
            # High priority: named viewpoints  
            if attrs.get('name') and attrs.get('name') != 'Unnamed':
                return (1, vp['detour_cost'])  # Sort group 1 by detour cost
            
            # Medium priority: peaks without names
            if attrs.get('natural') == 'peak':
                return (2, vp['detour_cost'])  # Sort group 2 by detour cost
            
            # Low priority: unnamed viewpoints
            return (3, vp['detour_cost'])  # Sort group 3 by detour cost
        
        viewpoint_nodes.sort(key=viewpoint_priority)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sorted viewpoints by priority (named peaks first)")
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(viewpoint_nodes)} reachable viewpoints")
        # Show details of viewpoints found, especially Ramberget
        ramberget_in_top = False
        for i, vp in enumerate(viewpoint_nodes[:10]):  # Show first 10
            poi_name = vp['poi'].get('attributes', {}).get('name', 'Unnamed')
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Viewpoint {i+1}: {poi_name} at ({vp['poi']['lat']:.6f}, {vp['poi']['lng']:.6f}), detour: {vp['detour_cost']:.0f}m")
            if poi_name == 'Ramberget':
                ramberget_in_top = True
                
        # Find Ramberget's position in the full list
        if not ramberget_in_top:
            for i, vp in enumerate(viewpoint_nodes):
                poi_name = vp['poi'].get('attributes', {}).get('name', 'Unnamed')
                if poi_name == 'Ramberget':
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] FOUND Ramberget at position {i+1}/{len(viewpoint_nodes)}: detour {vp['detour_cost']:.0f}m")
                    break
        
        # Try to build routes through multiple viewpoints
        best_route = None
        best_viewpoint_count = 0
        
        # Try different combinations of viewpoints (maximize viewpoints, no arbitrary limit)
        for num_viewpoints in range(len(viewpoint_nodes), 0, -1):  # Try all viewpoints down to 1
            for i in range(min(3, len(viewpoint_nodes) - num_viewpoints + 1)):  # Try 3 different starting positions
                try:
                    selected_viewpoints = viewpoint_nodes[i:i+num_viewpoints]
                    
                    # Build route through viewpoints
                    route_segments = []
                    current_node = start_node
                    
                    # Debug: Show planned viewpoints for this specific route attempt
                    planned_names = [vp['poi'].get('attributes', {}).get('name', 'Unnamed') for vp in selected_viewpoints]
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Building route through: {planned_names}")
                    
                    for vp in selected_viewpoints:
                        segment = nx.shortest_path(self.graph, current_node, vp['node'], weight='poi_weight')
                        if len(route_segments) > 0:
                            segment = segment[1:]  # Remove duplicate node
                        route_segments.extend(segment)
                        current_node = vp['node']
                        
                        # Debug: Confirm viewpoint node is included
                        vp_name = vp['poi'].get('attributes', {}).get('name', 'Unnamed')
                        if vp_name == 'Ramberget':
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Added Ramberget node {vp['node']} to route_segments (total: {len(route_segments)})")
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ramberget node in route_segments: {vp['node'] in route_segments}")
                    
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
                        planned_names = [vp['poi'].get('attributes', {}).get('name', 'Unnamed') for vp in selected_viewpoints]
                        if 'Ramberget' in planned_names:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Route with Ramberget REJECTED: too long ({route_time:.1f}min > {target_time * 1.6:.1f}min)")
                        continue
                    
                    # Check if route respects edge usage constraint (max 2 times per street)
                    if not self._validate_route_edge_usage(route_segments, max_edge_usage=2):
                        planned_names = [vp['poi'].get('attributes', {}).get('name', 'Unnamed') for vp in selected_viewpoints]
                        if 'Ramberget' in planned_names:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Route with Ramberget REJECTED: too much street repetition")
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Route rejected: too much street repetition")
                        continue
                    
                    # Find POIs along this route (use larger radius for viewpoint detection)
                    route_pois = self._find_pois_along_route(route_segments, radius=200.0)
                    viewpoint_count = len([poi for poi in route_pois if poi.get('category') == 'viewpoints'])
                    
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Route with {num_viewpoints} planned viewpoints found {viewpoint_count} total viewpoints, {route_time:.1f}min")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] route_pois has {len(route_pois)} total POIs, {len([poi for poi in route_pois if poi.get('category') == 'viewpoints'])} viewpoints")
                    
                    # Calculate route quality score (prioritize named peaks)
                    named_peaks = len([poi for poi in route_pois if poi.get('category') == 'viewpoints' and 
                                     poi.get('attributes', {}).get('natural') == 'peak' and 
                                     poi.get('attributes', {}).get('name')])
                    named_viewpoints = len([poi for poi in route_pois if poi.get('category') == 'viewpoints' and 
                                          poi.get('attributes', {}).get('name') and 
                                          poi.get('attributes', {}).get('name') != 'Unnamed'])
                    
                    # Route quality: named peaks worth 5 points, named viewpoints worth 2 points, unnamed worth 1 point
                    route_quality = named_peaks * 5 + (named_viewpoints - named_peaks) * 2 + (viewpoint_count - named_viewpoints) * 1
                    
                    # Debug: Check if Ramberget is in the route POIs
                    ramberget_in_route = any(poi.get('attributes', {}).get('name') == 'Ramberget' for poi in route_pois)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Route: {viewpoint_count} viewpoints, quality: {route_quality}, Ramberget: {ramberget_in_route}")
                    if ramberget_in_route:
                        planned_viewpoint_names = [vp['poi'].get('attributes', {}).get('name', 'Unnamed') for vp in viewpoint_nodes[:num_viewpoints]]
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Planned viewpoints for this route: {planned_viewpoint_names}")
                    else:
                        # Check if Ramberget was supposed to be in this route
                        planned_viewpoint_names = [vp['poi'].get('attributes', {}).get('name', 'Unnamed') for vp in viewpoint_nodes[:num_viewpoints]]
                        if 'Ramberget' in planned_viewpoint_names:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  PROBLEM: Ramberget was planned but not found in route!")
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Planned: {planned_viewpoint_names}")
                            # Check if Ramberget's node is in route_segments
                            ramberget_node = None
                            for vp in viewpoint_nodes[:num_viewpoints]:
                                if vp['poi'].get('attributes', {}).get('name') == 'Ramberget':
                                    ramberget_node = vp['node']
                                    break
                            if ramberget_node and ramberget_node in route_segments:
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] Ramberget node {ramberget_node} IS in route segments")
                            elif ramberget_node:
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] Ramberget node {ramberget_node} NOT in route segments")
                    
                    best_quality = getattr(self, '_best_route_quality', 0)
                    
                    if route_quality > best_quality or (route_quality == best_quality and viewpoint_count > best_viewpoint_count):
                        self._best_route_quality = route_quality
                        best_viewpoint_count = viewpoint_count
                        best_route = self._format_route_result(
                            route_segments, 'aggressive_viewpoint', route_time, route_distance, route_pois
                        )
                        
                        # Debug: Show which route became the best
                        route_viewpoint_names = [poi.get('attributes', {}).get('name', 'Unnamed') for poi in route_pois if poi.get('category') == 'viewpoints']
                        ramberget_in_best = 'Ramberget' in route_viewpoint_names
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] NEW BEST route (quality: {route_quality}, {viewpoint_count} viewpoints, {named_peaks} peaks): Ramberget: {ramberget_in_best}")
                        if ramberget_in_best:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Best route includes Ramberget!")
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Best route updated: {len(best_route.get('detailed_pois', []))} detailed_pois")
                        
                except (nx.NetworkXNoPath, IndexError, KeyError) as e:
                    planned_names = [vp['poi'].get('attributes', {}).get('name', 'Unnamed') for vp in selected_viewpoints] if 'selected_viewpoints' in locals() else []
                    if 'Ramberget' in planned_names:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Route with Ramberget FAILED: {type(e).__name__}: {e}")
                    continue
                    
            if best_route:  # If we found a good route, don't try fewer viewpoints
                break
        
        return best_route
    
    def _find_trail_with_waypoints(self, start_node: int, end_node: int, max_allowed_distance: float, 
                                  poi_preferences: Dict[str, float]) -> Optional[Dict]:
        """Find trail within distance constraints by adding strategic waypoints"""
        direct_route = nx.shortest_path(self.graph, start_node, end_node, weight='length')
        direct_distance = sum(self.graph[direct_route[i]][direct_route[i+1]].get('length', 0) 
                            for i in range(len(direct_route) - 1))
        
        if direct_distance >= max_allowed_distance:
            return None
        
        # Early exit if start == end (same node routes)
        if start_node == end_node:
            return None
        
        # Find midpoint of direct route
        mid_idx = len(direct_route) // 2
        mid_node = direct_route[mid_idx]
        
        # Optimize: Only check nodes within reasonable distance from midpoint
        mid_node_data = self.graph.nodes[mid_node]
        mid_lat, mid_lng = mid_node_data['y'], mid_node_data['x']
        max_search_distance = min(800, (max_allowed_distance - direct_distance) / 2)  # Stay within deviation limit
        
        candidate_waypoints = []
        nodes_checked = 0
        max_nodes_to_check = 50  # Reduced for trail generation
        
        for node in self.graph.nodes():
            if node == start_node or node == end_node:
                continue
            
            # Quick distance filter
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
                
                if detour_dist <= max_allowed_distance:
                    # Calculate POI score for this node
                    poi_score = self._calculate_node_poi_score(node, poi_preferences)
                    if poi_score > 0:
                        candidate_waypoints.append({
                            'node': node,
                            'detour_distance': detour_dist - direct_distance,
                            'poi_score': poi_score,
                            'total_distance': detour_dist
                        })
            except nx.NetworkXNoPath:
                continue
        
        if not candidate_waypoints:
            return None
        
        # Sort by POI score and select best waypoint within distance limit
        candidate_waypoints.sort(key=lambda x: x['poi_score'], reverse=True)
        
        for waypoint in candidate_waypoints[:3]:  # Try top 3 candidates
            try:
                waypoint_route = (nx.shortest_path(self.graph, start_node, waypoint['node'], weight='poi_weight') +
                                 nx.shortest_path(self.graph, waypoint['node'], end_node, weight='poi_weight')[1:])
                
                waypoint_time = self.calculate_route_time(waypoint_route)
                waypoint_distance = sum(self.graph[waypoint_route[i]][waypoint_route[i+1]].get('length', 0) 
                                      for i in range(len(waypoint_route) - 1))
                
                if waypoint_distance <= max_allowed_distance:
                    return {
                        'route': waypoint_route,
                        'time': waypoint_time,
                        'distance': waypoint_distance
                    }
                
            except nx.NetworkXNoPath:
                continue
        
        return None
    
    def _find_aggressive_viewpoint_trail(self, start_node: int, end_node: int, max_allowed_distance: float, 
                                        poi_preferences: Dict[str, float]) -> Optional[Dict]:
        """Aggressively seek viewpoints within distance constraints"""
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
            
        # Find nearest nodes for each viewpoint
        viewpoint_nodes = []
        for poi in viewpoint_pois:
            try:
                nearest_node = ox.distance.nearest_nodes(self.graph, X=poi['lng'], Y=poi['lat'], return_dist=False)
                # Check if viewpoint is reachable within distance constraints
                try:
                    dist_from_start = nx.shortest_path_length(self.graph, start_node, nearest_node, weight='length')
                    dist_to_end = nx.shortest_path_length(self.graph, nearest_node, end_node, weight='length')
                    total_dist = dist_from_start + dist_to_end
                    
                    # Only consider viewpoints that fit within deviation limit
                    if total_dist <= max_allowed_distance:
                        viewpoint_nodes.append({
                            'node': nearest_node,
                            'poi': poi,
                            'detour_cost': total_dist - nx.shortest_path_length(self.graph, start_node, end_node, weight='length'),
                            'total_dist': total_dist
                        })
                except nx.NetworkXNoPath:
                    continue
            except Exception:
                continue
        
        if not viewpoint_nodes:
            return None
            
        # Sort viewpoints by priority: named peaks/viewpoints first, then by detour cost
        def viewpoint_priority(vp):
            poi = vp['poi']
            attrs = poi.get('attributes', {})
            
            if attrs.get('natural') == 'peak' and attrs.get('name'):
                return (0, vp['detour_cost'])
            elif attrs.get('name') and attrs.get('name') != 'Unnamed':
                return (1, vp['detour_cost'])
            elif attrs.get('natural') == 'peak':
                return (2, vp['detour_cost'])
            else:
                return (3, vp['detour_cost'])
        
        viewpoint_nodes.sort(key=viewpoint_priority)
        
        # Try to build routes through multiple viewpoints within distance limit
        best_route = None
        best_viewpoint_count = 0
        
        # Try different combinations, starting with fewer viewpoints for distance constraints
        for num_viewpoints in range(min(3, len(viewpoint_nodes)), 0, -1):
            for i in range(min(2, len(viewpoint_nodes) - num_viewpoints + 1)):
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
                    
                    # Check if route fits distance constraints
                    if route_distance > max_allowed_distance:
                        continue
                    
                    # Find POIs along this route
                    route_pois = self._find_pois_along_route(route_segments, radius=200.0)
                    viewpoint_count = len([poi for poi in route_pois if poi.get('category') == 'viewpoints'])
                    
                    if viewpoint_count > best_viewpoint_count:
                        best_viewpoint_count = viewpoint_count
                        best_route = self._format_route_result(
                            route_segments, 'aggressive_viewpoint_trail', route_time, route_distance, route_pois
                        )
                        
                except (nx.NetworkXNoPath, IndexError, KeyError):
                    continue
                    
            if best_route:  # If we found a good route, don't try fewer viewpoints
                break
        
        return best_route
    
    def _find_aggressive_poi_route(self, start_node: int, end_node: int, target_time: float, 
                                  poi_preferences: Dict[str, float]) -> Optional[Dict]:
        """Aggressively seek POIs by building route through multiple high-priority POIs"""
        # Find all POIs matching the preferred categories
        category_pois = []
        for poi in self.pois:
            if 'lat' not in poi or 'lng' not in poi:
                continue
            category = self._categorize_poi(poi)
            if category and category in poi_preferences and poi_preferences[category] >= 10.0:  # Only high-priority categories
                category_pois.append(poi)
        
        if not category_pois:
            return None
            
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(category_pois)} high-priority POIs for aggressive routing")
        
        # Find nearest nodes for each POI
        poi_nodes = []
        for poi in category_pois:
            poi_name = poi.get('attributes', {}).get('name', 'Unnamed')
            try:
                nearest_node = ox.distance.nearest_nodes(self.graph, X=poi['lng'], Y=poi['lat'], return_dist=False)
                # Check if POI is reachable
                try:
                    dist_from_start = nx.shortest_path_length(self.graph, start_node, nearest_node, weight='length')
                    dist_to_end = nx.shortest_path_length(self.graph, nearest_node, end_node, weight='length')
                    total_dist = dist_from_start + dist_to_end
                    direct_dist = nx.shortest_path_length(self.graph, start_node, end_node, weight='length')
                    
                    detour_factor = total_dist / direct_dist
                    
                    # Allow up to 4x detour for aggressive routing (reduced from 6x for performance)
                    if total_dist <= direct_dist * 4.0:
                        category = self._categorize_poi(poi)
                        preference_score = poi_preferences.get(category, 0)
                        
                        poi_nodes.append({
                            'node': nearest_node,
                            'poi': poi,
                            'category': category,
                            'preference_score': preference_score,
                            'detour_cost': total_dist - direct_dist,
                            'total_dist': total_dist,
                            'name': poi_name
                        })
                except nx.NetworkXNoPath:
                    continue
            except Exception as e:
                continue
        
        if not poi_nodes:
            return None
            
        # Sort POIs by preference score and detour cost
        def poi_priority(poi_node):
            # Priority: preference score (higher first), then lower detour cost
            return (-poi_node['preference_score'], poi_node['detour_cost'])
        
        poi_nodes.sort(key=poi_priority)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(poi_nodes)} reachable high-priority POIs")
        
        # Show top POIs for debugging
        for i, pn in enumerate(poi_nodes[:10]):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] POI {i+1}: {pn['name']} ({pn['category']}) - score: {pn['preference_score']}, detour: {pn['detour_cost']:.0f}m")
        
        # Try to build routes through multiple POIs (maximize POIs, respect time constraints)
        best_route = None
        best_poi_count = 0
        best_quality_score = 0
        
        # Try different combinations of POIs (start with more POIs, work down)
        for num_pois in range(min(len(poi_nodes), 8), 0, -1):  # Try up to 8 POIs maximum (reduced from 15)
            for i in range(min(2, len(poi_nodes) - num_pois + 1)):  # Try 2 different starting positions (reduced from 3)
                try:
                    selected_pois = poi_nodes[i:i+num_pois]
                    
                    # Build route through POIs
                    route_segments = []
                    current_node = start_node
                    
                    planned_names = [pn['name'] for pn in selected_pois]
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Building aggressive route through {num_pois} POIs: {planned_names[:5]}{'...' if len(planned_names) > 5 else ''}")
                    
                    for pn in selected_pois:
                        segment = nx.shortest_path(self.graph, current_node, pn['node'], weight='poi_weight')
                        if len(route_segments) > 0:
                            segment = segment[1:]  # Remove duplicate node
                        route_segments.extend(segment)
                        current_node = pn['node']
                    
                    # Add final segment to end
                    final_segment = nx.shortest_path(self.graph, current_node, end_node, weight='poi_weight')
                    if len(route_segments) > 0:
                        final_segment = final_segment[1:]  # Remove duplicate node
                    route_segments.extend(final_segment)
                    
                    # Calculate route metrics
                    route_time = self.calculate_route_time(route_segments)
                    route_distance = sum(self.graph[route_segments[j]][route_segments[j+1]].get('length', 0) 
                                       for j in range(len(route_segments) - 1))
                    
                    # Check if route fits time constraints (allow up to 1.8x target time for aggressive routes)
                    if target_time and route_time > target_time * 1.8:
                        continue
                    
                    # Check if route respects edge usage constraint (max 2 times per street)
                    if not self._validate_route_edge_usage(route_segments, max_edge_usage=2):
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Route rejected: too much street repetition")
                        continue
                    
                    # Find POIs along this route (use larger radius for POI detection)
                    route_pois = self._find_pois_along_route(route_segments, radius=150.0)
                    
                    # Calculate route quality based on POI categories and preferences
                    quality_score = 0
                    category_counts = {}
                    for poi in route_pois:
                        category = poi.get('category')
                        if category and category in poi_preferences:
                            preference_value = poi_preferences[category]
                            quality_score += preference_value
                            category_counts[category] = category_counts.get(category, 0) + 1
                    
                    total_preferred_pois = sum(category_counts.values())
                    
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Route with {num_pois} planned POIs found {total_preferred_pois} preferred POIs, {route_time:.1f}min, quality: {quality_score:.1f}")
                    
                    # Select best route based on quality score and POI count
                    if quality_score > best_quality_score or (quality_score == best_quality_score and total_preferred_pois > best_poi_count):
                        best_quality_score = quality_score
                        best_poi_count = total_preferred_pois
                        best_route = self._format_route_result(
                            route_segments, 'aggressive_poi', route_time, route_distance, route_pois
                        )
                        
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] NEW BEST aggressive route (quality: {quality_score:.1f}, {total_preferred_pois} POIs)")
                        
                except (nx.NetworkXNoPath, IndexError, KeyError) as e:
                    continue
                    
            if best_route:  # If we found a good route, don't try fewer POIs
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
        
        # Prioritize viewpoints in detailed POIs
        viewpoints = [poi for poi in pois if poi.get('category') == 'viewpoints']
        other_pois = [poi for poi in pois if poi.get('category') != 'viewpoints']
        detailed_pois = viewpoints + other_pois[:max(0, 20 - len(viewpoints))]
        
        return {
            'route_type': route_type,
            'coordinates': coordinates,
            'nodes': route,
            'distance_meters': round(distance, 1),
            'time_minutes': round(time, 1),
            'waypoints': len(route),
            'pois_along_route': len(pois),
            'poi_categories': dict(poi_summary),
            'detailed_pois': detailed_pois,  # Prioritize viewpoints
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
            'restaurants': 25.0,   # Significantly increased to maximize route time
            'cafes': 15.0,         # Increased to find more cafes
            'bars_pubs': 8.0,      # Added to include nightlife options
            'fast_food': 5.0       # Added for more food variety
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
            'tourism': 25.0,       # Significantly increased to maximize route time
            'education': 15.0,     # Increased for cultural sites
            'restaurants': 8.0,    # Increased for meal stops
            'cafes': 5.0,          # Added for cultural café visits 
            'viewpoints': 10.0,    # Added for scenic cultural sites
            'nature': 3.0          # Added for parks and cultural gardens
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
            'shops': 25.0,         # Significantly increased to maximize route time
            'restaurants': 12.0,   # Increased for shopping breaks
            'cafes': 8.0,          # Increased for coffee breaks while shopping
            'bars_pubs': 5.0,      # Added for after-shopping drinks
            'tourism': 3.0,        # Added for shopping areas near attractions
            'transport': 2.0       # Added for public transport convenience
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
            'bars_pubs': 30.0,     # Significantly increased to maximize route time
            'restaurants': 15.0,   # Increased for dinner options
            'fast_food': 8.0,      # Increased for late-night eats
            'cafes': 5.0,          # Added for pre-nightlife coffee
            'tourism': 3.0,        # Added for nightlife near attractions
            'shops': 2.0           # Added for areas with mixed nightlife/shopping
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