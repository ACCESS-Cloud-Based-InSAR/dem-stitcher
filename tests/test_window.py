import geopandas as gpd
import numpy as np
import pytest
from affine import Affine
from numpy.testing import assert_array_equal
from rasterio.crs import CRS

from dem_stitcher.rio_window import (get_indices_from_extent,
                                     read_raster_from_window)

"""
This does a simple test of window reading over an extent of the following area:

xmin, ymin, xmax, ymax = 10, -10, 20, 0

with 1 degree resolution. The reference image is:

0 0 0 0 0 0 0 0 0 0
0 1 1 1 1 1 1 1 1 0
0 1 2 2 2 2 2 2 1 0
0 1 2 2 2 2 2 2 1 0
0 1 2 2 2 2 2 2 1 0
0 1 2 2 2 2 2 2 1 0
0 1 2 2 2 2 2 2 1 0
0 1 2 2 2 2 2 2 1 0
0 1 1 1 1 1 1 1 1 0
0 0 0 0 0 0 0 0 0 0

We expect that a window of size 9 degrees with extent [10.5, -9.5, 19.5, -.5] window should return the entire image.

If we start at (8.5, 1.5) and go for 7 degrees similarly, then we should get:

1 1 1 1 1 1 1 1
1 2 2 2 2 2 2 1
1 2 2 2 2 2 2 1
1 2 2 2 2 2 2 1
1 2 2 2 2 2 2 1
1 2 2 2 2 2 2 1
1 2 2 2 2 2 2 1
1 1 1 1 1 1 1 1
"""

ref = np.zeros((10, 10))
ref[1:9, 1:9] = 1
ref[2:8, 2:8] = 2
arrays = [ref,
          ref,
          ref[1:9, 1:9],
          ref[2:8, 2:8],
          ref[1:9, 2:8]
          ]


# Using upper left corner (10, 0) because (0, 0) raises warnings being the identify affine transformation
t = Affine(1, 0, 10, 0, -1, 0)
transforms = [t,                           # reference transform
              t,                           # reference transform
              t.translation(1, -1) * t,    # transform with UL corner at (11, -1)
              t.translation(2, -2) * t,    # trasnform with UL corner at (12, -2)
              t.translation(2, -1) * t]    # trasnform with UL corner at (12, -1)


extents = [
            [9.5, -10.5, 20.5, .5],     # beyond the reference image extent by .5 degrees
            [10.5, -9.5, 19.5, -.5],    # .5 degree within reference image
            [11.5, -8.5, 18.5, -1.5],   # 1.5 degree within reference image
            [12.5, -7.5, 17.5, -2.5],   # 2.5 degree within reference image
            [12.5, -8.5, 17.5, -1.5]    # 2.5 degree within x-axis and 1.5 within y-axis of reference
           ]


@pytest.mark.parametrize("extent, array, transform", zip(extents, arrays, transforms))
def test_read_window_4326(test_data_dir, extent, array, transform):
    raster_path = test_data_dir / 'rio_window' / 'test_window.tif'

    window_arr, p = read_raster_from_window(raster_path,
                                            extent,
                                            CRS.from_epsg(4326),
                                            res_buffer=0)
    assert_array_equal(array, window_arr)
    assert transform == p['transform']


@pytest.mark.parametrize("geojson_index, array, transform", zip([0, 1, 2, 3], arrays, transforms))
def test_read_window_utm(test_data_dir, geojson_index, array, transform):
    """Same test using bounds that have been reprojected into an appropriate UTM zone. Ignores index 4.
    """
    raster_path = test_data_dir / 'rio_window' / 'test_window.tif'
    geojson_path = test_data_dir / 'rio_window' / f'window_utm_{geojson_index}.geojson'

    df = gpd.read_file(geojson_path)
    extent = list(df.total_bounds)
    crs = df.crs

    window_arr, p = read_raster_from_window(raster_path,
                                            extent,
                                            crs,
                                            res_buffer=0)
    assert_array_equal(array, window_arr)
    assert transform == p['transform']


