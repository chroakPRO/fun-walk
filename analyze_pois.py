#!/usr/bin/env python3
"""
Analyze POIs from enhanced OSM data - restaurants, food, shops, etc.
Creates detailed statistics, maps, and exports for further analysis
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
import math

def calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two points in meters using Haversine formula"""
    R = 6371000  # Earth's radius in meters
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = (math.sin(delta_lat/2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def analyze_pois(json_file):
    """
    Comprehensive POI analysis with statistics and categorization
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Analyzing POIs from {json_file}")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    pois = data.get('pois', [])
    center_lat = data['metadata']['bounding_box']['center']['lat']
    center_lng = data['metadata']['bounding_box']['center']['lng']
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(pois)} POIs to analyze")
    
    # Categorize POIs
    categories = {
        'restaurants': [],
        'fast_food': [],
        'cafes': [],
        'bars_pubs': [],
        'food_other': [],
        'shops': [],
        'entertainment': [],
        'recreation': [],
        'transport': [],
        'accommodation': [],
        'healthcare': [],
        'education': [],
        'nature': [],
        'historic_culture': [],
        'services': [],
        'other': []
    }
    
    # Define category mappings
    category_mappings = {
        'restaurants': [
            ('amenity', 'restaurant'),
            ('amenity', 'food_court'),
            ('amenity', 'biergarten')
        ],
        'fast_food': [
            ('amenity', 'fast_food'),
            ('amenity', 'ice_cream')
        ],
        'cafes': [
            ('amenity', 'cafe'),
            ('amenity', 'pub'),
            ('shop', 'coffee')
        ],
        'bars_pubs': [
            ('amenity', 'bar'),
            ('amenity', 'pub'),
            ('amenity', 'nightclub')
        ],
        'food_other': [
            ('shop', 'bakery'),
            ('shop', 'butcher'),
            ('shop', 'deli'),
            ('shop', 'greengrocer'),
            ('shop', 'supermarket'),
            ('shop', 'convenience'),
            ('shop', 'alcohol'),
            ('shop', 'beverages')
        ],
        'shops': [
            ('shop', 'clothes'),
            ('shop', 'shoes'),
            ('shop', 'jewelry'),
            ('shop', 'books'),
            ('shop', 'electronics'),
            ('shop', 'furniture'),
            ('shop', 'gift'),
            ('shop', 'art'),
            ('shop', 'beauty'),
            ('shop', 'hairdresser')
        ],
        'entertainment': [
            ('amenity', 'cinema'),
            ('amenity', 'theatre'),
            ('amenity', 'arts_centre'),
            ('tourism', 'museum'),
            ('tourism', 'gallery')
        ],
        'recreation': [
            ('leisure', 'park'),
            ('leisure', 'garden'),
            ('leisure', 'playground'),
            ('leisure', 'sports_centre'),
            ('leisure', 'fitness_centre'),
            ('leisure', 'swimming_pool')
        ],
        'transport': [
            ('amenity', 'parking'),
            ('amenity', 'bicycle_parking'),
            ('public_transport', 'stop_position'),
            ('railway', 'station'),
            ('highway', 'bus_stop')
        ],
        'accommodation': [
            ('tourism', 'hotel'),
            ('tourism', 'hostel'),
            ('tourism', 'guest_house')
        ],
        'healthcare': [
            ('amenity', 'hospital'),
            ('amenity', 'clinic'),
            ('amenity', 'pharmacy'),
            ('amenity', 'dentist'),
            ('amenity', 'veterinary')
        ],
        'education': [
            ('amenity', 'school'),
            ('amenity', 'university'),
            ('amenity', 'library'),
            ('amenity', 'kindergarten')
        ],
        'nature': [
            ('natural', 'tree'),
            ('natural', 'water'),
            ('natural', 'park'),
            ('landuse', 'forest'),
            ('landuse', 'grass')
        ],
        'historic_culture': [
            ('historic', 'monument'),
            ('historic', 'memorial'),
            ('historic', 'building'),
            ('tourism', 'attraction'),
            ('tourism', 'viewpoint')
        ],
        'services': [
            ('amenity', 'bank'),
            ('amenity', 'atm'),
            ('amenity', 'post_office'),
            ('office', 'government'),
            ('office', 'lawyer')
        ]
    }
    
    # Categorize each POI
    for poi in pois:
        attrs = poi.get('attributes', {})
        categorized = False
        
        # Add distance from center
        if 'lat' in poi and 'lng' in poi:
            poi['distance_from_center'] = calculate_distance(
                center_lat, center_lng, poi['lat'], poi['lng']
            )
        
        # Try to categorize
        for category, mappings in category_mappings.items():
            for attr_key, attr_value in mappings:
                if attrs.get(attr_key) == attr_value:
                    categories[category].append(poi)
                    categorized = True
                    break
            if categorized:
                break
        
        if not categorized:
            categories['other'].append(poi)
    
    # Generate comprehensive statistics
    print(f"\n{'='*80}")
    print(f"POI ANALYSIS REPORT")
    print(f"{'='*80}")
    print(f"Total POIs analyzed: {len(pois):,}")
    print(f"Area center: {center_lat:.6f}, {center_lng:.6f}")
    
    # Category breakdown
    print(f"\nCATEGORY BREAKDOWN:")
    print(f"{'-'*50}")
    for category, poi_list in categories.items():
        if poi_list:
            percentage = (len(poi_list) / len(pois)) * 100
            print(f"{category.replace('_', ' ').title():<20} {len(poi_list):>6} ({percentage:>5.1f}%)")
    
    # Detailed analysis for food categories
    food_categories = ['restaurants', 'fast_food', 'cafes', 'bars_pubs', 'food_other']
    
    print(f"\n{'='*80}")
    print(f"DETAILED FOOD & DINING ANALYSIS")
    print(f"{'='*80}")
    
    for category in food_categories:
        poi_list = categories[category]
        if not poi_list:
            continue
            
        print(f"\n{category.upper().replace('_', ' ')} ({len(poi_list)} locations):")
        print(f"{'-'*60}")
        
        # Analyze attributes
        cuisines = Counter()
        names = Counter()
        brands = Counter()
        
        sample_locations = []
        
        for poi in poi_list:
            attrs = poi.get('attributes', {})
            
            # Extract interesting attributes
            if 'cuisine' in attrs:
                cuisines[attrs['cuisine']] += 1
            if 'name' in attrs and attrs['name'] != '':
                names[attrs['name']] += 1
            if 'brand' in attrs:
                brands[attrs['brand']] += 1
            
            # Create sample entry
            sample_locations.append({
                'name': attrs.get('name', 'Unnamed'),
                'cuisine': attrs.get('cuisine', 'Unknown'),
                'brand': attrs.get('brand', ''),
                'address': attrs.get('addr:street', ''),
                'lat': poi.get('lat', 0),
                'lng': poi.get('lng', 0),
                'distance': poi.get('distance_from_center', 0)
            })
        
        # Show top cuisines
        if cuisines:
            print("Top cuisines:")
            for cuisine, count in cuisines.most_common(10):
                print(f"  {cuisine:<20} {count:>3}")
        
        # Show popular chains/brands
        if brands:
            print("Popular chains/brands:")
            for brand, count in brands.most_common(10):
                print(f"  {brand:<20} {count:>3}")
        
        # Show sample locations
        print("Sample locations:")
        sample_locations.sort(key=lambda x: x['distance'])
        for loc in sample_locations[:5]:
            distance_str = f"{loc['distance']:.0f}m" if loc['distance'] > 0 else "center"
            cuisine_str = f" ({loc['cuisine']})" if loc['cuisine'] != 'Unknown' else ""
            print(f"  {loc['name'][:30]:<30}{cuisine_str:<15} {distance_str:>8}")
    
    # Geographic distribution analysis
    print(f"\n{'='*80}")
    print(f"GEOGRAPHIC DISTRIBUTION")
    print(f"{'='*80}")
    
    # Divide area into grid for density analysis
    grid_size = 4  # 4x4 grid
    lat_min = min(poi['lat'] for poi in pois if 'lat' in poi)
    lat_max = max(poi['lat'] for poi in pois if 'lat' in poi)
    lng_min = min(poi['lng'] for poi in pois if 'lng' in poi)
    lng_max = max(poi['lng'] for poi in pois if 'lng' in poi)
    
    lat_step = (lat_max - lat_min) / grid_size
    lng_step = (lng_max - lng_min) / grid_size
    
    grid_counts = defaultdict(int)
    grid_categories = defaultdict(Counter)
    
    for poi in pois:
        if 'lat' not in poi or 'lng' not in poi:
            continue
            
        grid_lat = int((poi['lat'] - lat_min) / lat_step)
        grid_lng = int((poi['lng'] - lng_min) / lng_step)
        grid_lat = min(grid_lat, grid_size - 1)
        grid_lng = min(grid_lng, grid_size - 1)
        
        grid_key = (grid_lat, grid_lng)
        grid_counts[grid_key] += 1
        
        # Find POI category
        for category, poi_list in categories.items():
            if poi in poi_list:
                grid_categories[grid_key][category] += 1
                break
    
    print("POI density by area (grid):")
    for lat_idx in range(grid_size):
        row = ""
        for lng_idx in range(grid_size):
            count = grid_counts.get((lat_idx, lng_idx), 0)
            row += f"{count:>6}"
        print(f"  {row}")
    
    # Export detailed data
    export_data = {
        'metadata': {
            'analysis_timestamp': datetime.now().isoformat(),
            'source_file': json_file,
            'total_pois': len(pois),
            'center_coordinates': [center_lat, center_lng]
        },
        'category_summary': {cat: len(poi_list) for cat, poi_list in categories.items()},
        'detailed_categories': {}
    }
    
    # Export detailed category data
    for category, poi_list in categories.items():
        if poi_list:
            export_data['detailed_categories'][category] = []
            for poi in poi_list:
                poi_export = {
                    'osm_id': poi.get('osm_id'),
                    'lat': poi.get('lat'),
                    'lng': poi.get('lng'),
                    'distance_from_center': poi.get('distance_from_center', 0),
                    'attributes': poi.get('attributes', {})
                }
                export_data['detailed_categories'][category].append(poi_export)
    
    # Save export
    export_filename = f"poi_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(export_filename, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Detailed analysis exported to {export_filename}")
    
    return export_data

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analyze_pois.py <enhanced_osm_dump_file.json>")
        import glob
        enhanced_files = glob.glob("enhanced_osm_dump_*.json")
        if enhanced_files:
            print("\nAvailable enhanced OSM files:")
            for f in enhanced_files:
                print(f"  {f}")
        sys.exit(1)
    
    result = analyze_pois(sys.argv[1])
    print(f"\nPOI analysis complete!")