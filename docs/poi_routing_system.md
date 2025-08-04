# POI-Based Routing System Documentation

## Overview

This system generates walking routes in Gothenburg, Sweden that prioritize Points of Interest (POIs) rather than just finding the shortest path. It's designed to create scenic, interesting routes that visit viewpoints, peaks, restaurants, shops, and other attractions.

## System Architecture

### 1. Data Generation: `enhanced_osm_dump.py`

This script extracts and processes OpenStreetMap data for a specific geographic area:

**What it does:**
- Downloads OSM data for Gothenburg area (coordinates: 57.68-57.73°N, 11.92-11.98°E)
- Extracts 44,769 POIs including restaurants, viewpoints, shops, nature features
- Builds a walking/cycling network graph with 15,070 nodes and 40,534 edges
- Saves processed data to `enhanced_osm_dump_YYYYMMDD_HHMMSS.json`

**Key features:**
- Filters for walkable paths (footways, paths, tracks, roads)
- Extracts comprehensive POI data with attributes
- Creates spatial indexing for efficient routing

### 2. Route Generation: `poi_routing_engine.py`

The main routing engine that creates intelligent, POI-aware walking routes.

## Core Features

### POI Categorization System

POIs are automatically categorized into:
- **Viewpoints** - Tourist viewpoints, peaks, summits (highest priority for nature routes)
- **Restaurants** - All types of dining establishments  
- **Shops** - Retail stores and shopping locations
- **Nature** - Parks, forests, water features, green spaces
- **Transport** - Bus stops, train stations, parking
- **Recreation** - Sports facilities, leisure venues
- **Tourism** - Hotels, attractions, museums
- **Education** - Schools, universities, libraries
- **Bars/Pubs** - Drinking establishments
- **Cafes** - Coffee shops and cafes
- **Fast Food** - Quick service restaurants

### Route Types Generated

1. **Restaurant Route** - Prioritizes dining establishments
2. **Tourism & Culture Route** - Focuses on cultural attractions and viewpoints
3. **Shopping Route** - Emphasizes retail and commercial areas
4. **Nightlife Route** - Targets bars, pubs, and entertainment
5. **Nature & Recreation Route** - Prioritizes natural areas, viewpoints, and peaks

### Advanced Routing Algorithms

#### Standard POI-Weighted Routing
- Applies attraction weights to graph edges near POIs
- Uses larger influence radius for viewpoint routes (100m vs 50m)
- Prefers walking paths over roads for nature routes

#### Aggressive Viewpoint Routing (Key Innovation)
When a nature route has fewer than 5 viewpoints, the system activates aggressive viewpoint-seeking:

**How it works:**
1. **Identifies all reachable viewpoints** within 4x detour distance
2. **Prioritizes by importance:**
   - **Priority 1:** Named peaks with elevation data (e.g., Ramberget)
   - **Priority 2:** Named viewpoints 
   - **Priority 3:** Unnamed peaks
   - **Priority 4:** Generic viewpoints
3. **Builds multi-viewpoint routes** through combinations of up to 6 planned viewpoints
4. **Selects routes with maximum viewpoint count** even if they exceed target time

#### Time Extension Algorithm
If routes are shorter than target time:
- Finds strategic waypoints that add interesting detours
- Extends routes to approximately match target walking time
- Balances efficiency with POI coverage

## Recent Key Changes Made

### 1. Fixed Aggressive Route Selection Logic
**Problem:** Aggressive routes with more viewpoints weren't being selected due to POI data structure issues.

**Solution:** Modified `_format_route_result()` to prioritize viewpoints in `detailed_pois` array:
```python
# Prioritize viewpoints in detailed POIs
viewpoints = [poi for poi in pois if poi.get('category') == 'viewpoints']
other_pois = [poi for poi in pois if poi.get('category') != 'viewpoints']
detailed_pois = viewpoints + other_pois[:max(0, 20 - len(viewpoints))]
```

### 2. Implemented Viewpoint Prioritization
**Problem:** Named peaks like Ramberget were ignored in favor of closer, less interesting viewpoints.

**Solution:** Added intelligent sorting that prioritizes:
- Named peaks with elevation data (like Ramberget) get highest priority
- Named viewpoints get high priority  
- Proximity is secondary to landmark importance

### 3. Enhanced Path Preference for Nature Routes
Nature routes now heavily favor walking paths over car roads:
```python
if highway_type in ['path', 'footway', 'track', 'bridleway']:
    path_multiplier = 0.3  # Much more attractive
elif highway_type in ['primary', 'secondary', 'tertiary', 'trunk']:
    path_multiplier = 3.0  # Much less attractive
```

## Usage

### Basic Usage
```bash
python poi_routing_engine.py enhanced_osm_dump_YYYYMMDD_HHMMSS.json 180
```
- First argument: Enhanced OSM data file
- Second argument: Target walking time in minutes

### Output Files
- **HTML Visualization:** Interactive map showing all 5 routes with different colors
- **JSON Data:** Complete route data with coordinates, POIs, and metadata

## Example Results

### Before Improvements (Regular Route)
- **Viewpoints:** 2
- **Time:** 180.8 minutes
- **Distance:** 13,560m
- **Missing:** Ramberget peak

### After Improvements (Aggressive Viewpoint Route)
- **Viewpoints:** 11 (including Ramberget as #1 priority)
- **Time:** 258.9 minutes (4.3 hours)
- **Distance:** 19,421m
- **Includes:** Named peaks, scenic viewpoints, natural paths

## Technical Implementation

### Spatial Indexing
- Grid-based spatial index for efficient POI proximity queries
- Configurable influence radius (50m standard, 100m for viewpoints)

### Graph Processing
- Uses NetworkX for shortest path calculations
- OSMnx for OpenStreetMap data processing
- Haversine distance calculations for geographic accuracy

### Route Optimization
- Multi-objective optimization balancing:
  - POI coverage and interest
  - Route length and time
  - Path quality (prefer walking paths)
  - Landmark importance

## Configuration

### Viewpoint Priority Weights
- **Viewpoints:** 30.0x priority (extremely high)
- **Nature:** 8.0x priority
- **Recreation:** 4.0x priority
- **Tourism:** 1.0x priority

### Route Constraints
- Maximum detour factor: 4.0x direct distance
- Time tolerance: 60% over target for scenic routes
- Maximum planned viewpoints: 6 per route

This system successfully balances algorithmic efficiency with human preferences for interesting, scenic routes that visit notable landmarks like peaks and viewpoints.