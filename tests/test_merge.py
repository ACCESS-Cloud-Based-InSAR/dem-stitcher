import numpy as np
import pytest
import rasterio
from affine import Affine
from numpy.testing import assert_array_equal

from dem_stitcher.stitcher import merge_tile_datasets_within_extent

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

    X, p = merge_tile_datasets_within_extent(tile_datasets, extent)

    list(map(lambda x: x.close, tile_datasets))

    array = array[np.newaxis, ...]
    assert_array_equal(X, array)
    assert p['transform'] == transform
