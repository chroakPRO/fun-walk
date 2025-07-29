#!/usr/bin/env python3
"""
Enhanced OSM data dumper that fetches POIs, amenities, and interesting locations
"""

import osmnx as ox
import json
from datetime import datetime

def fetch_comprehensive_osm_data(lat1, lng1, lat2, lng2, buffer_dist=2000):
    """
    Fetch comprehensive OSM data including POIs and amenities
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching comprehensive OSM data...")
    
    center_lat = (lat1 + lat2) / 2
    center_lng = (lng1 + lng2) / 2
    
    # 1. Get walking network
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching walking network...")
    G = ox.graph_from_point((center_lat, center_lng), dist=buffer_dist, network_type='walk', simplify=True)
    
    # 2. Get POIs and amenities
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching Points of Interest...")
    
    # Define interesting POI tags
    useful_tags = {
        'amenity': True,          # restaurants, cafes, shops, etc.
        'leisure': True,          # parks, playgrounds, sports
        'tourism': True,          # attractions, viewpoints, hotels
        'historic': True,         # monuments, buildings
        'natural': True,          # parks, water features, trees
        'landuse': ['recreation_ground', 'forest', 'grass', 'meadow', 'orchard', 'vineyard'],
        'shop': True,             # all types of shops
        'craft': True,            # breweries, workshops
        'office': True,           # offices, coworking spaces
        'public_transport': True, # transit stops
        'railway': True,          # train stations
        'waterway': True,         # rivers, streams
        'barrier': ['hedge', 'wall', 'fence'],  # landscape features
        'building': ['church', 'cathedral', 'mosque', 'synagogue', 'temple']  # religious buildings
    }
    
    try:
        # Get geometries (points, polygons) for POIs
        pois = ox.features_from_point(
            (center_lat, center_lng), 
            tags=useful_tags, 
            dist=buffer_dist
        )
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(pois)} POIs")
        
        # Convert POIs to serializable format
        poi_data = []
        for idx, row in pois.iterrows():
            poi_info = {
                'osm_id': idx[1] if isinstance(idx, tuple) else idx,
                'osm_type': idx[0] if isinstance(idx, tuple) else 'unknown',
                'geometry_type': str(row.geometry.geom_type),
                'attributes': {}
            }
            
            # Extract coordinates
            if row.geometry.geom_type == 'Point':
                poi_info['lat'] = row.geometry.y
                poi_info['lng'] = row.geometry.x
            elif hasattr(row.geometry, 'centroid'):
                poi_info['lat'] = row.geometry.centroid.y
                poi_info['lng'] = row.geometry.centroid.x
            
            # Extract all non-geometric attributes
            for col, val in row.items():
                if col != 'geometry' and pd.notna(val):
                    if isinstance(val, (list, dict)):
                        poi_info['attributes'][col] = str(val)
                    else:
                        poi_info['attributes'][col] = val
            
            poi_data.append(poi_info)
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error fetching POIs: {e}")
        poi_data = []
    
    # 3. Extract network data (same as before)
    nodes_data = []
    for node_id, node_attrs in G.nodes(data=True):
        node_info = {
            'node_id': node_id,
            'lat': node_attrs['y'],
            'lng': node_attrs['x'],
            'attributes': {}
        }
        
        for key, value in node_attrs.items():
            if key not in ['y', 'x']:
                node_info['attributes'][key] = str(value) if value is not None else None
        
        nodes_data.append(node_info)
    
    edges_data = []
    for u, v, edge_attrs in G.edges(data=True):
        edge_info = {
            'from_node': u,
            'to_node': v,
            'attributes': {}
        }
        
        for key, value in edge_attrs.items():
            if hasattr(value, '__geo_interface__'):
                edge_info['attributes'][key] = str(value)
            elif isinstance(value, (list, dict)):
                edge_info['attributes'][key] = str(value)
            elif value is not None:
                try:
                    json.dumps(value)
                    edge_info['attributes'][key] = value
                except (TypeError, ValueError):
                    edge_info['attributes'][key] = str(value)
            else:
                edge_info['attributes'][key] = None
        
        edges_data.append(edge_info)
    
    # Compile enhanced dataset
    enhanced_data = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'bounding_box': {
                'point1': {'lat': lat1, 'lng': lng1},
                'point2': {'lat': lat2, 'lng': lng2},
                'center': {'lat': center_lat, 'lng': center_lng}
            },
            'buffer_distance': buffer_dist,
            'total_nodes': len(nodes_data),
            'total_edges': len(edges_data),
            'total_pois': len(poi_data)
        },
        'nodes': nodes_data,
        'edges': edges_data,
        'pois': poi_data
    }
    
    # Save enhanced data
    filename = f"enhanced_osm_dump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(enhanced_data, f, indent=2, ensure_ascii=False)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Enhanced data saved to {filename}")
    print(f"Summary:")
    print(f"  - Network nodes: {len(nodes_data)}")
    print(f"  - Network edges: {len(edges_data)}")
    print(f"  - Points of Interest: {len(poi_data)}")
    
    # Show POI breakdown
    if poi_data:
        poi_types = {}
        for poi in poi_data:
            attrs = poi['attributes']
            # Find the most relevant attribute
            for key in ['amenity', 'leisure', 'tourism', 'shop', 'natural', 'historic']:
                if key in attrs:
                    poi_type = f"{key}={attrs[key]}"
                    poi_types[poi_type] = poi_types.get(poi_type, 0) + 1
                    break
        
        print(f"\nTop POI types found:")
        for poi_type, count in sorted(poi_types.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {poi_type}: {count}")
    
    return filename

if __name__ == "__main__":
    import pandas as pd  # Need pandas for POI processing
    
    # Swedish coordinates (Gothenburg area)
    lat1, lng1 = 57.68140618468316, 11.91668846971801
    lat2, lng2 = 57.72910760054658, 11.978299956994352
    
    fetch_comprehensive_osm_data(lat1, lng1, lat2, lng2)