"""
We test getting array indices from extents and a reference transform.

See https://rasterio.readthedocs.io/en/latest/topics/windowed-rw.html

We use the same transform as above and extents from previous tests.
Note we never go beyond UL corner specified by transform.
"""

indices = [
            ((0, 0), (11, 11)),  # ((row_start, col_start), (row_stop, col_stop))
            ((0, 0), (10, 10)),
            ((1, 1), (9, 9)),
            ((2, 2), (8, 8)),
          ]


@pytest.mark.parametrize("extent, arr_index", zip(extents, indices))
def test_get_indices(extent, arr_index):
    """Verifying the get indices for windowed reading returns correct window
    """
    t = Affine(1, 0, 10, 0, -1, 0)
    ul, br = get_indices_from_extent(t, extent)
    assert arr_index == (ul, br)


# Indices
indices_buffer = [
                  ((0, 0), (12, 12)),  # ((row_start, col_start), (row_stop, col_stop))
                  ((0, 0), (11, 11)),
                  ((0, 0), (10, 10)),
                  ((1, 1), (9, 9)),
                  ]


@pytest.mark.parametrize("extent, arr_index", zip(extents, indices_buffer))
def test_get_indices_buffered(extent, arr_index):
    """Make sure that windowed extents work correctly with 1 resolution buffer
    """
    t = Affine(1, 0, 10, 0, -1, 0)
    ul, br = get_indices_from_extent(t, extent, res_buffer=1)
    assert arr_index == (ul, br)


# Indices
indices_shape = [
                  ((0, 0), (12, 10)),
                  ((0, 0), (11, 10)),
                  ((0, 0), (10, 10)),
                  ((1, 1), (9, 9)),
                  ]


@pytest.mark.parametrize("extent, arr_index", zip(extents, indices_shape))
def test_get_indices_shape(extent, arr_index):
    """Similar test using shape to truncate row_stop and col_stop
    """
    t = Affine(1, 0, 10, 0, -1, 0)
    ul, br = get_indices_from_extent(t, extent, res_buffer=1, shape=(12, 10))
    assert arr_index == (ul, br)


# Additional tests for unequal dimensions
# bounds are (left=10.0, bottom=-4.0, right=15.0, top=0.0)
# t = Affine(1, 0, 10, 0, -1, 0) as above
# shape is now (4, 5) = (height, width)

extents_2 = [
              [9.5, -4.5, 15.5, .5],     # beyond the reference image extent by .5 degrees
              [10.5, -3.5, 14.5, -.5],   # .5 degree within reference image
              [11.5, -2.5, 13.5, -1.5],  # 1.5 degree within reference image
              [10.5, -5, 15, -.5],       # .5 degree on left and top
              [11.5, -5, 15, -1.5],      # 1.5 degree on left and top
             ]

ref_2 = np.zeros((4, 5))
ref_2[1:-1, 1:-1] = 1
arrays_2 = [ref_2,
            ref_2,
            ref_2[1:-1, 1:-1],
            ref_2,
            ref_2[1:, 1:]
            ]

# Using upper left corner (10, 0) because (0, 0) raises warnings being the identify affine transformation
t = Affine(1, 0, 10, 0, -1, 0)
transforms_2 = [t,                           # reference transform
                t,                           # reference transform
                t.translation(1, -1) * t,    # transform with UL corner at (, -1)
                t,                           # reference transform
                t.translation(1, -1) * t]    # trasnform with UL corner at (12, -1)


@pytest.mark.parametrize("extent, array, transform", zip(extents_2, arrays_2, transforms_2))
def test_read_window_4326_unequal_dims(test_data_dir, extent, array, transform):
    raster_path = test_data_dir / 'rio_window' / 'test_window_unequal_dim.tif'

    window_arr, p = read_raster_from_window(raster_path,
                                            extent,
                                            CRS.from_epsg(4326),
                                            res_buffer=0)
    assert_array_equal(array, window_arr)
    assert transform == p['transform']
