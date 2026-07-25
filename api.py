#!/usr/bin/env python3
"""
FastAPI backend for Fun Path Planner
Uses the working OSMnx routing engine
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Set, Tuple, Literal
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from threading import Lock
import osmnx as ox
import networkx as nx
import math
import os
import sqlite3
import time
from datetime import datetime
import requests
from PIL import Image
from rasterio.errors import RasterioError


def load_backend_environment() -> None:
    """Load local backend-only settings without evaluating shell syntax."""
    env_path = Path(__file__).resolve().with_name('.env')
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


load_backend_environment()

from vegetation import NMD_SOURCE, nmd_available, sample_vegetation_structure

app = FastAPI(title="Fun Path Planner API", version="1.0.0")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

class Coordinate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)

class RouteRequest(BaseModel):
    start: Coordinate
    end: Coordinate
    buffer_dist: int = Field(default=5000, ge=1000, le=20000)
    route_type: Literal['all', 'fastest', 'balanced', 'scenic', 'nature', 'shopping'] = 'scenic'

class PathTypeStats(BaseModel):
    distance: float
    time: float
    speed: float
    description: str

class SurfaceTypeStats(BaseModel):
    distance: float
    time: float
    speed_modifier: float
    description: str

class SpecialAreaStats(BaseModel):
    distance: float
    time: float
    description: str

class RouteSegmentStats(BaseModel):
    length: float
    time: float
    path_type: str
    surface_type: str
    speed: float
    features: List[str]
    name: str

class RouteStats(BaseModel):
    distance: float
    fun_weight: float
    fun_score: float
    estimated_time: float
    waypoints: int
    path_types: Dict[str, PathTypeStats]
    surface_types: Dict[str, SurfaceTypeStats]
    special_areas: Dict[str, SpecialAreaStats]
    segments: List[RouteSegmentStats]
    avg_speed: float
    node_type_distribution: Dict[str, int]

class Route(BaseModel):
    name: str
    description: str
    route: List[Coordinate]  # Changed from 'coordinates' to 'route' to match frontend
    stats: RouteStats
    color: str
    priority: str

class RouteResponse(BaseModel):
    routes: List[Route]
    success: bool
    message: Optional[str] = None

class AddressSearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 5

class AddressResult(BaseModel):
    display_name: str
    lat: float
    lng: float
    place_id: str
    importance: float

class AddressSearchResponse(BaseModel):
    results: List[AddressResult]
    success: bool
    message: Optional[str] = None

class TreeCoverPoint(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)

class TreeCoverRequest(BaseModel):
    points: List[TreeCoverPoint] = Field(min_length=1, max_length=80)
    sample_radius_meters: int = Field(default=35, ge=10, le=80)

class TreeCoverResult(BaseModel):
    id: str
    tree_cover_percent: float
    dense_cover_percent: float
    valid_pixel_percent: float

class TreeCoverResponse(BaseModel):
    results: List[TreeCoverResult]
    source: str = 'Copernicus Tree Cover Density 10m'
    cache_hits: int = 0
    cdse_points_fetched: int = 0
    cdse_requests: int = 0

class VegetationStructureRequest(BaseModel):
    points: List[TreeCoverPoint] = Field(min_length=1, max_length=80)
    sample_radius_meters: int = Field(default=35, ge=10, le=80)

class VegetationStructureResult(BaseModel):
    id: str
    low_vegetation_percent: float
    tall_vegetation_percent: float
    valid_pixel_percent: float

class VegetationStructureResponse(BaseModel):
    available: bool
    results: List[VegetationStructureResult]
    source: str = NMD_SOURCE
    cache_hits: int = 0

FUN_ROUTE_MAX_DETOUR = 1.45
BALANCED_ROUTE_MAX_DETOUR = 1.25
PARK_ROUTE_MAX_DETOUR = 1.60
SHOPPING_ROUTE_MAX_DETOUR = 1.40
MAX_ROUTE_OVERLAP = 0.75
DIVERSE_EDGE_PENALTY = 2.8
MAX_SCENIC_ANCHORS = 12
CONTEXT_FETCH_LIMIT_METERS = 12000

CDSE_TOKEN_URL = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
CDSE_PROCESS_URL = 'https://sh.dataspace.copernicus.eu/api/v1/process'
CDSE_TREE_COVER_COLLECTION = 'byoc-3751d55a-7370-4071-9543-493ec3341d16'
CDSE_PIXEL_SIZE_METERS = 10
TREE_COVER_CACHE_VERSION = 'tcd-10m-v1'
TREE_COVER_CACHE_PATH = Path(os.environ.get(
    'TREE_COVER_CACHE_PATH',
    str(Path(os.environ.get('OSMNX_CACHE_FOLDER', Path(__file__).resolve().with_name('cache'))) / 'tree_cover.sqlite3'),
))
_cdse_token: Optional[str] = None
_cdse_token_expires_at = 0.0
_cdse_token_lock = Lock()
_tree_cover_request_lock = Lock()


def get_cdse_access_token() -> str:
    global _cdse_token, _cdse_token_expires_at
    now = time.time()
    if _cdse_token and now < _cdse_token_expires_at - 60:
        return _cdse_token

    with _cdse_token_lock:
        now = time.time()
        if _cdse_token and now < _cdse_token_expires_at - 60:
            return _cdse_token

        client_id = os.environ.get('CDSE_CLIENT_ID')
        client_secret = os.environ.get('CDSE_CLIENT_SECRET')
        if not client_id or not client_secret:
            raise RuntimeError('CDSE credentials are not configured in the backend environment.')

        response = requests.post(
            CDSE_TOKEN_URL,
            data={
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': client_secret,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        _cdse_token = payload['access_token']
        _cdse_token_expires_at = now + int(payload.get('expires_in', 1800))
        return _cdse_token


def fetch_tree_cover_from_cdse(points: List[TreeCoverPoint], sample_radius_meters: int) -> List[TreeCoverResult]:
    mean_lat = sum(point.lat for point in points) / len(points)
    latitude_padding = 70 / 110_540
    longitude_scale = max(1, 111_320 * math.cos(math.radians(mean_lat)))
    longitude_padding = 70 / longitude_scale
    min_lat = min(point.lat for point in points) - latitude_padding
    max_lat = max(point.lat for point in points) + latitude_padding
    min_lng = min(point.lng for point in points) - longitude_padding
    max_lng = max(point.lng for point in points) + longitude_padding

    width_meters = max((max_lng - min_lng) * longitude_scale, 160)
    height_meters = max((max_lat - min_lat) * 110_540, 160)
    width = min(1024, max(16, math.ceil(width_meters / CDSE_PIXEL_SIZE_METERS)))
    height = min(1024, max(16, math.ceil(height_meters / CDSE_PIXEL_SIZE_METERS)))
    request_body = {
        'input': {
            'bounds': {
                'bbox': [min_lng, min_lat, max_lng, max_lat],
                'properties': {'crs': 'http://www.opengis.net/def/crs/OGC/1.3/CRS84'},
            },
            'data': [{
                'type': CDSE_TREE_COVER_COLLECTION,
                'dataFilter': {
                    'timeRange': {
                        'from': '2020-01-01T00:00:00Z',
                        'to': f'{datetime.utcnow().year}-12-31T23:59:59Z',
                    },
                    'mosaickingOrder': 'mostRecent',
                },
            }],
        },
        'output': {
            'width': width,
            'height': height,
            'responses': [{'identifier': 'default', 'format': {'type': 'image/png'}}],
        },
        'evalscript': '''//VERSION=3
function setup() {
  return { input: ["TCD", "dataMask"], output: { bands: 2, sampleType: "UINT8" } };
}
function evaluatePixel(sample) { return [sample.TCD, sample.dataMask * 255]; }
''',
    }

    response = requests.post(
        CDSE_PROCESS_URL,
        json=request_body,
        headers={'Authorization': f'Bearer {get_cdse_access_token()}'},
        timeout=45,
    )
    response.raise_for_status()
    image = Image.open(BytesIO(response.content)).convert('LA')
    pixels = image.load()
    pixel_width_meters = width_meters / image.width
    pixel_height_meters = height_meters / image.height
    radius_x = max(1, math.ceil(sample_radius_meters / pixel_width_meters))
    radius_y = max(1, math.ceil(sample_radius_meters / pixel_height_meters))

    results: List[TreeCoverResult] = []
    for point in points:
        center_x = round((point.lng - min_lng) / (max_lng - min_lng) * (image.width - 1))
        center_y = round((max_lat - point.lat) / (max_lat - min_lat) * (image.height - 1))
        cover_values: List[int] = []
        total_pixels = 0
        for y in range(max(0, center_y - radius_y), min(image.height, center_y + radius_y + 1)):
            for x in range(max(0, center_x - radius_x), min(image.width, center_x + radius_x + 1)):
                offset_x = (x - center_x) * pixel_width_meters
                offset_y = (y - center_y) * pixel_height_meters
                if math.hypot(offset_x, offset_y) > sample_radius_meters:
                    continue
                total_pixels += 1
                cover, valid = pixels[x, y]
                if valid:
                    cover_values.append(int(cover))

        valid_percent = len(cover_values) / total_pixels * 100 if total_pixels else 0
        mean_cover = sum(cover_values) / len(cover_values) if cover_values else 0
        dense_cover = sum(value >= 60 for value in cover_values) / len(cover_values) * 100 if cover_values else 0
        results.append(TreeCoverResult(
            id=point.id,
            tree_cover_percent=round(mean_cover, 1),
            dense_cover_percent=round(dense_cover, 1),
            valid_pixel_percent=round(valid_percent, 1),
        ))
    return results


def tree_cover_cache_key(point: TreeCoverPoint, sample_radius_meters: int) -> str:
    # Five decimal places is roughly one metre in Sweden, well below the 10 m source resolution.
    return f'{TREE_COVER_CACHE_VERSION}:{point.lat:.5f}:{point.lng:.5f}:{sample_radius_meters}'


def read_tree_cover_cache(
    points: List[TreeCoverPoint],
    sample_radius_meters: int,
) -> Dict[str, Tuple[float, float, float]]:
    keys = list(dict.fromkeys(tree_cover_cache_key(point, sample_radius_meters) for point in points))
    if not keys:
        return {}
    try:
        TREE_COVER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(TREE_COVER_CACHE_PATH, timeout=10) as connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS tree_cover_cache (
                    cache_key TEXT PRIMARY KEY,
                    tree_cover_percent REAL NOT NULL,
                    dense_cover_percent REAL NOT NULL,
                    valid_pixel_percent REAL NOT NULL,
                    created_at REAL NOT NULL
                )
            ''')
            placeholders = ','.join('?' for _ in keys)
            rows = connection.execute(
                f'''SELECT cache_key, tree_cover_percent, dense_cover_percent, valid_pixel_percent
                    FROM tree_cover_cache WHERE cache_key IN ({placeholders})''',
                keys,
            ).fetchall()
        return {row[0]: (float(row[1]), float(row[2]), float(row[3])) for row in rows}
    except (OSError, sqlite3.Error) as error:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Tree-cover cache read failed: {error}")
        return {}


def write_tree_cover_cache(
    entries: Dict[str, Tuple[float, float, float]],
) -> None:
    if not entries:
        return
    try:
        TREE_COVER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        with sqlite3.connect(TREE_COVER_CACHE_PATH, timeout=10) as connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS tree_cover_cache (
                    cache_key TEXT PRIMARY KEY,
                    tree_cover_percent REAL NOT NULL,
                    dense_cover_percent REAL NOT NULL,
                    valid_pixel_percent REAL NOT NULL,
                    created_at REAL NOT NULL
                )
            ''')
            connection.executemany(
                '''INSERT OR REPLACE INTO tree_cover_cache
                   (cache_key, tree_cover_percent, dense_cover_percent, valid_pixel_percent, created_at)
                   VALUES (?, ?, ?, ?, ?)''',
                [(key, *values, now) for key, values in entries.items()],
            )
    except (OSError, sqlite3.Error) as error:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Tree-cover cache write failed: {error}")


def fetch_tree_cover_cached(
    points: List[TreeCoverPoint],
    sample_radius_meters: int,
) -> Tuple[List[TreeCoverResult], int, int]:
    cached = read_tree_cover_cache(points, sample_radius_meters)
    initial_cache_keys = set(cached)
    missing_by_key = {
        tree_cover_cache_key(point, sample_radius_meters): point
        for point in points
        if tree_cover_cache_key(point, sample_radius_meters) not in cached
    }

    if missing_by_key:
        # Serialize misses and re-check inside the lock so simultaneous identical searches
        # result in one CDSE Process request instead of consuming quota twice.
        with _tree_cover_request_lock:
            refreshed = read_tree_cover_cache(list(missing_by_key.values()), sample_radius_meters)
            cached.update(refreshed)
            still_missing = {
                key: point for key, point in missing_by_key.items() if key not in cached
            }
            if still_missing:
                missing_points = list(still_missing.values())
                fetched = fetch_tree_cover_from_cdse(missing_points, sample_radius_meters)
                new_entries = {
                    key: (
                        result.tree_cover_percent,
                        result.dense_cover_percent,
                        result.valid_pixel_percent,
                    )
                    for key, result in zip(still_missing, fetched)
                }
                write_tree_cover_cache(new_entries)
                cached.update(new_entries)

    results = []
    for point in points:
        values = cached[tree_cover_cache_key(point, sample_radius_meters)]
        results.append(TreeCoverResult(
            id=point.id,
            tree_cover_percent=values[0],
            dense_cover_percent=values[1],
            valid_pixel_percent=values[2],
        ))
    cache_hits = sum(
        tree_cover_cache_key(point, sample_radius_meters) in initial_cache_keys
        for point in points
    )
    return results, cache_hits, len(missing_by_key) - len(refreshed if missing_by_key else {})

CONTEXT_FEATURE_TAGS = {
    'leisure': ['park', 'garden', 'nature_reserve'],
    'landuse': ['forest', 'grass', 'meadow', 'recreation_ground'],
    'natural': ['wood', 'water', 'bay', 'coastline'],
    'waterway': True,
    'tourism': ['viewpoint', 'attraction'],
    'historic': True,
}

SHOPPING_FEATURE_TAGS = {
    'shop': True,
    'amenity': ['marketplace', 'cafe', 'restaurant', 'fast_food', 'bar', 'pub'],
}

CONTEXT_FEATURE_CONFIG = {
    'park': {'score': 0.22, 'radius': 35.0},
    'nature_reserve': {'score': 0.30, 'radius': 45.0},
    'forest': {'score': 0.22, 'radius': 35.0},
    'green_area': {'score': 0.12, 'radius': 25.0},
    'water': {'score': 0.18, 'radius': 80.0},
    'viewpoint': {'score': 0.30, 'radius': 120.0},
    'attraction': {'score': 0.16, 'radius': 60.0},
    'historic': {'score': 0.14, 'radius': 50.0},
    'shopping': {'score': 0.28, 'radius': 55.0},
    'food': {'score': 0.18, 'radius': 65.0},
}

PATH_TYPE_INFO = {
    'sidewalk': {'speed': 5.0, 'description': 'Sidewalks and roadside walkways'},
    'footway': {'speed': 4.5, 'description': 'Dedicated walkways'},
    'pedestrian': {'speed': 4.5, 'description': 'Pedestrian streets'},
    'path': {'speed': 4.0, 'description': 'Natural trails and paths'},
    'track': {'speed': 3.8, 'description': 'Tracks and forest roads'},
    'cycleway': {'speed': 4.5, 'description': 'Shared cycle and walking paths'},
    'steps': {'speed': 2.8, 'description': 'Stairs and stepped paths'},
    'residential': {'speed': 4.8, 'description': 'Residential streets'},
    'service': {'speed': 4.4, 'description': 'Service roads and access paths'},
    'major_road': {'speed': 4.7, 'description': 'Larger roads with pedestrian access'},
    'other': {'speed': 4.0, 'description': 'Other walkable paths'},
}

SURFACE_TYPE_INFO = {
    'paved': {'speed_modifier': 1.0, 'description': 'Paved surfaces'},
    'gravel': {'speed_modifier': 0.90, 'description': 'Gravel and compacted surfaces'},
    'unpaved': {'speed_modifier': 0.85, 'description': 'Unpaved natural surfaces'},
    'grass': {'speed_modifier': 0.75, 'description': 'Grass and soft ground'},
    'sand': {'speed_modifier': 0.65, 'description': 'Sand and loose surfaces'},
    'wood': {'speed_modifier': 0.95, 'description': 'Wooden boardwalks and bridges'},
    'cobblestone': {'speed_modifier': 0.80, 'description': 'Cobblestone or uneven paving'},
    'unknown': {'speed_modifier': 0.90, 'description': 'Unknown surface type'},
}

HIGHWAY_FUN_COST = {
    # A path type is only a modest prior. Nearby scenery and road exposure
    # decide whether a particular segment is actually enjoyable.
    'sidewalk': 0.98,
    'footway': 0.84,
    'pedestrian': 0.82,
    'track': 0.82,
    'path': 0.88,
    'cycleway': 0.96,
    'steps': 1.12,
    'residential': 1.20,
    'service': 1.28,
    'major_road': 1.85,
    'other': 1.25,
}

SURFACE_FUN_COST = {
    'paved': 1.03,
    'gravel': 0.94,
    'unpaved': 0.96,
    'grass': 1.02,
    'sand': 1.18,
    'wood': 0.96,
    'cobblestone': 1.14,
    'unknown': 1.04,
}

def fetch_graph(start, end, buffer_dist=5000, route_type: str = 'scenic'):
    """
    Fetch walking network using OSMnx (same as original script)
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching walking network...")
    start_time = time.time()
    
    mid = ((start.lat + end.lat) / 2, (start.lng + end.lng) / 2)
    straight_line_distance = _haversine_meters(start.lat, start.lng, end.lat, end.lng)
    effective_buffer = max(buffer_dist, int(straight_line_distance / 2) + 1200)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Center point: {mid[0]:.4f}, {mid[1]:.4f}")
    
    G = ox.graph_from_point(mid, dist=effective_buffer, network_type='walk', simplify=True)
    enrich_graph_with_context(G, mid, effective_buffer, include_shopping=route_type in {'shopping', 'all'})
    
    elapsed = time.time() - start_time
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Graph fetched in {elapsed:.2f}s - {len(G.nodes)} nodes, {len(G.edges)} edges")
    return G

