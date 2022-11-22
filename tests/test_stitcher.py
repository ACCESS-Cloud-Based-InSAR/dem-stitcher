import numpy as np
import pytest
import rasterio
from affine import Affine
from numpy.testing import assert_array_equal
from rasterio import default_gtiff_profile

from dem_stitcher import stitch_dem
from dem_stitcher.datasets import DATASETS
from dem_stitcher.rio_tools import reproject_arr_to_match_profile
from dem_stitcher.stitcher import (merge_and_transform_dem_tiles, merge_tiles,
                                   shift_profile_for_pixel_loc)

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
           [10, -20, 30, 0],            # Full extents of image
           [10.5, -19.5, 29.5, -.5],    # within .5 degrees of image
           [11.5, -18.5, 28.5, -1.5],   # within 1.5 degrees of image
           [10.5, -9.5, 19.5, -.5],     # within .5 of top left corner (see UL above)
           [10, -10, 30, 0],            # Upper part of image
          ]

ref = np.zeros((20, 20))
ref[1:, 1:] = 1
ref[2:, 2:] = 2
ref[10:, 10:] = np.nan
arrays = [ref,
          ref,
          ref[1:19, 1:19],
          ref[:10, :10],
          ref[:10, :]
          ]

# Using upper left corner (10, 0) because (0, 0) raises warnings about (0, 0)
t = Affine(1, 0, 10, 0, -1, 0)
transforms = [t,                           # reference transform
              t,
              t.translation(1, -1) * t,    # transform with UL corner at (11, -1)
              t,
              t
              ]


@pytest.mark.parametrize("extent, array, transform", zip(extents, arrays, transforms))
def test_merge_tiles(test_data_dir, extent, array, transform):
    merge_dir = test_data_dir / 'stitcher' / 'merge_tiles'
    upper_left = merge_dir / 'ul.tif'
    upper_right = merge_dir / 'ur.tif'
    bottom_left = merge_dir / 'bl.tif'

    tile_datasets = [rasterio.open(path)
                     for path in [upper_left, upper_right, bottom_left]]

    X, p = merge_tiles(tile_datasets, extent)

    list(map(lambda x: x.close, tile_datasets))

    assert_array_equal(X, array)
    assert p['transform'] == transform


"""
See: https://www.usgs.gov/special-topics/significant-topographic-changes-in-the-united-states/science/srtm-ned-vertical?qt-science_center_objects=0#qt-science_center_objects  # noqa: E501

Simple test to check if translation is done correctly

All permutations of Area (or UL corner valued/gdal default) and Point (or pixel-centered, which is what SRTM uses)
"""

src_tags = ['Area',
            'Area',
            'Point',
            'Point'
            ]

dst_tags = ['Area',
            'Point',
            'Point',
            'Area'
            ]

t = Affine(1, 0, 10, 0, -1, 0)
transforms = [
              t,
              Affine(1, 0, 9.5, 0, -1, 0.5),
              t,
              Affine(1, 0, 10.5, 0, -1, -0.5),
              ]


@pytest.mark.parametrize("src_tag, dst_tag, transform_expected", zip(src_tags, dst_tags, transforms))
def test_shift_pixel_loc(src_tag, dst_tag, transform_expected):

    # Create dummy profile with reference transform
    p = default_gtiff_profile.copy()
    t_ref = Affine(1, 0, 10, 0, -1, 0)
    p['transform'] = t_ref

    # Translate if necessary
    p_new = shift_profile_for_pixel_loc(p, src_tag, dst_tag)
    t_new = p_new['transform']

    # Check the transform is what we expect
    assert transform_expected == t_new


@pytest.mark.parametrize("dem_name", ['glo_30', 'nasadem'])
def test_no_change_when_no_transformations_to_tile(get_los_angeles_tile_dataset, dem_name):
    """Opens a single glo tile, selects bounds contained inside of it and then reprojects the obtained tile back into
    the tiles original frame to determine if modifications were made.
    """
    datasets = [get_los_angeles_tile_dataset(dem_name)]
    X_tile = datasets[0].read(1)
    p_tile = datasets[0].profile

    # Within the Los Angeles tile
    bounds = [-118.8, 34.6, -118.5, 34.8]
    X_sub, p_sub = merge_and_transform_dem_tiles(datasets,
                                                 bounds,
                                                 dem_name=dem_name,
                                                 # Do not modify tile
                                                 dst_ellipsoidal_height=False,
                                                 dst_area_or_point='Point')

    datasets[0].close()

    X_sub_r, _ = reproject_arr_to_match_profile(X_sub, p_sub, p_tile,
                                                num_threads=5,
                                                resampling='nearest')
    X_sub_r = X_sub_r[0, ...]

    # The subset will have nan values so only compare areas with nan values
    # when reprojected into the original tile
    mask = np.isnan(X_sub_r)
    subset_data = X_sub_r[~mask]
    tile_data = X_tile[~mask]

    assert_array_equal(subset_data, tile_data)


@pytest.mark.integration
@pytest.mark.parametrize("dem_name", DATASETS)
def test_download_dem(dem_name):
    if dem_name == 'glo_90_missing':
        # Missing area
        bounds = [45.5, 39.5, 46.5, 40.5]
    else:
        # Within the Los Angeles tile
        bounds = [-118.8, 34.6, -118.5, 34.8]

    dem_arr, _ = stitch_dem(bounds,
                            dem_name,
                            n_threads_downloading=5,
                            dst_ellipsoidal_height=True,
                            dst_resolution=0.0002777777777777777775
                            )
    assert len(dem_arr.shape) == 2
