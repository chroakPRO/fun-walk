import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from vegetation import sample_vegetation_structure


class VegetationStructureTests(unittest.TestCase):
    def test_samples_nmd_density_classes_and_reuses_persistent_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            low_path = root / 'low.tif'
            tall_path = root / 'tall.tif'
            cache_path = root / 'vegetation.sqlite3'
            lat, lng = 58.537, 15.036
            x, y = Transformer.from_crs('EPSG:4326', 'EPSG:3006', always_xy=True).transform(lng, lat)
            profile = {
                'driver': 'GTiff',
                'height': 100,
                'width': 100,
                'count': 1,
                'dtype': 'uint8',
                'crs': 'EPSG:3006',
                'transform': from_origin(x - 500, y + 500, 10, 10),
                'nodata': 255,
            }
            with rasterio.open(low_path, 'w', **profile) as dataset:
                dataset.write(np.full((100, 100), 60, dtype=np.uint8), 1)
            with rasterio.open(tall_path, 'w', **profile) as dataset:
                dataset.write(np.full((100, 100), 80, dtype=np.uint8), 1)

            point = SimpleNamespace(id='test-point', lat=lat, lng=lng)
            environment = {
                'NMD_LOW_VEGETATION_RASTER': str(low_path),
                'NMD_TALL_VEGETATION_RASTER': str(tall_path),
                'VEGETATION_CACHE_PATH': str(cache_path),
            }
            with patch.dict(os.environ, environment, clear=False):
                first, first_hits = sample_vegetation_structure([point], 35)
                second, second_hits = sample_vegetation_structure([point], 35)

            self.assertEqual(first_hits, 0)
            self.assertEqual(second_hits, 1)
            self.assertEqual(first, second)
            self.assertEqual(first[0]['low_vegetation_percent'], 55.0)
            self.assertEqual(first[0]['tall_vegetation_percent'], 75.0)
            self.assertEqual(first[0]['valid_pixel_percent'], 100.0)


if __name__ == '__main__':
    unittest.main()
