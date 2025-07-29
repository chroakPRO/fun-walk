#!/usr/bin/env python3
"""
Analyze edge attributes in OSM data to find interesting location information
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime

def analyze_edge_attributes(json_file):
    """
    Analyze OSM edge attributes for interesting location data
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Analyzing edge attributes from {json_file}")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    edges = data.get('edges', [])
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(edges)} edges to analyze")
    
    # Count all attribute types
    attribute_counts = Counter()
    attribute_values = defaultdict(Counter)
    interesting_edges = []
    
    # Define interesting attributes that might indicate fun locations
    interesting_attrs = [
        'name', 'leisure', 'tourism', 'natural', 'landuse', 'amenity', 
        'shop', 'historic', 'waterway', 'barrier', 'surface', 'access',
        'bicycle', 'foot', 'park', 'garden', 'forest'
    ]
    
    for edge in edges:
        attrs = edge.get('attributes', {})
        
        has_interesting = False
        edge_info = {
            'from_node': edge['from_node'],
            'to_node': edge['to_node'],
            'interesting_attrs': {}
        }
        
        for attr_name, attr_value in attrs.items():
            attribute_counts[attr_name] += 1
            attribute_values[attr_name][str(attr_value)] += 1
            
            # Check if this is an interesting attribute
            if attr_name.lower() in interesting_attrs or any(interesting in attr_name.lower() for interesting in ['park', 'nature', 'water', 'green']):
                has_interesting = True
                edge_info['interesting_attrs'][attr_name] = attr_value
        
        if has_interesting:
            interesting_edges.append(edge_info)
    
    print(f"\n{'='*80}")
    print(f"EDGE ATTRIBUTE ANALYSIS")
    print(f"{'='*80}")
    print(f"Total edges: {len(edges):,}")
    print(f"Total unique attributes: {len(attribute_counts)}")
    print(f"Edges with potentially interesting attributes: {len(interesting_edges)}")
    
    # Show most common attributes
    print(f"\nMOST COMMON EDGE ATTRIBUTES:")
    print(f"{'-'*50}")
    for attr, count in attribute_counts.most_common(20):
        percentage = (count / len(edges)) * 100
        print(f"{attr:<25} {count:>8} ({percentage:>5.1f}%)")
    
    # Show interesting attributes in detail
    print(f"\nINTERESTING ATTRIBUTES FOUND:")
    print(f"{'-'*50}")
    
    for attr in interesting_attrs:
        if attr in attribute_counts:
            count = attribute_counts[attr]
            print(f"\n{attr.upper()} (found in {count} edges):")
            values = attribute_values[attr]
            for value, freq in values.most_common(10):
                print(f"  {value:<30} {freq:>5}")
    
    # Show sample interesting edges
    if interesting_edges:
        print(f"\nSAMPLE INTERESTING EDGES:")
        print(f"{'-'*50}")
        for i, edge in enumerate(interesting_edges[:10]):
            print(f"\nEdge {i+1}: {edge['from_node']} -> {edge['to_node']}")
            for attr, value in edge['interesting_attrs'].items():
                print(f"  {attr}: {value}")
    
    # Look for specific location types
    location_types = {
        'parks': [],
        'water_features': [],
        'trails': [],
        'named_places': [],
        'recreational': []
    }
    
    for edge in edges:
        attrs = edge.get('attributes', {})
        
        # Parks and green spaces
        if any(key in attrs for key in ['leisure', 'landuse']) or 'park' in str(attrs).lower():
            location_types['parks'].append(edge)
        
        # Water features
        if 'waterway' in attrs or 'water' in str(attrs).lower():
            location_types['water_features'].append(edge)
        
        # Trails and paths
        highway = attrs.get('highway', '')
        if highway in ['footway', 'path', 'track', 'cycleway']:
            location_types['trails'].append(edge)
        
        # Named places
        if 'name' in attrs and attrs['name'] not in ['', 'None']:
            location_types['named_places'].append(edge)
        
        # Recreational areas
        if attrs.get('leisure') or attrs.get('tourism') or attrs.get('amenity'):
            location_types['recreational'].append(edge)
    
    print(f"\nLOCATION TYPE SUMMARY:")
    print(f"{'-'*50}")
    for loc_type, edges_list in location_types.items():
        print(f"{loc_type.replace('_', ' ').title():<20} {len(edges_list):>6} edges")
        
        # Show samples
        if edges_list:
            print("  Samples:")
            for edge in edges_list[:3]:
                attrs = edge.get('attributes', {})
                name = attrs.get('name', 'unnamed')
                highway = attrs.get('highway', 'unknown')
                print(f"    {name} ({highway})")
    
    return {
        'total_edges': len(edges),
        'interesting_edges': len(interesting_edges),
        'location_types': {k: len(v) for k, v in location_types.items()},
        'top_attributes': dict(attribute_counts.most_common(20))
    }

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analyze_edge_attributes.py <osm_dump_file.json>")
        sys.exit(1)
    
    result = analyze_edge_attributes(sys.argv[1])
    print(f"\nAnalysis complete!")