# OSM Data Analysis for POI-Based Routing: Comprehensive Study

**Date:** July 28, 2025  
**Analysis Period:** July 2025  
**Study Areas:** Manhattan, NYC (USA) and Ljungsbro (Sweden)

## Executive Summary

This comprehensive analysis examined OpenStreetMap (OSM) data from two distinct geographic regions to evaluate the feasibility of creating point-of-interest (POI) based routing algorithms. Our findings reveal significant differences in data density and composition between urban and suburban/rural environments, with important implications for "fun path" routing implementations.

## Methodology

### Data Collection
- **Enhanced OSM Dump Scripts**: Created comprehensive data extraction tools
- **Walking Network Analysis**: Focused on pedestrian-accessible routes
- **POI Extraction**: Utilized OSMnx to gather amenities, leisure, tourism, and natural features
- **Geographic Coverage**: 2km buffer radius from center points

### Study Areas
1. **Manhattan, NYC**: Urban dense commercial district (40.735°N, -73.990°W)
2. **Ljungsbro, Sweden**: Suburban/rural town environment (58.500°N, 15.493°E)

## Key Findings

### 1. Data Density Comparison

| Metric | Manhattan, NYC | Ljungsbro, Sweden | Ratio |
|--------|----------------|-------------------|-------|
| **Walking Network Nodes** | 9,946 | 1,835 | 5.4:1 |
| **Walking Network Edges** | 31,236 | 5,218 | 6.0:1 |
| **Total POIs** | 22,942 | 575 | 39.9:1 |
| **POI Density** | ~1,835 POIs/km² | ~46 POIs/km² | 40:1 |

### 2. POI Category Distribution

#### Manhattan, NYC (22,942 POIs)
- **Nature Features**: 4,071 (17.7%) - Predominantly individual trees
- **Transport Infrastructure**: 2,652 (11.6%) - Parking, bike facilities
- **Food & Dining**: 3,763 (16.4%) - Diverse restaurants, cafes, chains
- **Recreation**: 1,575 (6.9%) - Parks, fitness centers
- **Commercial**: 1,144 (5.0%) - Retail shops, services

#### Ljungsbro, Sweden (575 POIs)
- **Transport Infrastructure**: 148 (25.7%) - Primarily parking facilities
- **Nature Features**: 106 (18.4%) - Forests, grass areas, water bodies
- **Recreation**: 39 (6.8%) - Playgrounds, sports facilities
- **Education**: 14 (2.4%) - Schools, kindergartens
- **Food & Dining**: 11 (1.9%) - Local restaurants, cafes

### 3. Nature Feature Analysis

#### Manhattan Nature (4,071 features)
- Individual street trees (3,310 - 81.3%)
- Small urban gardens and parks
- Limited natural water features
- High urban forest canopy

#### Swedish Nature (106 features)
- **Forest Areas**: 41 (38.7%) - Large woodland patches
- **Grass Areas**: 38 (35.8%) - Open meadows and parks
- **Water Features**: 19 (17.9%) - Natural lakes and streams
- **Individual Trees**: 8 (7.5%) - Notable specimens

### 4. Food & Dining Ecosystem

#### Manhattan (3,763 establishments)
**Restaurants (1,530)**:
- Italian: 123 establishments
- Chinese: 84 establishments  
- Pizza: 78 establishments
- Japanese: 74 establishments

**Fast Food (687)**:
- Dunkin': 36 locations
- Chipotle: 21 locations
- McDonald's: 17 locations

**Cafes (641)**:
- Starbucks: 56 locations
- Independent coffee shops: 500+ locations

#### Sweden (11 establishments)
- Local pizzerias: Pizzeria Ciao Ciao, Pizzeria Venus
- Traditional restaurants: Tre Bröder (regional cuisine)
- Nordic chains: ICA Nära (2), Hemköp (1)
- Ice cream: Ljungsbro Glass & Café

## POI-Based Routing Algorithm Design

### 1. Basic POI-Weighted Routing

