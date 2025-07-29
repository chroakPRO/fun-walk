#!/usr/bin/env python3
"""
Debug viewpoints and peaks to see why they're not being selected
"""

import json

def debug_viewpoints(enhanced_osm_file: str):
    """Debug viewpoints and peaks"""
    print(f"Loading OSM data from {enhanced_osm_file}...")
    
    with open(enhanced_osm_file, 'r', encoding='utf-8') as f:
        osm_data = json.load(f)
    
    pois = osm_data.get('pois', [])
    
    # Find all viewpoints and peaks
    viewpoints = []
    peaks = []
    
    for poi in pois:
        if 'lat' not in poi or 'lng' not in poi:
            continue
            
        attrs = poi.get('attributes', {})
        
        # Check for viewpoints
        if (attrs.get('tourism') == 'viewpoint' or 
            'viewpoint' in str(attrs.get('type', '')).lower()):
            viewpoints.append(poi)
        
        # Check for peaks
        if (attrs.get('natural') in ['peak', 'summit'] or
            'peak' in str(attrs.get('type', '')).lower()):
            peaks.append(poi)
    
    print(f"\nFound {len(viewpoints)} viewpoints and {len(peaks)} peaks")
    
    print("\nViewpoints:")
    for i, vp in enumerate(viewpoints):
        name = vp['attributes'].get('name', 'Unnamed')
        print(f"  {i+1}. {name} at ({vp['lat']:.6f}, {vp['lng']:.6f})")
        print(f"     Attributes: {vp['attributes']}")
    
    print("\nPeaks:")
    for i, peak in enumerate(peaks):
        name = peak['attributes'].get('name', 'Unnamed')
        print(f"  {i+1}. {name} at ({peak['lat']:.6f}, {peak['lng']:.6f})")
        print(f"     Attributes: {peak['attributes']}")
    
    # Check what the categorization function would return
    def categorize_poi(poi: dict) -> str:
        attrs = poi.get('attributes', {})
        if (attrs.get('tourism') == 'viewpoint' or 
            attrs.get('natural') in ['peak', 'summit'] or
            'viewpoint' in str(attrs.get('type', '')).lower() or
            'peak' in str(attrs.get('type', '')).lower()):
            return 'viewpoints'
        return 'other'
    
    print("\nCategorization check:")
    all_viewpoint_pois = viewpoints + peaks
    for poi in all_viewpoint_pois:
        category = categorize_poi(poi)
        name = poi['attributes'].get('name', 'Unnamed')
        print(f"  {name}: {category}")
    
    return all_viewpoint_pois

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python debug_viewpoints.py <enhanced_osm_file.json>")
        sys.exit(1)
    
    debug_viewpoints(sys.argv[1])