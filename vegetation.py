"""Local NMD 2023 vegetation-structure raster sampling and persistent caching."""

from __future__ import annotations

from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Tuple
import math
import os
import sqlite3
import time

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window


NMD_SOURCE = 'NMD 2023 object height and coverage'
NMD_CACHE_VERSION = 'nmd-object-coverage-v1'
NMD_DENSITY_MIDPOINTS = {
    0: 0.0,
    5: 2.5,
    10: 7.5,
    20: 15.0,
    30: 25.0,
    40: 35.0,
    50: 45.0,
    60: 55.0,
    70: 65.0,
    80: 75.0,
    90: 85.0,
    100: 95.0,
}
_sampling_lock = Lock()


def nmd_raster_paths() -> Tuple[Path, Path]:
    data_dir = Path(os.environ.get(
        'NMD_DATA_DIR',
        Path(__file__).resolve().parent / 'data' / 'nmd',
    ))
    low_path = Path(os.environ.get(
        'NMD_LOW_VEGETATION_RASTER',
        data_dir / 'low_vegetation_coverage.tif',
    ))
    tall_path = Path(os.environ.get(
        'NMD_TALL_VEGETATION_RASTER',
        data_dir / 'tall_vegetation_coverage.tif',
    ))
    return low_path, tall_path


def vegetation_cache_path() -> Path:
    default_cache_dir = Path(os.environ.get(
        'OSMNX_CACHE_FOLDER',
        Path(__file__).resolve().parent / 'cache',
    ))
    return Path(os.environ.get(
        'VEGETATION_CACHE_PATH',
        default_cache_dir / 'vegetation_structure.sqlite3',
    ))


def nmd_available() -> bool:
    low_path, _ = nmd_raster_paths()
    return low_path.is_file()


def source_signature() -> str:
    signatures = []
    for path in nmd_raster_paths():
        if not path.is_file():
            continue
        stat = path.stat()
        signatures.append(f'{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}')
    return sha256('|'.join(signatures).encode('utf-8')).hexdigest()[:16]


def cache_key(point: Any, radius_meters: int, signature: str) -> str:
    return f'{NMD_CACHE_VERSION}:{signature}:{point.lat:.5f}:{point.lng:.5f}:{radius_meters}'