def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

def _context_tags_for_feature(feature: Dict[str, Any]) -> Set[str]:
    tags = set()
    if _has_tag(feature, 'leisure', {'park', 'garden'}):
        tags.add('park')
    if _has_tag(feature, 'leisure', {'nature_reserve'}):
        tags.add('nature_reserve')
    if _has_tag(feature, 'landuse', {'forest'}) or _has_tag(feature, 'natural', {'wood'}):
        tags.add('forest')
    if _has_tag(feature, 'landuse', {'grass', 'meadow', 'recreation_ground'}):
        tags.add('green_area')
    if _has_tag(feature, 'natural', {'water', 'bay', 'coastline'}) or _has_meaningful_value(feature, 'waterway'):
        tags.add('water')
    if _has_tag(feature, 'tourism', {'viewpoint'}):
        tags.add('viewpoint')
    if _has_tag(feature, 'tourism', {'attraction'}):
        tags.add('attraction')
    if _has_meaningful_value(feature, 'historic'):
        tags.add('historic')
    if _has_meaningful_value(feature, 'shop') or _has_tag(feature, 'amenity', {'marketplace'}):
        tags.add('shopping')
    if _has_tag(feature, 'amenity', {'cafe', 'restaurant', 'fast_food', 'bar', 'pub'}):
        tags.add('food')
    return tags

