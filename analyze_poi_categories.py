#!/usr/bin/env python3
"""
Analyze what POI attributes are being categorized as 'other'
"""

import json
from collections import defaultdict

def analyze_poi_categories(enhanced_osm_file: str):
    """Analyze POI categories to see what's in 'other'"""
    print(f"Loading OSM data from {enhanced_osm_file}...")
    
    with open(enhanced_osm_file, 'r', encoding='utf-8') as f:
        osm_data = json.load(f)
    
    pois = osm_data.get('pois', [])
    print(f"Total POIs: {len(pois)}")
    
    # Track all attribute combinations
    attribute_combos = defaultdict(int)
    categorized_counts = defaultdict(int)
    other_examples = []
    
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
        elif attrs.get('natural') in ['tree', 'water'] or attrs.get('landuse') in ['forest', 'grass']:
            return 'nature'
        
        # Recreation
        elif attrs.get('leisure') in ['park', 'playground', 'sports_centre']:
            return 'recreation'
        
        # Shopping
        elif attrs.get('shop'):
            return 'shops'
        
        # Default
        return 'other'
    
    for poi in pois:
        attrs = poi.get('attributes', {})
        category = categorize_poi(poi)
        categorized_counts[category] += 1
        
        # Track key attributes for analysis
        key_attrs = []
        for key in ['amenity', 'shop', 'leisure', 'natural', 'landuse', 'tourism', 'highway', 'building']:
            if key in attrs:
                key_attrs.append(f"{key}={attrs[key]}")
        
        attr_combo = ", ".join(key_attrs) if key_attrs else "no_key_attributes"
        attribute_combos[attr_combo] += 1
        
        # Collect examples of 'other' category
        if category == 'other' and len(other_examples) < 20:
            other_examples.append({
                'name': attrs.get('name', 'Unnamed'),
                'attributes': attrs
            })
    
    print("\\nCategory counts:")
    for category, count in sorted(categorized_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {category}: {count}")
    
    print("\\nTop attribute combinations:")
    for combo, count in sorted(attribute_combos.items(), key=lambda x: x[1], reverse=True)[:20]:
        print(f"  {count:4d}: {combo}")
    
    print("\\nExamples of 'other' category POIs:")
    for i, example in enumerate(other_examples[:10]):
        print(f"  {i+1}. {example['name']}")
        for key, value in example['attributes'].items():
            if key != 'name':
                print(f"      {key}: {value}")
        print()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python analyze_poi_categories.py <enhanced_osm_file.json>")
        sys.exit(1)
    
    analyze_poi_categories(sys.argv[1])