```python
def calculate_poi_weighted_route(graph, start, end, poi_data, preferences):
    """
    Calculate route with POI influence on edge weights
    """
    # Base routing weights
    for u, v, data in graph.edges(data=True):
        base_weight = data['length']
        poi_bonus = 0
        
        # Find nearby POIs within influence radius (50m)
        nearby_pois = find_pois_near_edge(u, v, poi_data, radius=50)
        
        for poi in nearby_pois:
            category = poi['category']
            if category in preferences:
                # Apply preference multiplier
                poi_bonus += preferences[category] * poi.get('rating', 1.0)
        
        # Lower weight = more attractive path
        final_weight = base_weight / (1 + poi_bonus * 0.1)
        data['poi_weight'] = final_weight
    
    return nx.shortest_path(graph, start, end, weight='poi_weight')
```

### 2. Time-Constrained POI Routing

```python
def time_constrained_poi_route(graph, start, end, target_time_minutes, poi_preferences):
    """
    Generate route that takes approximately target_time while maximizing POI exposure
    """
    # Calculate direct route time
    direct_route = nx.shortest_path(graph, start, end, weight='length')
    direct_time = calculate_route_time(graph, direct_route)
    
    if direct_time >= target_time_minutes:
        return direct_route  # Cannot extend further
    
    # Find detour opportunities
    extra_time_budget = target_time_minutes - direct_time
    
    # Identify high-value POI clusters
    poi_clusters = identify_poi_clusters(poi_data, poi_preferences)
    viable_detours = []
    
    for cluster in poi_clusters:
        detour_time = calculate_detour_time(graph, start, end, cluster['centroid'])
        if detour_time <= extra_time_budget:
            poi_value = sum(poi['value'] for poi in cluster['pois'])
            viable_detours.append({
                'cluster': cluster,
                'time_cost': detour_time,
                'value': poi_value,
                'efficiency': poi_value / detour_time
            })
    
    # Select best detour by efficiency
    viable_detours.sort(key=lambda x: x['efficiency'], reverse=True)
    
    if viable_detours:
        best_detour = viable_detours[0]
        return create_waypoint_route(graph, start, best_detour['cluster']['centroid'], end)
    
    return direct_route
```

### 3. Category-Specific Routing Examples

#### A. Foodie Route (Manhattan)
```python
foodie_preferences = {
    'restaurants': 3.0,
    'cafes': 2.0,
    'fast_food': 1.0,
    'bars_pubs': 2.5
}

# Route from Union Square to Central Park via restaurant district
foodie_route = calculate_poi_weighted_route(
    manhattan_graph, 
    union_square_node, 
    central_park_node,
    manhattan_pois,
    foodie_preferences
)

# Expected result: Route through Little Italy, SoHo restaurant areas
# Estimated additional time: 15-25 minutes
# POI exposure: 45+ restaurants, 12+ cafes
```

#### B. Nature Route (Sweden)
```python
nature_preferences = {
    'nature': 4.0,
    'recreation': 3.0,
    'historic_culture': 2.0
}

# Route emphasizing forest paths and water features
nature_route = calculate_poi_weighted_route(
    swedish_graph,
    ljungsbro_center,
    destination_node,
    swedish_pois,
    nature_preferences
)

# Expected result: Route through forest areas, near lake
# Estimated additional time: 5-10 minutes
# POI exposure: 8+ forest patches, 3+ water features
```

### 4. Time-Based Routing Examples

#### Example 1: 30-Minute Coffee Tour (Manhattan)
```python
coffee_tour = time_constrained_poi_route(
    manhattan_graph,
    start_node=times_square,
    end_node=union_square,
    target_time_minutes=30,
    poi_preferences={'cafes': 5.0, 'restaurants': 1.0}
)

# Expected route characteristics:
# - Direct time: 18 minutes
# - Detour budget: 12 minutes
# - Route: Via Washington Square Park cafe district
# - POI exposure: 8-12 cafes including Starbucks cluster
# - Total time: ~29 minutes
```

#### Example 2: 45-Minute Nature Walk (Sweden)
```python
nature_walk = time_constrained_poi_route(
    swedish_graph,
    start_node=town_center,
    end_node=train_station,
    target_time_minutes=45,
    poi_preferences={'nature': 4.0, 'recreation': 2.0}
)

# Expected route characteristics:
# - Direct time: 15 minutes  
# - Detour budget: 30 minutes
# - Route: Via forest loop and lakeside path
# - POI exposure: 5-8 forest areas, 2-3 water features
# - Total time: ~43 minutes
```

## Implementation Considerations