def enrich_graph_with_context(
    G,
    center: Tuple[float, float],
    fetch_distance: int,
    include_shopping: bool = False,
) -> None:
    """
    Add nearby non-road OSM features to edge metadata.

    OSM normally maps a path and the park, waterfront, or landmark beside it as
    separate objects. Without this spatial join, route scoring cannot see most
    of the things a walker experiences along the path.
    """
    try:
        from shapely.ops import unary_union

        context_distance = min(fetch_distance, CONTEXT_FETCH_LIMIT_METERS)
        feature_tags = dict(CONTEXT_FEATURE_TAGS)
        if include_shopping:
            feature_tags.update(SHOPPING_FEATURE_TAGS)
        features = ox.features_from_point(
            center,
            tags=feature_tags,
            dist=context_distance,
        )
        if features.empty:
            return

        edge_gdf = ox.graph_to_gdfs(G, nodes=False, fill_edge_geometry=True)
        projected_edges = ox.project_gdf(edge_gdf)
        projected_features = features.to_crs(projected_edges.crs)

        geometries_by_tag = defaultdict(list)
        for _, feature in projected_features.iterrows():
            geometry = feature.get('geometry')
            if geometry is None or geometry.is_empty:
                continue
            for tag in _context_tags_for_feature(feature):
                geometries_by_tag[tag].append(geometry)

        influenced_edges = set()
        for tag, geometries in geometries_by_tag.items():
            config = CONTEXT_FEATURE_CONFIG[tag]
            combined_geometry = unary_union(geometries)
            distances = projected_edges.geometry.distance(combined_geometry)
            nearby = distances[distances <= config['radius']]

            for edge_key, distance in nearby.items():
                if not isinstance(edge_key, tuple) or len(edge_key) != 3:
                    continue
                edge = G.edges[edge_key]
                influence = max(0.0, 1.0 - (float(distance) / config['radius']))
                context = edge.setdefault('context_scenery', {})
                context[tag] = max(context.get(tag, 0.0), config['score'] * influence)
                influenced_edges.add(edge_key)

        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] Added nearby scenery context "
            f"to {len(influenced_edges)} edges from {len(features)} OSM features"
        )
    except Exception as error:
        # Routing remains usable when the secondary OSM feature query is down.
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Scenery context unavailable: {error}")

def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item is not None]
    return [value]

def _has_tag(data: Dict[str, Any], key: str, values: Set[str]) -> bool:
    return any(str(value) in values for value in _as_list(data.get(key)))

def _has_meaningful_value(data: Dict[str, Any], key: str) -> bool:
    empty_values = {'', 'none', 'nan', 'false', 'no', '<na>'}
    return any(str(value).strip().lower() not in empty_values for value in _as_list(data.get(key)))

def _first_value(data: Dict[str, Any], key: str, default: str = '') -> str:
    values = _as_list(data.get(key))
    return str(values[0]) if values else default

def _numeric_tag(data: Dict[str, Any], key: str, default: float = 0.0) -> float:
    for value in _as_list(data.get(key)):
        digits = ''.join(character for character in str(value) if character.isdigit() or character == '.')
        try:
            if digits:
                return float(digits)
        except ValueError:
            continue
    return default

def _classify_path_type(data: Dict[str, Any]) -> str:
    highway = _first_value(data, 'highway', 'other')
    footway = _first_value(data, 'footway', '')

    if highway == 'footway' and footway == 'sidewalk':
        return 'sidewalk'
    if highway in {'footway', 'pedestrian', 'path', 'track', 'cycleway', 'steps', 'service'}:
        return highway
    if highway in {'residential', 'living_street', 'unclassified'}:
        return 'residential'
    if highway in {'primary', 'secondary', 'tertiary', 'primary_link', 'secondary_link', 'tertiary_link'}:
        return 'major_road'
    return 'other'

def _classify_surface_type(data: Dict[str, Any]) -> str:
    surface = _first_value(data, 'surface', 'unknown')
    if surface in {'asphalt', 'concrete', 'paved', 'paving_stones', 'sett'}:
        return 'paved'
    if surface in {'gravel', 'fine_gravel', 'compacted', 'pebblestone'}:
        return 'gravel'
    if surface in {'unpaved', 'dirt', 'earth', 'ground', 'mud'}:
        return 'unpaved'
    if surface in {'grass', 'grass_paver'}:
        return 'grass'
    if surface in {'sand'}:
        return 'sand'
    if surface in {'wood', 'boardwalk'}:
        return 'wood'
    if surface in {'cobblestone', 'cobblestone:flattened'}:
        return 'cobblestone'
    return 'unknown'

