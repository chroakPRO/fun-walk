#!/usr/bin/env python3
"""
Test script for the new generate_trail function
"""

from poi_routing_engine import POIRoutingEngine


def test_trail_generation():
    """Test the generate_trail function with different scenarios"""
    
    # Initialize engine (you'll need to provide your OSM data file)
    # This is just an example - replace with your actual OSM data file
    osm_file = "enhanced_osm_data.json"  # Replace with your actual file
    
    try:
        engine = POIRoutingEngine(osm_file)
    except FileNotFoundError:
        print("Please provide the path to your OSM data file in the test script")
        return
    
    # Test coordinates (Swedish coordinates from your existing code)
    start_lat, start_lng = 57.685, 11.920   # Southwest area
    end_lat, end_lng = 57.725, 11.975       # Northeast area
    
    print("Testing generate_trail function")
    print("=" * 50)
    
    # Test 1: Basic trail with no POI preferences (should return direct route)
    print("\n1. Basic trail (no POI preferences):")
    result1 = engine.generate_trail(start_lat, start_lng, end_lat, end_lng)
    print(f"   Distance: {result1['distance_meters']:.0f}m")
    print(f"   Time: {result1['time_minutes']:.1f} minutes")
    print(f"   Route type: {result1['route_type']}")
    
    # Test 2: Nature trail with 40% deviation allowance
    print("\n2. Nature trail (40% deviation):")
    result2 = engine.generate_trail(
        start_lat, start_lng, end_lat, end_lng,
        poi_preferences={
            'viewpoints': 30.0,
            'nature': 8.0,
            'recreation': 4.0
        },
        deviation_factor=0.4
    )
    print(f"   Distance: {result2['distance_meters']:.0f}m")
    print(f"   Time: {result2['time_minutes']:.1f} minutes")
    print(f"   Route type: {result2['route_type']}")
    print(f"   POIs found: {result2['pois_along_route']}")
    if result2['poi_categories']:
        print(f"   Categories: {result2['poi_categories']}")
    
    # Test 3: Restaurant trail with 60% deviation allowance
    print("\n3. Restaurant trail (60% deviation):")
    result3 = engine.generate_trail(
        start_lat, start_lng, end_lat, end_lng,
        poi_preferences={
            'restaurants': 25.0,
            'cafes': 15.0,
            'bars_pubs': 8.0
        },
        deviation_factor=0.6
    )
    print(f"   Distance: {result3['distance_meters']:.0f}m")
    print(f"   Time: {result3['time_minutes']:.1f} minutes")
    print(f"   Route type: {result3['route_type']}")
    print(f"   POIs found: {result3['pois_along_route']}")
    if result3['poi_categories']:
        print(f"   Categories: {result3['poi_categories']}")
    
    # Test 4: Strict trail with only 20% deviation allowance
    print("\n4. Strict trail (20% deviation):")
    result4 = engine.generate_trail(
        start_lat, start_lng, end_lat, end_lng,
        poi_preferences={
            'viewpoints': 30.0,
            'nature': 8.0
        },
        deviation_factor=0.2
    )
    print(f"   Distance: {result4['distance_meters']:.0f}m")
    print(f"   Time: {result4['time_minutes']:.1f} minutes")
    print(f"   Route type: {result4['route_type']}")
    print(f"   POIs found: {result4['pois_along_route']}")
    
    print("\n" + "=" * 50)
    print("Trail generation tests completed!")
    
    # Show comparison
    direct_distance = result1['distance_meters']
    print(f"\nComparison (direct route = {direct_distance:.0f}m):")
    for i, result in enumerate([result1, result2, result3, result4], 1):
        deviation = ((result['distance_meters'] - direct_distance) / direct_distance) * 100
        print(f"  Test {i}: {result['distance_meters']:.0f}m ({deviation:+.1f}% deviation)")


if __name__ == "__main__":
    test_trail_generation()