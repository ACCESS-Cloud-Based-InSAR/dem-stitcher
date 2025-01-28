from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine
from numpy.testing import assert_array_equal
from rasterio.crs import CRS
from rasterio.transform import from_origin

from dem_stitcher.merge import merge_arrays_with_geometadata, merge_tile_datasets_within_extent


# from dem_stitcher.datasets import DATASETS

"""
We are considering the following 20 x 20 reference image with extent

xmin, ymin, xmax, ymax = 10, -10, 30, 10

and 1 degree resolution. The reference image is:

0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
0 1 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2
0 1 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2
0 1 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2
0 1 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2
0 1 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2
0 1 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2
0 1 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2
0 1 2 2 2 2 2 2 2 2 x x x x x x x x x x
0 1 2 2 2 2 2 2 2 2 x x x x x x x x x x
0 1 2 2 2 2 2 2 2 2 x x x x x x x x x x
0 1 2 2 2 2 2 2 2 2 x x x x x x x x x x
0 1 2 2 2 2 2 2 2 2 x x x x x x x x x x
0 1 2 2 2 2 2 2 2 2 x x x x x x x x x x
0 1 2 2 2 2 2 2 2 2 x x x x x x x x x x
0 1 2 2 2 2 2 2 2 2 x x x x x x x x x x
0 1 2 2 2 2 2 2 2 2 x x x x x x x x x x
0 1 2 2 2 2 2 2 2 2 x x x x x x x x x x
0 1 2 2 2 2 2 2 2 2 x x x x x x x x x x

where x indicates nodata

We place into 3 10-degree chunks with extents determined by:

UL) xmin, ymin, xmax, ymax = 10, -10, 20,   0
UR) xmin, ymin, xmax, ymax = 20, -10, 30,   0
LL) xmin, ymin, xmax, ymax = 10, -20, 20, -10
LR) xmin, ymin, xmax, ymax = 20, -20, 30, -10
"""

extents = [
    [10, -20, 30, 0],  # Full extents of image
    [10.5, -19.5, 29.5, -0.5],  # within .5 degrees of image
    [11.5, -18.5, 28.5, -1.5],  # within 1.5 degrees of image
    [10.5, -9.5, 19.5, -0.5],  # within .5 of top left corner (see UL above)
    [10, -10, 30, 0],  # Upper part of image
]

ref = np.zeros((20, 20))
ref[1:, 1:] = 1
ref[2:, 2:] = 2
ref[10:, 10:] = np.nan
arrays = [ref, ref, ref[1:19, 1:19], ref[:10, :10], ref[:10, :]]

# Using upper left corner (10, 0) because (0, 0) raises warnings about (0, 0)
t = Affine(1, 0, 10, 0, -1, 0)
transforms = [
    t,  # reference transform
    t,
    t.translation(1, -1) * t,  # transform with UL corner at (11, -1)
    t,
    t,
]


@pytest.mark.parametrize('extent, array, transform', zip(extents, arrays, transforms))
def test_merge_tiles(test_data_dir: Path, extent: list[float], array: np.ndarray, transform: Affine) -> None:
    merge_dir = test_data_dir / 'stitcher' / 'merge_tiles'
    upper_left = merge_dir / 'ul.tif'
    upper_right = merge_dir / 'ur.tif'
    bottom_left = merge_dir / 'bl.tif'

    tile_datasets = [rasterio.open(path) for path in [upper_left, upper_right, bottom_left]]

    X, p = merge_tile_datasets_within_extent(tile_datasets, extent)

    list(map(lambda x: x.close, tile_datasets))

    array = array[np.newaxis, ...]
    assert_array_equal(X, array)
    assert p['transform'] == transform


def test_merge_in_memory() -> None:
    size = 11
    array_1 = np.ones((size, size), dtype=np.float32)
    array_2 = np.ones((size, size), dtype=np.float32) * 2

    array_1[1:3, size - 1] = np.nan
    array_2[0:2, 0] = np.nan

    resolution = 0.1
    transform_1 = from_origin(-50, 25, resolution, resolution)
    transform_2 = from_origin(-49, 25, resolution, resolution)

    profile_1 = {
        'driver': 'GTiff',
        'dtype': np.float32,
        'count': 1,
        'height': size,
        'width': size,
        'crs': CRS.from_epsg(4326),
        'transform': transform_1,
        'nodata': np.nan,
    }

    profile_2 = {
        'driver': 'GTiff',
        'dtype': np.float32,
        'count': 1,
        'height': size,
        'width': size,
        'crs': CRS.from_epsg(4326),
        'transform': transform_2,
        'nodata': np.nan,
    }

    # Calculate merged array dimensions
    merged_height = 11  # Same width as original arrays
    merged_width = 21  # (11 + 11 - 1) for overlap

    # Create merged array
    merged_array_expected = np.zeros((1, merged_height, merged_width), dtype=np.float32)
    merged_array_expected[0, :, :size] = 1
    merged_array_expected[0, :, -size:] = 2
    merged_array_expected[0, 3:, size - 1] = 3
    # Nan in array 2
    merged_array_expected[0, 0, size - 1] = 1
    # Nan in both arrays
    merged_array_expected[0, 1, size - 1] = np.nan
    # Nan in array 1
    merged_array_expected[0, 2, size - 1] = 2

    # Create merged profile
    merged_transform = from_origin(-50, 25, resolution, resolution)
    merged_profile_expected = {
        'driver': 'GTiff',
        'dtype': np.float32,
        'count': 1,
        'height': merged_height,
        'width': merged_width,
        'crs': CRS.from_epsg(4326),
        'transform': merged_transform,
        'nodata': None,
    }

    merged_array_actual, merged_profile_actual = merge_arrays_with_geometadata(
        [array_1, array_2], [profile_1, profile_2], method='sum'
    )
    assert_array_equal(merged_array_actual, merged_array_expected)
    assert all(
        [
            val_expected == merged_profile_actual[key]
            for (key, val_expected) in merged_profile_expected.items()
            if key != 'nodata'
        ]
    )
    assert np.isnan(merged_profile_actual['nodata'])