def _edge_scenery_tags(data: Dict[str, Any]) -> Set[str]:
    tags = set()
    if _has_tag(data, 'leisure', {'park', 'garden', 'nature_reserve'}):
        tags.add('park' if not _has_tag(data, 'leisure', {'nature_reserve'}) else 'nature_reserve')
    if _has_tag(data, 'landuse', {'forest', 'grass', 'meadow', 'recreation_ground'}):
        tags.add('forest' if _has_tag(data, 'landuse', {'forest'}) else 'green_area')
    if _has_tag(data, 'natural', {'wood', 'tree_row'}):
        tags.add('forest')
    if _has_tag(data, 'natural', {'water', 'bay', 'coastline'}) or _has_meaningful_value(data, 'waterway'):
        tags.add('water')
    if _has_tag(data, 'tourism', {'viewpoint'}):
        tags.add('viewpoint')
    if _has_tag(data, 'tourism', {'attraction'}):
        tags.add('attraction')
    if _has_meaningful_value(data, 'historic'):
        tags.add('historic')
    if _has_tag(data, 'scenic', {'yes'}) or 'scenic' in _first_value(data, 'name', '').lower():
        tags.add('scenic')
    for tag, score in data.get('context_scenery', {}).items():
        if score > 0.02:
            tags.add(tag)
    return tags

def _edge_scenery_score(data: Dict[str, Any]) -> float:
    contributions = []
    direct_data = dict(data)
    direct_data.pop('context_scenery', None)
    direct_tags = _edge_scenery_tags(direct_data)
    tags = direct_tags | set(data.get('context_scenery', {}))
    direct_scores = {
        'park': 0.22,
        'nature_reserve': 0.30,
        'forest': 0.22,
        'green_area': 0.12,
        'water': 0.18,
        'viewpoint': 0.30,
        'attraction': 0.16,
        'historic': 0.14,
        'scenic': 0.18,
        'shopping': 0.28,
        'food': 0.18,
    }
    context = data.get('context_scenery', {})
    for tag in tags:
        direct_score = direct_scores.get(tag, 0.0) if tag in direct_tags else 0.0
        contributions.append(max(direct_score, context.get(tag, 0.0)))

    # Combine independent features with diminishing returns. This rewards a
    # wooded waterfront more than either feature alone without creating nearly
    # free edges that make the route spiral through one highly tagged area.
    remaining_cost = 1.0
    for contribution in contributions:
        remaining_cost *= 1.0 - min(max(contribution, 0.0), 0.40)
    return min(1.0 - remaining_cost, 0.52)

def _edge_shopping_score(data: Dict[str, Any], path_type: Optional[str] = None) -> float:
    """Measure useful retail and lively-street context around an edge."""
    context = data.get('context_scenery', {})
    score = context.get('shopping', 0.0)
    score += context.get('food', 0.0) * 0.75
    score += context.get('attraction', 0.0) * 0.45
    score += context.get('historic', 0.0) * 0.25

    path_type = path_type or _classify_path_type(data)
    if path_type == 'pedestrian':
        score += 0.16
    elif path_type in {'sidewalk', 'footway'}:
        score += 0.05
    return min(score, 0.58)

def _edge_safety_factor(data: Dict[str, Any], path_type: str) -> float:
    factor = 1.0
    sidewalk = _first_value(data, 'sidewalk', '')
    highway = _first_value(data, 'highway', '')
    max_speed = _numeric_tag(data, 'maxspeed')
    lanes = _numeric_tag(data, 'lanes', 1.0)

    if _has_tag(data, 'access', {'private', 'no'}) or _has_tag(data, 'foot', {'no', 'private'}):
        factor *= 25.0

    if path_type in {'residential', 'service'} and sidewalk in {'no', 'none'}:
        factor *= 1.12
    elif path_type == 'major_road':
        factor *= 1.15 if sidewalk in {'both', 'left', 'right', 'yes', 'separate'} else 1.75
    elif highway in {'trunk', 'trunk_link', 'motorway', 'motorway_link'}:
        factor *= 4.0

    if path_type in {'residential', 'service', 'major_road', 'other'}:
        if max_speed >= 70:
            factor *= 1.35
        elif max_speed >= 50:
            factor *= 1.18
        if lanes >= 4:
            factor *= 1.22

    if _has_tag(data, 'tunnel', {'yes', 'building_passage'}) and not _has_tag(data, 'lit', {'yes'}):
        factor *= 1.30
    if _has_tag(data, 'smoothness', {'very_bad', 'horrible', 'very_horrible', 'impassable'}):
        factor *= 1.35
    if _has_tag(data, 'sac_scale', {'demanding_mountain_hiking', 'alpine_hiking', 'demanding_alpine_hiking'}):
        factor *= 1.50

    return factor

def _edge_fun_factor(data: Dict[str, Any]) -> float:
    path_type = _classify_path_type(data)
    surface_type = _classify_surface_type(data)
    highway_cost = HIGHWAY_FUN_COST.get(path_type, HIGHWAY_FUN_COST['other'])
    surface_cost = SURFACE_FUN_COST.get(surface_type, SURFACE_FUN_COST['unknown'])
    safety_cost = _edge_safety_factor(data, path_type)
    scenery_discount = 1.0 - _edge_scenery_score(data)
    return max(0.35, min(highway_cost * surface_cost * safety_cost * scenery_discount, 4.0))

def _edge_pair(u, v) -> Tuple[Any, Any]:
    return (u, v) if str(u) <= str(v) else (v, u)

def _edge_data_options(G, u, v) -> List[Dict[str, Any]]:
    edge_data = G.get_edge_data(u, v)
    if not edge_data:
        return []
    if all(isinstance(value, dict) for value in edge_data.values()):
        return list(edge_data.values())
    return [edge_data]

def _select_edge_data(G, u, v, selected_weight: str = 'length') -> Dict[str, Any]:
    options = _edge_data_options(G, u, v)
    if not options:
        return {}
    return min(options, key=lambda data: data.get(selected_weight, data.get('length', 0)))

def _route_edges_with_data(G, route: List[Any], selected_weight: str = 'length'):
    for i in range(len(route) - 1):
        u, v = route[i], route[i + 1]
        data = _select_edge_data(G, u, v, selected_weight)
        if data:
            yield u, v, data

def _route_distance(G, route: List[Any], selected_weight: str = 'length') -> float:
    return sum(data.get('length', 0) for _, _, data in _route_edges_with_data(G, route, selected_weight))

def _route_key(route: List[Any]) -> Tuple[Any, ...]:
    return tuple(route)

def _route_edge_pairs(route: List[Any]) -> Set[Tuple[Any, Any]]:
    return {_edge_pair(route[i], route[i + 1]) for i in range(len(route) - 1)}

def _route_overlap_ratio(G, route: List[Any], existing_routes: List[List[Any]], selected_weight: str = 'length') -> float:
    if not existing_routes or len(route) < 2:
        return 0.0

    candidate_distance = 0.0
    candidate_edges = []
    for u, v, data in _route_edges_with_data(G, route, selected_weight):
        length = data.get('length', 0)
        candidate_distance += length
        candidate_edges.append((_edge_pair(u, v), length))

    if candidate_distance <= 0:
        return 0.0

    max_overlap = 0.0
    for existing in existing_routes:
        existing_pairs = _route_edge_pairs(existing)
        shared_distance = sum(length for pair, length in candidate_edges if pair in existing_pairs)
        max_overlap = max(max_overlap, shared_distance / candidate_distance)
    return max_overlap

