import pytest

from dem_stitcher import stitch_dem
from dem_stitcher.datasets import DATASETS


@pytest.mark.parametrize("dem_name", DATASETS)
def test_download_dem(dem_name):
    # Bay Area
    bounds = [-121.5, 34.95, -120.2, 36.25]
    dem_arr, _ = stitch_dem(bounds,
                            dem_name,
                            max_workers=5,
                            dst_ellipsoidal_height=False
                            )
    assert(len(dem_arr.shape) == 2)