def ensure_cache_table(connection: sqlite3.Connection) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS vegetation_structure_cache (
            cache_key TEXT PRIMARY KEY,
            low_vegetation_percent REAL NOT NULL,
            tall_vegetation_percent REAL NOT NULL,
            valid_pixel_percent REAL NOT NULL,
            created_at REAL NOT NULL
        )
    ''')


def read_cache(keys: List[str]) -> Dict[str, Tuple[float, float, float]]:
    if not keys:
        return {}
    path = vegetation_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=10) as connection:
            ensure_cache_table(connection)
            placeholders = ','.join('?' for _ in keys)
            rows = connection.execute(
                f'''SELECT cache_key, low_vegetation_percent, tall_vegetation_percent,
                           valid_pixel_percent
                    FROM vegetation_structure_cache WHERE cache_key IN ({placeholders})''',
                keys,
            ).fetchall()
        return {row[0]: (float(row[1]), float(row[2]), float(row[3])) for row in rows}
    except (OSError, sqlite3.Error):
        return {}


def write_cache(entries: Dict[str, Tuple[float, float, float]]) -> None:
    if not entries:
        return
    path = vegetation_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        with sqlite3.connect(path, timeout=10) as connection:
            ensure_cache_table(connection)
            connection.executemany(
                '''INSERT OR REPLACE INTO vegetation_structure_cache
                   (cache_key, low_vegetation_percent, tall_vegetation_percent,
                    valid_pixel_percent, created_at)
                   VALUES (?, ?, ?, ?, ?)''',
                [(key, *values, now) for key, values in entries.items()],
            )
    except (OSError, sqlite3.Error):
        return


def sample_density_raster(
    dataset: rasterio.io.DatasetReader,
    transformer: Transformer,
    lat: float,
    lng: float,
    radius_meters: int,
) -> Tuple[float, float]:
    x, y = transformer.transform(lng, lat)
    row, column = dataset.index(x, y)
    pixel_width = max(abs(dataset.transform.a), 0.01)
    pixel_height = max(abs(dataset.transform.e), 0.01)
    radius_columns = max(1, math.ceil(radius_meters / pixel_width) + 1)
    radius_rows = max(1, math.ceil(radius_meters / pixel_height) + 1)
    window = Window(
        column - radius_columns,
        row - radius_rows,
        radius_columns * 2 + 1,
        radius_rows * 2 + 1,
    )
    values = dataset.read(1, window=window, boundless=True, masked=True, fill_value=255)
    window_transform = dataset.window_transform(window)
    rows, columns = np.indices(values.shape)
    pixel_x = (
        window_transform.c
        + (columns + 0.5) * window_transform.a
        + (rows + 0.5) * window_transform.b
    )
    pixel_y = (
        window_transform.f
        + (columns + 0.5) * window_transform.d
        + (rows + 0.5) * window_transform.e
    )
    circle = np.hypot(pixel_x - x, pixel_y - y) <= radius_meters
    total_pixels = int(circle.sum())
    raw = np.asarray(values.data, dtype=np.int16)
    masked = np.ma.getmaskarray(values)
    known_codes = np.isin(raw, list(NMD_DENSITY_MIDPOINTS))
    valid = circle & ~masked & known_codes
    valid_count = int(valid.sum())
    if not valid_count or not total_pixels:
        return 0.0, 0.0

    lookup = np.full(256, np.nan, dtype=np.float32)
    for code, midpoint in NMD_DENSITY_MIDPOINTS.items():
        lookup[code] = midpoint
    decoded = lookup[np.clip(raw, 0, 255)]
    return round(float(decoded[valid].mean()), 1), round(valid_count / total_pixels * 100, 1)


def sample_missing(
    points_by_key: Dict[str, Any],
    radius_meters: int,
) -> Dict[str, Tuple[float, float, float]]:
    low_path, tall_path = nmd_raster_paths()
    results: Dict[str, Tuple[float, float, float]] = {}
    with ExitStack() as stack:
        low_dataset = stack.enter_context(rasterio.open(low_path))
        tall_dataset = stack.enter_context(rasterio.open(tall_path)) if tall_path.is_file() else None
        if low_dataset.crs is None or (tall_dataset is not None and tall_dataset.crs is None):
            raise ValueError('NMD vegetation rasters must include a coordinate reference system.')
        low_transformer = Transformer.from_crs('EPSG:4326', low_dataset.crs, always_xy=True)
        tall_transformer = Transformer.from_crs('EPSG:4326', tall_dataset.crs, always_xy=True) if tall_dataset else None
        for key, point in points_by_key.items():
            low_cover, low_valid = sample_density_raster(
                low_dataset, low_transformer, point.lat, point.lng, radius_meters,
            )
            if tall_dataset is not None and tall_transformer is not None:
                tall_cover, tall_valid = sample_density_raster(
                    tall_dataset, tall_transformer, point.lat, point.lng, radius_meters,
                )
                valid_percent = min(low_valid, tall_valid)
            else:
                tall_cover = 0.0
                valid_percent = low_valid
            results[key] = (low_cover, tall_cover, valid_percent)
    return results


def sample_vegetation_structure(
    points: Iterable[Any],
    radius_meters: int,
) -> Tuple[List[Dict[str, float | str]], int]:
    point_list = list(points)
    if not nmd_available():
        return [], 0

    signature = source_signature()
    keys = [cache_key(point, radius_meters, signature) for point in point_list]
    cached = read_cache(list(dict.fromkeys(keys)))
    initial_cache_keys = set(cached)
    missing = {
        cache_key(point, radius_meters, signature): point
        for point in point_list
        if cache_key(point, radius_meters, signature) not in cached
    }

    if missing:
        with _sampling_lock:
            refreshed = read_cache(list(missing))
            cached.update(refreshed)
            still_missing = {key: point for key, point in missing.items() if key not in cached}
            sampled = sample_missing(still_missing, radius_meters) if still_missing else {}
            write_cache(sampled)
            cached.update(sampled)

    results: List[Dict[str, float | str]] = []
    for point, key in zip(point_list, keys):
        low_cover, tall_cover, valid_percent = cached[key]
        results.append({
            'id': point.id,
            'low_vegetation_percent': low_cover,
            'tall_vegetation_percent': tall_cover,
            'valid_pixel_percent': valid_percent,
        })
    cache_hits = sum(key in initial_cache_keys for key in keys)
    return results, cache_hits