def _route_quality_score(G, route: List[Any], direct_distance: float, selected_weight: str = 'length') -> float:
    """Score actual route experience, with mild costs for detours and repetition."""
    total_distance = 0.0
    weighted_enjoyment = 0.0
    feature_distance = defaultdict(float)
    edge_usage = defaultdict(int)
    edge_lengths = {}

    for u, v, data in _route_edges_with_data(G, route, selected_weight):
        length = float(data.get('length', 0))
        fun_factor = float(data.get('fun_factor', _edge_fun_factor(data)))
        enjoyment = max(0.0, min((1.75 - fun_factor) / 1.40, 1.0))
        total_distance += length
        weighted_enjoyment += length * enjoyment
        pair = _edge_pair(u, v)
        edge_usage[pair] += 1
        edge_lengths[pair] = max(edge_lengths.get(pair, 0.0), length)
        for feature in _edge_scenery_tags(data):
            feature_distance[feature] += length

    if total_distance <= 0:
        return float('-inf')

    average_enjoyment = weighted_enjoyment / total_distance
    meaningful_features = sum(
        1 for distance in feature_distance.values()
        if distance >= min(100.0, total_distance * 0.08)
    )
    diversity_bonus = min(meaningful_features * 0.025, 0.10)
    detour = max((total_distance / direct_distance) - 1.0, 0.0) if direct_distance > 0 else 0.0
    repeated_distance = sum(
        edge_lengths[pair] * (count - 1)
        for pair, count in edge_usage.items()
        if count > 1
    )
    repetition_penalty = min(repeated_distance / total_distance, 1.0) * 0.35
    return average_enjoyment + diversity_bonus - (detour * 0.16) - repetition_penalty

def _find_scenic_anchor_nodes(
    G,
    start_node,
    end_node,
    direct_distance: float,
    max_distance: float,
    required_tags: Optional[Set[str]] = None,
) -> List[Any]:
    """Find spatially distinct scenic nodes that fit within the detour budget."""
    from_start = nx.single_source_dijkstra_path_length(
        G, start_node, cutoff=max_distance, weight='length'
    )
    to_end = nx.single_source_dijkstra_path_length(
        G.reverse(copy=False), end_node, cutoff=max_distance, weight='length'
    )
    anchor_scores = {}

    for u, v, data in G.edges(data=True):
        scenery_score = float(data.get('scenery_score', _edge_scenery_score(data)))
        scenery_tags = _edge_scenery_tags(data)
        if scenery_score < 0.08 or (required_tags and not scenery_tags.intersection(required_tags)):
            continue

        for node in (u, v):
            if node not in from_start or node not in to_end:
                continue
            via_distance = from_start[node] + to_end[node]
            if via_distance > max_distance:
                continue
            detour = max((via_distance / direct_distance) - 1.0, 0.0) if direct_distance > 0 else 0.0
            value = scenery_score / (1.0 + detour * 1.6)
            if value > anchor_scores.get(node, 0.0):
                anchor_scores[node] = value

    ranked = sorted(anchor_scores, key=anchor_scores.get, reverse=True)
    selected = []
    for node in ranked:
        node_data = G.nodes[node]
        latitude = node_data.get('y')
        longitude = node_data.get('x')
        if latitude is not None and longitude is not None:
            too_close = any(
                _haversine_meters(
                    latitude,
                    longitude,
                    G.nodes[chosen].get('y', latitude),
                    G.nodes[chosen].get('x', longitude),
                ) < 140.0
                for chosen in selected
            )
            if too_close:
                continue
        selected.append(node)
        if len(selected) >= MAX_SCENIC_ANCHORS:
            break
    return selected

def _reconstruct_dijkstra_path(predecessors: Dict[Any, List[Any]], source, target) -> List[Any]:
    if target == source:
        return [source]
    if target not in predecessors or not predecessors[target]:
        raise nx.NetworkXNoPath

    path = [target]
    visited = {target}
    while path[-1] != source:
        previous = predecessors.get(path[-1], [])
        if not previous:
            raise nx.NetworkXNoPath
        node = previous[0]
        if node in visited:
            raise nx.NetworkXNoPath
        visited.add(node)
        path.append(node)
    path.reverse()
    return path

def _generate_route_candidates(
    G,
    start_node,
    end_node,
    direct_distance: float,
    max_distance: float,
    base_weights: List[str],
    include_scenic_anchors: bool = True,
    required_anchor_tags: Optional[Set[str]] = None,
    primary_weight: str = 'fun_weight',
) -> List[Tuple[List[Any], str]]:
    """Generate varied weighted and waypoint routes for constrained ranking."""
    candidates = []
    seen = set()

    def add_route(route, weight):
        key = _route_key(route)
        if key in seen:
            return False
        if _route_distance(G, route, selected_weight=weight) > max_distance:
            return False
        seen.add(key)
        candidates.append((route, weight))
        return True

    for weight in base_weights:
        try:
            add_route(nx.shortest_path(G, start_node, end_node, weight=weight), weight)
        except nx.NetworkXNoPath:
            continue

    # Repeatedly penalize edges already represented in the pool. This exposes
    # useful alternatives in a MultiDiGraph without relying on k-shortest-path
    # APIs, which NetworkX does not implement for multigraphs.
    for round_number in range(5):
        if not candidates:
            break
        usage = defaultdict(int)
        for route, _ in candidates:
            for pair in _route_edge_pairs(route):
                usage[pair] += 1

        attribute = f'_candidate_{primary_weight}_{round_number}'
        for u, v, _, data in G.edges(keys=True, data=True):
            count = usage.get(_edge_pair(u, v), 0)
            penalty = min(1.0 + (0.52 * count), 3.6)
            data[attribute] = data.get(primary_weight, data.get('length', 0)) * penalty
        try:
            add_route(nx.shortest_path(G, start_node, end_node, weight=attribute), attribute)
        except nx.NetworkXNoPath:
            break

    if include_scenic_anchors:
        anchors = _find_scenic_anchor_nodes(
            G,
            start_node,
            end_node,
            direct_distance,
            max_distance,
            required_tags=required_anchor_tags,
        )
        tree_cache = G.graph.setdefault('_waypoint_tree_cache', {})
        cache_key = (start_node, end_node, primary_weight)
        if cache_key not in tree_cache:
            from_start_predecessors, _ = nx.dijkstra_predecessor_and_distance(
                G, start_node, weight=primary_weight
            )
            from_end_predecessors, _ = nx.dijkstra_predecessor_and_distance(
                G.reverse(copy=False), end_node, weight=primary_weight
            )
            tree_cache[cache_key] = (from_start_predecessors, from_end_predecessors)
        from_start_predecessors, from_end_predecessors = tree_cache[cache_key]

        for anchor in anchors:
            try:
                first = _reconstruct_dijkstra_path(from_start_predecessors, start_node, anchor)
                reverse_second = _reconstruct_dijkstra_path(from_end_predecessors, end_node, anchor)
                second = list(reversed(reverse_second))
                add_route(first + second[1:], primary_weight)
            except nx.NetworkXNoPath:
                continue

    return candidates

def _set_diverse_weight(G, attr_name: str, base_weight_attr: str, used_edges: Set[Tuple[Any, Any]], penalty: float = DIVERSE_EDGE_PENALTY):
    for u, v, k, data in G.edges(keys=True, data=True):
        base_weight = data.get(base_weight_attr, data.get('length', 0))
        data[attr_name] = base_weight * (penalty if _edge_pair(u, v) in used_edges else 1.0)

def _set_blended_weight(G, attr_name: str, base_weight_attr: str, distance_share: float):
    for _, _, _, data in G.edges(keys=True, data=True):
        length = data.get('length', 0)
        base_weight = data.get(base_weight_attr, length)
        data[attr_name] = (length * distance_share) + (base_weight * (1.0 - distance_share))

def _route_to_coordinates(G, route: List[Any]) -> List[Coordinate]:
    coordinates = []
    for node_id in route:
        node = G.nodes[node_id]
        coordinates.append(Coordinate(lat=node['y'], lng=node['x']))
    return coordinates

def _nearest_graph_node(G, coordinate: Coordinate):
    """Find the nearest node without OSMnx's optional scikit-learn dependency."""
    nearest_node = None
    nearest_distance = float('inf')
    for node_id, node in G.nodes(data=True):
        distance = _haversine_meters(
            coordinate.lat,
            coordinate.lng,
            float(node['y']),
            float(node['x']),
        )
        if distance < nearest_distance:
            nearest_node = node_id
            nearest_distance = distance
    if nearest_node is None:
        raise nx.NodeNotFound('The downloaded walking graph contains no nodes')
    return nearest_node