### 1. POI Influence Radius
- **Urban environments**: 25-50m radius (high density)
- **Rural environments**: 100-200m radius (sparse distribution)
- **Dynamic scaling** based on local POI density

### 2. Preference Weighting Systems
```python
PREFERENCE_SCALES = {
    'urban': {
        'restaurants': 1.0-5.0,
        'cafes': 1.0-4.0,
        'shops': 1.0-3.0,
        'nature': 2.0-6.0  # Higher weight due to scarcity
    },
    'rural': {
        'nature': 1.0-3.0,  # Lower weight due to abundance
        'restaurants': 2.0-8.0,  # Higher weight due to scarcity
        'recreation': 1.0-4.0
    }
}
```

### 3. Performance Optimization
- **Spatial indexing**: Use R-tree or similar for POI proximity queries
- **Preprocessing**: Pre-calculate POI influence on edges
- **Caching**: Store computed routes for common origin-destination pairs
- **Approximation algorithms**: Use for real-time routing with large POI datasets

## Routing Algorithm Performance Estimates

### Manhattan Scenario
- **Graph size**: 9,946 nodes, 31,236 edges
- **POI processing**: ~1-2 seconds for full analysis
- **Route calculation**: 200-500ms with POI weighting
- **Memory usage**: ~15-25MB for full dataset

### Swedish Scenario  
- **Graph size**: 1,835 nodes, 5,218 edges
- **POI processing**: ~100-200ms for full analysis
- **Route calculation**: 50-100ms with POI weighting
- **Memory usage**: ~3-5MB for full dataset

## Conclusions and Recommendations

### 1. Feasibility Assessment
POI-based routing is **highly feasible** with the following considerations:
- Urban areas provide rich commercial POI data for diverse routing preferences
- Rural areas excel in nature-based routing with significant outdoor recreation potential
- OSM data quality is sufficient for production routing applications

### 2. Algorithm Recommendations

#### For Urban Environments (NYC-style):
- **Multi-modal preference systems** supporting food, shopping, culture
- **Dynamic time-based weighting** to account for business hours
- **Crowd-sourced rating integration** for POI quality assessment
- **Real-time updates** for temporary closures/events

#### For Rural Environments (Sweden-style):
- **Nature-focused algorithms** emphasizing scenic routes
- **Seasonal adaptations** for weather-dependent outdoor features
- **Cultural heritage integration** highlighting historic sites
- **Multi-activity routing** combining recreation types

### 3. Technical Implementation Strategy

1. **Preprocessing Pipeline**:
   - Download and parse OSM data for region
   - Extract walking network and POI data
   - Build spatial indices for efficient proximity queries
   - Calculate base POI influence on network edges

2. **Real-time Routing Engine**:
   - Accept user preferences and time constraints
   - Apply POI weighting to network
   - Calculate optimized route using A* or Dijkstra variants
   - Return route with POI annotations and timing estimates

3. **User Interface Considerations**:
   - Preference sliders for different POI categories
   - Time constraint input (minimum/maximum duration)
   - Route preview with POI highlights
   - Alternative route suggestions

### 4. Future Research Opportunities

- **Machine learning integration** for personalized preference learning
- **Multi-objective optimization** balancing time, distance, and POI exposure
- **Social routing** incorporating user reviews and crowd-sourced data
- **Temporal routing** considering time-of-day variations in POI attractiveness
- **Weather integration** for outdoor POI routing

## Data Availability

All analysis scripts, data files, and interactive maps are available in the project directory:
- `enhanced_osm_dump.py` - Comprehensive OSM data extraction
- `analyze_pois.py` - POI categorization and analysis
- `create_poi_map.py` / `create_swedish_poi_map.py` - Interactive visualizations
- Raw data files: `enhanced_osm_dump_*.json`
- Analysis results: `poi_analysis_*.json`
- Interactive maps: `*_poi_map_*.html`

This analysis demonstrates that OSM data provides a robust foundation for implementing sophisticated POI-based routing algorithms, with significant opportunities for creating more engaging and personalized navigation experiences.

---

**Author**: Claude Code Assistant  
**Institution**: Anthropic  
**Contact**: Generated via Claude Code CLI  
**Data Sources**: OpenStreetMap Contributors, OSMnx Library  
**Analysis Tools**: Python, OSMnx, NetworkX, Leaflet.js