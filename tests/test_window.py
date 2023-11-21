import geopandas as gpd
import numpy as np
import pytest
import rasterio
from affine import Affine
from numpy.testing import assert_array_equal
from rasterio.crs import CRS
from rasterio.windows import bounds as get_window_bounds
from shapely.geometry import box

from dem_stitcher.geoid import read_geoid
from dem_stitcher.rio_window import (get_indices_from_extent,
                                     get_window_from_extent,
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
    array_gdal_format = array[np.newaxis, ...]
    assert_array_equal(array_gdal_format, window_arr)
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
    array_gdal_format = array[np.newaxis, ...]
    assert_array_equal(array_gdal_format, window_arr)
    assert transform == p['transform']


@pytest.mark.parametrize("geojson_index, array, transform", zip([0, 1, 2, 3], arrays, transforms))
def test_get_window_obj_utm(test_data_dir, geojson_index, array, transform):
    """Checks the window's bounds contains the input extent once intersected with the rasters (sometimes the extent
    can go beyond the raster)"""
    raster_path = test_data_dir / 'rio_window' / 'test_window.tif'
    geojson_path = test_data_dir / 'rio_window' / f'window_utm_{geojson_index}.geojson'

    df = gpd.read_file(geojson_path)
    extent = list(df.total_bounds)
    crs = df.crs

    with rasterio.open(raster_path) as ds:
        src_profile = ds.profile

    window = get_window_from_extent(src_profile,
                                    extent,
                                    crs
                                    )
    with rasterio.open(raster_path) as ds:
        window_transform = ds.window_transform(window=window)

    window_bounds = get_window_bounds(window, window_transform)
    window_geo = box(*window_bounds)
    extent_raster_crs = df.to_crs(src_profile['crs']).total_bounds
    extent_geo = box(*extent_raster_crs)
    # The extent geometry goes beyond the actual image in the last case.
    extent_geo = extent_geo.intersection(window_geo)

    assert window_geo.contains(extent_geo)


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
    array = array[np.newaxis, ...]
    assert_array_equal(array, window_arr)
    assert transform == p['transform']


# The dummy data is a 100 x 200 (.25 deg resolution) raster with origin at
# (0, 0). So it's bounds are [0, -25, 50, 0] (xmin, ymin, xmax, ymax)
bad_extents = [
                # intersection along left of
                # box i.e. line from (0, 0) to (0, -25)
                [-10, -25, 0, 0],
                # intersection along top of box i.e. from (0, 0) to
                # (50, 0)
                [0, 0, 50, 10]
              ]


@pytest.mark.parametrize("bad_extent", bad_extents)
def test_rio_window_exception(test_data_dir, bad_extent):
    raster_path = test_data_dir / 'rio_window' / 'warning_exception_data.tif'
    with pytest.raises(RuntimeError):
        X, p = read_raster_from_window(raster_path,
                                       bad_extent,
                                       CRS.from_epsg(4326),
                                       res_buffer=0)


# The dummy data is a 100 x 200 (.25 deg resolution) raster with origin at
# (0, 0). So it's bounds are [0, -25, 50, 0] (xmin, ymin, xmax, ymax)
warn_extents = [
                [-1, -27, 1, -23],
                [49, -1, 51, 1]
                ]


@pytest.mark.parametrize("warn_extent", warn_extents)
def test_rio_window_warning(test_data_dir, warn_extent):
    raster_path = test_data_dir / 'rio_window' / 'warning_exception_data.tif'
    with pytest.warns(RuntimeWarning):
        X, p = read_raster_from_window(raster_path,
                                       warn_extent,
                                       CRS.from_epsg(4326),
                                       res_buffer=0)


def test_riow_window_get_one_pixel(test_data_dir):
    raster_path = test_data_dir / 'rio_window' / 'warning_exception_data.tif'
    X, p = read_raster_from_window(raster_path,
                                   [0, -25, 0.01, -24.999],
                                   CRS.from_epsg(4326),
                                   res_buffer=0)
    assert X.shape == (1, 1, 1)
    assert p['width'] == p['height']
    assert p['width'] == 1


def test_bad_extents_for_window():
    with pytest.raises(RuntimeError):
        '''Outside of Geoid Bounds'''
        bounds = [-180, 34, -179, 35]

        X, p = read_geoid('geoid_18',
                          bounds)