def _make_route_result(G, route: List[Any], selected_weight: str, name: str, description: str, color: str, priority: str) -> Dict[str, Any]:
    return {
        'name': name,
        'description': description,
        'coordinates': _route_to_coordinates(G, route),
        'stats': calculate_detailed_route_stats(G, route, selected_weight=selected_weight),
        'color': color,
        'priority': priority,
        'nodes': route,
    }

def _best_capped_route(
    G,
    start_node,
    end_node,
    candidate_weights: List[str],
    max_distance: float,
    existing_routes: Optional[List[List[Any]]] = None,
    max_overlap: float = MAX_ROUTE_OVERLAP,
    direct_distance: Optional[float] = None,
    route_candidates: Optional[List[Tuple[List[Any], str]]] = None,
):
    existing_routes = existing_routes or []
    candidates = []
    seen = set()

    weighted_routes = list(route_candidates or [])
    for weight in candidate_weights:
        try:
            weighted_routes.append((nx.shortest_path(G, start_node, end_node, weight=weight), weight))
        except nx.NetworkXNoPath:
            pass

    for route, weight in weighted_routes:
        key = _route_key(route)
        if key in seen:
            continue
        seen.add(key)

        distance = _route_distance(G, route, selected_weight=weight)
        if distance > max_distance:
            continue

        stats = calculate_detailed_route_stats(G, route, selected_weight=weight)
        overlap = _route_overlap_ratio(G, route, existing_routes, selected_weight=weight)
        candidates.append({
            'route': route,
            'weight': weight,
            'distance': distance,
            'fun_score': stats['fun_score'],
            'overlap': overlap,
            'stats': stats,
            'quality': _route_quality_score(
                G,
                route,
                direct_distance if direct_distance is not None else max_distance,
                selected_weight=weight,
            ),
        })

    if not candidates:
        return None

    preferred = [candidate for candidate in candidates if candidate['overlap'] <= max_overlap]
    pool = preferred or candidates
    return max(
        pool,
        key=lambda candidate: (
            candidate['quality'],
            candidate['fun_score'],
            -candidate['distance'],
            -candidate['overlap'],
        ),
    )

