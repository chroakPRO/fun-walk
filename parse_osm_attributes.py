#!/usr/bin/env python3
"""
Parse OSM dump JSON files to analyze node attributes
Counts all unique attributes and their occurrences, excluding street_count-only nodes
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime

def parse_osm_attributes(json_file):
    """
    Parse OSM JSON file and analyze node attributes
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Parsing OSM data from {json_file}")
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File {json_file} not found")
        return
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON file - {e}")
        return
    
    # Statistics counters
    total_nodes = len(data.get('nodes', []))
    nodes_with_only_street_count = 0
    nodes_with_attributes = 0
    
    # Attribute counters
    attribute_counts = Counter()
    attribute_values = defaultdict(Counter)
    nodes_by_attribute = defaultdict(list)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Analyzing {total_nodes} nodes...")
    
    for node in data.get('nodes', []):
        node_id = node['node_id']
        lat = node['lat']
        lng = node['lng']
        attributes = node.get('attributes', {})
        
        # Skip nodes with only street_count attribute
        if len(attributes) == 1 and 'street_count' in attributes:
            nodes_with_only_street_count += 1
            continue
        
        # Skip empty attributes
        if not attributes:
            continue
        
        nodes_with_attributes += 1
        
        # Count each attribute type
        for attr_name, attr_value in attributes.items():
            if attr_name != 'street_count':  # Ignore street_count as requested
                attribute_counts[attr_name] += 1
                attribute_values[attr_name][attr_value] += 1
                nodes_by_attribute[attr_name].append({
                    'node_id': node_id,
                    'lat': lat,
                    'lng': lng,
                    'value': attr_value
                })
    
    # Print summary statistics
    print(f"\n{'='*60}")
    print(f"OSM NODE ATTRIBUTE ANALYSIS")
    print(f"{'='*60}")
    print(f"Total nodes: {total_nodes:,}")
    print(f"Nodes with only 'street_count': {nodes_with_only_street_count:,}")
    print(f"Nodes with interesting attributes: {nodes_with_attributes:,}")
    print(f"Unique attribute types found: {len(attribute_counts)}")
    
    if not attribute_counts:
        print("\nNo interesting attributes found (all nodes only have street_count)")
        return
    
    # Print attribute frequency table
    print(f"\n{'ATTRIBUTE FREQUENCY':<30} {'COUNT':<10} {'PERCENTAGE'}")
    print(f"{'-'*55}")
    for attr_name, count in attribute_counts.most_common():
        percentage = (count / nodes_with_attributes) * 100
        print(f"{attr_name:<30} {count:<10} {percentage:>8.1f}%")
    
    # Print detailed breakdown for each attribute
    print(f"\n{'='*60}")
    print(f"DETAILED ATTRIBUTE BREAKDOWN")
    print(f"{'='*60}")
    
    for attr_name, count in attribute_counts.most_common():
        print(f"\n{attr_name.upper()} (found in {count} nodes):")
        print(f"{'-'*40}")
        
        # Show value distribution
        values = attribute_values[attr_name]
        print("Values and their frequencies:")
        for value, freq in values.most_common(10):  # Show top 10 values
            percentage = (freq / count) * 100
            print(f"  {value:<25} {freq:>5} ({percentage:>5.1f}%)")
        
        if len(values) > 10:
            print(f"  ... and {len(values) - 10} more values")
        
        # Show sample nodes with this attribute
        sample_nodes = nodes_by_attribute[attr_name][:3]  # Show 3 sample nodes
        print(f"\nSample nodes with '{attr_name}' attribute:")
        for node in sample_nodes:
            print(f"  Node {node['node_id']} at ({node['lat']:.6f}, {node['lng']:.6f}) = '{node['value']}'")
    
    # Save detailed report to file
    report_filename = f"osm_attribute_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_filename, 'w', encoding='utf-8') as f:
        f.write(f"OSM Node Attribute Analysis Report\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Source: {json_file}\n")
        f.write(f"{'='*60}\n\n")
        
        f.write(f"SUMMARY:\n")
        f.write(f"Total nodes: {total_nodes:,}\n")
        f.write(f"Nodes with only 'street_count': {nodes_with_only_street_count:,}\n")
        f.write(f"Nodes with interesting attributes: {nodes_with_attributes:,}\n")
        f.write(f"Unique attribute types: {len(attribute_counts)}\n\n")
        
        f.write(f"ATTRIBUTE FREQUENCIES:\n")
        for attr_name, count in attribute_counts.most_common():
            percentage = (count / nodes_with_attributes) * 100
            f.write(f"{attr_name}: {count} nodes ({percentage:.1f}%)\n")
        
        f.write(f"\nDETAILED BREAKDOWN:\n")
        f.write(f"{'='*40}\n")
        
        for attr_name, count in attribute_counts.most_common():
            f.write(f"\n{attr_name.upper()}:\n")
            values = attribute_values[attr_name]
            for value, freq in values.most_common():
                percentage = (freq / count) * 100
                f.write(f"  {value}: {freq} ({percentage:.1f}%)\n")
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Detailed report saved to {report_filename}")
    
    return {
        'total_nodes': total_nodes,
        'nodes_with_attributes': nodes_with_attributes,
        'attribute_counts': dict(attribute_counts),
        'attribute_values': {k: dict(v) for k, v in attribute_values.items()}
    }

def main():
    if len(sys.argv) != 2:
        print("Usage: python parse_osm_attributes.py <osm_dump_file.json>")
        print("\nAvailable OSM dump files:")
        import glob
        osm_files = glob.glob("osm_dump_*.json")
        for f in osm_files:
            print(f"  {f}")
        sys.exit(1)
    
    json_file = sys.argv[1]
    result = parse_osm_attributes(json_file)
    
    if result:
        print(f"\nAnalysis complete! Found {len(result['attribute_counts'])} unique attribute types.")

if __name__ == "__main__":
    main()