def annotate_fun_weights(G):
    """
    Set route weights from separate path, safety, surface, and scenery factors.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Calculating fun weights...")
    start_time = time.time()

    edge_count = 0
    scenic_edges = 0
    for u, v, k, data in G.edges(keys=True, data=True):
        length = max(float(data.get('length', 0)), 1.0)
        path_type = _classify_path_type(data)
        surface_type = _classify_surface_type(data)
        scenery_score = _edge_scenery_score(data)
        safety_factor = _edge_safety_factor(data, path_type)
        fun_factor = _edge_fun_factor(data)

        data['path_type'] = path_type
        data['surface_type'] = surface_type
        data['scenery_score'] = scenery_score
        data['safety_factor'] = safety_factor
        data['fun_factor'] = fun_factor
        data['fun_weight'] = length * fun_factor
        data['balanced_weight'] = length * (0.75 + (0.25 * fun_factor))
        shopping_factor = (
            HIGHWAY_FUN_COST.get(path_type, HIGHWAY_FUN_COST['other'])
            * SURFACE_FUN_COST.get(surface_type, SURFACE_FUN_COST['unknown'])
            * safety_factor
            * (1.0 - _edge_shopping_score(data, path_type))
        )
        data['shopping_score'] = _edge_shopping_score(data, path_type)
        data['shopping_weight'] = length * max(0.42, min(shopping_factor, 5.0))

        edge_count += 1
        if scenery_score > 0:
            scenic_edges += 1

    elapsed = time.time() - start_time
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fun weights calculated in {elapsed:.2f}s for {edge_count} edges ({scenic_edges} scenic)")

def calculate_detailed_route_stats(G, route, selected_weight: str = 'length'):
    """
    Calculate detailed route statistics from the actual selected graph edges.
    """
    total_distance = 0
    total_fun_weight = 0
    node_type_counts = {}

    path_types = {
        key: {'distance': 0, 'time': 0, 'speed': value['speed'], 'description': value['description']}
        for key, value in PATH_TYPE_INFO.items()
    }
    surface_types = {
        key: {'distance': 0, 'time': 0, 'speed_modifier': value['speed_modifier'], 'description': value['description']}
        for key, value in SURFACE_TYPE_INFO.items()
    }
    special_areas = {}
    segments = []

    # Count node types
    for node_id in route:
        if G.has_node(node_id):
            incident_edges = G.edges(node_id, data=True)
            if incident_edges:
                path_type_values = [_classify_path_type(d) for _, _, d in incident_edges]
                if path_type_values:
                    dominant_hw = max(set(path_type_values), key=path_type_values.count)
                    node_type_counts[dominant_hw] = node_type_counts.get(dominant_hw, 0) + 1

    for _, _, edge in _route_edges_with_data(G, route, selected_weight):
        length = edge.get('length', 0)
        total_distance += length
        total_fun_weight += edge.get('fun_weight', length)

        path_type = edge.get('path_type') or _classify_path_type(edge)
        surface_type = edge.get('surface_type') or _classify_surface_type(edge)
        if path_type not in path_types:
            path_type = 'other'
        if surface_type not in surface_types:
            surface_type = 'unknown'
        path_info = path_types.get(path_type, path_types['other'])
        surface_info = surface_types.get(surface_type, surface_types['unknown'])
        speed = max(path_info['speed'] * surface_info['speed_modifier'], 1.0)
        segment_time = (length / 1000) * (60 / speed)

        path_types[path_type]['distance'] += length
        path_types[path_type]['time'] += segment_time
        surface_types[surface_type]['distance'] += length
        surface_types[surface_type]['time'] += segment_time

        features = sorted(_edge_scenery_tags(edge))
        segments.append({
            'length': length,
            'time': segment_time,
            'path_type': path_type,
            'surface_type': surface_type,
            'speed': speed,
            'features': features,
            'name': _first_value(edge, 'name', 'Unnamed path'),
        })

        for tag in features:
            if tag not in special_areas:
                special_areas[tag] = {
                    'distance': 0,
                    'time': 0,
                    'description': {
                        'park': 'Parks and green areas',
                        'nature_reserve': 'Nature reserves',
                        'forest': 'Forests and wooded areas',
                        'green_area': 'Open green areas',
                        'water': 'Waterfronts and water features',
                        'viewpoint': 'Scenic viewpoints',
                        'attraction': 'Attractions and landmarks',
                        'historic': 'Historic areas',
                        'scenic': 'Mapped scenic sections',
                        'shopping': 'Shops and retail streets',
                        'food': 'Cafés, restaurants, and food stops',
                    }.get(tag, 'Special area')
                }
            special_areas[tag]['distance'] += length
            special_areas[tag]['time'] += segment_time

    total_time = sum(data['time'] for data in path_types.values() if data['time'] > 0)
    if total_time == 0:
        total_time = total_distance / 1000 * (60 / 4.2)
    
    return {
        'distance': total_distance,
        'fun_weight': total_fun_weight,
        'fun_score': total_distance / total_fun_weight if total_fun_weight > 0 else 1.0,
        'estimated_time': total_time,
        'waypoints': len(route),
        'path_types': path_types,
        'surface_types': surface_types,
        'special_areas': special_areas,
        'segments': segments,
        'avg_speed': (total_distance / 1000) / (total_time / 60) if total_time > 0 else 4.2,
        'node_type_distribution': node_type_counts
}

def compute_multiple_routes(
    start: Coordinate,
    end: Coordinate,
    buffer_dist: int = 5000,
    route_type: str = 'all',
):
    """Compute only the requested detour-capped walking route mode."""
    valid_route_types = {'all', 'fastest', 'balanced', 'scenic', 'nature', 'shopping'}
    if route_type not in valid_route_types:
        raise ValueError(f"Unknown route type: {route_type}")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Computing {route_type} route option...")
    total_start = time.time()
    G = fetch_graph(start, end, buffer_dist, route_type=route_type)
    annotate_fun_weights(G)
    orig = _nearest_graph_node(G, start)
    dest = _nearest_graph_node(G, end)

    routes = []
    selected_node_routes = []
    selected_route_keys = set()

    def append_route(result):
        if not result:
            return False
        route_nodes = result.pop('nodes')
        route_key = _route_key(route_nodes)
        if route_key in selected_route_keys:
            return False
        selected_route_keys.add(route_key)
        selected_node_routes.append(route_nodes)
        routes.append(result)
        return True

    try:
        route_shortest = nx.shortest_path(G, orig, dest, weight='length')
    except nx.NetworkXNoPath:
        return routes
    direct_distance = _route_distance(G, route_shortest, selected_weight='length')

    if route_type in {'all', 'fastest'}:
        append_route(_make_route_result(
            G, route_shortest, 'length', 'SHORTEST', 'Fastest direct route', '#ff4444', 'speed'
        ))
    else:
        # Use the shortest route as the diversity baseline without returning it.
        selected_node_routes.append(route_shortest)

    if route_type == 'fastest':
        return routes

    if route_type in {'all', 'scenic'}:
        used_edges = set().union(*[_route_edge_pairs(route) for route in selected_node_routes])
        _set_diverse_weight(G, 'fun_weight_diverse', 'fun_weight', used_edges)
        _set_blended_weight(G, 'fun_weight_25_distance', 'fun_weight_diverse', 0.25)
        _set_blended_weight(G, 'fun_weight_45_distance', 'fun_weight_diverse', 0.45)
        fun_weights = [
            'fun_weight_diverse', 'fun_weight_25_distance', 'fun_weight',
            'fun_weight_45_distance', 'balanced_weight',
        ]
        fun_candidate = _best_capped_route(
            G,
            orig,
            dest,
            [],
            direct_distance * FUN_ROUTE_MAX_DETOUR,
            selected_node_routes,
            direct_distance=direct_distance,
            route_candidates=_generate_route_candidates(
                G, orig, dest, direct_distance,
                direct_distance * FUN_ROUTE_MAX_DETOUR, fun_weights,
            ),
        )
        if fun_candidate:
            route_fun = fun_candidate['route']
            append_route({
                'name': 'MOST_FUN',
                'description': f"Most enjoyable route, at most {(FUN_ROUTE_MAX_DETOUR - 1):.0%} longer than shortest",
                'coordinates': _route_to_coordinates(G, route_fun),
                'stats': fun_candidate['stats'],
                'color': '#44ff44',
                'priority': 'fun',
                'nodes': route_fun,
            })

    if route_type in {'all', 'nature'}:
        park_candidate = _best_capped_route(
            G,
            orig,
            dest,
            [],
            direct_distance * PARK_ROUTE_MAX_DETOUR,
            selected_node_routes,
            max_overlap=0.82,
            direct_distance=direct_distance,
            route_candidates=_generate_route_candidates(
                G,
                orig,
                dest,
                direct_distance,
                direct_distance * PARK_ROUTE_MAX_DETOUR,
                [],
                required_anchor_tags={'park', 'nature_reserve', 'forest', 'green_area', 'water'},
            ),
        )
        if park_candidate:
            route_parks = park_candidate['route']
            append_route({
                'name': 'PARK_HUNTER',
                'description': f'Nature-focused route, at most {(PARK_ROUTE_MAX_DETOUR - 1):.0%} longer than shortest',
                'coordinates': _route_to_coordinates(G, route_parks),
                'stats': park_candidate['stats'],
                'color': '#00aa00',
                'priority': 'park',
                'nodes': route_parks,
            })

    if route_type in {'all', 'shopping'}:
        used_edges = set().union(*[_route_edge_pairs(route) for route in selected_node_routes])
        _set_diverse_weight(G, 'shopping_weight_diverse', 'shopping_weight', used_edges, penalty=2.3)
        _set_blended_weight(G, 'shopping_weight_25_distance', 'shopping_weight_diverse', 0.25)
        _set_blended_weight(G, 'shopping_weight_45_distance', 'shopping_weight_diverse', 0.45)
        shopping_weights = [
            'shopping_weight_diverse', 'shopping_weight_25_distance',
            'shopping_weight', 'shopping_weight_45_distance', 'balanced_weight',
        ]
        shopping_candidate = _best_capped_route(
            G,
            orig,
            dest,
            [],
            direct_distance * SHOPPING_ROUTE_MAX_DETOUR,
            selected_node_routes,
            max_overlap=0.82,
            direct_distance=direct_distance,
            route_candidates=_generate_route_candidates(
                G,
                orig,
                dest,
                direct_distance,
                direct_distance * SHOPPING_ROUTE_MAX_DETOUR,
                shopping_weights,
                required_anchor_tags={'shopping', 'food'},
                primary_weight='shopping_weight',
            ),
        )
        if shopping_candidate:
            route_shopping = shopping_candidate['route']
            append_route({
                'name': 'SHOPPING',
                'description': f'Shops, markets, and café streets, at most {(SHOPPING_ROUTE_MAX_DETOUR - 1):.0%} longer than shortest',
                'coordinates': _route_to_coordinates(G, route_shopping),
                'stats': shopping_candidate['stats'],
                'color': '#a855f7',
                'priority': 'shopping',
                'nodes': route_shopping,
            })

    if route_type in {'all', 'balanced'}:
        used_edges = set().union(*[_route_edge_pairs(route) for route in selected_node_routes])
        _set_diverse_weight(G, 'balanced_weight_diverse', 'balanced_weight', used_edges, penalty=2.2)
        _set_blended_weight(G, 'balanced_weight_60_distance', 'balanced_weight_diverse', 0.60)
        balanced_weights = [
            'balanced_weight_diverse', 'balanced_weight_60_distance', 'balanced_weight', 'length'
        ]
        balanced_candidate = _best_capped_route(
            G,
            orig,
            dest,
            balanced_weights,
            direct_distance * BALANCED_ROUTE_MAX_DETOUR,
            selected_node_routes,
            direct_distance=direct_distance,
            route_candidates=_generate_route_candidates(
                G,
                orig,
                dest,
                direct_distance,
                direct_distance * BALANCED_ROUTE_MAX_DETOUR,
                balanced_weights,
                include_scenic_anchors=False,
                primary_weight='balanced_weight',
            ),
        )
        if balanced_candidate:
            route_balanced = balanced_candidate['route']
            append_route({
                'name': 'BALANCED',
                'description': f'Good mix of speed and scenery, at most {(BALANCED_ROUTE_MAX_DETOUR - 1):.0%} longer than shortest',
                'coordinates': _route_to_coordinates(G, route_balanced),
                'stats': balanced_candidate['stats'],
                'color': '#4444ff',
                'priority': 'balanced',
                'nodes': route_balanced,
            })

    if not routes:
        append_route(_make_route_result(
            G,
            route_shortest,
            'length',
            'SHORTEST',
            f'No distinct {route_type} alternative was found; showing the safest direct route',
            '#ff4444',
            'speed',
        ))

    total_time = time.time() - total_start
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {route_type} route computed in {total_time:.2f}s")
    return routes

def search_addresses(query: str, limit: int = 5) -> List[AddressResult]:
    """
    Search for addresses, house numbers, stores, and POIs using Nominatim
    """
    try:
        # Use Nominatim API for comprehensive geocoding
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'limit': limit * 2,  # Get more results to filter and sort
            'addressdetails': 1,
            'extratags': 1,
            'namedetails': 1,
            'dedupe': 1,  # Remove duplicates
        }
        
        headers = {
            'User-Agent': 'FunPathPlanner/1.0 (contact@example.com)'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        for item in data:
            # Get location type and category
            place_type = item.get('type', '')
            place_class = item.get('class', '')
            
            # Calculate relevance score based on type
            relevance_score = float(item.get('importance', 0.5))
            
            # Boost scores for useful location types
            if place_type in ['house', 'building', 'address']:
                relevance_score += 0.3  # Houses and addresses
            elif place_type in ['shop', 'store', 'retail']:
                relevance_score += 0.25  # Shops and stores
            elif place_type in ['restaurant', 'cafe', 'bar', 'pub', 'fast_food']:
                relevance_score += 0.25  # Food and drink
            elif place_type in ['hotel', 'hostel', 'guest_house']:
                relevance_score += 0.2  # Accommodation
            elif place_type in ['hospital', 'clinic', 'pharmacy', 'dentist']:
                relevance_score += 0.2  # Healthcare
            elif place_type in ['school', 'university', 'college', 'library']:
                relevance_score += 0.2  # Education
            elif place_type in ['bank', 'atm', 'post_office']:
                relevance_score += 0.15  # Services
            elif place_type in ['park', 'garden', 'playground']:
                relevance_score += 0.15  # Recreation
            elif place_type in ['bus_stop', 'train_station', 'subway_entrance']:
                relevance_score += 0.1  # Transport
            
            # Boost if it has a house number
            address = item.get('address', {})
            if address.get('house_number'):
                relevance_score += 0.2
            
            # Create enhanced display name with house numbers
            display_name = item['display_name']
            address = item.get('address', {})
            
            # Extract and format address components
            house_number = address.get('house_number', '')
            street = address.get('road', '')
            city = address.get('city', address.get('town', address.get('village', '')))
            
            # Create a better formatted address for houses/buildings
            if house_number and street:
                # Format as "Street Number, City" for addresses
                formatted_address = f"{street} {house_number}"
                if city:
                    formatted_address += f", {city}"
                
                # Use the formatted address as the main display
                display_name = formatted_address + ", " + ", ".join(display_name.split(', ')[2:])
            
            # Add type information for POIs (stores, restaurants, etc.)
            if place_type and place_type not in ['house', 'building', 'address', 'road']:
                type_info = place_type.replace('_', ' ').title()
                if place_class and place_class != place_type:
                    type_info = f"{place_class.title()} - {type_info}"
                
                # Add type info to display name if not already present
                name_parts = display_name.split(',')
                if len(name_parts) > 0 and type_info.lower() not in name_parts[0].lower():
                    name_parts[0] = f"{name_parts[0]} ({type_info})"
                    display_name = ', '.join(name_parts)
            
            results.append(AddressResult(
                display_name=display_name,
                lat=float(item['lat']),
                lng=float(item['lon']),
                place_id=str(item['place_id']),
                importance=relevance_score
            ))
        
        # Sort by relevance score (higher is better)
        results.sort(key=lambda x: x.importance, reverse=True)
        
        # Remove very similar results (within 50m)
        filtered_results = []
        for result in results:
            is_duplicate = False
            for existing in filtered_results:
                # Calculate rough distance (simplified)
                lat_diff = abs(result.lat - existing.lat)
                lng_diff = abs(result.lng - existing.lng)
                if lat_diff < 0.0005 and lng_diff < 0.0005:  # ~50m
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                filtered_results.append(result)
                
            if len(filtered_results) >= limit:
                break
        
        return filtered_results
        
    except Exception as e:
        print(f"Geocoding error: {str(e)}")
        return []

@app.get("/")
async def root():
    return {"message": "Fun Path Planner API", "status": "running"}

@app.post("/api/search-addresses", response_model=AddressSearchResponse)
async def search_addresses_endpoint(request: AddressSearchRequest):
    """
    Search for addresses and return coordinates
    """
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Address search: '{request.query}'")
        
        if len(request.query.strip()) < 3:
            return AddressSearchResponse(
                results=[],
                success=False,
                message="Query too short (minimum 3 characters)"
            )
        
        results = search_addresses(request.query, request.limit)
        
        return AddressSearchResponse(
            results=results,
            success=True,
            message=f"Found {len(results)} addresses"
        )
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Address search error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Address search failed: {str(e)}")

@app.post("/api/tree-cover", response_model=TreeCoverResponse)
def tree_cover_endpoint(request: TreeCoverRequest):
    """Measure local canopy around candidate points using Copernicus TCD data."""
    try:
        results, cache_hits, cdse_points_fetched = fetch_tree_cover_cached(
            request.points,
            request.sample_radius_meters,
        )
        return TreeCoverResponse(
            results=results,
            cache_hits=cache_hits,
            cdse_points_fetched=cdse_points_fetched,
            cdse_requests=1 if cdse_points_fetched else 0,
        )
    except requests.RequestException as error:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] CDSE request failed: {error}")
        raise HTTPException(status_code=503, detail='Satellite tree-cover data is temporarily unavailable.')
    except (KeyError, RuntimeError, ValueError) as error:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] CDSE configuration error: {error}")
        raise HTTPException(status_code=503, detail=str(error))

@app.post("/api/vegetation-structure", response_model=VegetationStructureResponse)
def vegetation_structure_endpoint(request: VegetationStructureRequest):
    """Measure eye-level and tall vegetation from locally installed NMD rasters."""
    if not nmd_available():
        return VegetationStructureResponse(available=False, results=[])
    try:
        raw_results, cache_hits = sample_vegetation_structure(
            request.points,
            request.sample_radius_meters,
        )
        return VegetationStructureResponse(
            available=True,
            results=[VegetationStructureResult(**result) for result in raw_results],
            cache_hits=cache_hits,
        )
    except (OSError, ValueError, RasterioError) as error:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] NMD raster sampling failed: {error}")
        raise HTTPException(status_code=503, detail='Local vegetation-height data could not be read.')

@app.get("/api/debug-node-details")
async def debug_node_details():
    """
    Temporary endpoint to get debug information for a sample node and its edges.
    """
    try:
        sample_point = (58.54, 15.03)
        G = ox.graph_from_point(sample_point, dist=500, network_type='walk', simplify=True)
        
        node_ids = list(G.nodes)
        if not node_ids:
            return {"error": "Could not fetch any nodes."}

        sample_node_id = node_ids[0]
        node_data = G.nodes[sample_node_id]
        
        incident_edges = list(G.in_edges(sample_node_id, data=True)) + list(G.out_edges(sample_node_id, data=True))
        
        edge_details = []
        for u, v, data in incident_edges:
            # Sanitize edge data to ensure it's JSON serializable
            sanitized_data = {k: str(v) for k, v in data.items()}
            edge_info = {
                "from_node": u,
                "to_node": v,
                "data": sanitized_data
            }
            edge_details.append(edge_info)

        return {
            "node_id": sample_node_id, 
            "node_data": node_data,
            "connected_edges": edge_details
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/routes", response_model=RouteResponse)
async def calculate_routes(request: RouteRequest):
    """
    Calculate multiple walking routes between two points
    """
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Route request: {request.start} -> {request.end}")
        
        routes_data = compute_multiple_routes(
            request.start,
            request.end,
            request.buffer_dist,
            route_type=request.route_type,
        )
        
        if not routes_data:
            raise HTTPException(status_code=404, detail="No routes found")
        
        # Convert to API format
        routes = []
        for route_data in routes_data:
            # Convert stats to proper format
            stats_dict = route_data['stats']
            
            # Convert path_types
            path_types = {}
            for key, value in stats_dict['path_types'].items():
                if value['distance'] > 0:  # Only include non-zero entries
                    path_types[key] = PathTypeStats(**value)
            
            # Convert surface_types  
            surface_types = {}
            for key, value in stats_dict['surface_types'].items():
                if value['distance'] > 0:  # Only include non-zero entries
                    surface_types[key] = SurfaceTypeStats(**value)
            
            # Convert special_areas
            special_areas = {}
            for key, value in stats_dict['special_areas'].items():
                special_areas[key] = SpecialAreaStats(**value)

            segments = [RouteSegmentStats(**segment) for segment in stats_dict.get('segments', [])]
            
            stats = RouteStats(
                distance=stats_dict['distance'],
                fun_weight=stats_dict['fun_weight'],
                fun_score=stats_dict['fun_score'],
                estimated_time=stats_dict['estimated_time'],
                waypoints=stats_dict['waypoints'],
                path_types=path_types,
                surface_types=surface_types,
                special_areas=special_areas,
                segments=segments,
                avg_speed=stats_dict['avg_speed'],
                node_type_distribution=stats_dict.get('node_type_distribution', {})
            )
            
            route = Route(
                name=route_data['name'],
                description=route_data['description'],
                route=route_data['coordinates'],  # Frontend expects 'route', not 'coordinates'
                stats=stats,
                color=route_data['color'],
                priority=route_data['priority']
            )
            routes.append(route)
        
        return RouteResponse(
            routes=routes,
            success=True,
            message=f"Found {len(routes)} routes"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Route calculation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("Starting Fun Path Planner API...")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
